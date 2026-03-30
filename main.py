# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
Ponto de entrada da aplicação. Orquestra todo o fluxo de subida,
limpeza e deploy distribuído da rede Hyperledger Fabric.

Comandos disponíveis:

  --up
      Sobe a rede completa localmente (modo de desenvolvimento).
      Todos os containers rodam na mesma máquina.

  --up --machine <nome>
      Sobe apenas os containers atribuídos a esta máquina.
      Assume que o setup (crypto, canais, chaincode) já foi feito.
      Usado para retomar containers individuais sem refazer o deploy.

  --start --machine <nome> --phase <fase>
      Inicia uma fase específica de containers nesta máquina.
      Fases: cas | nodes | ccaas
      Usado internamente pelos jobs SLURM do --slurm-deploy.

  --setup --phase <fase>
      Executa uma fase de setup no nó coordenador com IPs reais (distributed=True).
      Fases: enroll | artifacts | channels | chaincode
      Usado internamente pelos jobs SLURM do --slurm-deploy.

  --slurm-deploy
      Submete todos os jobs SLURM necessários para o deploy distribuído
      completo. Executa apenas da máquina de gerenciamento e retorna
      imediatamente após a submissão. Requer 'slurm_node' e 'coordinator'
      definidos em network.yaml > machines.

  --clean [all|net]
      Limpa a infraestrutura. 'all' remove tudo incluindo binários,
      'net' derruba apenas os containers e artefatos gerados.
