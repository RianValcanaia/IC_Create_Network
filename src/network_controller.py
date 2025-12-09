import os
import subprocess
from .colors import Colors as co

class NetworkController:
    def __init__(self, config, paths):
        self.config = config
        self.paths = paths # Instância do PathManager

    def _get_env_vars(self):
        """Converte as configurações de versão em variáveis de ambiente"""
        versions = self.config['env_versions']['versions']
        images = self.config['env_versions']['images']
        
        # Caminho absoluto para a pasta bin do projeto
        project_bin_path = str(self.paths.base_dir / "bin")
        
        # Pega o PATH atual do sistema
        system_path = os.environ["PATH"]

        return {
            "FABRIC_VERSION": versions['fabric'],
            "CA_VERSION": versions['fabric_ca'],
            "GO_VERSION": versions['go'],
            "DOCKER_IMAGE_PREFIX": images['org_hyperledger'],
            "PATH": f"{project_bin_path}:{system_path}"
        }

    def run_script(self, script_name, extra_env=None):
        script_path = os.path.join(self.paths.scripts_dir, script_name)
        
        # 1. Carrega variáveis base do sistema
        env = os.environ.copy()
        
        # 2. Injeta variáveis de versão (Carregadas do YAML)
        env.update(self._get_env_vars())
        
        # 3. Injeta o caminho da pasta network (Do PathManager)
        env["NETWORK_DIR"] = str(self.paths.network_dir)

        # 4. Injeta variáveis extras específicas da chamada
        if extra_env:
            env.update(extra_env)

        co.infoln(f"Executando {script_name} (Fabric v{env['FABRIC_VERSION']})...")
        try:
            # check true garante erro se o script falhar
            subprocess.run(["bash", script_path], check=True, env=env)
        except subprocess.CalledProcessError as e:
            co.errorln(f"Erro ao executar {script_name}: {e}")
            raise


        

    def prepare_environment(self):
        # Cria as pastas necessárias
        self.paths.ensure_network_dirs()
        # Poderia chamar um script de limpeza aqui também
        # self._run_script("00_cleanup.sh")