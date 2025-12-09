from src.path_manager import PathManager
from src.config_loader import ConfigLoader
from src.network_controller import NetworkController
from src.colors import Colors as co

def create_network():
    # 1. Configurar Caminhos
    paths = PathManager()

    # 2. Carregar Configurações
    loader = ConfigLoader(paths.network_yaml, paths.versions_yaml)
    config = loader.load()

    # 3. Inicializar Controlador
    controller = NetworkController(config, paths)

    # 4. Verifica versões e pré-requisitos
    # try:
    #     controller.run_script("check_reqs.sh")
    # except Exception as e:
    #     co.errorln(f"\n Erro nos pré-requisitos: {e}")
    #     return
    
    try:
        controller.run_script("check_reqs.sh")
    except Exception as e:
        co.errorln(f"\n Erro nos pré-requisitos: {e}")
        return

def clean_files():
    # 1. Configurar Caminhos
    paths = PathManager()

    # 2. Carregar Configurações
    loader = ConfigLoader(paths.network_yaml, paths.versions_yaml)
    config = loader.load()

    # 3. Inicializar Controlador
    controller = NetworkController(config, paths)


    try:
        controller.run_script("clean.sh")
    except Exception as e:
        co.errorln(f"\n Erro nos pré-requisitos: {e}")
        return

def main():

    print("Digite a opcao desejada:")
    print("1 - Criar network")
    print("2 - Limpar arquivos gerados e network")
    print("0 - sair")
    opcao = input()

    if opcao == '1':
        create_network()
    elif opcao == '2':
        clean_files()
    elif opcao == '0':
        print("Saindo...")
    else:
        print("Opcao invalida.")


if __name__ == "__main__":
    main()