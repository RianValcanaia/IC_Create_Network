# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
Gera o script register_enroll.sh, que automatiza a criação de identidades 
digitais na rede. Ele gerencia o processo de bootstrap do administrador da CA, 
o registro e a matrícula (enrollment) de peers, usuários e administradores de 
organizações utilizando o fabric-ca-client.
"""
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
        
        linhas = []
        
        # cabecalho do Script Bash
        linhas.append("#!/bin/bash")
        linhas.append("set -e") 
        linhas.append(f"source {self.paths.scripts_dir}/utils.sh")
        
        # exporta os binarios do Fabric para o PATH
        linhas.append(f"export PATH={self.paths.base_dir}/bin:$PATH")
        
        # validacao de pre-requisitos
        linhas.append("""
# Verifica se fabric-ca-clientestá instalado
command -v fabric-ca-client >/dev/null || {
    errorln "'fabric-ca-client' não encontrado. Verifique seu PATH."
    exit 1
}""")

        # inclui funcoes bash auxiliares
        linhas.append(self._get_bash_functions())

        linhas.append('infoln "--- Iniciando Geração de Identidades ---"')

        # -------------------- Processa peers das organizações --------------------
        for org in orgs:
            org_name = org['name']
            ca_port = org['ca']['port']
            ca_name = org['ca']['name']
            
            # caminho base
            org_base_dir = f"{self.paths.network_dir}/organizations/peerOrganizations/{org_name}.{domain}"
            
            # onde o cliente da CA salva as credenciais temporarias do admin
            ca_client_home = f"{self.paths.network_dir}/organizations/fabric-ca/{org_name}/client"

            linhas.append(f"\n# --- Organização: {org_name} ---")
            linhas.append(f"infoln 'Processando Organização: {org_name}'")
            
            linhas.append(f"mkdir -p {org_base_dir}")
            
            # enroll do admin da CA
            linhas.append(f"mkdir -p {ca_client_home}")
            linhas.append(f"export FABRIC_CA_CLIENT_HOME={ca_client_home}")
            
            linhas.append(f"infoln 'Bootstrap Admin CA ({org_name})...'")

            # loga como admin da CA para ter permissao de registrar outros
            linhas.append(f"fabric-ca-client enroll -u http://admin:adminpw@localhost:{ca_port} --caname {ca_name}")

            # registrar e matricular peers
            for peer in org['peers']:
                p_name = peer['name']
                p_full = f"{p_name}.{org_name}.{domain}"
                p_pass = f"{p_name}pw"
                
                # chamada da funcaoo bash modular
                linhas.append(f"registerAndEnrollPeer '{p_name}' '{p_pass}' 'http://localhost:{ca_port}' '{ca_name}' '{p_full}' '{org_base_dir}'")

            # registrar e matricular admin da org
            admin_name = f"{org_name}admin"
            admin_pass = f"{org_name}adminpw"
            
            linhas.append(f"registerAndEnrollOrgAdmin '{admin_name}' '{admin_pass}' 'http://localhost:{ca_port}' '{ca_name}' '{org_base_dir}' 'Admin@{org_name}.{domain}'")

            # finalizar MSP da org (copiar certs públicos)
            linhas.append(f"finishOrgMSP '{org_base_dir}' '{org_base_dir}/users/Admin@{org_name}.{domain}/msp'")


        # -------------------- Processa Orderers --------------------
        # tenta pegar config de CA do orderer, se não existir, define padrões
        ord_ca_conf = orderer_conf.get('ca', {})
        ord_ca_name = ord_ca_conf.get('name', 'ca-orderer')
        ord_ca_port = ord_ca_conf.get('port', 7054) 
        
        # define home do client da CA do Orderer
        ord_ca_client_home = f"{self.paths.network_dir}/organizations/fabric-ca/ordererOrg/client"
        ord_base_dir = f"{self.paths.network_dir}/organizations/ordererOrganizations/{domain}"

        linhas.append(f"\n# --- Organização Orderer ({domain}) ---")
        linhas.append(f"infoln 'Processando Orderer Org (CA: {ord_ca_name}:{ord_ca_port})'")
        
        linhas.append(f"mkdir -p {ord_base_dir}")
        linhas.append(f"mkdir -p {ord_ca_client_home}")
        linhas.append(f"export FABRIC_CA_CLIENT_HOME={ord_ca_client_home}")

        # enroll admin da CA do orderer
        linhas.append(f"infoln 'Bootstrap Admin CA Orderer...'")
        linhas.append(f"fabric-ca-client enroll -u http://admin:adminpw@localhost:{ord_ca_port} --caname {ord_ca_name}")

        # processar nos orderers
        for node in orderer_conf['nodes']:
            o_name = node['name']
            o_pass = f"{o_name}pw"
            o_full = f"{o_name}.{domain}"
            
            # chamada da funcao bash modular para orderer
            linhas.append(f"registerAndEnrollOrdererNode '{o_name}' '{o_pass}' 'http://localhost:{ord_ca_port}' '{ord_ca_name}' '{o_full}' '{ord_base_dir}'")

        # admin do orderer
        linhas.append(f"registerAndEnrollOrgAdmin 'ordererAdmin' 'ordererAdminpw' 'http://localhost:{ord_ca_port}' '{ord_ca_name}' '{ord_base_dir}' 'Admin@{domain}'")

        # finalizar MSP da org orderer
        linhas.append(f"finishOrgMSP '{ord_base_dir}' '{ord_base_dir}/users/Admin@{domain}/msp'")

        linhas.append('\nsuccessln "Todas as identidades foram geradas com sucesso!"')

        org_base_dir = f"{self.paths.network_dir}/organizations"
        linhas.append(f"\ninfoln 'Corrigindo permissões da pasta organizations...'")
        linhas.append(f"fix_permissions '{org_base_dir}'")
        
        # Salva o arquivo e dá permissão de execução
        with open(self.script_saida, 'w') as f:
            f.write("\n".join(linhas))
        
        st = os.stat(self.script_saida)
        os.chmod(self.script_saida, st.st_mode | stat.S_IEXEC)
        
        co.successln(f"Script gerado: {self.script_saida}")

    def _get_bash_functions(self):
        return """