"""
import argparse
import json
import sys
import time
import socket

from src.path_manager import PathManager
from src.config_loader import ConfigLoader
from src.network_controller import NetworkController
from src.parser import ConfigParser
from src.utils import Colors as co

from src.generator.compose import ComposeGenerator
from src.generator.crypto import CryptoGenerator
from src.generator.configtx import ConfigTxGenerator
from src.generator.channel import ChannelScriptGenerator
from src.generator.deploy import ChaincodeDeployGenerator
from src.generator.deploy import assign_ops_ports
from src.generator.slurm import SlurmDeployGenerator


# ──────────────────────────────────────────────────────────────────────────────
# Utilitários
# ──────────────────────────────────────────────────────────────────────────────

def _wait_for_port(host, port, timeout=60):
    """Aguarda até que uma porta específica esteja aberta."""
    start_time = time.time()
    while True:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (ConnectionRefusedError, socket.timeout):
            if time.time() - start_time > timeout:
                return False
            time.sleep(2)


# ──────────────────────────────────────────────────────────────────────────────
# Etapas do fluxo local (--up)
# ──────────────────────────────────────────────────────────────────────────────

def _verifica_prerequisitos(controller):
    co.infoln("Verificando pré-requisitos do sistema")
    try:
        controller.run_script("check_reqs.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'check_reqs.sh': {e}")
        return

def _valida_configuracoes(config):
    co.infoln("Validando configurações do arquivo de definição da rede")
    parser = ConfigParser(config)
    parser.valida()
    if parser.erros:
        raise RuntimeError("Erros de validação encontrados.")

def _exporta_network_contexto(config, paths):
    co.infoln("Exportando contexto ativo da rede")
    context = {
        "domain": config['network_topology']['network']['domain'],
        "orderers": [
            {"name": node['name'], "port": node['port']}
            for node in config['network_topology']['orderer']['nodes']
        ],
        "orgs": {}
    }
    for org in config['network_topology']['organizations']:
        context["orgs"][org['name']] = {
            "msp_id": org['msp_id'],
            "peers": {
                p['name']: {"port": p['port'], "tls_port": p.get('chaincode_port')}
                for p in org['peers']
            }
        }
    with open(paths.network_dir / "contexto_ativo.json", "w") as f:
        json.dump(context, f, indent=2)

def _cria_compose_ca(config, paths, machine=None):
    co.infoln("Gerando arquivos docker-compose para ca")
    ComposeGenerator(config, paths, machine=machine).generate_ca_compose()

def _start_CA(controller):
    co.infoln("Iniciando os servidores CA")
    try:
        controller.run_script("start_cas.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao iniciar servidores CA: {e}")
        return

def _register_enroll(controller, config, paths, distributed=False):
    """
    Gera e executa register_enroll.sh.
    distributed=True: usa IPs reais das CAs (modo SLURM/coordenador).
    distributed=False: usa localhost (modo local --up).
    """
    co.infoln("Registrando e matriculando identidades")
    crypto = CryptoGenerator(config, paths, distributed=distributed)
    co.actionln("Gerando script de identidades (register_enroll.sh)...")
    crypto.generate()
    try:
        time.sleep(2)
        controller.run_script("register_enroll.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'register_enroll.sh': {e}")
        return

def _cria_artefatos(controller, config, paths):
    co.infoln("Gerando artefatos da rede (configtx.yaml, blocos, canais, etc)")
    ConfigTxGenerator(config, paths).generate()
    try:
        controller.run_script("create_artifacts.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'create_artifacts.sh': {e}")
        return

def _inicializa_nos(controller, config, paths, machine=None):
    co.infoln("Gerando arquivos docker-compose para peers e orderers")
    ComposeGenerator(config, paths, machine=machine).generate_nodes_compose()
    try:
        controller.run_script("start_nodes.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'start_nodes.sh': {e}")
        return

def _configura_canais(controller, config, paths, distributed=False):
    """
    Gera e executa create_channel.sh.
    distributed=True: usa IPs reais de peers e orderers (modo SLURM/coordenador).
    distributed=False: usa localhost (modo local --up).
    """
    co.infoln("Configurando canais e fazendo peers entrarem neles")
    ChannelScriptGenerator(config, paths, distributed=distributed).generate_channel_script()
    try:
        controller.run_script("create_channel.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'create_channel.sh': {e}")
        return

def _deploy_chaincode(controller, config, paths, distributed=False):
    """
    Gera e executa deploy_chaincode.sh.
    distributed=True: usa IPs reais de peers e orderers (modo SLURM/coordenador).
    distributed=False: usa localhost (modo local --up).
    """
    co.infoln("Fazendo deploy de chaincodes")
    ChaincodeDeployGenerator(config, paths, distributed=distributed).generate()
    try:
        controller.run_script("deploy_chaincode.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'deploy_chaincode.sh': {e}")
        return

def _start_chaincodes(controller, config, paths, machine):
    co.infoln(f"Iniciando containers CCAAS de '{machine}'")
    ChaincodeDeployGenerator(config, paths).generate_ccaas_start_script(machine)
    try:
        controller.run_script("start_chaincodes.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'start_chaincodes.sh': {e}")
        return


# ──────────────────────────────────────────────────────────────────────────────
# Fluxos principais
# ──────────────────────────────────────────────────────────────────────────────

def _network_up(controller, config, paths, machine=None):
    """
    Sobe a rede completa.
    Sem machine: fluxo local completo (desenvolvimento).
    Com machine: sobe apenas os containers locais desta máquina
                 (assume setup já executado).
    """
    co.headerln("Iniciando a rede")
    paths.ensure_network_dirs()

    if machine:
        machines_cfg = config['network_topology'].get('machines', {})
        if machine not in machines_cfg:
            raise RuntimeError(
                f"Máquina '{machine}' não encontrada em 'machines' no network.yaml. "
                f"Disponíveis: {list(machines_cfg.keys())}"
            )
        co.infoln(f"Modo distribuído: iniciando componentes de '{machine}' "
                  f"(IP: {machines_cfg[machine]['ip']})")
        _cria_compose_ca(config, paths, machine=machine)
        _start_CA(controller)
        _inicializa_nos(controller, config, paths, machine=machine)
        _start_chaincodes(controller, config, paths, machine)
        return

    # Fluxo local completo
    _verifica_prerequisitos(controller)
    _valida_configuracoes(config)
    _exporta_network_contexto(config, paths)

    pkg_id_file = paths.network_dir / "CC_PACKAGE_ID"
    if not pkg_id_file.exists():
        pkg_id_file.touch()

    _cria_compose_ca(config, paths)
    _start_CA(controller)
    _register_enroll(controller, config, paths)
    _cria_artefatos(controller, config, paths)
    _inicializa_nos(controller, config, paths)
    _configura_canais(controller, config, paths)
    _deploy_chaincode(controller, config, paths)

    chaincodes = config['network_topology'].get('chaincodes', [])
    for cc in chaincodes:
        cc_port = cc.get('port')
        cc_name = cc.get('name', 'chaincode')
        if not cc_port:
            continue
        co.infoln(f"Aguardando estabilização do chaincode '{cc_name}' (porta {cc_port})...")
        if _wait_for_port("localhost", cc_port, timeout=120):
            co.successln(f"Chaincode '{cc_name}' está escutando na porta {cc_port}!")
        else:
            co.warnln(f"Timeout: O chaincode '{cc_name}' não respondeu na porta {cc_port} a tempo.")


def _start_phase(controller, config, paths, machine, phase):
    """
    Inicia uma fase específica de containers na máquina local.
    Chamado pelos jobs SLURM submetidos pelo --slurm-deploy.

      cas   — gera compose-ca.yaml filtrado e sobe as CAs locais
      nodes — gera compose-nodes.yaml filtrado e sobe peers/orderers locais
      ccaas — gera start_chaincodes.sh e inicia os containers CCAAS locais
    """
    machines_cfg = config['network_topology'].get('machines', {})
    if machine not in machines_cfg:
        raise RuntimeError(
            f"Máquina '{machine}' não encontrada em 'machines' no network.yaml."
        )

    paths.ensure_network_dirs()
    co.headerln(f"[SLURM] --start --machine {machine} --phase {phase}")

    if phase == 'cas':
        _cria_compose_ca(config, paths, machine=machine)
        _start_CA(controller)
    elif phase == 'nodes':
        _inicializa_nos(controller, config, paths, machine=machine)
    elif phase == 'ccaas':
        _start_chaincodes(controller, config, paths, machine)
    else:
        raise RuntimeError(
            f"Fase desconhecida para --start: '{phase}'. "
            f"Valores válidos: cas, nodes, ccaas"
        )


def _setup_phase(controller, config, paths, phase):
    """
    Executa uma fase de setup no nó coordenador com distributed=True,
    conectando aos componentes pelos IPs reais da LAN.
    Chamado pelos jobs SLURM submetidos pelo --slurm-deploy.

      enroll    — registra e matricula todas as identidades (fabric-ca-client)
      artifacts — gera configtx.yaml, genesis block e canal artifacts (local)
      channels  — faz peers e orderers entrarem nos canais
      chaincode — instala, aprova e commita o chaincode (lifecycle completo)
    """
    paths.ensure_network_dirs()
    co.headerln(f"[SLURM] --setup --phase {phase}")

    if phase == 'enroll':
        _register_enroll(controller, config, paths, distributed=True)
    elif phase == 'artifacts':
        _cria_artefatos(controller, config, paths)
    elif phase == 'channels':
        _configura_canais(controller, config, paths, distributed=True)
    elif phase == 'chaincode':
        _deploy_chaincode(controller, config, paths, distributed=True)
    else:
        raise RuntimeError(
            f"Fase desconhecida para --setup: '{phase}'. "
            f"Valores válidos: enroll, artifacts, channels, chaincode"
        )


def _slurm_deploy(config, paths, time):
    """
    Gera um único script bash com todas as fases do deploy e o submete como
    um único job SLURM. Deve ser executado do nó de login (externo aos nós
    de compute). Retorna logo após a submissão.
    """
    SlurmDeployGenerator(config, paths).deploy(time=time)


def _clean_files(controller, op=1):
    try:
        if op == 1:
            controller.run_script("clean_all.sh")
        else:
            controller.run_script("clean_network.sh")
    except Exception as e:
        co.errorln(f"\n Erro nos pré-requisitos: {e}")
        return


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Hyperledger Fabric Network Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--log",
        action="store_true",
        help="Salva a saída dos scripts em arquivos de log em network/logs/."
    )
    parser.add_argument(
        "--clean",
        choices=["all", "net"],
        help="'all' remove tudo (incluindo binários). 'net' derruba apenas a rede atual."
    )
    parser.add_argument(
        '-n', '--network',
        type=str,
        required=False,
        help="Caminho alternativo para o network.yaml."
    )

    # ── Comandos principais (mutuamente exclusivos) ───────────────────────────
    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "--up",
        action="store_true",
        help="Sobe a rede completa localmente, ou apenas os containers de --machine."
    )
    group.add_argument(
        "--start",
        action="store_true",
        help=(
            "Inicia uma fase de containers na máquina local. "
            "Requer --machine e --phase [cas|nodes|ccaas]. "
            "Usado pelos jobs SLURM do --slurm-deploy."
        )
    )
    group.add_argument(
        "--setup",
        action="store_true",
        help=(
            "Executa uma fase de setup distribuída no nó coordenador. "
            "Requer --phase [enroll|artifacts|channels|chaincode]. "
            "Usado pelos jobs SLURM do --slurm-deploy."
        )
    )
    group.add_argument(
        "--slurm-deploy",
        action="store_true",
        dest="slurm_deploy",
        help=(
            "Gera um script bash com todas as fases do deploy e o submete como "
            "um único job SLURM a partir do nó de login. Requer --time. "
            "Requer 'slurm_node' e 'coordinator' em network.yaml > machines."
        )
    )

    # ── Argumentos auxiliares ─────────────────────────────────────────────────
    parser.add_argument(
        '--machine',
        type=str,
        required=False,
        metavar='NOME',
        help="Nome da máquina definida em network.yaml > machines."
    )
    parser.add_argument(
        '--phase',
        type=str,
        required=False,
        metavar='FASE',
        help=(
            "Fase a executar. "
            "Para --start: cas | nodes | ccaas. "
            "Para --setup: enroll | artifacts | channels | chaincode."
        )
    )
    parser.add_argument(
        '--time',
        type=str,
        required=False,
        metavar='HH:MM:SS',
        help="Duração máxima do job SLURM (ex: 03:00:00). Obrigatório com --slurm-deploy."
    )

    args = parser.parse_args()

    try:
        paths = PathManager(custom_network_yaml=args.network)
        co.infoln(f"Alvo: {paths.network_yaml.name}")

        loader = ConfigLoader(paths.network_yaml, paths.versions_yaml)
        config = loader.load()
        config = assign_ops_ports(config)

        controller = NetworkController(config, paths, log_to_file=args.log)
        paths.ensure_network_dirs()

        if args.clean:
            op_code = 1 if args.clean == "all" else 0
            _clean_files(controller, op=op_code)

        elif args.up:
            _network_up(controller, config, paths, machine=args.machine)

        elif args.start:
            if not args.machine:
                parser.error("--start requer --machine <nome>")
            if not args.phase:
                parser.error("--start requer --phase [cas|nodes|ccaas]")
            _start_phase(controller, config, paths, args.machine, args.phase)

        elif args.setup:
            if not args.phase:
                parser.error("--setup requer --phase [enroll|artifacts|channels|chaincode]")
            _setup_phase(controller, config, paths, args.phase)

        elif args.slurm_deploy:
            if not args.time:
                parser.error("--slurm-deploy requer --time HH:MM:SS")
            _slurm_deploy(config, paths, args.time)

        else:
            parser.print_help()

    except Exception as e:
        co.errorln(f"Falha Crítica: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
