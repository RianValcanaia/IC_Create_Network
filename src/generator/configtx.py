import os
import stat
from ..utils import Colors as co

class ConfigTxGenerator:
    def __init__(self, config, paths):
        self.config = config
        self.paths = paths
        self.config_output_path = self.paths.network_dir / "configtx.yaml"
        self.script_saida = self.paths.scripts_dir / "create_artifacts.sh"

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
        orgs = self.config['network_topology']['organizations']
        channels = self.config['network_topology'].get('channels', [])

        yaml_content = "Profiles:\n"
        
        consenters_block = ""
        if ord_type == 'bft':
            consenters_block = self._build_smart_bft_consenters(domain)
        else:
            consenters_block = self._build_raft_consenters(domain)

        bootstrap_profile = None
        bootstrap_channel = None
        for cc in channels:
            if len(cc.get('participating_orgs', [])) == len(orgs):
                bootstrap_channel = cc['name']  # pega o primeiro com todas as orgs para bootstrap
                bootstrap_profile = bootstrap_channel[0].upper() + bootstrap_channel[1:] + "Profile"
                break

        if not bootstrap_channel:
            raise Exception("Nenhum canal de bootstrap encontrado. É necessário um canal que inclua todas as organizações.")
                
        yaml_content += f"  {bootstrap_profile}:\n"
        yaml_content += "    <<: *ChannelDefaults\n"
        yaml_content += "    Orderer:\n"
        yaml_content += "      <<: *OrdererDefaults\n"
        yaml_content += consenters_block
        yaml_content += "      Organizations:\n"
        yaml_content += "        - *OrdererOrg\n"
        yaml_content += "      Capabilities: *OrdererCapabilities\n"
        
        yaml_content += "    Application:\n"
        yaml_content += "      <<: *ApplicationDefaults\n"
        yaml_content += "      Organizations:\n"
        for o in orgs:
            org_name = o['name']
            yaml_content += f"        - *{org_name}\n"
        yaml_content += "      Capabilities: *ApplicationCapabilities\n"

        # perfis para outros canais
        for ch in channels:
            ch_name = ch['name']
            profile_name = ch_name[0].upper() + ch_name[1:] + "Profile"
            
            if profile_name == bootstrap_profile:
                continue  # ja criado acima

            yaml_content += f"\n  {profile_name}:\n"
            yaml_content += "    <<: *ChannelDefaults\n"
            
            yaml_content += "    Orderer:\n"
            yaml_content += "      <<: *OrdererDefaults\n"
            yaml_content += consenters_block # reusa a configuracao de consenso
            yaml_content += "      Organizations:\n"
            yaml_content += "        - *OrdererOrg\n"
            yaml_content += "      Capabilities: *OrdererCapabilities\n"

            yaml_content += "    Application:\n"
            yaml_content += "      <<: *ApplicationDefaults\n"
            yaml_content += "      Organizations:\n"
            
            participating = ch.get('participating_orgs', [])
            for p_org in participating:
                yaml_content += f"        - *{p_org}\n"
                
            yaml_content += "      Capabilities: *ApplicationCapabilities\n"

        return yaml_content

    # ------------ HELPERS (Raft/BFT/Endpoints) ------------
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
            identity_cert = f"organizations/ordererOrganizations/{domain}/orderers/{host}/msp/signcerts/cert.pem"
            server_tls = f"organizations/ordererOrganizations/{domain}/orderers/{host}/tls/server.crt"
            consenter_id = node.get('consenter_id', node.get('id', 1)) 
            content += f"          - ConsenterId: {consenter_id}\n"
            content += f"            Host: {host}\n"
            content += f"            Port: {port}\n"
            content += f"            Identity: {identity_cert}\n"
            content += f"            ClientTLSCert: {server_tls}\n"
            content += f"            ServerTLSCert: {server_tls}\n"
            content += f"            MspId: OrdererMSP\n"
        return content
    
    def _get_orderer_endpoints_list(self):
        endpoints = []
        domain = self.config['network_topology']['network']['domain']
        for node in self.config['network_topology']['orderer']['nodes']:
            endpoints.append(f"{node['name']}.{domain}:{node['port']}")
        return endpoints

    # ------------ Cria o script shell (create_artifacts.sh) ------------
    def _create_shell_script(self):
        channels = self.config['network_topology'].get('channels', [])
        orgs = self.config['network_topology']['organizations']

        bootstrap_profile = None
        bootstrap_channel = None
        for cc in channels:
            if len(cc.get('participating_orgs', [])) == len(orgs):
                bootstrap_channel = cc['name']  # pega o primeiro com todas as orgs para bootstrap, mesma logica do profile
                bootstrap_profile = bootstrap_channel[0].upper() + bootstrap_channel[1:] + "Profile"
                break

        if not bootstrap_channel:
            raise Exception("Nenhum canal de bootstrap encontrado. É necessário um canal que inclua todas as organizações.")
        
        linhas = []
        linhas.append("#!/bin/bash")
        linhas.append("set -e")
        linhas.append(f"source {self.paths.scripts_dir}/utils.sh")
        linhas.append(f"export PATH={self.paths.base_dir}/bin:$PATH")
        
        linhas.append(f"export FABRIC_CFG_PATH={self.paths.network_dir}\n")
        output = f"{self.paths.network_dir}/channel-artifacts"
        
        linhas.append("# cria Genesis Block")
        linhas.append('infoln "--- Gerando Blocos de Configuração (Fabric v3) ---"')
        linhas.append(f"mkdir -p {output}")
        
        # Genesis Block, para o canal de bootstrap
        cmd_genesis = (
            f"configtxgen -profile {bootstrap_profile} "
            f"-channelID {bootstrap_channel} "
            f"-outputBlock {output}/genesis.block"
        )
        linhas.append(f"infoln 'Gerando Genesis Block ({bootstrap_channel})...'")
        linhas.append(cmd_genesis)
        
        # blocos de configuracao para outros canais
        for ch in channels:
            ch_name = ch['name']

            if ch_name == bootstrap_channel:
                linhas.append(f"# Copiando genesis block para o canal {ch_name}")
                linhas.append(f"cp {output}/genesis.block {output}/{ch_name}.block")  # so para ter ele mesmo
                continue  # ja criado acima
            
            profile_name = ch_name[0].upper() + ch_name[1:] + "Profile"
            
            cmd_channel = (
                f"configtxgen -profile {profile_name} "
                f"-channelID {ch_name} "
                f"-outputBlock {output}/{ch_name}.block"
            )
            linhas.append(f"\n# gerando bloco para o canal {ch_name}")
            linhas.append(f"infoln 'Gerando Block: {output}/{ch_name}.block'")
            linhas.append(cmd_channel)
        
        linhas.append('\nsuccessln "Artefatos criados com sucesso!"')

        with open(self.script_saida, 'w') as f:
            f.write("\n".join(linhas))
        
        st = os.stat(self.script_saida)
        os.chmod(self.script_saida, st.st_mode | stat.S_IEXEC)
        co.successln(f"Script gerado: {self.script_saida}")