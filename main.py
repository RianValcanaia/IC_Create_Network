# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
O ponto de entrada da aplicação que orquestra todo o fluxo de
subida ou limpeza da rede. Ele processa os argumentos de linha
de comando e chama sequencialmente os validadores e geradores de scripts.

Comandos disponíveis:

  --up
      Sobe a rede completa localmente (modo de desenvolvimento).
      Todos os containers rodam na mesma máquina.

  --up --machine <nome>
      Sobe apenas os containers atribuídos a esta máquina.
      Assume que o setup (crypto, canais, chaincode) já foi feito.

  --start --machine <nome> --phase <fase>
      Inicia uma fase específica de containers nesta máquina.
      Fases: clean | cas | nodes | ccaas
      Usado internamente pelos jobs SLURM do --slurm-deploy.

  --setup --phase <fase>
      Executa uma fase de setup no nó coordenador com IPs reais (distributed=True).
      Fases: clean | prereqs | enroll | artifacts | channels | chaincode
      Usado internamente pelos jobs SLURM do --slurm-deploy.

  --slurm-deploy --time HH:MM:SS
      Gera e submete o deploy distribuído completo via SLURM. Requer
      'machines' (com 'slurm_node'/'ip'/'coordinator') e 'slurm.cluster_project_dir'
      definidos em network.yaml.

  --clean [all|net]
      Limpa a infraestrutura. 'all' remove tudo incluindo binários,
      'net' derruba apenas os containers e artefatos gerados.

  --redeploy-cc {code|ledger} [--cc-name <nome>]
      Atualiza chaincode(s) de uma rede já ativa, sem derrubá-la.
      'code' recompila e reinicia apenas o container CCAAS.
      'ledger' também reinstala e roda approveformyorg/commit (requer
      bump manual de 'version'/'sequence' no network.yaml antes de rodar).
      --cc-name filtra um chaincode específico; sem ele, atualiza todos.

  --register-user <username> --org <Org> --secret <senha>
      Registra (fabric-ca-client register) e matricula (enroll) um novo
      cliente na CA de uma organização de uma rede já ativa. Usa o mesmo
      domínio do admin da organização (network.yaml) e o mesmo padrão de
      pasta (<username>@<org>.<domain>). Gera os certificados em
      organizations/peerOrganizations/<org>.<domain>/users/
      <username>@<org>.<domain>/msp. Requer que a CA da organização já
      tenha sido inicializada por --up (admin da CA matriculado em
      register_enroll.sh).
