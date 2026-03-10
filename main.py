# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
O ponto de entrada da aplicação que orquestra todo o fluxo de 
subida ou limpeza da rede. Ele processa os argumentos de linha 
de comando (--up, --clean) e chama sequencialmente os validadores 
e geradores de scripts.
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

def _cria_compose_ca(config, paths):
    co.infoln("Gerando arquivos docker-compose para ca")

    compose_generator = ComposeGenerator(config, paths)
    compose_generator.generate_ca_compose()

def _start_CA(controller):
    co.infoln("Iniciando os servidores CA")

    try:
        controller.run_script("start_cas.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao iniciar servidores CA: {e}")
        return

def _register_enroll(controller, config, paths):
    co.infoln("Registrando e matriculando identidades")

    crypto = CryptoGenerator(config, paths)

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

def _inicializa_nos(controller, config, paths):
    co.infoln("Gerando arquivos docker-compose para peers e orderers")

    compose_generator = ComposeGenerator(config, paths)
    compose_generator.generate_nodes_compose()

    try:
        controller.run_script("start_nodes.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'start_nodes.sh': {e}")
        return
    
def _configura_canais(controller, config, paths):
    co.infoln("Configurando canais e fazendo peers entrarem neles")

    channel_gen = ChannelScriptGenerator(config, paths)
    channel_gen.generate_channel_script()

    try:
        controller.run_script("create_channel.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'create_channel.sh': {e}")
        return

def _deploy_chaincode(controller, config, paths):
    co.infoln("Fazendo deploy de chaincodes")

    deploy_gen = ChaincodeDeployGenerator(config, paths)
    deploy_gen.generate()

    try:
        controller.run_script("deploy_chaincode.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'deploy_chaincode.sh': {e}")
        return

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
        org_data = {
            "msp_id": org['msp_id'],
            "peers": {p['name']: {"port": p['port'], "tls_port": p.get('chaincode_port')} for p in org['peers']}
        }
        context["orgs"][org['name']] = org_data

    with open(paths.network_dir / "contexto_ativo.json", "w") as f:
        json.dump(context, f, indent=2)

def _network_up(controller, config, paths):
    co.headerln("Iniciando a rede")

    paths.ensure_network_dirs()

    # --- Validações iniciais ---
    _verifica_prerequisitos(controller)
    _valida_configuracoes(config)
    _exporta_network_contexto(config, paths)

    pkg_id_file = paths.network_dir / "CC_PACKAGE_ID"
    if not pkg_id_file.exists():
        pkg_id_file.touch()

    _cria_compose_ca(config, paths)

   # --- Inicialização da rede ---
    _start_CA(controller)
    _register_enroll(controller, config, paths)
    _cria_artefatos(controller, config, paths)
    _inicializa_nos(controller, config, paths)
    _configura_canais(controller, config, paths)
    _deploy_chaincode(controller, config, paths)
    
    co.infoln("Aguardando estabilização final do Chaincode (Porta 9999)...")
    if _wait_for_port("localhost", 9999, timeout=120):
        co.successln("Chaincode está escutando na porta 9999!")
    else:
        co.warnln("Timeout: O Chaincode não respondeu na porta 9999 a tempo.")

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
    
    parser.add_argument(
        "--up", 
        action="store_true", 
        help="Inicia o processo completo de subida da rede (network_up)."
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
            _network_up(controller, config, paths)

        if not args.clean and not args.up:
            parser.print_help()

    except Exception as e:
        co.errorln(f"Falha Crítica: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()