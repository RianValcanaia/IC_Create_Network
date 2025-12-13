import yaml
import os
from ..utils import Colors as co

class ComposeGenerator:
    def __init__(self, config, paths):
        self.config = config
        self.paths = paths
        self.compose_dir = self.paths.network_dir / "compose"

    def generate_ca_compose(self):        
        services = {}
        orgs = self.config['network_topology']['organizations']
        
        # Prefixo da imagem (ex: hyperledger) e versão
        img_prefix = self.config['env_versions']['images']['org_hyperledger']
        ca_version = self.config['env_versions']['versions']['fabric_ca']

        network_name = self.config['network_topology']['network']['name']

        for org in orgs:
            ca_config = org['ca']
            org_name = org['name']
            
            # Definição do Serviço
            service_name = ca_config['name']
            port = ca_config['port']
            
            # Caminho onde os dados da CA ficarão salvos (persistência)
            # ex: network/organizations/fabric-ca/org1
            ca_server_home = f"/etc/hyperledger/fabric-ca-server"
            
            services[service_name] = {
                'image': f"{img_prefix}/fabric-ca:{ca_version}",
                'labels': {
                    'service': "hyperledger-fabric-ca"
                },
                'container_name': service_name,
                'environment':[
                    f"FABRIC_CA_HOME={ca_server_home}",
                    f"FABRIC_CA_SERVER_CA_NAME={service_name}",
                    "FABRIC_CA_SERVER_TLS_ENABLED=false", # TLS desligado por enquanto, futuramente pensar em ativar
                    f"FABRIC_CA_SERVER_PORT={port}",
                    # Usuário admin padrão para bootstrap
                    "FABRIC_CA_SERVER_CSR_CN=" + service_name,
                    "FABRIC_CA_SERVER_CSR_HOSTS=0.0.0.0",
                    # - FABRIC_CA_SERVER_OPERATIONS_LISTENADDRESS=0.0.0.0:17054, se futuramente quiser ativar a interface de operações like prometheus
                ],
                'ports': [f"{port}:{port}"],
                'command': "sh -c 'fabric-ca-server start -b admin:adminpw -d'",
                'volumes': [
                    # Mapeia pasta local network/organizations/fabric-ca/orgX para dentro do container
                    f"../organizations/fabric-ca/{org_name}:{ca_server_home}"
                ],
                'networks': [network_name]
            }   

        # Monta o dicionário final do Docker Compose
        compose_content = {
            'networks': {
                network_name: {
                    'name': f"{network_name}_net" # Nome fixo da rede Docker
                }
            },
            'services': services
        }

        # Garante que a pasta docker existe
        self.compose_dir.mkdir(parents=True, exist_ok=True)
        
        # Salva o arquivo
        output_path = self.compose_dir / "compose-ca.yaml"
        with open(output_path, 'w') as f:
            yaml.dump(compose_content, f, sort_keys=False)
            
        co.successln(f"Arquivo gerado: {output_path}")