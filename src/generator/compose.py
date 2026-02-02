# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
Gerador dos arquivos de orquestração Docker Compose 
(compose-ca.yaml e compose-nodes.yaml). Ele define 
as imagens, variáveis de ambiente, volumes e redes 
necessárias para rodar as Autoridades Certificadoras 
(CAs), Peers e Orderers.

Rever: futuramente ver a TLS ativa para os CAs e a interface de operações.
"""
import yaml
import shutil
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

        # --- CAs das Organizações de Peers ---
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

        # --- CA do Orderer ---
        # Tenta pegar config do yaml ou usa defaults
        ord_ca = orderer_conf.get('ca', {})
        ord_ca_name = ord_ca.get('name', 'ca-orderer')
        ord_ca_port = ord_ca.get('port', 7054)
        
        # Pasta de persistência do Orderer
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
                    'external': True,
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

    def generate_nodes_compose(self):
        try:
            target_file = self.paths.peer_cfg_dir / "core.yaml"
            shutil.copy(self.paths.core_yaml_template, target_file)
        except Exception as e:
            co.errorln(f"Erro ao copiar core.yaml: {e}")
            return

        services = {}
        orgs = self.config['network_topology']['organizations']
        orderer_conf = self.config['network_topology']['orderer']
        domain = self.config['network_topology']['network']['domain']
        network_name = self.config['network_topology']['network']['name']
        img_prefix = self.config['env_versions']['images']['org_hyperledger']
        fabric_version = self.config['env_versions']['versions']['fabric']

        # --- seção de Orderers ---
        for node in orderer_conf['nodes']:
            full_name = f"{node['name']}.{domain}"
            services[full_name] = {
                'container_name': full_name,
                'image': f"{img_prefix}/fabric-orderer:{fabric_version}",
                'labels': {'service': 'hyperledger-fabric'},
                'environment': [
                    "FABRIC_LOGGING_SPEC=INFO",
                    "ORDERER_GENERAL_LISTENADDRESS=0.0.0.0",
                    f"ORDERER_GENERAL_LISTENPORT={node['port']}",
                    "ORDERER_GENERAL_LOCALMSPID=OrdererMSP",
                    "ORDERER_GENERAL_LOCALMSPDIR=/var/hyperledger/orderer/msp",
                    "ORDERER_GENERAL_BOOTSTRAPMETHOD=none",
                    "ORDERER_CHANNELPARTICIPATION_ENABLED=true",
                    "ORDERER_GENERAL_TLS_ENABLED=true",
                    "ORDERER_GENERAL_TLS_PRIVATEKEY=/var/hyperledger/orderer/tls/server.key",
                    "ORDERER_GENERAL_TLS_CERTIFICATE=/var/hyperledger/orderer/tls/server.crt",
                    "ORDERER_GENERAL_TLS_ROOTCAS=[/var/hyperledger/orderer/tls/ca.crt]",
                    "ORDERER_ADMIN_TLS_ENABLED=true",
                    "ORDERER_ADMIN_TLS_CERTIFICATE=/var/hyperledger/orderer/tls/server.crt",
                    "ORDERER_ADMIN_TLS_PRIVATEKEY=/var/hyperledger/orderer/tls/server.key",
                    "ORDERER_ADMIN_TLS_ROOTCAS=[/var/hyperledger/orderer/tls/ca.crt]",
                    f"ORDERER_ADMIN_TLS_CLIENTROOTCAS=[/var/hyperledger/orderer/tls/ca.crt]",
                    f"ORDERER_ADMIN_LISTENADDRESS=0.0.0.0:{node['admin_port']}",
                ],
                'working_dir': '/root',
                'command': 'orderer',
                'volumes': [
                    f"../organizations/ordererOrganizations/{domain}/orderers/{full_name}/msp:/var/hyperledger/orderer/msp",
                    f"../organizations/ordererOrganizations/{domain}/orderers/{full_name}/tls/:/var/hyperledger/orderer/tls",
                    f"{full_name}:/var/hyperledger/production/orderer"
                ],
                'ports': [
                    f"{node['port']}:{node['port']}",
                    f"{node['admin_port']}:{node['admin_port']}"
                ],
                'networks': [network_name]
            }

        # --- seção de Peers ---
        for org in orgs:
            peer_addresses = [f"{p['name']}.{org['name']}.{domain}:{p['port']}" for p in org['peers']]

            for idx, peer in enumerate(org['peers']):
                p_full = f"{peer['name']}.{org['name']}.{domain}"

                if len(peer_addresses) > 1:
                    bootstrap_peer = peer_addresses[1] if idx == 0 else peer_addresses[0]
                else :
                    bootstrap_peer = peer_addresses[0]

                services[p_full] = {
                    'container_name': p_full,
                    'image': f"{img_prefix}/fabric-peer:{fabric_version}",
                    'labels': {'service': 'hyperledger-fabric'},
                    'environment': [
                        "FABRIC_CFG_PATH=/etc/hyperledger/peercfg",
                        "FABRIC_LOGGING_SPEC=INFO",
                        "CORE_PEER_TLS_ENABLED=true",
                        "CORE_PEER_TLS_CERT_FILE=/etc/hyperledger/fabric/tls/server.crt",
                        "CORE_PEER_TLS_KEY_FILE=/etc/hyperledger/fabric/tls/server.key",
                        "CORE_PEER_TLS_ROOTCERT_FILE=/etc/hyperledger/fabric/tls/ca.crt",
                        f"CORE_PEER_ID={p_full}",
                        f"CORE_PEER_ADDRESS={p_full}:{peer['port']}",
                        f"CORE_PEER_LISTENADDRESS=0.0.0.0:{peer['port']}",
                        f"CORE_PEER_CHAINCODEADDRESS={p_full}:{peer['chaincode_port']}",
                        f"CORE_PEER_CHAINCODELISTENADDRESS=0.0.0.0:{peer['chaincode_port']}",
                        f"CORE_PEER_GOSSIP_EXTERNALENDPOINT={p_full}:{peer['port']}",
                        f"CORE_PEER_GOSSIP_BOOTSTRAP={bootstrap_peer}",
                        f"CORE_PEER_LOCALMSPID={org['msp_id']}",
                        "CORE_PEER_MSPCONFIGPATH=/etc/hyperledger/fabric/msp",
                    ],
                    'volumes': [
                        "/var/run/docker.sock:/host/var/run/docker.sock",
                        "./peercfg:/etc/hyperledger/peercfg", 
                        f"../organizations/peerOrganizations/{org['name']}.{domain}/peers/{p_full}:/etc/hyperledger/fabric",
                        f"{p_full}:/var/hyperledger/production",
                        f"../../builders/ccaas:/opt/hyperledger/ccaas_builder"
                    ],
                    'ports': [f"{peer['port']}:{peer['port']}"],
                    'networks': [network_name], 
                    'command': 'peer node start'
                }
    
        # composição final
        compose_dict = {
            'version': '3.7',
            'networks': {network_name: {
                'external': True,
                'name': f"{network_name}_net"}
            },
            'volumes': {name: None for name in services.keys()},
            'services': services
        }
        
        # salva o arquivo
        output_path = self.compose_dir / "compose-nodes.yaml"
        with open(output_path, 'w') as f:
            yaml.dump(compose_dict, f, sort_keys=False)
        co.successln(f"Arquivo de nós gerado: {output_path}")
        