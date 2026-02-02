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
        self.config = config
        self.paths = paths 
        self.log_to_file = log_to_file

        if self.log_to_file:
            self.log_dir = Path(self.paths.network_dir) / "logs"
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def _get_env_vars(self):
        """Converte as configurações de versão em variáveis de ambiente"""
        versions = self.config['env_versions']['versions']
        images = self.config['env_versions']['images']
        network_name = self.config['network_topology']['network']['name']

        # caminho absoluto para a pasta bin do projeto
        project_bin_path = str(self.paths.base_dir / "bin")
        
        # pega o PATH atual do sistema
        system_path = os.environ["PATH"]

        return {
            "FABRIC_VERSION": versions['fabric'],
            "CA_VERSION": versions['fabric_ca'],
            "GO_VERSION": versions['go'],
            "DOCKER_IMAGE_PREFIX": images['org_hyperledger'],
            "NETWORK_NAME": network_name,
            "PATH": f"{project_bin_path}:{system_path}"
        }

    def run_script(self, script_name, extra_env=None):
        script_path = os.path.join(self.paths.scripts_dir, script_name)
        env = os.environ.copy()
        env.update(self._get_env_vars())
        env["NETWORK_DIR"] = str(self.paths.network_dir)
        
        if extra_env:
            env.update(extra_env)

        if self.log_to_file:
            log_file_path = self.log_dir / f"{script_name}.log"
            co.infoln(f"Executando {script_name}... (Logs em {log_file_path})")

            try:
                with open(log_file_path, "w") as log_file:
                    subprocess.run(
                        ["bash", script_path], 
                        check=True, 
                        env=env,
                        stdout=log_file, 
                        stderr=log_file  
                    )
                    co.successln(f"Concluido {script_name} com sucesso.")
            except subprocess.CalledProcessError as e:
                co.errorln(f"Erro ao executar {script_name}: {e}")
                raise
        else:
            co.infoln(f"Executando {script_name} (Modo Verboso)...")
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