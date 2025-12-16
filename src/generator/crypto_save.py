import os
import stat
from ..utils import Colors as co

class CryptoGenerator:
    def __init__(self, config, paths):
        self.config = config
        self.paths = paths
        
        self.script_saida = self.paths.scripts_dir / "register_enroll.sh"

    def generate(self):
        orgs = self.config['network_topology']['organizations']
        orderer_conf = self.config['network_topology']['orderer']
        domain = self.config['network_topology']['network']['domain']
        
        # cabeçalho do script
        linhas = []
        linhas.append("#!/bin/bash")
        linhas.append("set -e") # Para o script imediatamente se der erro
        linhas.append(f"source {self.paths.scripts_dir}/utils.sh")
        
        # Garante que os binários (fabric-ca-client) estejam no PATH
        linhas.append(f"export PATH={self.paths.base_dir}/bin:$PATH")
        
        linhas.append('infoln "--- Iniciando Geração de Identidades ---"')

        # ------------------ Processar Organizações ------------------
        for org in orgs:
            org_name = org['name']
            ca_port = org['ca']['port']
            ca_name = org['ca']['name']
            
            # Caminho base: network/organizations/peerOrganizations/org1.exemplo.com
            org_base_dir = f"{self.paths.network_dir}/organizations/peerOrganizations/{org_name}.{domain}"
            
            # Onde o cliente da CA salva as credenciais temporárias do admin
            ca_client_home = f"{self.paths.network_dir}/organizations/fabric-ca/{org_name}/client"

            linhas.append(f"infoln 'Processando Organização: {org_name}'")
            linhas.append(f"mkdir -p {org_base_dir}")
            
            # enroll do admin da CA
            linhas.append(f"mkdir -p {ca_client_home}")
            linhas.append(f"export FABRIC_CA_CLIENT_HOME={ca_client_home}")
            
            linhas.append(f"infoln '-> Enroll Admin da CA {org_name}...'")

            # Loga como admin da CA para ter permissão de registrar outros
            linhas.append(f"fabric-ca-client enroll -u http://admin:adminpw@localhost:{ca_port} --caname {ca_name}")

            # Define o arquivo config.yaml (NodeOUs) que será colocado em cada MSP
            node_ou_yaml = self._get_node_ou_config(f"cacerts/localhost-{ca_port}-{ca_name}.pem")

            # B) Registrar e Matricular Peers
            for peer in org['peers']:
                p_name = peer['name']
                p_full = f"{p_name}.{org_name}.{domain}"
                p_pass = f"{p_name}pw"
                
                # Register (Cria usuário no banco da CA)
                linhas.append(f"infoln '-> Registrando Peer: {p_name}'")
                linhas.append(f'fabric-ca-client register --caname {ca_name} --id.name {p_name} --id.secret {p_pass} --id.type peer --id.attrs \'"hf.Registrar.Roles=peer"\' || true')

                # Enroll (Baixa certificados)
                peer_msp_dir = f"{org_base_dir}/peers/{p_full}/msp"
                linhas.append(f"infoln '-> Enroll Peer: {p_name}'")
                linhas.append(f"fabric-ca-client enroll -u http://{p_name}:{p_pass}@localhost:{ca_port} --caname {ca_name} -M {peer_msp_dir}")
                
                # Salva o config.yaml
                linhas.append(f"echo '{node_ou_yaml}' > {peer_msp_dir}/config.yaml")

                # Isso gera server.crt e server.key
                peer_tls_dir = f"{org_base_dir}/peers/{p_full}/tls"
                linhas.append(f"infoln '-> Enroll TLS Peer: {p_name}'")
                
                # A mágica está aqui: usamos HTTP para conectar, mas pedimos um perfil 'tls'
                # csr.hosts garante que o certificado seja válido para o nome do container e localhost
                linhas.append(f"fabric-ca-client enroll -u http://{p_name}:{p_pass}@localhost:{ca_port} --caname {ca_name} -M {peer_tls_dir} --enrollment.profile tls --csr.hosts {p_full} --csr.hosts localhost")

                # Organiza os arquivos TLS com nomes padrão que o Peer espera
                # O Fabric CA gera keystore/chave_longa... copiamos para server.key
                linhas.append(f"cp {peer_tls_dir}/tlscacerts/* {peer_tls_dir}/ca.crt")
                linhas.append(f"cp {peer_tls_dir}/signcerts/* {peer_tls_dir}/server.crt")
                linhas.append(f"cp {peer_tls_dir}/keystore/* {peer_tls_dir}/server.key")

            # C) Registrar e Matricular Admin da Org
            linhas.append(f"infoln '-> Registrando Admin da Org {org_name}'")
            linhas.append(f'fabric-ca-client register --caname {ca_name} --id.name {org_name}admin --id.secret {org_name}adminpw --id.type admin --id.attrs \'"hf.Registrar.Roles=admin"\' || true')
            
            user_msp_dir = f"{org_base_dir}/users/Admin@{org_name}.{domain}/msp"
            linhas.append(f"fabric-ca-client enroll -u http://{org_name}admin:{org_name}adminpw@localhost:{ca_port} --caname {ca_name} -M {user_msp_dir}")
            linhas.append(f"echo '{node_ou_yaml}' > {user_msp_dir}/config.yaml")

            # D) Setup do MSP Principal da Org (Pasta msp/)
            # Copia os certificados do Admin para a estrutura global da Org
            org_msp_dir = f"{org_base_dir}/msp"
            linhas.append(f"mkdir -p {org_msp_dir}/cacerts")
            linhas.append(f"mkdir -p {org_msp_dir}/tlscacerts")

            linhas.append(f"cp {user_msp_dir}/cacerts/* {org_msp_dir}/cacerts/")
            linhas.append(f"cp {user_msp_dir}/cacerts/* {org_msp_dir}/tlscacerts/")

            linhas.append(f"echo '{node_ou_yaml}' > {org_msp_dir}/config.yaml")


        # ------------------------------------------------------------------
        # 2. PROCESSAR ORDERERS (Usando a CA da Org1)
        # ------------------------------------------------------------------
        # Nota: Como não temos CA de Orderer dedicada, usamos a da Org1
        first_org = orgs[0]
        ord_ca_port = first_org['ca']['port']
        ord_ca_name = first_org['ca']['name']
        
        # Recupera o home do cliente da CA da Org1
        ca_client_home = f"{self.paths.network_dir}/organizations/fabric-ca/{first_org['name']}/client"
        linhas.append(f"export FABRIC_CA_CLIENT_HOME={ca_client_home}")

        # Caminho base do Orderer
        ord_base_dir = f"{self.paths.network_dir}/organizations/ordererOrganizations/{domain}"
        
        for node in orderer_conf['nodes']:
            o_name = node['name']
            o_pass = f"{o_name}pw"
            o_full = f"{o_name}.{domain}"
            
            linhas.append(f"infoln 'Processando Orderer: {o_name} (via CA da {first_org['name']})'")
            
            # Register
            linhas.append(f'fabric-ca-client register --caname {ord_ca_name} --id.name {o_name} --id.secret {o_pass} --id.type orderer --id.attrs \'"hf.Registrar.Roles=orderer"\' || true')
            
            # Enroll
            ord_msp_dir = f"{ord_base_dir}/orderers/{o_full}/msp"
            linhas.append(f"fabric-ca-client enroll -u http://{o_name}:{o_pass}@localhost:{ord_ca_port} --caname {ord_ca_name} -M {ord_msp_dir}")
            
            # TLS do Orderer
            ord_tls_dir = f"{ord_base_dir}/orderers/{o_full}/tls"
            linhas.append(f"infoln '-> Enroll Orderer TLS: {o_name}'")

            # Enroll com perfil TLS
            linhas.append(f"fabric-ca-client enroll -u http://{o_name}:{o_pass}@localhost:{ord_ca_port} --caname {ord_ca_name} -M {ord_tls_dir} --enrollment.profile tls --csr.hosts {o_full} --csr.hosts localhost")

            # NodeOUs (Orderer precisa disso para saber que ele é um orderer)
            node_ou_ord = self._get_node_ou_config(f"cacerts/localhost-{ord_ca_port}-{ord_ca_name}.pem")
            linhas.append(f"echo '{node_ou_ord}' > {ord_msp_dir}/config.yaml")

        # Setup do MSP da Organização Orderer
        ord_org_msp = f"{ord_base_dir}/msp"
        linhas.append(f"mkdir -p {ord_org_msp}/cacerts")
        linhas.append(f"cp {ord_msp_dir}/cacerts/* {ord_org_msp}/cacerts/")
        linhas.append(f"echo '{node_ou_ord}' > {ord_org_msp}/config.yaml")
        
        # Criação do Admin do Orderer (Necessário para criar canais com osnadmin)
        linhas.append(f"infoln '-> Registrando Admin do Orderer'")
        linhas.append(f'fabric-ca-client register --caname {ord_ca_name} --id.name ordererAdmin --id.secret ordererAdminpw --id.type admin --id.attrs \'"hf.Registrar.Roles=admin"\' || true')
        
        ord_admin_msp = f"{ord_base_dir}/users/Admin@{domain}/msp"
        linhas.append(f"fabric-ca-client enroll -u http://ordererAdmin:ordererAdminpw@localhost:{ord_ca_port} --caname {ord_ca_name} -M {ord_admin_msp}")
        linhas.append(f"echo '{node_ou_ord}' > {ord_admin_msp}/config.yaml")

        linhas.append('successln "✅ Todas as identidades foram geradas!"')

        # Salva o arquivo e dá permissão de execução
        with open(self.script_saida, 'w') as f:
            f.write("\n".join(linhas))
        
        st = os.stat(self.script_saida)
        os.chmod(self.script_saida, st.st_mode | stat.S_IEXEC)
        
        co.successln(f"Script gerado: {self.script_saida}")

    def _get_node_ou_config(self, ca_cert_file):
        # Template YAML obrigatório para habilitar papéis (Identity Roles)
        return f"""NodeOUs:
  Enable: true
  ClientOUIdentifier:
    Certificate: {ca_cert_file}
    OrganizationalUnitIdentifier: client
  PeerOUIdentifier:
    Certificate: {ca_cert_file}
    OrganizationalUnitIdentifier: peer
  AdminOUIdentifier:
    Certificate: {ca_cert_file}
    OrganizationalUnitIdentifier: admin
  OrdererOUIdentifier:
    Certificate: {ca_cert_file}
    OrganizationalUnitIdentifier: orderer"""