import os
from pathlib import Path

class PathManager:
    def __init__(self):
        # Base do projeto (assumindo que este arquivo está em src/)
        self.base_dir = Path(__file__).parent.parent.resolve()
        
        # Caminhos principais
        self.config_dir = self.base_dir / "config"
        self.network_dir = self.base_dir / "network"
        self.scripts_dir = self.base_dir / "scripts"
        self.templates_dir = self.base_dir / "template"
        self.versions_yaml = self.config_dir / "versions.yaml"
        
        # Arquivo de config
        self.network_yaml = self.config_dir / "network.yaml"

    def get_paths(self):
        """Retorna um dicionário com todos os caminhos convertidos para string"""
        return {
            "BASE_DIR": str(self.base_dir),
            "NETWORK_DIR": str(self.network_dir),
            "SCRIPTS_DIR": str(self.scripts_dir),
            "CONFIG_FILE": str(self.network_yaml),
            "TEMPLATES_DIR": str(self.templates_dir),
        }

    def ensure_network_dirs(self):
        """Cria a estrutura de pastas dentro de network/ se não existir"""
        subdirs = ["organizations", "channel-artifacts", "docker"]
        for sub in subdirs:
            (self.network_dir / sub).mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    print("Caminhos configurados:")
    pm = PathManager()
    paths = pm.get_paths()
    for key, value in paths.items():
        print(f"{key}: {value}")