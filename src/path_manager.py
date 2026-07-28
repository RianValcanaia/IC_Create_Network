# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
Gerenciador central de caminhos e diretórios do projeto.

Responsável por resolver caminhos absolutos para configurações, scripts e
artefatos da rede, garantindo que a estrutura de diretórios necessária
(organizations, channel-artifacts, docker) exista antes da execução.
"""

import os
from pathlib import Path

import yaml

class PathManager:
    def __init__(self, custom_network_yaml):
        # base do projeto (assumindo que este arquivo está em src/)
        self.base_dir = Path(__file__).parent.parent.resolve()

        # caminhos principais
        self.config_dir = self.base_dir / "project_config"
        network_folder = self._read_network_folder(Path(custom_network_yaml).resolve())
        self.network_dir = self.base_dir / "network" / network_folder
        self.scripts_dir = self.base_dir / "scripts"
        self.templates_dir = self.base_dir / "template"
        self.versions_yaml = self.config_dir / "versions.yaml"
        self.chaincode_dir = self.base_dir / "chaincode"

        self.network_yaml = Path(custom_network_yaml).resolve()

        self.core_yaml_template = self.config_dir / "core.yaml"
        self.peer_cfg_dir = self.network_dir / "compose" / "peercfg"

    # le network.folder (ou network.name) do YAML — pasta que isola os artefatos desta rede
    @staticmethod
    def _read_network_folder(network_yaml):
        """Lê network.folder (ou network.name) do YAML — pasta que isola os artefatos desta rede"""
        with open(network_yaml) as f:
            data = yaml.safe_load(f)
        net = data["network"]
        return net.get("folder", net["name"])

    # retorna um dicionário com todos os caminhos convertidos para string
    def get_paths(self):
        """Retorna um dicionário com todos os caminhos convertidos para string"""
        return {
            "BASE_DIR": str(self.base_dir),
            "NETWORK_DIR": str(self.network_dir),
            "SCRIPTS_DIR": str(self.scripts_dir),
            "CONFIG_FILE": str(self.network_yaml),
            "TEMPLATES_DIR": str(self.templates_dir),
        }

    # cria a estrutura de pastas dentro de network/ se não existir
    def ensure_network_dirs(self):
        """Cria a estrutura de pastas dentro de network/ se não existir"""
        subdirs = ["organizations", "channel-artifacts", "docker", "compose/peercfg"]
        for sub in subdirs:
            (self.network_dir / sub).mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    print("Caminhos configurados:")
    pm = PathManager()
    paths = pm.get_paths()
    for key, value in paths.items():
        print(f"{key}: {value}")