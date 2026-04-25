#!/bin/bash
set -e
source /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/scripts/utils.sh
export PATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/bin:$PATH

# Verifica se fabric-ca-clientestá instalado
command -v fabric-ca-client >/dev/null || {
    errorln "'fabric-ca-client' não encontrado. Verifique seu PATH."
    exit 1
}

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
    local ip=${7:-}   # IP real do nó — opcional, usado em modo distribuído para IP SANs

    infoln "[TLS] Gerando certificados para $hostname"

    # monta os --csr.hosts: sempre hostname + localhost; adiciona IP se fornecido
    local csr_hosts="--csr.hosts ${hostname} --csr.hosts localhost"
    if [ -n "$ip" ]; then
        csr_hosts="$csr_hosts --csr.hosts ${ip}"
    fi

    # enroll com perfil TLS
    fabric-ca-client enroll -u ${url} \
        --caname "${ca_name}" \
        -M "${tls_dir}" \
        --enrollment.profile tls \
        ${csr_hosts}

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
    local ip=${7:-}   # IP real do nó — opcional, para IP SANs no certificado TLS

    infoln "Configurando Peer: ${name}"

    # Register
    fabric-ca-client register --caname "${ca_name}" \
        --id.name "${name}" --id.secret "${secret}" --id.type peer \
        || true

    # Enroll MSP (treta de ter que usar scape na url, se der ruim o problema tá aqui)
    local msp_dir="${base_dir}/peers/${hostname}/msp"
    fabric-ca-client enroll -u "${url//:\/\//://${name}:${secret}@}" \
        --caname "${ca_name}" -M "${msp_dir}"

    # Configura NodeOUsm pega o arquivo da CA e extrai apenas o nome do arquivo para o config.yaml
    local ca_cert_path=$(ls "${msp_dir}/cacerts/"*)
    local ca_filename=$(basename "$ca_cert_path")
    createNodeOUsConfig "${msp_dir}" "cacerts/${ca_filename}"

    # Enroll TLS
    local tls_dir="${base_dir}/peers/${hostname}/tls"
    enrollTLS "${url//:\/\//://${name}:${secret}@}" "${ca_name}" "${tls_dir}" "${name}" "${secret}" "${hostname}" "${ip}"
}

