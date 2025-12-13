from src.path_manager import PathManager
from src.config_loader import ConfigLoader
from src.network_controller import NetworkController
from src.parser import ConfigParser
from src.utils import Colors as co
from src.generator.compose import ComposeGenerator as cg

def _verifica_prerequisitos(controller):
    try:
        controller.run_script("check_reqs.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao rodar 'check_reqs.sh': {e}")
        return

def _valida_configuracoes(config):    
    parser = ConfigParser(config)
    parser.valida()

def _cria_compose_ca(config, paths):
    compose_generator = cg(config, paths)
    compose_generator.generate_ca_compose()

def _start_CA(controller):
    try:
        controller.run_script("start_cas.sh")
    except Exception as e:
        co.errorln(f"\n Erro ao iniciar servidores CA: {e}")
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

def clean_files(controller):
    try:
        controller.run_script("clean.sh")
    except Exception as e:
        co.errorln(f"\n Erro nos pré-requisitos: {e}")
        return

def main():
    # 1. Configurar Caminhos
    paths = PathManager()

    # 2. Carregar Configurações
    loader = ConfigLoader(paths.network_yaml, paths.versions_yaml)
    config = loader.load()

    # 3. Inicializar Controlador
    controller = NetworkController(config, paths)

    #network_up(controller, config, paths)
    clean_files(controller)

if __name__ == "__main__":
    main()
