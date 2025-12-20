from src.path_manager import PathManager
from src.config_loader import ConfigLoader
from src.network_controller import NetworkController
from src.parser import ConfigParser
from src.utils import Colors as co

from src.generator.compose import ComposeGenerator 
from src.generator.crypto import CryptoGenerator 
from src.generator.configtx import ConfigTxGenerator

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

def network_up(controller, config, paths):
    # ------------- Preparando o ambiente --------------
    co.infoln("Iniciando a rede")
    co.infoln("Verificando pré-requisitos do sistema")
    _verifica_prerequisitos(controller)
    co.infoln("Validando configurações do arquivo network.yaml")
    _valida_configuracoes(config)
    co.infoln("Gerando arquivos docker-compose para ca")
    _cria_compose_ca(config, paths)

   # ------------- Iniciando a network --------------
    co.infoln("Iniciando os servidores CA")
    _start_CA(controller)
    co.infoln("Registrando e matriculando identidades")
    _register_enroll(controller, config, paths)
    co.infoln("Gerando artefatos da rede (configtx.yaml, blocos, canais, etc)")
    _cria_artefatos(controller, config, paths)

def clean_files(controller, op = 1):
    try:
        if op == 1:
            controller.run_script("clean_all.sh")
        else:
            controller.run_script("clean_network.sh")
    except Exception as e:
        co.errorln(f"\n Erro nos pré-requisitos: {e}")
        return

def main():
    try:
        # configura caminhos
        paths = PathManager()

        # carregar configuracoes
        loader = ConfigLoader(paths.network_yaml, paths.versions_yaml)
        config = loader.load()

        # inicializa controller da rede
        controller = NetworkController(config, paths)
        paths.ensure_network_dirs()
        
        # network_up(controller, config, paths)
        clean_files(controller)
    except Exception as e:
        co.errorln(f"{e}")
        exit(1)

if __name__ == "__main__":
    main()
