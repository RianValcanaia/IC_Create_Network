"""
Rever: futuramente ver a TLS ativa para os CAs e a interface de operações.
"""
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
        orderer_conf = self.config['network_topology']['orderer']
        
        img_prefix = self.config['env_versions']['images']['org_hyperledger']
        ca_version = self.config['env_versions']['versions']['fabric_ca']
        network_name = self.config['network_topology']['network']['name']

        # --- 1. CAs das Organizações de Peers ---
        for org in orgs:
            ca_config = org['ca']
            org_name = org['name']
            service_name = ca_config['name']
            port = ca_config['port']
            
            # Caminho de persistência: network/organizations/fabric-ca/Org1
            ca_server_home = "/etc/hyperledger/fabric-ca-server"
            
            services[service_name] = {
                'image': f"{img_prefix}/fabric-ca:{ca_version}",
                'labels': {'service': "hyperledger-fabric-ca"},
                'container_name': service_name,
                'environment': [
                    f"FABRIC_CA_HOME={ca_server_home}",
                    f"FABRIC_CA_SERVER_CA_NAME={service_name}",
                    "FABRIC_CA_SERVER_TLS_ENABLED=false",
                    f"FABRIC_CA_SERVER_PORT={port}",
                    "FABRIC_CA_SERVER_CSR_CN=" + service_name,
                    "FABRIC_CA_SERVER_CSR_HOSTS=0.0.0.0",
                ],
                'ports': [f"{port}:{port}"],
                'command': "sh -c 'fabric-ca-server start -b admin:adminpw -d'",
                'volumes': [
                    f"../organizations/fabric-ca/{org_name}:{ca_server_home}"
                ],
                'networks': [network_name]
            }

        # --- 2. CA do Orderer (NOVO TRECHO) ---
        # Tenta pegar config do yaml ou usa defaults
        ord_ca = orderer_conf.get('ca', {})
        ord_ca_name = ord_ca.get('name', 'ca-orderer')
        ord_ca_port = ord_ca.get('port', 7054)
        
        # Pasta de persistência do Orderer
        # Nota: Usamos 'ordererOrg' como nome de pasta padrão para a organização do orderer
        ord_org_folder = "ordererOrg" 
        
        services[ord_ca_name] = {
            'image': f"{img_prefix}/fabric-ca:{ca_version}",
            'labels': {'service': "hyperledger-fabric-ca"},
            'container_name': ord_ca_name,
            'environment': [
                f"FABRIC_CA_HOME=/etc/hyperledger/fabric-ca-server",
                f"FABRIC_CA_SERVER_CA_NAME={ord_ca_name}",
                "FABRIC_CA_SERVER_TLS_ENABLED=false",
                f"FABRIC_CA_SERVER_PORT={ord_ca_port}",
                f"FABRIC_CA_SERVER_CSR_CN={ord_ca_name}",
                "FABRIC_CA_SERVER_CSR_HOSTS=0.0.0.0",
            ],
            'ports': [f"{ord_ca_port}:{ord_ca_port}"],
            'command': "sh -c 'fabric-ca-server start -b admin:adminpw -d'",
            'volumes': [
                f"../organizations/fabric-ca/{ord_org_folder}:/etc/hyperledger/fabric-ca-server"
            ],
            'networks': [network_name]
        }

        # Monta o arquivo final
        compose_content = {
            'networks': {
                network_name: {
                    'name': f"{network_name}_net"
                }
            },
            'services': services
        }

        self.compose_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = self.compose_dir / "compose-ca.yaml"
        with open(output_path, 'w') as f:
            yaml.dump(compose_content, f, sort_keys=False)
            
        co.successln(f"Arquivo gerado: {output_path}")