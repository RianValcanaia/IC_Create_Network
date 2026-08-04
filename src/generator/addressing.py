# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
Fonte única de verdade para o cálculo dos IPs estáticos determinísticos de
cada CA/orderer/peer/chaincode dentro da subnet fixa da rede (network.subnet).

Usado tanto pelo ComposeGenerator (para popular 'networks.<net>.ipv4_address'
dos containers) quanto pelos geradores de scripts CLI (CryptoGenerator,
ChannelScriptGenerator, ChaincodeDeployGenerator) e por main.py
(contexto_ativo.json) — todos calculam o IP de um mesmo serviço a partir
daqui, garantindo que nunca fiquem dessincronizados.

Offsets dentro da subnet: .5+ CAs | .10+ orderers | .20+ peers | .30+ chaincodes
"""
import ipaddress

IP_OFFSET_CA = 5
IP_OFFSET_ORDERER = 10
IP_OFFSET_PEER = 20
IP_OFFSET_CHAINCODE = 30


def default_gateway(subnet):
    """Gateway padrão usado por redes macvlan quando 'gateway' não é definido no YAML:
    primeiro host válido da subnet (ex.: 10.10.20.0/24 -> 10.10.20.1)."""
    return str(ipaddress.ip_network(subnet)[1])


class StaticIPAllocator:
    def __init__(self, config):
        net = config['network_topology']['network']
        subnet = net.get('subnet')
        self._base = ipaddress.ip_network(subnet)[0] if subnet else None
        # True quando a rede tem subnet fixa (pré-condição para qualquer IP estático,
        # com ou sem macvlan — modo bridge com subnet já usa isso hoje)
        self.enabled = self._base is not None

        orgs = config['network_topology']['organizations']
        orderer_conf = config['network_topology']['orderer']

        self._ca_ip_by_org = {org['name']: self._ip(IP_OFFSET_CA + i) for i, org in enumerate(orgs)}
        self._orderer_ca_ip = self._ip(IP_OFFSET_CA + len(orgs))
        self._orderer_ip_by_name = {
            node['name']: self._ip(IP_OFFSET_ORDERER + i)
            for i, node in enumerate(orderer_conf['nodes'])
        }

        self._peer_ip_by_key = {}
        idx = 0
        for org in orgs:
            for peer in org['peers']:
                self._peer_ip_by_key[(org['name'], peer['name'])] = self._ip(IP_OFFSET_PEER + idx)
                idx += 1

    def _ip(self, offset):
        if self._base is None:
            return None
        return str(self._base + offset)

    def ca_ip(self, org_name):
        return self._ca_ip_by_org.get(org_name)

    def orderer_ca_ip(self):
        return self._orderer_ca_ip

    def orderer_ip(self, node_name):
        return self._orderer_ip_by_name.get(node_name)

    def peer_ip(self, org_name, peer_name):
        return self._peer_ip_by_key.get((org_name, peer_name))

    def chaincode_ip(self, cc_idx):
        return self._ip(IP_OFFSET_CHAINCODE + cc_idx)
