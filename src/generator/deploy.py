# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
Gerencia o ciclo de vida do chaincode no modelo Chaincode-as-a-Service (CCAAS). 
Ele cria o pacote do chaincode, gera o script deploy_chaincode.sh para instalação, 
aprovação e commit da definição no canal, além de iniciar o container do chaincode via Docker.

Rever: adicionar mais de um chaicode, tratar erros, validar estados.
"""

import os
import stat
import json
import tarfile
import io
from ..utils import Colors as co

class ChaincodeDeployGenerator:
    def __init__(self, config, paths):
        self.config = config
        self.paths = paths
        self.script_saida = self.paths.scripts_dir / "deploy_chaincode.sh"
        self._generate_collections_json()

    def generate(self):
        linhas = [
            "#!/bin/bash",
            "set -e",
            f"source {self.paths.scripts_dir}/utils.sh",
            f"export FABRIC_CFG_PATH={self.paths.network_dir}/compose/peercfg",
            f"export PATH={self.paths.base_dir}/bin:$PATH\n",
            "infoln '--- Iniciando Deploy de Chaincode ---'"
        ]

        for cc in self.config['network_topology']['chaincodes']:
            domain = self.config['network_topology']['network']['domain']
            orderer = self.config['network_topology']['orderer']['nodes'][0]
            
            network_name = self.config['network_topology']['network']['name']
            img_prefix = self.config['env_versions']['images']['org_hyperledger']
            fabric_version = self.config['env_versions']['versions']['fabric']

            package_file = (self.paths.chaincode_dir / f"{cc['name']}.tar.gz").resolve()
            pdc_config = (self.paths.chaincode_dir / f"{cc['name']}_collections.json").resolve()
            
            # caminho absoluto da pasta do chaincode vindo do Python
            abs_cc_path = self.paths.chaincode_dir / cc['name']
            
            self._create_ccaas_package(cc, package_file)

            # --- instalação ---
            for org in self.config['network_topology']['organizations']:
                for peer in org['peers']:
                    p_full = f"{peer['name']}.{org['name']}.{domain}"
                    linhas.append(f"infoln 'Instalando no {p_full}...'")
                    linhas.extend(self._get_peer_env(org, peer, domain))
                    linhas.append(f"peer lifecycle chaincode install {package_file}\n")

            # --- PACKAGE ID ---
            linhas.append(f"PACKAGE_ID=$(peer lifecycle chaincode queryinstalled | grep '{cc['name']}_{cc['version']}' | head -n 1 | sed -n 's/^Package ID: //; s/, Label:.*$//p')")
            
            cc_service = f"{cc['name']}.{cc['channel']}"
            linhas.append(f"docker rm -f {cc_service} 2>/dev/null || true")
            
            # usando caminho absoluto direto do PathManager
            linhas.append(f"fix_permissions '{abs_cc_path}'")

            # substituido $(pwd) pelo caminho absoluto injetado pelo Python
            linhas.append(f"docker run -d --name {cc_service} --network {network_name}_net "
                        f"-e CHAINCODE_SERVER_ADDRESS=0.0.0.0:9999 "
                        f"-e CORE_CHAINCODE_ID_NAME=$PACKAGE_ID "
                        f"-v {abs_cc_path}:/opt/gopath/src/chaincode "
                        f"{img_prefix}/fabric-ccenv:{fabric_version} "
                        f"sh -c 'cd /opt/gopath/src/chaincode && go mod tidy && go build -o chaincode && ./chaincode'")

            # --- aprovação e Commit ---
            ord_tls_ca = (self.paths.network_dir / "organizations" / "ordererOrganizations" / domain / "orderers" / f"{orderer['name']}.{domain}" / "tls" / "ca.crt").resolve()

            for org in self.config['network_topology']['organizations']:
                linhas.append(f"\ninfoln 'Aprovando definição para {org['name']}...'")
                linhas.extend(self._get_peer_env(org, org['peers'][0], domain))
                
                approve_cmd = (
                    f"peer lifecycle chaincode approveformyorg "
                    f"-o localhost:{orderer['port']} --ordererTLSHostnameOverride {orderer['name']}.{domain} "
                    f"--tls --cafile {ord_tls_ca} --channelID {cc['channel']} --name {cc['name']} "
                    f"--version {cc['version']} --package-id $PACKAGE_ID --sequence {cc['sequence']} "
                    f"--collections-config {pdc_config} "
                    f"--signature-policy \"{cc['endorsement_policy']}\""
                )
                linhas.append(approve_cmd)

            # montagem do Commit
            peer_addresses = ""
            tls_root_cas = ""
            for org in self.config['network_topology']['organizations']:
                peer = org['peers'][0]
                peer_addresses += f" --peerAddresses localhost:{peer['port']}"
                tls_ca = (self.paths.network_dir / "organizations" / "peerOrganizations" / f"{org['name']}.{domain}" / "peers" / f"{peer['name']}.{org['name']}.{domain}" / "tls" / "ca.crt").resolve()
                tls_root_cas += f" --tlsRootCertFiles {tls_ca}"

            commit_cmd = (
                f"peer lifecycle chaincode commit "
                f"-o localhost:{orderer['port']} --ordererTLSHostnameOverride {orderer['name']}.{domain} "
                f"--tls --cafile {ord_tls_ca} --channelID {cc['channel']} --name {cc['name']} "
                f"--version {cc['version']} --sequence {cc['sequence']} "
                f"--collections-config {pdc_config} "
                f"--signature-policy \"{cc['endorsement_policy']}\" "
                f"{peer_addresses} {tls_root_cas}"
            )
            linhas.append(commit_cmd)
            linhas.append(f"\nsuccessln 'Deploy do chaincode {cc['name']} concluído com sucesso!'")

        # escrita do arquivo movida para o final (após processar todos os CCs)
        with open(self.script_saida, 'w') as f:
            f.write("\n".join(linhas))
        os.chmod(self.script_saida, os.stat(self.script_saida).st_mode | stat.S_IEXEC)

    # helper para importar variaveis de ambiente do peer
    def _get_peer_env(self, org, peer, domain):
        p_full = f"{peer['name']}.{org['name']}.{domain}"
        peer_base = (self.paths.network_dir / "organizations" / "peerOrganizations" / f"{org['name']}.{domain}").resolve()
        return [
            f"export CORE_PEER_TLS_ENABLED=true",
            f"export CORE_PEER_LOCALMSPID={org['msp_id']}",
            f"export CORE_PEER_TLS_ROOTCERT_FILE={peer_base}/peers/{p_full}/tls/ca.crt",
            f"export CORE_PEER_MSPCONFIGPATH={peer_base}/users/Admin@{org['name']}.{domain}/msp",
            f"export CORE_PEER_ADDRESS=localhost:{peer['port']}"
        ]
    
    def _generate_collections_json(self):
        for cc in self.config['network_topology']['chaincodes']:
            collections = []
            for pdc_info in cc.get('pdc', []):
                collections.append({
                    "name": pdc_info['name'],
                    "policy": pdc_info['policy'],
                    "requiredPeerCount": pdc_info['required_peer_count'],
                    "maxPeerCount": pdc_info['max_peer_count'],
                    "blockToLive": pdc_info['block_to_live'],
                    "memberOnlyRead": True if 'member' in pdc_info['member_only_read'] else False,
                    "memberOnlyWrite": True if 'member' in pdc_info['member_only_write'] else False
                })
            # salva um ficheiro por chaincode
            output_path = self.paths.chaincode_dir / f"{cc['name']}_collections.json"
            with open(output_path, 'w') as f:
                json.dump(collections, f, indent=4)

    def _create_ccaas_package(self, cc, output_path):
        connection = {
            "address": f"{cc['name']}.{cc['channel']}:9999",
            "dial_timeout": "10s",
            "tls_required": False
        }
        
        metadata = {
            "type": "ccaas",
            "label": f"{cc['name']}_{cc['version']}"
        }

        with tarfile.open(output_path, "w:gz") as outer_tar:
            
            code_tar_buffer = io.BytesIO()
            with tarfile.open(fileobj=code_tar_buffer, mode="w:gz") as inner_tar:
                data_conn = json.dumps(connection).encode('utf-8')
                info_conn = tarfile.TarInfo(name="connection.json")
                info_conn.size = len(data_conn)
                inner_tar.addfile(info_conn, io.BytesIO(data_conn))
            
            data_meta = json.dumps(metadata).encode('utf-8')
            info_meta = tarfile.TarInfo(name="metadata.json")
            info_meta.size = len(data_meta)
            outer_tar.addfile(info_meta, io.BytesIO(data_meta))

            code_tar_bytes = code_tar_buffer.getvalue()
            info_code = tarfile.TarInfo(name="code.tar.gz")
            info_code.size = len(code_tar_bytes)
            outer_tar.addfile(info_code, io.BytesIO(code_tar_bytes))
        
        co.successln(f"Pacote CCAAS corrigido gerado em: {output_path}")