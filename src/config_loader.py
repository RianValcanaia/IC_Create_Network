# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
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
        # inicializa os caminhos dos arquivos de configuracao
        self.network_config_path = network_config_path
        self.versions_config_path = versions_config_path
        # dict que armazena toda a configuracao consolidada
        self.full_config = {}

    # faz a leitura dos arquivos e convertem em objetos python
    def load(self):
        # carrega o arquivo da topologia da rede 
        with open(self.network_config_path, 'r') as f:
            # yaml.safe_load transforma o texto do yaml em um dict python
            self.full_config['network_topology'] = yaml.safe_load(f)
        
        # carrega as versões do ambiente    
        if os.path.exists(self.versions_config_path):
            with open(self.versions_config_path, 'r') as f:
                # armazena as definicoes de versoes 
                self.full_config['env_versions'] = yaml.safe_load(f)
        else:
            raise FileNotFoundError("Arquivo versions.yaml não encontrado!")
        return self.full_config