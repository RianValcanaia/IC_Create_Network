# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
Gerador dos arquivos de orquestração Docker Compose 
(compose-ca.yaml e compose-nodes.yaml). Ele define 
as imagens, variáveis de ambiente, volumes e redes 
necessárias para rodar as Autoridades Certificadoras 
(CAs), Peers e Orderers.

Rever: futuramente ver a TLS ativa para os CAs e a interface de operações.
"""
import json
import os
import yaml
import shutil
from pathlib import Path          # ← PATCH: para criar diretórios de monitoramento
from ..utils import Colors as co

class ComposeGenerator:
    def __init__(self, config, paths, machine=None):
        # inicia com a caminhos e config da rede
        self.config = config
        self.paths = paths
        self.compose_dir = self.paths.network_dir / "compose"
        # nome da máquina local para deploy distribuído (None = modo local completo)
        self.machine = machine

    def _build_extra_hosts(self):
        """
        Retorna um dict {hostname: ip} para todos os nós cujo campo `machine`
        aponta para uma máquina diferente da local. Usado para injetar entradas
        no /etc/hosts dos containers, permitindo conectividade entre máquinas
        distintas na mesma LAN.
        """
        machines = self.config['network_topology'].get('machines', {})
        domain = self.config['network_topology']['network']['domain']
        orgs = self.config['network_topology']['organizations']
        orderer_conf = self.config['network_topology']['orderer']

        extra_hosts = {}

        for node in orderer_conf['nodes']:
            node_machine = node.get('machine')
            if node_machine and node_machine != self.machine and node_machine in machines:
                extra_hosts[f"{node['name']}.{domain}"] = machines[node_machine]['ip']

        for org in orgs:
            for peer in org['peers']:
                peer_machine = peer.get('machine')
                if peer_machine and peer_machine != self.machine and peer_machine in machines:
                    extra_hosts[f"{peer['name']}.{org['name']}.{domain}"] = machines[peer_machine]['ip']

        # chaincodes CCAAS: peers precisam resolver o hostname do container chaincode
        # mesmo que ele esteja em outra máquina
        for cc in self.config['network_topology'].get('chaincodes', []):
            cc_machine = cc.get('machine')
            if cc_machine and cc_machine != self.machine and cc_machine in machines:
                # hostname usado pelo peer para conectar ao chaincode (nome do container)
                cc_hostname = f"{cc['name']}.{cc['channel']}"
                extra_hosts[cc_hostname] = machines[cc_machine]['ip']

        return extra_hosts

    # gera o arquivo que sobe todas as CAs da rede
    def generate_ca_compose(self):   
        services = {}
        orgs = self.config['network_topology']['organizations']
        orderer_conf = self.config['network_topology']['orderer']
        
        # recupera versoes e prefixos de imagem definidos no version.yaml
        img_prefix = self.config['env_versions']['images']['org_hyperledger']
        ca_version = self.config['env_versions']['versions']['fabric_ca']
        network_name = self.config['network_topology']['network']['name']

        # cria a CA de cada Org de peers
        for org in orgs:
            ca_config = org['ca']
            # em modo distribuído, inclui apenas CAs atribuídas a esta máquina
            if self.machine and ca_config.get('machine') != self.machine:
                continue

            org_name = org['name']
            service_name = ca_config['name']
            port = ca_config['port']

            # caminho interno do container onde a CA guarda seus dados
            ca_server_home = "/etc/hyperledger/fabric-ca-server"

            # define o docker para a CA
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

        # CA do orderer
        ord_ca = orderer_conf.get('ca', {})
        ord_ca_name = ord_ca.get('name', 'ca-orderer')
        ord_ca_port = ord_ca.get('port', 7054)
        ord_org_folder = "ordererOrg"

        # em modo distribuído, inclui apenas se a CA do orderer pertence a esta máquina
        if not self.machine or ord_ca.get('machine') == self.machine:
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

    # Gera o arquivo que sobe peers, orderers e prepara o peercfg
    def generate_nodes_compose(self):

        os.makedirs(self.paths.peer_cfg_dir, exist_ok=True)
        shutil.copy(self.paths.core_yaml_template, self.paths.peer_cfg_dir / "core.yaml")

        services = {}
        orgs = self.config['network_topology']['organizations']
        orderer_conf = self.config['network_topology']['orderer']
        domain = self.config['network_topology']['network']['domain']
        network_name = self.config['network_topology']['network']['name']
        img_prefix = self.config['env_versions']['images']['org_hyperledger']
        fabric_version = self.config['env_versions']['versions']['fabric']

        # extra_hosts para conectividade entre máquinas (vazio em modo local)
        extra_hosts = self._build_extra_hosts() if self.machine else {}

        # configuracao dos nos orderers
        for node in orderer_conf['nodes']:
            # em modo distribuído, inclui apenas orderers desta máquina
            if self.machine and node.get('machine') != self.machine:
                continue

            full_name = f"{node['name']}.{domain}"

            # ── PATCH: ops_port deve ter sido atribuído por assign_ops_ports() ──
            # Se não existir (deploy sem patch principal), usa 0 como fallback seguro
            ops_port = node.get('ops_port', 0)

            orderer_env = [
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
            ]

            # ── PATCH: métricas Prometheus no orderer ─────────────────────────
            if ops_port:
                orderer_env += [
                    "ORDERER_METRICS_PROVIDER=prometheus",
                    f"ORDERER_OPERATIONS_LISTENADDRESS=0.0.0.0:{ops_port}",
                    "ORDERER_OPERATIONS_TLS_ENABLED=false",
                ]

            orderer_ports = [
                f"{node['port']}:{node['port']}",
                f"{node['admin_port']}:{node['admin_port']}",
            ]

            # ── PATCH: expor ops_port do orderer ──────────────────────────────
            if ops_port:
                orderer_ports.append(f"{ops_port}:{ops_port}")

            svc = {
                'container_name': full_name,
                'image': f"{img_prefix}/fabric-orderer:{fabric_version}",
                'labels': {'service': 'hyperledger-fabric'},
                'environment': orderer_env,
                'working_dir': '/root',
                'command': 'orderer',
                'volumes': [
                    f"../organizations/ordererOrganizations/{domain}/orderers/{full_name}/msp:/var/hyperledger/orderer/msp",
                    f"../organizations/ordererOrganizations/{domain}/orderers/{full_name}/tls/:/var/hyperledger/orderer/tls",
                    f"{full_name}:/var/hyperledger/production/orderer"
                ],
                'ports': orderer_ports,
                'networks': [network_name]
            }
            if extra_hosts:
                svc['extra_hosts'] = [f"{host}:{ip}" for host, ip in extra_hosts.items()]
            services[full_name] = svc

        # configuracao dos nos peers
        for org in orgs:
            peer_addresses = [f"{p['name']}.{org['name']}.{domain}:{p['port']}" for p in org['peers']]

            for idx, peer in enumerate(org['peers']):
                # em modo distribuído, inclui apenas peers desta máquina
                if self.machine and peer.get('machine') != self.machine:
                    continue

                p_full = f"{peer['name']}.{org['name']}.{domain}"

                if len(peer_addresses) > 1:
                    bootstrap_peer = peer_addresses[(idx + 1) % len(peer_addresses)]
                else:
                    bootstrap_peer = peer_addresses[0]

                # ── PATCH: ops_port deve ter sido atribuído por assign_ops_ports() ──
                ops_port = peer.get('ops_port', 0)

                peer_env = [
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
                ]

                # ── PATCH: métricas Prometheus no peer ───────────────────────
                if ops_port:
                    peer_env += [
                        "CORE_METRICS_PROVIDER=prometheus",
                        f"CORE_OPERATIONS_LISTENADDRESS=0.0.0.0:{ops_port}",
                        "CORE_OPERATIONS_TLS_ENABLED=false",
                    ]

                peer_ports = [f"{peer['port']}:{peer['port']}"]

                # ── PATCH: expor ops_port do peer ─────────────────────────────
                if ops_port:
                    peer_ports.append(f"{ops_port}:{ops_port}")

                peer_svc = {
                    'container_name': p_full,
                    'image': f"{img_prefix}/fabric-peer:{fabric_version}",
                    'labels': {'service': 'hyperledger-fabric'},
                    'environment': peer_env,
                    'volumes': [
                        "/var/run/docker.sock:/host/var/run/docker.sock",
                        "./peercfg:/etc/hyperledger/peercfg",
                        f"../organizations/peerOrganizations/{org['name']}.{domain}/peers/{p_full}:/etc/hyperledger/fabric",
                        f"{p_full}:/var/hyperledger/production",
                        f"../../builders/ccaas:/opt/hyperledger/ccaas_builder"
                    ],
                    'ports': peer_ports,
                    'networks': [network_name],
                    'command': 'peer node start'
                }
                if extra_hosts:
                    peer_svc['extra_hosts'] = [f"{host}:{ip}" for host, ip in extra_hosts.items()]
                services[p_full] = peer_svc

        compose_dict = {
            'version': '3.7',
            'networks': {network_name: {
                'external': True,
                'name': f"{network_name}_net"}
            },
            'volumes': {name: None for name in services.keys()},
            'services': services
        }

        output_path = self.compose_dir / "compose-nodes.yaml"
        with open(output_path, 'w') as f:
            yaml.dump(compose_dict, f, sort_keys=False)
        co.successln(f"Arquivo de nós gerado: {output_path}")

        # ── PATCH: gerar prometheus.yml automaticamente após o compose ────────
        self._generate_prometheus_config()

    def _generate_prometheus_config(self):
        """
        Gera monitoring/prometheus.yml dinamicamente com os ops_ports
        atribuídos por assign_ops_ports(). Chamado ao final de generate_nodes_compose().
        """
        domain = self.config['network_topology']['network']['domain']
        network_name = self.config['network_topology']['network']['name']
        orgs = self.config['network_topology']['organizations']
        orderer_conf = self.config['network_topology']['orderer']

        peer_targets = []
        for org in orgs:
            org_name = org['name']
            for peer in org['peers']:
                ops_port = peer.get('ops_port')
                if ops_port:
                    peer_targets.append(f"{peer['name']}.{org_name}.{domain}:{ops_port}")

        orderer_targets = []
        for node in orderer_conf.get('nodes', []):
            ops_port = node.get('ops_port')
            if ops_port:
                orderer_targets.append(f"{node['name']}.{domain}:{ops_port}")

        if not peer_targets and not orderer_targets:
            co.infoln("Nenhum ops_port encontrado — prometheus.yml não gerado. "
                      "Verifique se assign_ops_ports() foi chamado antes do ComposeGenerator.")
            return

        prometheus_config = {
            'global': {
                'scrape_interval': '5s',
                'evaluation_interval': '5s',
            },
            'scrape_configs': [
                {
                    'job_name': 'fabric-peers',
                    'static_configs': [{
                        'targets': peer_targets,
                        'labels': {'network': network_name, 'role': 'peer'}
                    }]
                },
                {
                    'job_name': 'fabric-orderers',
                    'static_configs': [{
                        'targets': orderer_targets,
                        'labels': {'network': network_name, 'role': 'orderer'}
                    }]
                },
            ]
        }

        # salva em IC_Create_Network/monitoring/prometheus.yml
        monitoring_dir = self.paths.network_dir.parent / "monitoring"
        monitoring_dir.mkdir(parents=True, exist_ok=True)
        output_path = monitoring_dir / "prometheus.yml"

        with open(output_path, 'w') as f:
            yaml.dump(prometheus_config, f, default_flow_style=False, sort_keys=False)

        co.successln(f"prometheus.yml gerado em: {output_path}")
        co.infoln(f"  Peers:    {peer_targets}")
        co.infoln(f"  Orderers: {orderer_targets}")

    # gera os arquivos json de perfil de conexao (CCP) usados pelos SDKs como node.js
    def generate_connection_profiles(self):
        orgs = self.config['network_topology']['organizations']
        domain = self.config['network_topology']['network']['domain']
        network_name = self.config['network_topology']['network']['name']
        orgs_root = self.paths.network_dir / "organizations"

        for org in orgs:
            org_name = org['name']
            msp_id = org['msp_id']
            
            ccp = {
                "name": f"{network_name}-{org_name}",
                "version": "1.0.0",
                "client": {"organization": org_name},
                "organizations": {
                    org_name: {
                        "mspid": msp_id,
                        "peers": [f"{p['name']}.{org_name}.{domain}" for p in org['peers']],
                        "certificateAuthorities": [org['ca']['name']]
                    }
                },
                "peers": {},
                "certificateAuthorities": {}
            }

            for peer in org['peers']:
                p_full = f"{peer['name']}.{org_name}.{domain}"
                tls_cert_path = (orgs_root / "peerOrganizations" / f"{org_name}.{domain}" / "peers" / p_full / "tls" / "ca.crt").resolve()
                ccp["peers"][p_full] = {
                    "url": f"grpcs://{p_full}:{peer['port']}",
                    "tlsCACerts": {"path": str(tls_cert_path)},
                    "grpcOptions": {"ssl-target-name-override": p_full}
                }

            ca_name = org['ca']['name']
            ca_cert_path = f"../organizations/peerOrganizations/{org_name}.{domain}/msp/cacerts/localhost-{org['ca']['port']}-{ca_name}.pem"
            
            ccp["certificateAuthorities"][ca_name] = {
                "url": f"https://localhost:{org['ca']['port']}",
                "caName": ca_name,
                "tlsCACerts": {"path": ca_cert_path},
                "httpOptions": {"verify": False}
            }

            output_file = self.paths.peer_cfg_dir / f"connection-{org_name.lower()}.json"
            with open(output_file, 'w') as f:
                json.dump(ccp, f, indent=4)
            
            co.successln(f"Connection Profile gerado: {output_file}")