# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
Gera o script register_enroll.sh, que automatiza a criação de identidades
digitais na rede. Ele gerencia o processo de bootstrap do administrador da CA,
o registro e a matrícula (enrollment) de peers, usuários e administradores de
organizações utilizando o fabric-ca-client.

Suporte a deploy distribuído:
  Quando a seção 'machines' está definida no network.yaml e cada CA possui o
  campo 'machine', as URLs do fabric-ca-client são geradas com os IPs reais de
  cada CA em vez de 'localhost'. Isso permite executar register_enroll.sh de
  qualquer máquina do cluster que enxergue a LAN. Sem 'machines', o
  comportamento é idêntico ao original (localhost).

Suporte a macvlan:
  Quando 'network.macvlan' está definido no network.yaml, cada CA/peer/orderer
  já tem um IP real e estático na subnet do host (ver ComposeGenerator e
  StaticIPAllocator) - as URLs do fabric-ca-client e os IP SANs dos certificados
  TLS usam esse IP em vez de 'localhost'. Mutuamente exclusivo com 'machines'
  (modo distribuído): se ambos estiverem presentes, 'machines' tem prioridade.
"""
import os
import stat
from ..utils import Colors as co
from .addressing import StaticIPAllocator

class CryptoGenerator:
    def __init__(self, config, paths, distributed=False, macvlan=False):
        # inicializa as referencias de configuracao
        self.config = config
        self.paths = paths

        # quando True, usa os IPs reais da seção 'machines' do network.yaml;
        # quando False (padrão / modo local), todos os endereços usam 'localhost'.
        self.distributed = distributed

        # quando True, usa o IP real/estático de cada CA/peer/orderer na subnet
        # macvlan em vez de 'localhost' (ver StaticIPAllocator)
        self.allocator = StaticIPAllocator(config)
        self.macvlan = macvlan and self.allocator.enabled

        # local de saida do script register_enroll.sh
        self.script_saida = self.paths.scripts_dir / "register_enroll.sh"

    def _resolve_host(self, machine_name, machines, macvlan_ip):
        """
        Resolve o host (IP ou 'localhost') de um componente da rede, na ordem:
        1. IP real da máquina em 'machines' (modo distribuído, se aplicável);
        2. IP estático macvlan do próprio componente (se modo macvlan ativo);
        3. 'localhost' (modo local padrão).
        """
        if machine_name and machine_name in machines:
            return machines[machine_name]['ip']
        if macvlan_ip:
            return macvlan_ip
        return "localhost"

    def _ca_host(self, ca_config, machines, macvlan_ip=None):
        """
        Retorna o host (IP ou 'localhost') de uma CA para uso nas URLs do
        fabric-ca-client. Ver _resolve_host para a ordem de prioridade.
        """
        return self._resolve_host(ca_config.get('machine'), machines, macvlan_ip)

    # gera o conteudo do script bash para registro e matricula das identidades
    def generate(self):
        # extrai informacoes da topologia
        orgs = self.config['network_topology']['organizations']
        orderer_conf = self.config['network_topology']['orderer']
        domain = self.config['network_topology']['network']['domain']

        machines = self.config['network_topology'].get('machines', {}) if self.distributed else {}

        linhas = []
        
        # -------------------- Configuracao inicial do script bash --------------------
        linhas.append("#!/bin/bash")
        linhas.append("set -e") 
        linhas.append(f"source {self.paths.scripts_dir}/utils.sh")
        
        # adiciona os binarios do fabric ao PATH para execucao dos comandos ca-client
        linhas.append(f"export PATH={self.paths.base_dir}/bin:$PATH")
        
        # verifica se o executavel do fabric-ca-cliente está disponivel no sistema
        linhas.append("""