"""
import argparse
import json
import os
import subprocess
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
from src.generator.slurm import SlurmDeployGenerator
from src.generator.addressing import StaticIPAllocator

def _wait_for_port(host, port, timeout=60):
    """Aguarda até que uma porta específica esteja aberta"""
    start_time = time.time()
    while True:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (ConnectionRefusedError, socket.timeout):
            if time.time() - start_time > timeout:
                return False
            time.sleep(2)

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

def _cria_compose_ca(config, paths, machine=None):
    co.infoln("Gerando arquivos docker-compose para ca")

    compose_generator = ComposeGenerator(config, paths, machine=machine)
    return compose_generator.generate_ca_compose()

def _start_CA(controller, compose_path=None):
    co.infoln("Iniciando os servidores CA")

    extra = {"COMPOSE_FILE": str(compose_path)} if compose_path else {}
    try:
        controller.run_script("start_cas.sh", extra_env=extra)
    except Exception as e:
        co.errorln(f"\n Erro ao iniciar servidores CA: {e}")
        return

def _register_enroll(controller, config, paths, distributed=False, macvlan=False):
    """
    Gera e executa register_enroll.sh.
    distributed=True: usa IPs reais das CAs (modo SLURM/coordenador).
    macvlan=True: usa o IP estático real de cada CA na subnet macvlan (modo local --up).
    Nenhum dos dois: usa localhost (modo local --up padrão).
    """
    co.infoln("Registrando e matriculando identidades")

    crypto = CryptoGenerator(config, paths, distributed=distributed, macvlan=macvlan)

    co.actionln("Gerando script de identidades (register_enroll.sh)...")
    crypto.generate()

    try:
        import time
        time.sleep(2)
        controller.run_script("register_enroll.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'register_enroll.sh': {e}")
        return

def _cria_artefatos(controller, config, paths):
    co.infoln("Gerando artefatos da rede (configtx.yaml, blocos, canais, etc)")

    configtx_gen = ConfigTxGenerator(config, paths)
    configtx_gen.generate()

    try:
        controller.run_script("create_artifacts.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'create_artifacts.sh': {e}")
        return

def _inicializa_nos(controller, config, paths, machine=None):
    co.infoln("Gerando arquivos docker-compose para peers e orderers")

    compose_generator = ComposeGenerator(config, paths, machine=machine)
    compose_path = compose_generator.generate_nodes_compose()

    extra = {"COMPOSE_FILE": str(compose_path)} if machine else {}
    try:
        controller.run_script("start_nodes.sh", extra_env=extra)
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'start_nodes.sh': {e}")
        return

def _configura_canais(controller, config, paths, distributed=False, macvlan=False):
    """
    Gera e executa create_channel.sh.
    distributed=True: usa IPs reais de peers e orderers (modo SLURM/coordenador).
    macvlan=True: usa o IP estático real de cada peer/orderer na subnet macvlan.
    Nenhum dos dois: usa localhost (modo local --up padrão).
    """
    co.infoln("Configurando canais e fazendo peers entrarem neles")

    channel_gen = ChannelScriptGenerator(config, paths, distributed=distributed, macvlan=macvlan)
    channel_gen.generate_channel_script()

    try:
        controller.run_script("create_channel.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'create_channel.sh': {e}")
        return

def _deploy_chaincode(controller, config, paths, distributed=False, macvlan=False):
    """
    Gera e executa deploy_chaincode.sh.
    distributed=True: usa IPs reais de peers e orderers (modo SLURM/coordenador);
    o container CCAAS não é iniciado aqui (ver _start_chaincodes).
    macvlan=True: usa o IP estático real de cada peer/orderer/chaincode na subnet
    macvlan e não publica porta do container CCAAS (modo local --up).
    Nenhum dos dois: usa localhost e já inicia o container CCAAS (modo local --up padrão).
    """
    co.infoln("Fazendo deploy de chaincodes")

    deploy_gen = ChaincodeDeployGenerator(config, paths, distributed=distributed, macvlan=macvlan)
    deploy_gen.generate()

    try:
        controller.run_script("deploy_chaincode.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'deploy_chaincode.sh': {e}")
        return

def _start_chaincodes(controller, config, paths, machine):
    co.infoln(f"Iniciando containers CCAAS de '{machine}'")

    deploy_gen = ChaincodeDeployGenerator(config, paths)
    deploy_gen.generate_ccaas_start_script(machine)

    try:
        controller.run_script("start_chaincodes.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'start_chaincodes.sh': {e}")
        return

def _exporta_network_contexto(config, paths):
    co.infoln("Exportando contexto ativo da rede")
    macvlan_enabled = bool(config['network_topology']['network'].get('macvlan'))
    allocator = StaticIPAllocator(config) if macvlan_enabled else None

    context = {
        "network": config['network_topology']['network']['name'],
        "domain": config['network_topology']['network']['domain'],
        "orderers": [
            {
                "name": node['name'],
                "port": node['port'],
                **({"ip": allocator.orderer_ip(node['name'])} if allocator else {})
            }
            for node in config['network_topology']['orderer']['nodes']
        ],
        "orgs": {}
    }

    for org in config['network_topology']['organizations']:
        org_data = {
            "msp_id": org['msp_id'],
            "peers": {
                p['name']: {
                    "port": p['port'],
                    "tls_port": p.get('chaincode_port'),
                    **({"ip": allocator.peer_ip(org['name'], p['name'])} if allocator else {})
                }
                for p in org['peers']
            }
        }
        context["orgs"][org['name']] = org_data

    with open(paths.network_dir / "contexto_ativo.json", "w") as f:
        json.dump(context, f, indent=2)

def _network_up(controller, config, paths, machine=None):
    """
    Sobe a rede completa.
    Sem machine: fluxo local completo (desenvolvimento).
    Com machine: sobe apenas os containers locais desta máquina
                 (assume que o setup já foi executado a partir do coordenador).
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
        compose_ca = _cria_compose_ca(config, paths, machine=machine)
        _start_CA(controller, compose_path=compose_ca)
        _inicializa_nos(controller, config, paths, machine=machine)
        _start_chaincodes(controller, config, paths, machine)
        return

    # --- Validações iniciais ---
    _verifica_prerequisitos(controller)
    _valida_configuracoes(config)
    _exporta_network_contexto(config, paths)

    macvlan_enabled = bool(config['network_topology']['network'].get('macvlan'))

    pkg_id_file = paths.network_dir / "CC_PACKAGE_ID"
    if not pkg_id_file.exists():
        pkg_id_file.touch()

    _cria_compose_ca(config, paths)

   # --- Inicialização da rede ---
    _start_CA(controller)
    _register_enroll(controller, config, paths, macvlan=macvlan_enabled)
    _cria_artefatos(controller, config, paths)
    _inicializa_nos(controller, config, paths)
    _configura_canais(controller, config, paths, macvlan=macvlan_enabled)
    _deploy_chaincode(controller, config, paths, macvlan=macvlan_enabled)

    chaincodes = config['network_topology'].get('chaincodes', [])
    cc_allocator = StaticIPAllocator(config) if macvlan_enabled else None
    for cc_idx, cc in enumerate(chaincodes):
        cc_port = cc.get('port')
        cc_name = cc.get('name', 'chaincode')
        if not cc_port:
            continue
        cc_host = cc_allocator.chaincode_ip(cc_idx) if cc_allocator else "localhost"
        co.infoln(f"Aguardando estabilização do chaincode '{cc_name}' ({cc_host}:{cc_port})...")
        if _wait_for_port(cc_host, cc_port, timeout=120):
            co.successln(f"Chaincode '{cc_name}' está escutando na porta {cc_port}!")
        else:
            co.warnln(f"Timeout: O chaincode '{cc_name}' não respondeu na porta {cc_port} a tempo.")

