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
from ..utils import Colors as co
from .addressing import StaticIPAllocator

class ComposeGenerator:
    def __init__(self, config, paths, machine=None):
        # inicia com a caminhos e config da rede
        self.config = config
        self.paths = paths
        self.compose_dir = self.paths.network_dir / "compose"

        # nome da máquina local para deploy distribuído (None = modo local completo,
        # gera todos os serviços; com valor, filtra só o que pertence a essa máquina)
        self.machine = machine

        # isolamento entre redes coexistentes na mesma máquina:
        # - folder: sufixo p/ nomes de container que não são únicos por si (CAs)
        # - subnet: sub-rede fixa da docker network -> IPs estáticos por serviço
        net = self.config['network_topology']['network']
        self.folder = net.get('folder', net['name'])
        self.subnet = net.get('subnet')

        # macvlan: containers ganham o IP estático diretamente na subnet real do host
        # (via interface 'parent'), sem publish/NAT -> 'ports' é omitido dos serviços
        self.macvlan = bool(net.get('macvlan'))
        self.allocator = StaticIPAllocator(config)

    def _service_networks(self, network_name, ip):
        """Bloco 'networks' do serviço: com subnet vira dict com ipv4_address fixo"""
        if ip:
            return {network_name: {'ipv4_address': ip}}
        return [network_name]

    def _ports(self, *port_pairs):
        """Bloco 'ports' do serviço: omitido em modo macvlan, já que o container
        tem IP próprio na subnet real e não precisa de publish/NAT do host."""
        if self.macvlan:
            return {}
        return {'ports': [f"{p}:{p}" for p in port_pairs]}

    def _build_extra_hosts(self):
        """
        Retorna um dict {hostname: ip} para todos os nós cujo campo `machine`
        aponta para uma máquina diferente da local. Usado para injetar entradas
        no /etc/hosts dos containers, permitindo conectividade entre máquinas
        distintas na mesma LAN (deploy distribuído via --machine).
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

        for cc in self.config['network_topology'].get('chaincodes', []):
            cc_machine = cc.get('machine')
            if cc_machine and cc_machine != self.machine and cc_machine in machines:
                cc_hostname = f"{cc['name']}.{cc['channel']}-{self.folder}"
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
        for ca_idx, org in enumerate(orgs):
            ca_config = org['ca']
            # em modo distribuído, inclui apenas CAs atribuídas a esta máquina (o índice ca_idx é preservado sobre a lista completa para manter o IP estático determinístico mesmo quando filtrado)
            if self.machine and ca_config.get('machine') != self.machine:
                continue

            org_name = org['name']
            service_name = ca_config['name']
            container_name = f"{service_name}-{self.folder}"
            port = ca_config['port']

            # caminho interno do container onde a CA guarda seus dados
            ca_server_home = "/etc/hyperledger/fabric-ca-server"

            # define o docker para a CA
            services[service_name] = {
                'image': f"{img_prefix}/fabric-ca:{ca_version}",
                'labels': {'service': "hyperledger-fabric-ca"},
                'container_name': container_name,
                'environment': [
                    f"FABRIC_CA_HOME={ca_server_home}",
                    f"FABRIC_CA_SERVER_CA_NAME={service_name}",
                    "FABRIC_CA_SERVER_TLS_ENABLED=false",
                    f"FABRIC_CA_SERVER_PORT={port}",
                    "FABRIC_CA_SERVER_CSR_CN=" + service_name,
                    "FABRIC_CA_SERVER_CSR_HOSTS=0.0.0.0",
                ],
                **self._ports(port),
                'command': "sh -c 'fabric-ca-server start -b admin:adminpw -d'",
                'volumes': [
                    f"../organizations/fabric-ca/{org_name}:{ca_server_home}"
                ],
                'networks': self._service_networks(network_name, self.allocator.ca_ip(org_name))
            }

        # CA do orderer
        # Tenta pegar config do yaml ou usa defaults
        ord_ca = orderer_conf.get('ca', {})
        ord_ca_name = ord_ca.get('name', 'ca-orderer')
        ord_ca_port = ord_ca.get('port', 7054)
        ord_org_folder = "ordererOrg"

        # em modo distribuído, inclui apenas se a CA do orderer pertence a esta máquina
        if not self.machine or ord_ca.get('machine') == self.machine:
            services[ord_ca_name] = {
                'image': f"{img_prefix}/fabric-ca:{ca_version}",
                'labels': {'service': "hyperledger-fabric-ca"},
                'container_name': f"{ord_ca_name}-{self.folder}",
                'environment': [
                    f"FABRIC_CA_HOME=/etc/hyperledger/fabric-ca-server",
                    f"FABRIC_CA_SERVER_CA_NAME={ord_ca_name}",
                    "FABRIC_CA_SERVER_TLS_ENABLED=false",
                    f"FABRIC_CA_SERVER_PORT={ord_ca_port}",
                    f"FABRIC_CA_SERVER_CSR_CN={ord_ca_name}",
                    "FABRIC_CA_SERVER_CSR_HOSTS=0.0.0.0",
                ],
                **self._ports(ord_ca_port),
                'command': "sh -c 'fabric-ca-server start -b admin:adminpw -d'",
                'volumes': [
                    f"../organizations/fabric-ca/{ord_org_folder}:/etc/hyperledger/fabric-ca-server"
                ],
                'networks': self._service_networks(network_name, self.allocator.orderer_ca_ip())
            }

        # estrutura final do compose para as CAs
        compose_content = {
            'networks': {
                network_name: {
                    'external': True,
                    'name': f"{network_name}_net"
                }
            },
            'services': services
        }

        # garante que o diretório de saída existe
        self.compose_dir.mkdir(parents=True, exist_ok=True)
        filename = f"compose-ca-{self.machine}.yaml" if self.machine else "compose-ca.yaml"
        output_path = self.compose_dir / filename

        # salva o arquivo YAML
        with open(output_path, 'w') as f:
            yaml.dump(compose_content, f, sort_keys=False)

        co.successln(f"Arquivo gerado: {output_path}")
        return output_path

    # Gera o arquivo que sobe peers, orderers e prepara o peercfg
    def generate_nodes_compose(self):

        # garante que o arquivo core.yaml padrao esteja na pasta de configuracao
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
        for ord_idx, node in enumerate(orderer_conf['nodes']):
            # em modo distribuído, inclui apenas orderers desta máquina
            # (ord_idx preservado sobre a lista completa para manter o IP estático)
            if self.machine and node.get('machine') != self.machine:
                continue

            full_name = f"{node['name']}.{domain}"
            orderer_svc = {
                'container_name': full_name,
                'image': f"{img_prefix}/fabric-orderer:{fabric_version}",
                'labels': {'service': 'hyperledger-fabric'},
                'environment': [
                    "FABRIC_LOGGING_SPEC=INFO",
                    "ORDERER_GENERAL_LISTENADDRESS=0.0.0.0",
                    f"ORDERER_GENERAL_LISTENPORT={node['port']}",
                    "ORDERER_GENERAL_LOCALMSPID=OrdererMSP",
                    "ORDERER_GENERAL_LOCALMSPDIR=/var/hyperledger/orderer/msp",
                    "ORDERER_GENERAL_BOOTSTRAPMETHOD=none", # fabric v3 nao usa system channel, é preciso setar um canal para bootstrap
                    "ORDERER_CHANNELPARTICIPATION_ENABLED=true",  # ativa a nova API de participacam em canais
                    "ORDERER_GENERAL_TLS_ENABLED=true",  # obrigatorio
                    "ORDERER_GENERAL_TLS_PRIVATEKEY=/var/hyperledger/orderer/tls/server.key",
                    "ORDERER_GENERAL_TLS_CERTIFICATE=/var/hyperledger/orderer/tls/server.crt",
                    "ORDERER_GENERAL_TLS_ROOTCAS=[/var/hyperledger/orderer/tls/ca.crt]",
                    "ORDERER_ADMIN_TLS_ENABLED=true",
                    "ORDERER_ADMIN_TLS_CERTIFICATE=/var/hyperledger/orderer/tls/server.crt",
                    "ORDERER_ADMIN_TLS_PRIVATEKEY=/var/hyperledger/orderer/tls/server.key",
                    "ORDERER_ADMIN_TLS_ROOTCAS=[/var/hyperledger/orderer/tls/ca.crt]",
                    f"ORDERER_ADMIN_TLS_CLIENTROOTCAS=[/var/hyperledger/orderer/tls/ca.crt]",
                    f"ORDERER_ADMIN_LISTENADDRESS=0.0.0.0:{node['admin_port']}",  # porta para o comando osadmin
                ],
                'working_dir': '/root',
                'command': 'orderer',
                'volumes': [
                    # mapeia os certificados gerados pelo cryptogen para dentro do container
                    f"../organizations/ordererOrganizations/{domain}/orderers/{full_name}/msp:/var/hyperledger/orderer/msp",
                    f"../organizations/ordererOrganizations/{domain}/orderers/{full_name}/tls/:/var/hyperledger/orderer/tls",
                    f"{full_name}:/var/hyperledger/production/orderer"  # dados do ledger persistente
                ],
                **self._ports(node['port'], node['admin_port']),
                'networks': self._service_networks(network_name, self.allocator.orderer_ip(node['name']))
            }
            if extra_hosts:
                orderer_svc['extra_hosts'] = [f"{host}:{ip}" for host, ip in extra_hosts.items()]
            services[full_name] = orderer_svc

        # configuracao dos nos peers
        peer_global_idx = 0
        for org in orgs:
            # lista de enderecos de todos os peers desta organizacao
            peer_addresses = [f"{p['name']}.{org['name']}.{domain}:{p['port']}" for p in org['peers']]

            for idx, peer in enumerate(org['peers']):
                # índice global preservado sobre a lista completa (mesmo quando
                # filtrado por máquina) para manter o IP estático determinístico
                this_peer_idx = peer_global_idx
                peer_global_idx += 1

                # em modo distribuído, inclui apenas peers desta máquina
                if self.machine and peer.get('machine') != self.machine:
                    continue

                p_full = f"{peer['name']}.{org['name']}.{domain}"

                # configura o gossip bootstrap, um peer aponta para o proximo em "anel"
                if len(peer_addresses) > 1:
                    bootstrap_peer = peer_addresses[(idx + 1) % len(peer_addresses)]
                else:
                    bootstrap_peer = peer_addresses[0]

                peer_svc = {
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
                        f"CORE_PEER_GOSSIP_BOOTSTRAP={bootstrap_peer}",  # peer vizinho para sincronizacao inicial
                        f"CORE_PEER_LOCALMSPID={org['msp_id']}",
                        "CORE_PEER_MSPCONFIGPATH=/etc/hyperledger/fabric/msp",
                    ],
                    'volumes': [
                        "/var/run/docker.sock:/host/var/run/docker.sock",  # permite que o peer gerencie containers do chaincode
                        "./peercfg:/etc/hyperledger/peercfg", 
                        f"../organizations/peerOrganizations/{org['name']}.{domain}/peers/{p_full}:/etc/hyperledger/fabric",
                        f"{p_full}:/var/hyperledger/production",
                        f"../../../builders/ccaas:/opt/hyperledger/ccaas_builder"  # builder necessario para o modelo CCAAS (compose fica em network/<rede>/compose)
                    ],
                    **self._ports(peer['port']),
                    'networks': self._service_networks(network_name, self.allocator.peer_ip(org['name'], peer['name'])),
                    'command': 'peer node start'
                }
                if extra_hosts:
                    peer_svc['extra_hosts'] = [f"{host}:{ip}" for host, ip in extra_hosts.items()]
                services[p_full] = peer_svc

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
        filename = f"compose-nodes-{self.machine}.yaml" if self.machine else "compose-nodes.yaml"
        output_path = self.compose_dir / filename
        with open(output_path, 'w') as f:
            yaml.dump(compose_dict, f, sort_keys=False)
        co.successln(f"Arquivo de nós gerado: {output_path}")
        return output_path
        
    # gera os arquivos json de perfil de conecao (CCP) usados pelos SDKs como node.js
    def generate_connection_profiles(self):
        orgs = self.config['network_topology']['organizations']
        domain = self.config['network_topology']['network']['domain']
        network_name = self.config['network_topology']['network']['name']
        orgs_root = self.paths.network_dir / "organizations"

        for org in orgs:
            org_name = org['name']
            msp_id = org['msp_id']
            
            # estrutura base do Common Connection Profile
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

            # preenche os detalhes de cada peer para o SDK saber onde se conectar
            for peer in org['peers']:
                p_full = f"{peer['name']}.{org_name}.{domain}"

                tls_cert_path = (orgs_root / "peerOrganizations" / f"{org_name}.{domain}" / "peers" / p_full / "tls" / "ca.crt").resolve()
                ccp["peers"][p_full] = {
                    "url": f"grpcs://{p_full}:{peer['port']}", 
                    "tlsCACerts": {"path": str(tls_cert_path)},
                    "grpcOptions": {"ssl-target-name-override": p_full}
                }

            # apreenche os detalhes da CA no perfil de conexao
            # (host da CA no nome do arquivo/URL: IP real da subnet em modo macvlan,
            # 'localhost' no modo padrão - precisa bater com o host usado no enroll)
            ca_name = org['ca']['name']
            ca_host = self.allocator.ca_ip(org_name) if self.macvlan else "localhost"
            ca_cert_path = f"../organizations/peerOrganizations/{org_name}.{domain}/msp/cacerts/{ca_host}-{org['ca']['port']}-{ca_name}.pem"

            ccp["certificateAuthorities"][ca_name] = {
                "url": f"https://{ca_host}:{org['ca']['port']}",
                "caName": ca_name,
                "tlsCACerts": {"path": ca_cert_path},
                "httpOptions": {"verify": False}
            }


            # salva o arquivo JSON
            output_file = self.paths.peer_cfg_dir / f"connection-{org_name.lower()}.json"
            with open(output_file, 'w') as f:
                json.dump(ccp, f, indent=4)
            
            co.successln(f"Connection Profile gerado: {output_file}")