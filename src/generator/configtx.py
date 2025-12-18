import os
import stat
from ..utils import Colors as co

class ConfigTxGenerator:
    def __init__(self, config, paths):
        self.config = config
        self.paths = paths
        self.config_output_path = self.paths.network_dir / "configtx.yaml"
        self.script_saida = self.paths.scripts_dir / "03_create_artifacts.sh"

    def generate(self):        
        # gera as secoes do configtx.yaml
        organizations_section = self._build_organizations_section()
        capabilities_section = self._build_capabilities_section()
        application_section = self._build_application_section()
        orderer_section = self._build_orderer_section()
        channel_section = self._build_channel_section()
        profiles_section = self._build_profiles_section()

        # monta o conteúdo final
        content = (
            f"{organizations_section}"
            f"{capabilities_section}\n"
            f"{application_section}\n"
            f"{orderer_section}"
            f"{channel_section}\n"
            f"{profiles_section}\n"
        )

        # salva o arquivo
        with open(self.config_output_path, 'w') as f:
            f.write(content)
        
        co.successln(f"Arquivo configtx.yaml gerado em: {self.config_output_path}")

        # gera o script shell
        self._create_shell_script()

    def _build_organizations_section(self):
        domain = self.config['network_topology']['network']['domain']
        orgs_yaml = "Organizations:\n"

        # criando orderer Org
        ord_msp_dir = f"organizations/ordererOrganizations/{domain}/msp"
        orderer_endpoints = self._get_orderer_endpoints_list()
        
        orgs_yaml += "  - &OrdererOrg\n"
        orgs_yaml += "    Name: OrdererOrg\n"
        orgs_yaml += "    ID: OrdererMSP\n"
        orgs_yaml += f"    MSPDir: {ord_msp_dir}\n"
        orgs_yaml += "    Policies:\n"
        orgs_yaml += "      Readers:\n        Type: Signature\n        Rule: \"OR('OrdererMSP.member')\"\n"
        orgs_yaml += "      Writers:\n        Type: Signature\n        Rule: \"OR('OrdererMSP.member')\"\n"
        orgs_yaml += "      Admins:\n        Type: Signature\n        Rule: \"OR('OrdererMSP.admin')\"\n"
        orgs_yaml += "    OrdererEndpoints:\n"
        for ep in orderer_endpoints:
            orgs_yaml += f"      - {ep}\n"

        # adicionando as orgs
        for org in self.config['network_topology']['organizations']:
            org_name = org['name']
            msp_id = org['msp_id']
            msp_dir = f"organizations/peerOrganizations/{org_name}.{domain}/msp"

            orgs_yaml += f"  - &{org_name}\n" 
            orgs_yaml += f"    Name: {msp_id}\n"
            orgs_yaml += f"    ID: {msp_id}\n"
            orgs_yaml += f"    MSPDir: {msp_dir}\n"
            orgs_yaml += "    Policies:\n"
            orgs_yaml += f"      Readers:\n        Type: Signature\n        Rule: \"OR('{msp_id}.admin', '{msp_id}.peer', '{msp_id}.client')\"\n"
            orgs_yaml += f"      Writers:\n        Type: Signature\n        Rule: \"OR('{msp_id}.admin', '{msp_id}.client')\"\n"
            orgs_yaml += f"      Admins:\n        Type: Signature\n        Rule: \"OR('{msp_id}.admin')\"\n"
            orgs_yaml += f"      Endorsement:\n        Type: Signature\n        Rule: \"OR('{msp_id}.peer')\"\n"

        return orgs_yaml

    def _build_capabilities_section(self):
        return """
Capabilities:
  Channel: &ChannelCapabilities
    V2_0: true
  Orderer: &OrdererCapabilities
    V2_0: true
  Application: &ApplicationCapabilities
    V2_5: true"""

    def _build_application_section(self):
        return """
Application: &ApplicationDefaults
  Organizations:
  Policies:
    Readers:
      Type: ImplicitMeta
      Rule: "ANY Readers"
    Writers:
      Type: ImplicitMeta
      Rule: "ANY Writers"
    Admins:
      Type: ImplicitMeta
      Rule: "MAJORITY Admins"
    LifecycleEndorsement:
      Type: ImplicitMeta
      Rule: "MAJORITY Endorsement"
    Endorsement:
      Type: ImplicitMeta
      Rule: "MAJORITY Endorsement"
  Capabilities:
    <<: *ApplicationCapabilities
"""

    # ESSA FUNCAO TEM COISAS SOBRE O RAFT E O BFT QUE NAO SEI COMO FAZER POR ENQUANTO, ACHO QUE NAO VAI SER NECESSARIO AGORA, RIAN DO FUTURO FIQUE MAIS INTELIGENTE PARA SABER COMO FAZER
    def _build_orderer_section(self):
        ord_conf = self.config['network_topology']['orderer']
        ord_type = ord_conf.get('type', 'etcdraft')
        
        # Defaults
        batch_timeout = ord_conf.get('batch_timeout', '2s')
        max_msg = ord_conf.get('batch_size', {}).get('max_message_count', 10)
        abs_max_bytes = ord_conf.get('batch_size', {}).get('absolute_max_bytes', '99 MB')
        pref_max_bytes = ord_conf.get('batch_size', {}).get('preferred_max_bytes', '512 KB')
        
        yaml_content = "Orderer: &OrdererDefaults\n"
        yaml_content += "  Addresses:\n"
        for ep in self._get_orderer_endpoints_list():
            yaml_content += f"    - {ep}\n"
            
        yaml_content += f"  BatchTimeout: {batch_timeout}\n"
        yaml_content += "  BatchSize:\n"
        yaml_content += f"    MaxMessageCount: {max_msg}\n"
        yaml_content += f"    AbsoluteMaxBytes: {abs_max_bytes}\n"
        yaml_content += f"    PreferredMaxBytes: {pref_max_bytes}\n"
        yaml_content += "    MaxChannels: 0\n"   # se 0 implica ilimitado, ver futuramente de usar no network.yaml

        # ver como fazer futuramente, ainda não é um problema 
        if ord_type == 'bft':
            # aqui vai a definicao do consenterMapping, por enquanto vou usar somente o raft, futuramente vejo isso, pois tenho que estudar mais o bft antes de implementar, segue exemplo de como talvez seja
            # # ConsenterMapping contains the definition of consenter identity, endpoints, and crypto material.
            # # The ConsenterMapping is used in the BFT consensus protocol, and should include enough servers to ensure
            # # fault-tolerance; In BFT this number is at least 3*F+1, where F is the number of potential failures.
            # # In BFT it is highly recommended that the addresses for delivery & broadcast (the OrdererEndpoints item in the
            # # org definition) map 1:1 to the Orderer/ConsenterMapping (for cluster consensus). That is, every consenter should
            # # be represented by a delivery endpoint. Note that in BFT (V3) global Orderer/Addresses are no longer supported.
            # ConsenterMapping:
            #     - ID: 1
            #     Host: bft0.example.com
            #     Port: 7050
            #     MSPID: OrdererOrg1
            #     Identity: /path/to/identity
            #     ClientTLSCert: path/to/ClientTLSCert0
            #     ServerTLSCert: path/to/ServerTLSCert0
            #     - ID: 2
            #     Host: bft1.example.com
            #     Port: 7050
            #     MSPID: OrdererOrg2
            #     Identity: /path/to/identity
            #     ClientTLSCert: path/to/ClientTLSCert1
            #     ServerTLSCert: path/to/ServerTLSCert1
            #     - ID: 3
            #     Host: bft2.example.com
            #     Port: 7050
            #     MSPID: OrdererOrg3
            #     Identity: /path/to/identity
            #     ClientTLSCert: path/to/ClientTLSCert2
            #     ServerTLSCert: path/to/ServerTLSCert2
            #     - ID: 4
            #     Host: bft3.example.com
            #     Port: 7050
            #     MSPID: OrdererOrg4
            #     Identity: /path/to/identity
            #     ClientTLSCert: path/to/ClientTLSCert3
            #     ServerTLSCert: path/to/ServerTLSCert3
            pass
        else:
            # ver se é necessário, acho que por enquanto não:
            # EtcdRaft:
            # # The set of Raft replicas for this network. For the etcd/raft-based
            # # implementation, we expect every replica to also be an OSN. Therefore,
            # # a subset of the host:port items enumerated in this list should be
            # # replicated under the Orderer.Addresses key above.
            # Consenters:
            # - Host: raft0.example.com
            #     Port: 7050
            #     ClientTLSCert: path/to/ClientTLSCert0
            #     ServerTLSCert: path/to/ServerTLSCert0
            # - Host: raft1.example.com
            #     Port: 7050
            #     ClientTLSCert: path/to/ClientTLSCert1
            #     ServerTLSCert: path/to/ServerTLSCert1
            # - Host: raft2.example.com
            #     Port: 7050
            #     ClientTLSCert: path/to/ClientTLSCert2
            #     ServerTLSCert: path/to/ServerTLSCert2
            pass
        
        # ver se é necessario usar options, por enquanto não
        # # Options to be specified for all the etcd/raft nodes. The values here
        # # are the defaults for all new channels and can be modified on a
        # # per-channel basis via configuration updates.
        # Options:
        # # TickInterval is the time interval between two Node.Tick invocations.
        # TickInterval: 500ms

        # # ElectionTick is the number of Node.Tick invocations that must pass
        # # between elections. That is, if a follower does not receive any
        # # message from the leader of current term before ElectionTick has
        # # elapsed, it will become candidate and start an election.
        # # ElectionTick must be greater than HeartbeatTick.
        # ElectionTick: 10

        # # HeartbeatTick is the number of Node.Tick invocations that must
        # # pass between heartbeats. That is, a leader sends heartbeat
        # # messages to maintain its leadership every HeartbeatTick ticks.
        # HeartbeatTick: 1

        # # MaxInflightBlocks limits the max number of in-flight append messages
        # # during optimistic replication phase.
        # MaxInflightBlocks: 5

        # # SnapshotIntervalSize defines number of bytes per which a snapshot is taken
        # SnapshotIntervalSize: 16 MB

        yaml_content += "  Organizations:\n"
        yaml_content += "  Policies:\n"
        yaml_content += "    Readers:\n      Type: ImplicitMeta\n      Rule: \"ANY Readers\"\n"
        yaml_content += "    Writers:\n      Type: ImplicitMeta\n      Rule: \"ANY Writers\"\n"
        yaml_content += "    Admins:\n      Type: ImplicitMeta\n      Rule: \"MAJORITY Admins\"\n"
        yaml_content += "    BlockValidation:\n      Type: ImplicitMeta\n      Rule: \"ANY Writers\"\n"
        yaml_content += "  Capabilities:\n    <<: *OrdererCapabilities\n"
        
        return yaml_content

    def _build_channel_section(self):
        return """
Channel: &ChannelDefaults
  Policies:
    Readers:
      Type: ImplicitMeta
      Rule: "ANY Readers"
    Writers:
      Type: ImplicitMeta
      Rule: "ANY Writers"
    Admins:
      Type: ImplicitMeta
      Rule: "MAJORITY Admins"
  Capabilities:
    <<: *ChannelCapabilities
"""

    def _build_profiles_section(self):
        domain = self.config['network_topology']['network']['domain']
        ord_conf = self.config['network_topology']['orderer']
        ord_type = ord_conf.get('type', 'etcdraft').lower()

        yaml_content = "Profiles:\n"
        if ord_type == 'bft':
            yaml_content += f"  ChannelUsingBFT:\n"
        else:
            yaml_content += f"  ChannelUsingRaft:\n"
        yaml_content += "    <<: *ChannelDefaults\n"
        
        # orderer config do profile
        yaml_content += "    Orderer:\n"
        yaml_content += "      <<: *OrdererDefaults\n"
        yaml_content += f"      OrdererType: {ord_type}\n"
        
        # lida com os consensos
        if ord_type == 'bft':
            yaml_content += self._build_smart_bft_consenters(domain)
        else:
            yaml_content += self._build_raft_consenters(domain)
            
        yaml_content += "      Organizations:\n"
        yaml_content += "        - *OrdererOrg\n"
        yaml_content += "      Capabilities: *OrdererCapabilities\n"
        
        # adicione aplications config do profile
        yaml_content += "    Application:\n"
        yaml_content += "      <<: *ApplicationDefaults\n"
        yaml_content += "      Organizations:\n"
        
        for org in self.config['network_topology']['organizations']:
            org_name = org['name']
            yaml_content += f"        - *{org_name}\n"
            
        yaml_content += "      Capabilities: *ApplicationCapabilities\n"
        
        # consortiums 
        yaml_content += "    Consortiums:\n"
        yaml_content += "      SampleConsortium:\n"
        yaml_content += "        Organizations:\n"
        for org in self.config['network_topology']['organizations']:
            org_name = org['name']
            yaml_content += f"          - *{org_name}\n"

        return yaml_content

    # ------------- Helpers para Consenso -------------
    def _build_raft_consenters(self, domain):
        content = "      EtcdRaft:\n"
        content += "        Consenters:\n"
        for node in self.config['network_topology']['orderer']['nodes']:
            host = f"{node['name']}.{domain}"
            port = node['port']
            server_tls = f"organizations/ordererOrganizations/{domain}/orderers/{host}/tls/server.crt"
            
            content += f"          - Host: {host}\n"
            content += f"            Port: {port}\n"
            content += f"            ClientTLSCert: {server_tls}\n"
            content += f"            ServerTLSCert: {server_tls}\n"
        return content

    def _build_smart_bft_consenters(self, domain):
        content = "      SmartBFT:\n"
        content += "        Consenters:\n"
        for node in self.config['network_topology']['orderer']['nodes']:
            host = f"{node['name']}.{domain}"
            port = node['port']
            # para BFT, precisa do certificado de identidade (Enrollment Cert) além do TLS
            identity_cert = f"organizations/ordererOrganizations/{domain}/orderers/{host}/msp/signcerts/cert.pem"
            server_tls = f"organizations/ordererOrganizations/{domain}/orderers/{host}/tls/server.crt"
            
            # Consenter ID geralmente é o próprio ID do MSP se for 1 node por org, 
            # ou o ID do node. Vamos usar o ID do node para garantir unicidade local.
            consenter_id = node.get('consenter_id', node.get('id', 1)) 

            content += f"          - ConsenterId: {consenter_id}\n"
            content += f"            Host: {host}\n"
            content += f"            Port: {port}\n"
            content += f"            Identity: {identity_cert}\n"
            content += f"            ClientTLSCert: {server_tls}\n"
            content += f"            ServerTLSCert: {server_tls}\n"
            content += f"            MspId: OrdererMSP\n" # Assumindo unico MSP para orderers por enquanto
        return content
    
    # ------------- Funções Auxiliares --------------
    def _get_orderer_endpoints_list(self):
        endpoints = []
        domain = self.config['network_topology']['network']['domain']
        for node in self.config['network_topology']['orderer']['nodes']:
            endpoints.append(f"{node['name']}.{domain}:{node['port']}")
        return endpoints

    # ver isso ainda, como tem mais de um canal precisa gerar artefatos para cada um?
    def _create_shell_script(self):
        channels = self.config['network_topology']['network'].get('channels', {})

        linhas = []
        linhas.append("#!/bin/bash\n")
        linhas.append("set -e")
        linhas.append(f"source {self.paths.scripts_dir}/utils.sh\n")
        linhas.append(f"export PATH={self.paths.base_dir}/bin:$PATH")
        
        # Configura onde buscar o configtx.yaml
        linhas.append(f"export FABRIC_CFG_PATH={self.paths.network_dir}\n")
        
        output = f"{self.paths.network_dir}/channel-artifacts"
        
        linhas.append('infoln "--- Gerando Bloco Gênese ---"\n')
        linhas.append(f"mkdir -p {self.paths.network_dir}/channel-artifacts")
        
        cmd = (
            f"configtxgen -profile GenesisProfile "
            f"-channelID system-channel "
            f"-outputBlock {output}/genesis.block"
        )
        
        linhas.append(f"infoln 'Gerando: {output}/genesis.block'")
        linhas.append(cmd)
        for ch in channels:
            cmd = (
                f"configtxgen -profile GenesisProfile "
                f"-channelID {ch['name']} "
                f"-outputBlock {output}/{ch['name']}.tx"
            )
            linhas.append(f"infoln 'Gerando: {output}/{ch['name']}.tx'")
            linhas.append(cmd)
        
        linhas.append('successln "Bloco Gênese criado com sucesso!"')

        with open(self.script_saida, 'w') as f:
            f.write("\n".join(linhas))
        
        st = os.stat(self.script_saida)
        os.chmod(self.script_saida, st.st_mode | stat.S_IEXEC)
        co.successln(f"Script gerado: {self.script_saida}")