# Verifica se fabric-ca-clientestá instalado
command -v fabric-ca-client >/dev/null || {
    errorln "'fabric-ca-client' não encontrado. Verifique seu PATH."
    exit 1
}""")

        # insere o bloco de funcoes bash auxliares
        linhas.append(self._get_bash_functions())

        linhas.append('infoln "--- Iniciando Geração de Identidades ---"')

        # -------------------- Processamento peers das organizações --------------------
        for org in orgs:
            org_name = org['name']
            ca_port = org['ca']['port']
            ca_name = org['ca']['name']

            # host da CA desta org: IP real em modo distribuído/macvlan, localhost em modo local
            ca_host = self._ca_host(org['ca'], machines, self.allocator.ca_ip(org_name) if self.macvlan else None)
            ca_url = f"http://{ca_host}:{ca_port}"

            # define o diretorio base da organizacao e a home temporaria do cliente CA
            org_base_dir = f"{self.paths.network_dir}/organizations/peerOrganizations/{org_name}.{domain}"
            ca_client_home = f"{self.paths.network_dir}/organizations/fabric-ca/{org_name}/client"

            linhas.append(f"\n# --- Organização: {org_name} (CA em {ca_host}:{ca_port}) ---")
            linhas.append(f"infoln 'Processando Organização: {org_name}'")

            linhas.append(f"mkdir -p {org_base_dir}")
            linhas.append(f"mkdir -p {ca_client_home}")

            # define o ambiente de trabalho do CA client para a org
            linhas.append(f"export FABRIC_CA_CLIENT_HOME={ca_client_home}")
            linhas.append(f"infoln 'Bootstrap Admin CA ({org_name} em {ca_host}:{ca_port})...'")

            # realiza o enroll do ademir da CA para permitir registro de novos nos
            linhas.append(f"fabric-ca-client enroll -u http://admin:adminpw@{ca_host}:{ca_port} --caname {ca_name}")

            # registra e matricula peers
            for peer in org['peers']:
                p_name = peer['name']
                p_full = f"{p_name}.{org_name}.{domain}"
                p_pass = f"{p_name}pw"
                peer_machine = peer.get('machine')
                peer_ip = machines.get(peer_machine, {}).get('ip', '') if peer_machine else ''
                if not peer_ip and self.macvlan:
                    peer_ip = self.allocator.peer_ip(org_name, p_name) or ''
                # chamada da funcao bash definida (7º arg: IP real do peer p/ TLS SAN)
                linhas.append(f"registerAndEnrollPeer '{p_name}' '{p_pass}' '{ca_url}' '{ca_name}' '{p_full}' '{org_base_dir}' '{peer_ip}'")

            # registra e matricula ademir da org
            admin_name = f"{org_name}admin"
            admin_pass = f"{org_name}adminpw"
            linhas.append(f"registerAndEnrollOrgAdmin '{admin_name}' '{admin_pass}' '{ca_url}' '{ca_name}' '{org_base_dir}' 'Admin@{org_name}.{domain}'")

            # finaliz MSP da org, copia certs 
            linhas.append(f"finishOrgMSP '{org_base_dir}' '{org_base_dir}/users/Admin@{org_name}.{domain}/msp'")


        # -------------------- Processamento dos Orderers --------------------
        # tenta pegar config de CA do orderer, se não existir, define padrões
        ord_ca_conf = orderer_conf.get('ca', {})
        ord_ca_name = ord_ca_conf.get('name', 'ca-orderer')
        ord_ca_port = ord_ca_conf.get('port', 7054)

        # host da CA do orderer: IP real em modo distribuído/macvlan, localhost em modo local
        ord_ca_host = self._ca_host(ord_ca_conf, machines, self.allocator.orderer_ca_ip() if self.macvlan else None)
        ord_ca_url = f"http://{ord_ca_host}:{ord_ca_port}"

        # define home do client da CA do Orderer
        ord_ca_client_home = f"{self.paths.network_dir}/organizations/fabric-ca/ordererOrg/client"
        ord_base_dir = f"{self.paths.network_dir}/organizations/ordererOrganizations/{domain}"

        linhas.append(f"\n# --- Organização Orderer ({domain}, CA em {ord_ca_host}:{ord_ca_port}) ---")
        linhas.append(f"infoln 'Processando Orderer Org (CA: {ord_ca_name} em {ord_ca_host}:{ord_ca_port})'")

        linhas.append(f"mkdir -p {ord_base_dir}")
        linhas.append(f"mkdir -p {ord_ca_client_home}")
        linhas.append(f"export FABRIC_CA_CLIENT_HOME={ord_ca_client_home}")

        # realiza o enroll do ademir da CA do order
        linhas.append(f"infoln 'Bootstrap Admin CA Orderer ({ord_ca_host}:{ord_ca_port})...'")
        linhas.append(f"fabric-ca-client enroll -u http://admin:adminpw@{ord_ca_host}:{ord_ca_port} --caname {ord_ca_name}")

        # registra e matricula cada no do orderer
        for node in orderer_conf['nodes']:
            o_name = node['name']
            o_pass = f"{o_name}pw"
            o_full = f"{o_name}.{domain}"
            node_machine = node.get('machine')
            node_ip = machines.get(node_machine, {}).get('ip', '') if node_machine else ''
            if not node_ip and self.macvlan:
                node_ip = self.allocator.orderer_ip(o_name) or ''
            # chamada da funcao bash modular para orderer (7º arg: IP real p/ TLS SAN)
            linhas.append(f"registerAndEnrollOrdererNode '{o_name}' '{o_pass}' '{ord_ca_url}' '{ord_ca_name}' '{o_full}' '{ord_base_dir}' '{node_ip}'")

        # registra e matricula o admir do servico de ordenacao
        linhas.append(f"registerAndEnrollOrgAdmin 'ordererAdmin' 'ordererAdminpw' '{ord_ca_url}' '{ord_ca_name}' '{ord_base_dir}' 'Admin@{domain}'")

        # finaliza o MSP do orderer
        linhas.append(f"finishOrgMSP '{ord_base_dir}' '{ord_base_dir}/users/Admin@{domain}/msp'")
        
        # finalizacao e correcao de permissoes no sistema de arquivos 
        linhas.append('\nsuccessln "Todas as identidades foram geradas com sucesso!"')
        org_base_dir = f"{self.paths.network_dir}/organizations"
        linhas.append(f"\ninfoln 'Corrigindo permissões da pasta organizations...'")
        linhas.append(f"fix_permissions '{org_base_dir}'")
        
        # salva o script gerado no disco e define permissoes de execucao
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
    local ip=${7:-}   # IP real do nó — opcional, usado em modo distribuído para IP SANs

    infoln "[TLS] Gerando certificados para $hostname"

    # monta os --csr.hosts: sempre hostname + localhost; adiciona IP se fornecido
    local csr_hosts="--csr.hosts ${hostname} --csr.hosts localhost"
    if [ -n "$ip" ]; then
        csr_hosts="$csr_hosts --csr.hosts ${ip}"
    fi

    # enroll com perfil TLS
    fabric-ca-client enroll -u ${url} \\
        --caname "${ca_name}" \\
        -M "${tls_dir}" \\
        --enrollment.profile tls \\
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
    enrollTLS "${url//:\\/\\//://${name}:${secret}@}" "${ca_name}" "${tls_dir}" "${name}" "${secret}" "${hostname}" "${ip}"
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
    enrollTLS "${url//:\\/\\//://${name}:${secret}@}" "${ca_name}" "${tls_dir}" "${name}" "${secret}" "${hostname}" "${ip}"
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