# ---------------- FUNÇÕES AUXILIARES ----------------

# gera o arquivo config.yaml (NodeOUs)
function createNodeOUsConfig() {
    local msp_dir=$1
    local ca_cert_file=$2    # caminho relativo esperado pelo config.yaml
    
    # verifica se o arquivo da CA existe
    if [ ! -f "${msp_dir}/${ca_cert_file}" ]; then
        errorln "Arquivo de CA não encontrado para NodeOUs: ${msp_dir}/${ca_cert_file}"
        exit 1
    fi

    echo "NodeOUs:
  Enable: true
  ClientOUIdentifier:
    Certificate: ${ca_cert_file}
    OrganizationalUnitIdentifier: client
  PeerOUIdentifier:
    Certificate: ${ca_cert_file}
    OrganizationalUnitIdentifier: peer
  AdminOUIdentifier:
    Certificate: ${ca_cert_file}
    OrganizationalUnitIdentifier: admin
  OrdererOUIdentifier:
    Certificate: ${ca_cert_file}
    OrganizationalUnitIdentifier: orderer" > "${msp_dir}/config.yaml"
}

# Rfaz o enroll TLS para um nó (peer ou orderer)
function enrollTLS() {
    local url=$1
    local ca_name=$2
    local tls_dir=$3
    local user=$4
    local pass=$5
    local hostname=$6

    infoln "[TLS] Gerando certificados para $hostname"
    
    # enroll com perfil TLS 
    fabric-ca-client enroll -u ${url} \\
        --caname "${ca_name}" \\
        -M "${tls_dir}" \\
        --enrollment.profile tls \\
        --csr.hosts "${hostname}" \\
        --csr.hosts localhost

    # organiza arquivos para o padrao fabric
    cp "${tls_dir}/tlscacerts/"* "${tls_dir}/ca.crt"
    cp "${tls_dir}/signcerts/"* "${tls_dir}/server.crt"
    cp "${tls_dir}/keystore/"* "${tls_dir}/server.key"
    
    rm -rf "${tls_dir}/cacerts" "${tls_dir}/keystore" "${tls_dir}/signcerts" "${tls_dir}/user"
}

