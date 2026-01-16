import argparse
import time

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

def _verifica_prerequisitos(controller):
    try:
        controller.run_script("check_reqs.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'check_reqs.sh': {e}")
        return

def _valida_configuracoes(config):    
    parser = ConfigParser(config)
    parser.valida()

    if parser.erros:
        raise RuntimeError("Erros de validação encontrados.")


def _cria_compose_ca(config, paths):
    compose_generator = ComposeGenerator(config, paths)
    compose_generator.generate_ca_compose()

def _start_CA(controller):
    try:
        controller.run_script("start_cas.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao iniciar servidores CA: {e}")
        return

def _register_enroll(controller, config, paths):
    crypto = CryptoGenerator(config, paths)

    co.infoln("Gerando script de identidades (register_enroll.sh)...")
    crypto.generate()

    try:
        import time
        time.sleep(2)
        controller.run_script("register_enroll.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'register_enroll.sh': {e}")
        return
    
def _cria_artefatos(controller, config, paths):
    configtx_gen = ConfigTxGenerator(config, paths)
    configtx_gen.generate()

    try:
        controller.run_script("create_artifacts.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'create_artifacts.sh': {e}")
        return

def _inicializa_nos(controller, config, paths):
    compose_generator = ComposeGenerator(config, paths)
    compose_generator.generate_nodes_compose()

    try:
        controller.run_script("start_nodes.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'start_nodes.sh': {e}")
        return
    
def _configura_canais(controller, config, paths):
    channel_gen = ChannelScriptGenerator(config, paths)
    channel_gen.generate_channel_script()

    try:
        controller.run_script("create_channel.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'create_channel.sh': {e}")
        return

def _deploy_chaincode(controller, config, paths):
    deploy_gen = ChaincodeDeployGenerator(config, paths)
    deploy_gen.generate()

    try:
        controller.run_script("deploy_chaincode.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'deploy_chaincode.sh': {e}")
        return


def _network_up(controller, config, paths):
    # ------------- Preparando o ambiente --------------
    co.infoln("Iniciando a rede")
    co.infoln("Verificando pré-requisitos do sistema")
    _verifica_prerequisitos(controller)
    co.infoln("Validando configurações do arquivo network.yaml")
    _valida_configuracoes(config)

    pkg_id_file = paths.network_dir / "CC_PACKAGE_ID"
    if not pkg_id_file.exists():
        pkg_id_file.touch()

    co.infoln("Gerando arquivos docker-compose para ca")
    _cria_compose_ca(config, paths)

   # ------------- Iniciando a network --------------
    co.infoln("Iniciando os servidores CA")
    _start_CA(controller)
    co.infoln("Registrando e matriculando identidades")
    _register_enroll(controller, config, paths)
    co.infoln("Gerando artefatos da rede (configtx.yaml, blocos, canais, etc)")
    _cria_artefatos(controller, config, paths)
    co.infoln("Gerando arquivos docker-compose para peers e orderers")
    _inicializa_nos(controller, config, paths)
    co.infoln("Aguardando inicialização completa dos containers...")
    time.sleep(10) 
    co.infoln("Configurando canais e fazendo peers entrarem neles")
    _configura_canais(controller, config, paths)
    co.infoln("Fazendo deploy de chaincodes")
    _deploy_chaincode(controller, config, paths)

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

    args = parser.parse_args()

    try:
        # configura caminhos
        paths = PathManager()

        # carregar configuracoes
        loader = ConfigLoader(paths.network_yaml, paths.versions_yaml)
        config = loader.load()

        # inicializa controller da rede
        controller = NetworkController(config, paths, log_to_file=args.log)
        paths.ensure_network_dirs()

        # Executa em modo limpeza
        if args.clean:
            op_code = 1 if args.clean == "all" else 0
            co.infoln(f"Executando limpeza modo: {args.clean}")
            _clean_files(controller, op=op_code)

        # Sobe a rede
        if args.up:
            _network_up(controller, config, paths)

        if not args.clean and not args.up:
            parser.print_help()

    except Exception as e:
        co.errorln(f"{e}")
        exit(1)

if __name__ == "__main__":
    main()
