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
        
        # Inicia a lista de linhas do script
        linhas = []
        
        # 1. Cabeçalho e Verificações Iniciais
        linhas.append("#!/bin/bash")
        linhas.append("set -e") # Para o script imediatamente se der erro
        linhas.append(f"source {self.paths.scripts_dir}/utils.sh")
        
        # Garante que os binários (fabric-ca-client) estejam no PATH
        linhas.append(f"export PATH={self.paths.base_dir}/bin:$PATH")
        
        # Validação de pré-requisito no início do script
        linhas.append("""
# Verifica se o cliente da CA está instalado
command -v fabric-ca-client >/dev/null || {
    errorln "❌ Erro: 'fabric-ca-client' não encontrado. Verifique seu PATH."
    exit 1
}""")

        # 2. Injeção das Funções Bash (Modularização)
        linhas.append(self._get_bash_functions_template())

        linhas.append('infoln "--- Iniciando Geração de Identidades ---"')

        # ------------------------------------------------------------------
        # 3. PROCESSAR ORGANIZAÇÕES (Peers)
        # ------------------------------------------------------------------
        for org in orgs:
            org_name = org['name']
            ca_port = org['ca']['port']
            ca_name = org['ca']['name']
            
            # Caminho base
            org_base_dir = f"{self.paths.network_dir}/organizations/peerOrganizations/{org_name}.{domain}"
            
            # Onde o cliente da CA salva as credenciais temporárias do admin
            ca_client_home = f"{self.paths.network_dir}/organizations/fabric-ca/{org_name}/client"

            linhas.append(f"\n# --- Organização: {org_name} ---")
            linhas.append(f"infoln 'Processando Organização: {org_name}'")
            
            linhas.append(f"mkdir -p {org_base_dir}")
            
            # enroll do admin da CA
            linhas.append(f"mkdir -p {ca_client_home}")
            linhas.append(f"export FABRIC_CA_CLIENT_HOME={ca_client_home}")
            
            linhas.append(f"infoln '-> Bootstrap Admin CA ({org_name})...'")

            # Loga como admin da CA para ter permissão de registrar outros
            linhas.append(f"fabric-ca-client enroll -u http://admin:adminpw@localhost:{ca_port} --caname {ca_name}")

            # B) Registrar e Matricular Peers
            for peer in org['peers']:
                p_name = peer['name']
                p_full = f"{p_name}.{org_name}.{domain}"
                p_pass = f"{p_name}pw"
                
                # Chamada da função Bash modular
                # Args: Nome, Senha, URL_CA, CA_Name, Host_Full, Org_Base_Dir
                linhas.append(f"registerAndEnrollPeer '{p_name}' '{p_pass}' 'http://localhost:{ca_port}' '{ca_name}' '{p_full}' '{org_base_dir}'")

            # C) Registrar e Matricular Admin da Org
            admin_name = f"{org_name}admin"
            admin_pass = f"{org_name}adminpw"
            
            # Args: User, Pass, URL_CA, CA_Name, Org_Base_Dir, Full_Identity_String
            linhas.append(f"registerAndEnrollOrgAdmin '{admin_name}' '{admin_pass}' 'http://localhost:{ca_port}' '{ca_name}' '{org_base_dir}' 'Admin@{org_name}.{domain}'")

            # D) Finalizar MSP da Org (Copiar Certs Públicos)
            # Args: Org_Base_Dir, Admin_MSP_Source
            linhas.append(f"finishOrgMSP '{org_base_dir}' '{org_base_dir}/users/Admin@{org_name}.{domain}/msp'")


        # ------------------------------------------------------------------
        # 4. PROCESSAR ORDERERS (CA Dedicada ou Padrão)
        # ------------------------------------------------------------------
        # Tenta pegar config de CA do orderer, se não existir, define padrões
        ord_ca_conf = orderer_conf.get('ca', {})
        ord_ca_name = ord_ca_conf.get('name', 'ca-orderer')
        ord_ca_port = ord_ca_conf.get('port', 7054) 
        
        # Define home do client da CA do Orderer
        ord_ca_client_home = f"{self.paths.network_dir}/organizations/fabric-ca/ordererOrg/client"
        ord_base_dir = f"{self.paths.network_dir}/organizations/ordererOrganizations/{domain}"

        linhas.append(f"\n# --- Organização Orderer ({domain}) ---")
        linhas.append(f"infoln 'Processando Orderer Org (CA: {ord_ca_name}:{ord_ca_port})'")
        
        linhas.append(f"mkdir -p {ord_base_dir}")
        linhas.append(f"mkdir -p {ord_ca_client_home}")
        linhas.append(f"export FABRIC_CA_CLIENT_HOME={ord_ca_client_home}")

        # Enroll Admin da CA do Orderer
        linhas.append(f"infoln '-> Bootstrap Admin CA Orderer...'")
        linhas.append(f"fabric-ca-client enroll -u http://admin:adminpw@localhost:{ord_ca_port} --caname {ord_ca_name}")

        # Processar Nós Orderers
        for node in orderer_conf['nodes']:
            o_name = node['name']
            o_pass = f"{o_name}pw"
            o_full = f"{o_name}.{domain}"
            
            # Chamada da função Bash modular para Orderer
            linhas.append(f"registerAndEnrollOrdererNode '{o_name}' '{o_pass}' 'http://localhost:{ord_ca_port}' '{ord_ca_name}' '{o_full}' '{ord_base_dir}'")

        # Admin do Orderer
        linhas.append(f"registerAndEnrollOrgAdmin 'ordererAdmin' 'ordererAdminpw' 'http://localhost:{ord_ca_port}' '{ord_ca_name}' '{ord_base_dir}' 'Admin@{domain}'")

        # Finalizar MSP da Org Orderer
        linhas.append(f"finishOrgMSP '{ord_base_dir}' '{ord_base_dir}/users/Admin@{domain}/msp'")

        linhas.append('\nsuccessln "✅ Todas as identidades foram geradas com sucesso!"')

        # Salva o arquivo e dá permissão de execução
        with open(self.script_saida, 'w') as f:
            f.write("\n".join(linhas))
        
        st = os.stat(self.script_saida)
        os.chmod(self.script_saida, st.st_mode | stat.S_IEXEC)
        
        co.successln(f"Script gerado: {self.script_saida}")

    def _get_bash_functions_template(self):
        # Nota: Usamos strings normais (""") mas escapamos as barras invertidas (\\) 
        # para que o Python não interprete mal as regex do Bash e não gere SyntaxWarning.
        return """
# ==============================================================================
# FUNÇÕES AUXILIARES
# ==============================================================================

# Gera o arquivo config.yaml (NodeOUs)
function createNodeOUsConfig() {
    local msp_dir=$1
    local ca_cert_file=$2 # Caminho relativo esperado pelo config.yaml (ex: cacerts/arquivo.pem)
    
    # CORREÇÃO: Verificamos o arquivo usando o caminho ABSOLUTO combinando msp_dir
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

# Realiza o Enroll de TLS para um nó (Peer ou Orderer)
function enrollTLS() {
    local url=$1
    local ca_name=$2
    local tls_dir=$3
    local user=$4
    local pass=$5
    local hostname=$6

    infoln "   [TLS] Gerando certificados para $hostname"
    
    # Enroll com perfil TLS (Sem --quiet para evitar erros de versão)
    fabric-ca-client enroll -u ${url} \\
        --caname "${ca_name}" \\
        -M "${tls_dir}" \\
        --enrollment.profile tls \\
        --csr.hosts "${hostname}" \\
        --csr.hosts localhost

    # Organiza arquivos para o padrão Fabric
    cp "${tls_dir}/tlscacerts/"* "${tls_dir}/ca.crt"
    cp "${tls_dir}/signcerts/"* "${tls_dir}/server.crt"
    cp "${tls_dir}/keystore/"* "${tls_dir}/server.key"
    
    rm -rf "${tls_dir}/cacerts" "${tls_dir}/keystore" "${tls_dir}/signcerts" "${tls_dir}/user"
}

# Registra e Matricula um PEER
function registerAndEnrollPeer() {
    local name=$1
    local secret=$2
    local url=$3
    local ca_name=$4
    local hostname=$5
    local base_dir=$6
    
    infoln "-> Configurando Peer: ${name}"

    # 1. Register (Sem papel de registrar outros peers)
    fabric-ca-client register --caname "${ca_name}" \\
        --id.name "${name}" --id.secret "${secret}" --id.type peer \\
        || true

    # 2. Enroll MSP
    # Aqui usamos replace do bash com barras escapadas para Python: //:\\/\\//
    local msp_dir="${base_dir}/peers/${hostname}/msp"
    fabric-ca-client enroll -u "${url//:\\/\\//://${name}:${secret}@}" \\
        --caname "${ca_name}" -M "${msp_dir}"

    # 3. Configura NodeOUs
    # Pega o arquivo da CA e extrai apenas o nome do arquivo para o config.yaml
    local ca_cert_path=$(ls "${msp_dir}/cacerts/"*)
    local ca_filename=$(basename "$ca_cert_path")
    createNodeOUsConfig "${msp_dir}" "cacerts/${ca_filename}"

    # 4. Enroll TLS
    local tls_dir="${base_dir}/peers/${hostname}/tls"
    enrollTLS "${url//:\\/\\//://${name}:${secret}@}" "${ca_name}" "${tls_dir}" "${name}" "${secret}" "${hostname}"
}

# Registra e Matricula um ORDERER
function registerAndEnrollOrdererNode() {
    local name=$1
    local secret=$2
    local url=$3
    local ca_name=$4
    local hostname=$5
    local base_dir=$6
    
    infoln "-> Configurando Orderer Node: ${name}"

    # 1. Register
    fabric-ca-client register --caname "${ca_name}" \\
        --id.name "${name}" --id.secret "${secret}" --id.type orderer \\
        || true

    # 2. Enroll MSP
    local msp_dir="${base_dir}/orderers/${hostname}/msp"
    fabric-ca-client enroll -u "${url//:\\/\\//://${name}:${secret}@}" \\
        --caname "${ca_name}" -M "${msp_dir}"

    # 3. Configura NodeOUs
    local ca_cert_path=$(ls "${msp_dir}/cacerts/"*)
    local ca_filename=$(basename "$ca_cert_path")
    createNodeOUsConfig "${msp_dir}" "cacerts/${ca_filename}"

    # 4. Enroll TLS
    local tls_dir="${base_dir}/orderers/${hostname}/tls"
    enrollTLS "${url//:\\/\\//://${name}:${secret}@}" "${ca_name}" "${tls_dir}" "${name}" "${secret}" "${hostname}"
}

# Registra e Matricula um ADMIN de Organização
function registerAndEnrollOrgAdmin() {
    local user=$1
    local pass=$2
    local url=$3
    local ca_name=$4
    local base_dir=$5
    local admin_folder_name=$6 

    infoln "-> Configurando Admin da Org: ${user}"

    # 1. Register
    fabric-ca-client register --caname "${ca_name}" \\
        --id.name "${user}" --id.secret "${pass}" --id.type admin \\
        --id.attrs "hf.Registrar.Roles=admin" \\
        || true

    # 2. Enroll MSP
    local msp_dir="${base_dir}/users/${admin_folder_name}/msp"
    fabric-ca-client enroll -u "${url//:\\/\\//://${user}:${pass}@}" \\
        --caname "${ca_name}" -M "${msp_dir}"

    # 3. Configura NodeOUs
    local ca_cert_path=$(ls "${msp_dir}/cacerts/"*)
    local ca_filename=$(basename "$ca_cert_path")
    createNodeOUsConfig "${msp_dir}" "cacerts/${ca_filename}"
}

# Copia certificados para a estrutura global da MSP da Organização
function finishOrgMSP() {
    local org_base_dir=$1
    local source_msp=$2 

    infoln "-> Finalizando MSP da Organização em ${org_base_dir}/msp"
    
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