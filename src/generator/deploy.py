import os
import stat
from ..utils import Colors as co

class ChaincodeDeployGenerator:
    def __init__(self, config, paths):
        self.config = config
        self.paths = paths
        self.script_saida = self.paths.scripts_dir / "deploy_chaincode.sh"

    def generate(self):
        # passos:
        # 1 - Instalar chaincode em todos os peers
        # 2 - Aprovar definição por cada org
        # 3 - Commit da definição no canal
        # 4 - Rezar para que deu certo :)

        # primeiro chaincode da lista, !!!!!!!!!!!!!! verificar demais implementações depois !!!!!!!!!!!!!
        cc = self.config['chaincodes'][0]
        domain = self.config['network_topology']['network']['domain']
        orderer = self.config['network_topology']['orderer']['nodes'][0]
        
        # path dos artefatos
        package_file = f"./chaincode/{cc['name']}.tar.gz"
        pdc_config = f"./chaincode/{cc['name']}_collections.json"
        
        linhas = [
            "#!/bin/bash",
            "set -e",
            f"source {self.paths.scripts_dir}/utils.sh",
            f"export FABRIC_CFG_PATH={self.paths.network_dir}/compose/peercfg",
            f"export PATH={self.paths.base_dir}/bin:$PATH\n",
            "infoln '--- Iniciando Deploy de Chaincode ---'"
        ]

        # --- Instalacao em todos os peers ---
        for org in self.config['network_topology']['organizations']:
            for peer in org['peers']:
                p_full = f"{peer['name']}.{org['name']}.{domain}"
                linhas.append(f"infoln 'Instalando no {p_full}...'")
                linhas.extend(self._get_peer_env(org, peer, domain))
                linhas.append(f"peer lifecycle chaincode install {package_file}")

        # --- Consultar Package ID ---
        linhas.append("\ninfoln 'Buscando Package ID...'")
        linhas.append(f"PACKAGE_ID=$(peer lifecycle chaincode queryinstalled | grep '{cc['name']}_{cc['version']}' | cut -d' ' -f3 | cut -d',' -f1)")
        linhas.append("if [ -z \"$PACKAGE_ID\" ]; then errorln 'Package ID não encontrado'; exit 1; fi")
        linhas.append("successln \"Package ID: $PACKAGE_ID\"")

        # --- Aprovação por cada org ---
        # a maioria das orgs devem aprovar a definicao
        ord_tls_ca = f"./network/organizations/ordererOrganizations/{domain}/orderers/{orderer['name']}.{domain}/tls/ca.crt"
        
        for org in self.config['network_topology']['organizations']:
            linhas.append(f"\ninfoln 'Aprovando definição para {org['name']}...'")
            linhas.extend(self._get_peer_env(org, org['peers'][0], domain))
            
            approve_cmd = (
                f"peer lifecycle chaincode approveformyorg "
                f"-o localhost:{orderer['port']} --ordererTLSHostnameOverride {orderer['name']}.{domain} "
                f"--tls --cafile {ord_tls_ca} --channelID {cc['channel']} --name {cc['name']} "
                f"--version {cc['version']} --package-id $PACKAGE_ID --sequence {cc['sequence']} "
                f"--collections-config {pdc_config}"
            )
            linhas.append(approve_cmd)

        # --- Commit da definicao ---
        linhas.append(f"\ninfoln 'Realizando Commit do Chaincode no canal {cc['channel']}...'")
        
        # Monta a string de peerAddresses para o commit
        peer_addresses = ""
        tls_root_cas = ""
        for org in self.config['network_topology']['organizations']:
            peer = org['peers'][0]
            peer_addresses += f" --peerAddresses localhost:{peer['port']}"
            tls_ca = f"./network/organizations/peerOrganizations/{org['name']}.{domain}/peers/{peer['name']}.{org['name']}.{domain}/tls/ca.crt"
            tls_root_cas += f" --tlsRootCertFiles {tls_ca}"

        commit_cmd = (
            f"peer lifecycle chaincode commit "
            f"-o localhost:{orderer['port']} --ordererTLSHostnameOverride {orderer['name']}.{domain} "
            f"--tls --cafile {ord_tls_ca} --channelID {cc['channel']} --name {cc['name']} "
            f"--version {cc['version']} --sequence {cc['sequence']} "
            f"--collections-config {pdc_config}"
            f"{peer_addresses} {tls_root_cas}"
        )
        linhas.append(commit_cmd)
        
        linhas.append(f"\nsuccessln 'Deploy do chaincode {cc['name']} concluído com sucesso!'")

        with open(self.script_saida, 'w') as f:
            f.write("\n".join(linhas))
        os.chmod(self.script_saida, os.stat(self.script_saida).st_mode | stat.S_IEXEC)

    # helper para importar variaveis de ambiente do peer
    def _get_peer_env(self, org, peer, domain):
        p_full = f"{peer['name']}.{org['name']}.{domain}"
        peer_base = f"./network/organizations/peerOrganizations/{org['name']}.{domain}"
        return [
            f"export CORE_PEER_TLS_ENABLED=true",
            f"export CORE_PEER_LOCALMSPID={org['msp_id']}",
            f"export CORE_PEER_TLS_ROOTCERT_FILE={peer_base}/peers/{p_full}/tls/ca.crt",
            f"export CORE_PEER_MSPCONFIGPATH={peer_base}/users/Admin@{org['name']}.{domain}/msp",
            f"export CORE_PEER_ADDRESS=localhost:{peer['port']}"
        ]