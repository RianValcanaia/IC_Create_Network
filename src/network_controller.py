# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
Controlador de execução e orquestração de scripts da rede.

Atua como ponte entre a aplicação Python e os scripts Bash, gerenciando
variáveis de ambiente (versões do Fabric/Go, caminhos), preparando o
sistema de arquivos e executando subprocessos para criação e limpeza da rede.
"""
import os
import subprocess
from pathlib import Path
from .utils import Colors as co

class NetworkController:
    def __init__(self, config, paths, log_to_file=False):
        """
        inicializa o controlador
        :param config: Configurações da rede, carregada pelo configLoader
        :param paths: gerenciador de caminhos do projeto
        :param log_to_file: Se True, salva em arquivos .log
        """
        self.config = config
        self.paths = paths 
        self.log_to_file = log_to_file

        # se o log estiver ativo, cria uma pasta logs dentro do diretorio da rede
        if self.log_to_file:
            self.log_dir = Path(self.paths.network_dir) / "logs"
            self.log_dir.mkdir(parents=True, exist_ok=True)

    
    def _get_env_vars(self):
        """
        metodo privado que prepara as variaveis de ambiente 
        que os scripts bash vao precisa, evitando que tenha que
        configurar matualmente
        """
        versions = self.config['env_versions']['versions']
        images = self.config['env_versions']['images']
        network_name = self.config['network_topology']['network']['name']

        # garante que os binarios do fabric na pasta /bin tenham prioridade sobre os binarios globais do sistema
        project_bin_path = str(self.paths.base_dir / "bin")
        system_path = os.environ["PATH"]

        # retorna um dicionario com as versoes e o path atualizado
        return {
            "FABRIC_VERSION": versions['fabric'],
            "CA_VERSION": versions['fabric_ca'],
            "GO_VERSION": versions['go'],
            "DOCKER_IMAGE_PREFIX": images['org_hyperledger'],
            "NETWORK_NAME": network_name,
            "NETWORK_CONFIG": str(self.paths.network_yaml),
            "PATH": f"{project_bin_path}:{system_path}"
        }

    def run_script(self, script_name, extra_env=None):
        """
        Executa um script bash localizado na pasta de scripts
        """
        script_path = os.path.join(self.paths.scripts_dir, script_name)
        
        # cria uma copia da variaveis de ambiente atuais do sistema e injeta as da rede
        env = os.environ.copy()
        env.update(self._get_env_vars())
        env["NETWORK_DIR"] = str(self.paths.network_dir) # informa ao bash aonde a rede esta
        
        # se houver variaveis extras passadas na chamada, injeta tambem
        if extra_env:
            env.update(extra_env)

        # logica de execucao com log em arquivo
        if self.log_to_file:
            log_file_path = self.log_dir / f"{script_name}.log"
            co.infoln(f"Executando {script_name}... (Logs em {log_file_path})")

            try:
                with open(log_file_path, "w") as log_file:
                    # executa o scrit e redireciona a saida (stdout) e erros (stderr) para o arquivo de log
                    subprocess.run(
                        ["bash", script_path], 
                        check=True,  # para se o script bash der pau
                        env=env,
                        stdout=log_file, 
                        stderr=log_file  
                    )
                    co.successln(f"Concluido {script_name} com sucesso.")
            except subprocess.CalledProcessError as e:
                co.errorln(f"Erro ao executar {script_name}: {e}")
                raise  # repasse o erro para o chamador
        # logica de execucao com saida no teminal (modo verboso)
        else:
            co.infoln(f"Executando {script_name} (Modo Verboso)")
            try:
                subprocess.run(
                    ["bash", script_path], 
                    check=True, 
                    env=env
                )
                co.successln(f"Concluido {script_name} com sucesso.")
            except subprocess.CalledProcessError as e:
                co.errorln(f"Erro ao executar {script_name}: {e}")
                raise

    def prepare_environment(self):
        self.paths.ensure_network_dirs()