def _start_phase(controller, config, paths, machine, phase):
    """
    Inicia uma fase específica de containers na máquina local.
    Chamado pelos jobs SLURM submetidos pelo --slurm-deploy.

      clean — derruba containers/rede/volumes desta máquina
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

    if phase == 'clean':
        compose_dir = paths.network_dir / "compose"
        extra = {
            "COMPOSE_FILE_CA": str(compose_dir / f"compose-ca-{machine}.yaml"),
            "COMPOSE_FILE_NODES": str(compose_dir / f"compose-nodes-{machine}.yaml"),
        }
        controller.run_script("clean_node.sh", extra_env=extra)
    elif phase == 'cas':
        compose_ca = _cria_compose_ca(config, paths, machine=machine)
        _start_CA(controller, compose_path=compose_ca)
    elif phase == 'nodes':
        _inicializa_nos(controller, config, paths, machine=machine)
    elif phase == 'ccaas':
        _start_chaincodes(controller, config, paths, machine)
    else:
        raise RuntimeError(
            f"Fase desconhecida para --start: '{phase}'. "
            f"Valores válidos: clean, cas, nodes, ccaas"
        )

def _setup_phase(controller, config, paths, phase):
    """
    Executa uma fase de setup no nó coordenador com distributed=True,
    conectando aos componentes pelos IPs reais da LAN.
    Chamado pelos jobs SLURM submetidos pelo --slurm-deploy.

      clean     — limpa artefatos gerados no NFS compartilhado (preserva bin/builders)
      prereqs   — verifica/baixa binários do Fabric
      enroll    — registra e matricula todas as identidades (fabric-ca-client)
      artifacts — gera configtx.yaml, genesis block e canal artifacts (local)
      channels  — faz peers e orderers entrarem nos canais
      chaincode — instala, aprova e commita o chaincode (lifecycle completo)
    """
    paths.ensure_network_dirs()
    co.headerln(f"[SLURM] --setup --phase {phase}")

    if phase == 'clean':
        controller.run_script("clean_network.sh")
    elif phase == 'prereqs':
        _verifica_prerequisitos(controller)
    elif phase == 'enroll':
        _register_enroll(controller, config, paths, distributed=True)
    elif phase == 'artifacts':
        _exporta_network_contexto(config, paths)
        _cria_artefatos(controller, config, paths)
    elif phase == 'channels':
        _configura_canais(controller, config, paths, distributed=True)
    elif phase == 'chaincode':
        _deploy_chaincode(controller, config, paths, distributed=True)
    else:
        raise RuntimeError(
            f"Fase desconhecida para --setup: '{phase}'. "
            f"Valores válidos: clean, prereqs, enroll, artifacts, channels, chaincode"
        )

def _redeploy_chaincode(controller, config, paths, mode, cc_name=None):
    """
    Atualiza chaincode(s) de uma rede já ativa, sem derrubar os demais
    componentes.
      mode='code'   — recompila e reinicia apenas o container CCAAS.
      mode='ledger' — além do container, reinstala o pacote em todos os peers
                      e roda approveformyorg/commit com a nova 'version'/
                      'sequence' (devem ter sido incrementadas no network.yaml
                      antes de rodar).
    cc_name filtra o chaincode alvo pelo nome; None/vazio atualiza todos.
    """
    alvo = f" (alvo: {cc_name})" if cc_name else " (todos os chaincodes)"
    co.headerln(f"Atualizando chaincode — modo '{mode}'{alvo}")

    macvlan_enabled = bool(config['network_topology']['network'].get('macvlan'))
    deploy_gen = ChaincodeDeployGenerator(config, paths, macvlan=macvlan_enabled)
    deploy_gen.generate_redeploy()

    env_vars = {
        "CC_REDEPLOY_MODE": mode,
        "TARGET_CC": cc_name if cc_name else ""
    }
    try:
        controller.run_script("redeploy_chaincode.sh", extra_env=env_vars)
    except Exception as e:
        co.errorln(f"\n Erro ao atualizar chaincode: {e}")
        return

def _write_node_ous_config(msp_dir):
    """
    Replica createNodeOUsConfig() de src/generator/crypto.py (usado por
    register_enroll.sh) para identidades registradas fora do fluxo de --up.
    Sem esse config.yaml referenciando o certificado da CA, a MSP do Fabric
    não reconhece a Organizational Unit (client, no caso desta flag) da
    identidade, já que NodeOUs está habilitado em todas as MSPs desta rede.
    """
    cacerts_dir = msp_dir / "cacerts"
    ca_files = list(cacerts_dir.glob("*"))
    if not ca_files:
        raise RuntimeError(f"Certificado da CA não encontrado em {cacerts_dir}")
    ca_filename = ca_files[0].name

    config_yaml = f"""NodeOUs:
  Enable: true
  ClientOUIdentifier:
    Certificate: cacerts/{ca_filename}
    OrganizationalUnitIdentifier: client
  PeerOUIdentifier:
    Certificate: cacerts/{ca_filename}
    OrganizationalUnitIdentifier: peer
  AdminOUIdentifier:
    Certificate: cacerts/{ca_filename}
    OrganizationalUnitIdentifier: admin
  OrdererOUIdentifier:
    Certificate: cacerts/{ca_filename}
    OrganizationalUnitIdentifier: orderer