# registra e faz enroll de um PEER
function registerAndEnrollPeer() {
    local name=$1
    local secret=$2
    local url=$3
    local ca_name=$4
    local hostname=$5
    local base_dir=$6
    
    infoln "Configurando Peer: ${name}"

    # Register 
    fabric-ca-client register --caname "${ca_name}" \\
        --id.name "${name}" --id.secret "${secret}" --id.type peer \\
        || true

    # Enroll MSP (treta de ter que usar scape na url, se der ruim o problema tá aqui)
    local msp_dir="${base_dir}/peers/${hostname}/msp"
    fabric-ca-client enroll -u "${url//:\\/\\//://${name}:${secret}@}" \\
        --caname "${ca_name}" -M "${msp_dir}"

    # Configura NodeOUsm pega o arquivo da CA e extrai apenas o nome do arquivo para o config.yaml
    local ca_cert_path=$(ls "${msp_dir}/cacerts/"*)
    local ca_filename=$(basename "$ca_cert_path")
    createNodeOUsConfig "${msp_dir}" "cacerts/${ca_filename}"

    # Enroll TLS
    local tls_dir="${base_dir}/peers/${hostname}/tls"
    enrollTLS "${url//:\\/\\//://${name}:${secret}@}" "${ca_name}" "${tls_dir}" "${name}" "${secret}" "${hostname}"
}

# registra e faz enroll de um orderer
function registerAndEnrollOrdererNode() {
    local name=$1
    local secret=$2
    local url=$3
    local ca_name=$4
    local hostname=$5
    local base_dir=$6
    
    infoln "Configurando Orderer Node: ${name}"

    # Register
    fabric-ca-client register --caname "${ca_name}" \\
        --id.name "${name}" --id.secret "${secret}" --id.type orderer \\
        || true

    # Enroll MSP
    local msp_dir="${base_dir}/orderers/${hostname}/msp"
    fabric-ca-client enroll -u "${url//:\\/\\//://${name}:${secret}@}" \\
        --caname "${ca_name}" -M "${msp_dir}"

    # Configura NodeOUs
    local ca_cert_path=$(ls "${msp_dir}/cacerts/"*)
    local ca_filename=$(basename "$ca_cert_path")
    createNodeOUsConfig "${msp_dir}" "cacerts/${ca_filename}"

    # Enroll TLS
    local tls_dir="${base_dir}/orderers/${hostname}/tls"
    enrollTLS "${url//:\\/\\//://${name}:${secret}@}" "${ca_name}" "${tls_dir}" "${name}" "${secret}" "${hostname}"
}

# registra e faz enroll de um admin de Organização
function registerAndEnrollOrgAdmin() {
    local user=$1
    local pass=$2
    local url=$3
    local ca_name=$4
    local base_dir=$5
    local admin_folder_name=$6 

    infoln "Configurando Admin da Org: ${user}"

    # Register
    fabric-ca-client register --caname "${ca_name}" \\
        --id.name "${user}" --id.secret "${pass}" --id.type admin \\
        --id.attrs "hf.Registrar.Roles=admin" \\
        || true

    # Enroll MSP
    local msp_dir="${base_dir}/users/${admin_folder_name}/msp"
    fabric-ca-client enroll -u "${url//:\\/\\//://${user}:${pass}@}" \\
        --caname "${ca_name}" -M "${msp_dir}"

    # Configura NodeOUs
    local ca_cert_path=$(ls "${msp_dir}/cacerts/"*)
    local ca_filename=$(basename "$ca_cert_path")
    createNodeOUsConfig "${msp_dir}" "cacerts/${ca_filename}"
}

# Copia certificados para a estrutura global da MSP da Organização
function finishOrgMSP() {
    local org_base_dir=$1
    local source_msp=$2 

    infoln "Finalizando MSP da Organização em ${org_base_dir}/msp"
    
    local target_msp="${org_base_dir}/msp"
    mkdir -p "${target_msp}/cacerts"
    mkdir -p "${target_msp}/tlscacerts"

    cp "${source_msp}/cacerts/"* "${target_msp}/cacerts/"
    cp "${source_msp}/cacerts/"* "${target_msp}/tlscacerts/"
    
    local ca_cert_path=$(ls "${target_msp}/cacerts/"*)
    local ca_filename=$(basename "$ca_cert_path")
    createNodeOUsConfig "${target_msp}" "cacerts/${ca_filename}"
}
"""