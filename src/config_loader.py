"""
Carregador de arquivos de configuração YAML.

Responsável por ler os arquivos 'network.yaml' (topologia) e 'versions.yaml'
(versões do ambiente), convertendo-os em dicionários Python para serem
consumidos pelo restante da aplicação.
"""

import yaml
import os
from .utils import Colors as co

class ConfigLoader:
    def __init__(self, network_config_path, versions_config_path):
        self.network_config_path = network_config_path
        self.versions_config_path = versions_config_path
        self.full_config = {}

    def load(self):
        # 1. Carrega topologia da rede
        with open(self.network_config_path, 'r') as f:
            self.full_config['network_topology'] = yaml.safe_load(f)

        # 2. Carrega versões
        if os.path.exists(self.versions_config_path):
            with open(self.versions_config_path, 'r') as f:
                self.full_config['env_versions'] = yaml.safe_load(f)
        else:
            raise FileNotFoundError("Arquivo versions.yaml não encontrado!")

        co.successln("Todas as configurações carregadas.")
        return self.full_config