"""
    (msp_dir / "config.yaml").write_text(config_yaml)

def _register_user(config, paths, org_name, username, secret):
    """
    Registra e matricula (register + enroll) um novo cliente na CA de uma
    organização de uma rede já ativa, via fabric-ca-client. Identidade
    sempre registrada com --id.type client (esta flag só cadastra clientes,
    não admins/peers/orderers — esses têm seus próprios fluxos dedicados em
    register_enroll.sh, com enroll de TLS incluso).

    Usa sempre o domínio de network.yaml (network_topology.network.domain) —
    o mesmo domínio já usado por Admin@<org>.<domain> — e nomeia a pasta da
    identidade seguindo o mesmo padrão (<username>@<org>.<domain>, com a org
    no nome, não só o domínio).

    Requer que o admin da CA já esteja matriculado (feito por
    register_enroll.sh durante o --up) em
    network/<folder>/organizations/fabric-ca/<org>/client — reaproveitado
    aqui como --home do 'register' para autenticar o pedido. O 'enroll' gera
    os certificados do novo usuário em
    network/<folder>/organizations/peerOrganizations/<org>.<domain>/users/<username>@<org>.<domain>/msp.
    """
    domain = config['network_topology']['network']['domain']
    orgs = config['network_topology']['organizations']
    org = next((o for o in orgs if o['name'] == org_name), None)
    if not org:
        raise RuntimeError(
            f"Organização '{org_name}' não encontrada em network.yaml. "
            f"Disponíveis: {[o['name'] for o in orgs]}"
        )

    ca_name = org['ca']['name']
    ca_port = org['ca']['port']
    machines = config['network_topology'].get('machines', {})
    ca_machine = org['ca'].get('machine')
    macvlan_enabled = bool(config['network_topology']['network'].get('macvlan'))
    if ca_machine and ca_machine in machines:
        ca_host = machines[ca_machine]['ip']
    elif macvlan_enabled:
        ca_host = StaticIPAllocator(config).ca_ip(org_name) or "localhost"
    else:
        ca_host = "localhost"
    ca_url = f"http://{ca_host}:{ca_port}"

    ca_client_home = paths.network_dir / "organizations" / "fabric-ca" / org_name / "client"
    if not (ca_client_home / "msp").exists():
        raise RuntimeError(
            f"Admin da CA de '{org_name}' não encontrado em {ca_client_home}. "
            f"A rede foi trazida ao ar (--up) com esta mesma pasta de rede?"
        )

    user_target_folder = (
        paths.network_dir / "organizations" / "peerOrganizations"
        / f"{org_name}.{domain}" / "users" / f"{username}@{org_name}.{domain}"
    )
    if (user_target_folder / "msp").exists():
        raise RuntimeError(
            f"Já existe uma identidade matriculada em {user_target_folder}. "
            f"Escolha outro --register-user ou remova a pasta manualmente."
        )

    co.headerln(f"Cadastrando cliente '{username}' em {org_name} ({ca_url})")

    env = os.environ.copy()
    env["PATH"] = f"{paths.base_dir}/bin:{env.get('PATH', '')}"

    co.infoln(f"Registrando '{username}' na CA de {org_name}...")
    subprocess.run(
        [
            "fabric-ca-client", "register",
            "--caname", ca_name,
            "--id.name", username,
            "--id.secret", secret,
            "--id.type", "client",
            "--home", str(ca_client_home),
            "-u", ca_url,
        ],
        check=True, env=env
    )

    co.infoln(f"Matriculando '{username}' (gerando certificados)...")
    subprocess.run(
        [
            "fabric-ca-client", "enroll",
            "-u", f"http://{username}:{secret}@{ca_host}:{ca_port}",
            "--caname", ca_name,
            "--home", str(user_target_folder),
        ],
        check=True, env=env
    )

    _write_node_ous_config(user_target_folder / "msp")

    co.successln(
        f"Usuário '{username}' cadastrado com sucesso em {org_name}. "
        f"Certificados em: {user_target_folder}/msp"
    )

def _slurm_deploy(config, paths, deploy_time):
    """
    Gera um script bash com todas as fases do deploy distribuído e imprime as
    instruções para copiar e submeter manualmente no cluster SLURM.
    """
    SlurmDeployGenerator(config, paths).deploy(time=deploy_time)

def _clean_files(controller, op = 1):
    try:
        if op == 1:
            controller.run_script("clean_all.sh")
        else:
            controller.run_script("clean_network.sh")
    except Exception as e:
        co.errorln(f"\n Erro nos pré-requisitos: {e}")
        return

def main():
    parser = argparse.ArgumentParser(description="Hyperledger Fabric Network Generator")
    parser.add_argument(
        "--log",
        action="store_true",
        help="Salva a saída dos scripts em arquivos de log em network/logs/ em vez de mostrar no terminal."
    )

    parser.add_argument(
        "--clean",
        choices=["all", "net"],
        help="Executa a limpeza da rede. 'all' remove tudo (incluindo binários), 'net' limpa apenas a infraestrutura atual."
    )

    # ── Comandos principais (mutuamente exclusivos) ───────────────────────────
    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "--up",
        action="store_true",
        help="Inicia o processo completo de subida da rede localmente, ou apenas os containers de --machine."
    )
    group.add_argument(
        "--start",
        action="store_true",
        help=(
            "Inicia uma fase de containers na máquina local. "
            "Requer --machine e --phase [clean|cas|nodes|ccaas]. "
            "Usado pelos jobs SLURM do --slurm-deploy."
        )
    )
    group.add_argument(
        "--setup",
        action="store_true",
        help=(
            "Executa uma fase de setup distribuída no nó coordenador. "
            "Requer --phase [clean|prereqs|enroll|artifacts|channels|chaincode]. "
            "Usado pelos jobs SLURM do --slurm-deploy."
        )
    )
    group.add_argument(
        "--slurm-deploy",
        action="store_true",
        dest="slurm_deploy",
        help=(
            "Gera um script bash com todas as fases do deploy distribuído via SLURM. "
            "Requer --time e as seções 'machines'/'slurm' em network.yaml."
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
            "Para --start: clean | cas | nodes | ccaas. "
            "Para --setup: clean | prereqs | enroll | artifacts | channels | chaincode."
        )
    )
    parser.add_argument(
        '--time',
        type=str,
        required=False,
        metavar='HH:MM:SS',
        help="Duração máxima do job SLURM (ex: 03:00:00). Obrigatório com --slurm-deploy."
    )

    parser.add_argument(
        "--redeploy-cc",
        choices=["code", "ledger"],
        dest="redeploy_cc",
        help=(
            "Atualiza chaincode(s) de uma rede já ativa, sem derrubá-la. "
            "'code' recompila e reinicia apenas o container CCAAS. "
            "'ledger' também reinstala e roda approveformyorg/commit com a "
            "nova 'version'/'sequence' do network.yaml (devem ser "
            "incrementadas manualmente antes de rodar)."
        )
    )
    parser.add_argument(
        '--cc-name',
        type=str,
        dest="cc_name",
        metavar='NOME',
        help="Nome do chaincode a atualizar com --redeploy-cc (ex: cc_basic_asset). Se omitido, atualiza todos."
    )

    parser.add_argument(
        "--register-user",
        type=str,
        dest="register_user",
        metavar='USERNAME',
        help=(
            "Registra e matricula (fabric-ca-client register/enroll) um novo "
            "cliente na CA de uma organização de uma rede já ativa. "
            "Requer --org e --secret."
        )
    )
    parser.add_argument(
        '--org',
        type=str,
        dest="org",
        metavar='ORG',
        help="Organização alvo de --register-user (ex: Org1)."
    )
    parser.add_argument(
        '--secret',
        type=str,
        dest="secret",
        metavar='SENHA',
        help="Senha/secret da nova identidade para --register-user. Obrigatório, sem valor padrão."
    )

    parser.add_argument(
        '-n', '--network',
        type=str,
        required=True,
        help="Caminho para o arquivo network.yaml que será utilizado"
    )

    args = parser.parse_args()

    try:
        paths = PathManager(custom_network_yaml=args.network)
        co.infoln(f"Alvo: {paths.network_yaml.name}")

        loader = ConfigLoader(paths.network_yaml, paths.versions_yaml)
        config = loader.load()

        controller = NetworkController(config, paths, log_to_file=args.log)

        paths.ensure_network_dirs()

        if args.clean:
            op_code = 1 if args.clean == "all" else 0

            if not args.network:
                co.warnln("Nenhum arquivo de configuração de rede especificado para limpeza. Usando o padrão 'network.yaml' no diretório do projeto.")
            _clean_files(controller, op=op_code)

        if args.up:
            _network_up(controller, config, paths, machine=args.machine)

        elif args.start:
            if not args.machine:
                parser.error("--start requer --machine <nome>")
            if not args.phase:
                parser.error("--start requer --phase [clean|cas|nodes|ccaas]")
            _start_phase(controller, config, paths, args.machine, args.phase)

        elif args.setup:
            if not args.phase:
                parser.error("--setup requer --phase [clean|prereqs|enroll|artifacts|channels|chaincode]")
            _setup_phase(controller, config, paths, args.phase)

        elif args.slurm_deploy:
            if not args.time:
                parser.error("--slurm-deploy requer --time HH:MM:SS")
            _slurm_deploy(config, paths, args.time)

        elif args.redeploy_cc:
            _redeploy_chaincode(controller, config, paths, args.redeploy_cc, args.cc_name)

        elif args.register_user:
            if not args.org:
                parser.error("--register-user requer --org <nome>")
            if not args.secret:
                parser.error("--register-user requer --secret <senha>")
            _register_user(config, paths, args.org, args.register_user, args.secret)

        elif not args.clean:
            parser.print_help()

    except Exception as e:
        co.errorln(f"Falha Crítica: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