# registra e faz enroll de um orderer
function registerAndEnrollOrdererNode() {
    local name=$1
    local secret=$2
    local url=$3
    local ca_name=$4
    local hostname=$5
    local base_dir=$6
    local ip=${7:-}   # IP real do nó — opcional, para IP SANs no certificado TLS

    infoln "Configurando Orderer Node: ${name}"

    # Register
    fabric-ca-client register --caname "${ca_name}" \
        --id.name "${name}" --id.secret "${secret}" --id.type orderer \
        || true

    # Enroll MSP
    local msp_dir="${base_dir}/orderers/${hostname}/msp"
    fabric-ca-client enroll -u "${url//:\/\//://${name}:${secret}@}" \
        --caname "${ca_name}" -M "${msp_dir}"

    # Configura NodeOUs
    local ca_cert_path=$(ls "${msp_dir}/cacerts/"*)
    local ca_filename=$(basename "$ca_cert_path")
    createNodeOUsConfig "${msp_dir}" "cacerts/${ca_filename}"

    # Enroll TLS
    local tls_dir="${base_dir}/orderers/${hostname}/tls"
    enrollTLS "${url//:\/\//://${name}:${secret}@}" "${ca_name}" "${tls_dir}" "${name}" "${secret}" "${hostname}" "${ip}"
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
    fabric-ca-client register --caname "${ca_name}" \
        --id.name "${user}" --id.secret "${pass}" --id.type admin \
        --id.attrs "hf.Registrar.Roles=admin" \
        || true

    # Enroll MSP
    local msp_dir="${base_dir}/users/${admin_folder_name}/msp"
    fabric-ca-client enroll -u "${url//:\/\//://${user}:${pass}@}" \
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

infoln "--- Iniciando Geração de Identidades ---"

# --- Organização: Org1 (CA em 10.10.20.151:8054) ---
infoln 'Processando Organização: Org1'
mkdir -p /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com
mkdir -p /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/fabric-ca/Org1/client
export FABRIC_CA_CLIENT_HOME=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/fabric-ca/Org1/client
infoln 'Bootstrap Admin CA (Org1 em 10.10.20.151:8054)...'
fabric-ca-client enroll -u http://admin:adminpw@10.10.20.151:8054 --caname ca-org1
registerAndEnrollPeer 'peer0' 'peer0pw' 'http://10.10.20.151:8054' 'ca-org1' 'peer0.Org1.exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com' '10.10.20.151'
registerAndEnrollPeer 'peer1' 'peer1pw' 'http://10.10.20.151:8054' 'ca-org1' 'peer1.Org1.exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com' '10.10.20.151'
registerAndEnrollOrgAdmin 'Org1admin' 'Org1adminpw' 'http://10.10.20.151:8054' 'ca-org1' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com' 'Admin@Org1.exemplo.com'
finishOrgMSP '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/users/Admin@Org1.exemplo.com/msp'

# --- Organização: Org2 (CA em 10.10.20.151:9054) ---
infoln 'Processando Organização: Org2'
mkdir -p /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com
mkdir -p /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/fabric-ca/Org2/client
export FABRIC_CA_CLIENT_HOME=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/fabric-ca/Org2/client
infoln 'Bootstrap Admin CA (Org2 em 10.10.20.151:9054)...'
fabric-ca-client enroll -u http://admin:adminpw@10.10.20.151:9054 --caname ca-org2
registerAndEnrollPeer 'peer0' 'peer0pw' 'http://10.10.20.151:9054' 'ca-org2' 'peer0.Org2.exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com' '10.10.20.151'
registerAndEnrollPeer 'peer1' 'peer1pw' 'http://10.10.20.151:9054' 'ca-org2' 'peer1.Org2.exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com' '10.10.20.151'
registerAndEnrollOrgAdmin 'Org2admin' 'Org2adminpw' 'http://10.10.20.151:9054' 'ca-org2' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com' 'Admin@Org2.exemplo.com'
finishOrgMSP '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/users/Admin@Org2.exemplo.com/msp'

# --- Organização: Org3 (CA em 10.10.20.152:10054) ---
infoln 'Processando Organização: Org3'
mkdir -p /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com
mkdir -p /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/fabric-ca/Org3/client
export FABRIC_CA_CLIENT_HOME=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/fabric-ca/Org3/client
infoln 'Bootstrap Admin CA (Org3 em 10.10.20.152:10054)...'
fabric-ca-client enroll -u http://admin:adminpw@10.10.20.152:10054 --caname ca-org3
registerAndEnrollPeer 'peer0' 'peer0pw' 'http://10.10.20.152:10054' 'ca-org3' 'peer0.Org3.exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com' '10.10.20.152'
registerAndEnrollPeer 'peer1' 'peer1pw' 'http://10.10.20.152:10054' 'ca-org3' 'peer1.Org3.exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com' '10.10.20.152'
registerAndEnrollOrgAdmin 'Org3admin' 'Org3adminpw' 'http://10.10.20.152:10054' 'ca-org3' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com' 'Admin@Org3.exemplo.com'
finishOrgMSP '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/users/Admin@Org3.exemplo.com/msp'

# --- Organização: Org4 (CA em 10.10.20.152:11054) ---
infoln 'Processando Organização: Org4'
mkdir -p /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com
mkdir -p /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/fabric-ca/Org4/client
export FABRIC_CA_CLIENT_HOME=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/fabric-ca/Org4/client
infoln 'Bootstrap Admin CA (Org4 em 10.10.20.152:11054)...'
fabric-ca-client enroll -u http://admin:adminpw@10.10.20.152:11054 --caname ca-org4
registerAndEnrollPeer 'peer0' 'peer0pw' 'http://10.10.20.152:11054' 'ca-org4' 'peer0.Org4.exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com' '10.10.20.152'
registerAndEnrollPeer 'peer1' 'peer1pw' 'http://10.10.20.152:11054' 'ca-org4' 'peer1.Org4.exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com' '10.10.20.152'
registerAndEnrollOrgAdmin 'Org4admin' 'Org4adminpw' 'http://10.10.20.152:11054' 'ca-org4' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com' 'Admin@Org4.exemplo.com'
finishOrgMSP '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/users/Admin@Org4.exemplo.com/msp'

# --- Organização Orderer (exemplo.com, CA em 10.10.20.151:7054) ---
infoln 'Processando Orderer Org (CA: ca-orderer em 10.10.20.151:7054)'
mkdir -p /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com
mkdir -p /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/fabric-ca/ordererOrg/client
export FABRIC_CA_CLIENT_HOME=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/fabric-ca/ordererOrg/client
infoln 'Bootstrap Admin CA Orderer (10.10.20.151:7054)...'
fabric-ca-client enroll -u http://admin:adminpw@10.10.20.151:7054 --caname ca-orderer
registerAndEnrollOrdererNode 'orderer0' 'orderer0pw' 'http://10.10.20.151:7054' 'ca-orderer' 'orderer0.exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com' '10.10.20.151'
registerAndEnrollOrdererNode 'orderer1' 'orderer1pw' 'http://10.10.20.151:7054' 'ca-orderer' 'orderer1.exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com' '10.10.20.151'
registerAndEnrollOrdererNode 'orderer2' 'orderer2pw' 'http://10.10.20.151:7054' 'ca-orderer' 'orderer2.exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com' '10.10.20.152'
registerAndEnrollOrdererNode 'orderer3' 'orderer3pw' 'http://10.10.20.151:7054' 'ca-orderer' 'orderer3.exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com' '10.10.20.152'
registerAndEnrollOrgAdmin 'ordererAdmin' 'ordererAdminpw' 'http://10.10.20.151:7054' 'ca-orderer' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com' 'Admin@exemplo.com'
finishOrgMSP '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com' '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/users/Admin@exemplo.com/msp'

successln "Todas as identidades foram geradas com sucesso!"

infoln 'Corrigindo permissões da pasta organizations...'
fix_permissions '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations'