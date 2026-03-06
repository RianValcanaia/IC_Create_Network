# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
Responsável pela orquestração da entrada dos nós nos canais 
através do script create_channel.sh. Ele automatiza o uso do 
osnadmin para o join dos Orderers e do comando peer channel 
join para que os Peers participem dos canais definidos na topologia.
"""
import os
import stat
from ..utils import Colors as co

class ChannelScriptGenerator:
    def __init__(self, config, paths):
        # inicializa a referencia de caminhos
        self.config = config
        self.paths = paths

        # caminho do script de saída
        self.script_saida = self.paths.scripts_dir / "create_channel.sh"

    def generate_channel_script(self):
        # coleta dados da topologia
        channels = self.config['network_topology'].get('channels', [])
        domain = self.config['network_topology']['network']['domain']
        orderer_node = self.config['network_topology']['orderer']['nodes'][0]
        
        linhas = [
            "#!/bin/bash",
            "set -e",  # para a execucao em caso de erro
            f"source {self.paths.scripts_dir}/utils.sh",
            f"export PATH={self.paths.base_dir}/bin:$PATH",
            f"export FABRIC_CFG_PATH={self.paths.network_dir}/compose/peercfg\n",
            self._get_anchor_peer_bash_function(),
            "headerln 'Iniciando Configuração de Canais (Fabric v3)'"
        ]

        # define variaveis de ambiente TLs para que o script possa falar com o orderer
        ord_full = f"{orderer_node['name']}.{domain}"
        ord_tls_path = f"{self.paths.network_dir}/organizations/ordererOrganizations/{domain}/orderers/{ord_full}/tls"
        ord_address = f"localhost:{orderer_node['port']}"
        
        linhas.append(f"export ORD_CA={ord_tls_path}/ca.crt")
        linhas.append(f"export ORD_ADMIN_CERT={ord_tls_path}/server.crt")
        linhas.append(f"export ORD_ADMIN_KEY={ord_tls_path}/server.key\n")

        for node in self.config['network_topology']['orderer']['nodes']:
            node_full = f"{node['name']}.{domain}"
            node_tls = f"{self.paths.network_dir}/organizations/ordererOrganizations/{domain}/orderers/{node_full}/tls"
            node_name = node['name']  # ← extrai antes
            linhas.append(
                f"until curl -sk "
                f"--cert {node_tls}/server.crt "
                f"--key {node_tls}/server.key "
                f"--cacert {node_tls}/ca.crt "
                f"https://localhost:{node['admin_port']}/participation/v1/channels "
                f">/dev/null 2>&1; do "
                f"echo 'Aguardando {node_name}...'; sleep 2; done"
            )

        # itera sobre os canais definidos na topologia
        for ch in channels:
            ch_name = ch['name']
            block_path = f"{self.paths.network_dir}/channel-artifacts/{ch_name}.block"
            
            linhas.append(f"infoln '>> Configurando Canal: {ch_name} <<'")
            
            # 1. faz todos os orderers entrarem no canal usando osnadmin
            for node in self.config['network_topology']['orderer']['nodes']:
                node_full = f"{node['name']}.{domain}"
                node_tls_path = f"{self.paths.network_dir}/organizations/ordererOrganizations/{domain}/orderers/{node_full}/tls"
                
                cmd_osn = (
                    f"osnadmin channel join --channelID {ch_name} "
                    f"--config-block {block_path} -o localhost:{node['admin_port']} "
                    f"--ca-file {node_tls_path}/ca.crt "
                    f"--client-cert {node_tls_path}/server.crt "
                    f"--client-key {node_tls_path}/server.key"
                )
                linhas.append(cmd_osn)

            linhas.append("sleep 2") # pausa para a estabilizacao da rede
            
            # 2. Faz os peers entrarem no canal
            for org_name in ch['participating_orgs']:
                # pega os dados da organizacao participante
                org_data = next(o for o in self.config['network_topology']['organizations'] if o['name'] == org_name)
                
                # para cada peer da org, gera comandos de join no canal, e se for o primeiro peer, define ele como Anchor Peer
                for idx, peer in enumerate(org_data['peers']):
                    p_full = f"{peer['name']}.{org_name}.{domain}"
                    peer_base = f"{self.paths.network_dir}/organizations/peerOrganizations/{org_name}.{domain}"
                    
                    linhas.append(f"\n# --- Configurando Peer {p_full} ---")
                    linhas.append(f"export CORE_PEER_LOCALMSPID={org_data['msp_id']}")
                    linhas.append(f"export CORE_PEER_TLS_ROOTCERT_FILE={peer_base}/peers/{p_full}/tls/ca.crt")
                    linhas.append(f"export CORE_PEER_MSPCONFIGPATH={peer_base}/users/Admin@{org_name}.{domain}/msp")
                    linhas.append(f"export CORE_PEER_ADDRESS=localhost:{peer['port']}")
                    
                    linhas.append(f"peer channel join -b {block_path}")

                    if idx == 0:
                        linhas.append(f"updateAnchorPeer '{org_name}' '{org_data['msp_id']}' '{ch_name}' '{peer['name']}' '{peer['port']}' '{ord_address}'")

        # salva o arquivo
        with open(self.script_saida, 'w') as f:
            f.write("\n".join(linhas))
        os.chmod(self.script_saida, os.stat(self.script_saida).st_mode | stat.S_IEXEC)

    def _get_anchor_peer_bash_function(self):
        return """
function updateAnchorPeer() {
    local org=$1; local msp=$2; local channel=$3; local peer_name=$4; local port=$5; local orderer=$6
    infoln "Definindo Anchor Peer para ${org} no canal ${channel}..."

    # 1. Fetch config
    peer channel fetch config config_block.pb -o ${orderer} -c ${channel} --tls --cafile $ORD_CA
    
    # 2. Decode e extrair a parte da config
    configtxlator proto_decode --input config_block.pb --type common.Block --output config_block.json
    jq '.data.data[0].payload.data.config' config_block.json > config.json

    # 3. Adicionar o anchor peer no JSON
    jq '.channel_group.groups.Application.groups.'${msp}'.values += {"AnchorPeers": {"mod_policy": "Admins","value": {"anchor_peers": [{"host": "'${peer_name}.${org}'.exemplo.com","port": '${port}'}]},"version": "0"}}' config.json > config_updated.json

    # 4. Re-encode e calcular delta
    configtxlator proto_encode --input config.json --type common.Config --output config.pb
    configtxlator proto_encode --input config_updated.json --type common.Config --output config_updated.pb
    configtxlator compute_update --channel_id ${channel} --original config.pb --updated config_updated.pb --output anchor_update.pb

    # 5. Criar envelope e submeter
    configtxlator proto_decode --input anchor_update.pb --type common.ConfigUpdate --output anchor_update.json
    echo '{"payload":{"header":{"channel_header":{"channel_id":"'$channel'", "type":2}},"data":{"config_update":'$(cat anchor_update.json)'}}}' | jq . > anchor_update_envelope.json
    configtxlator proto_encode --input anchor_update_envelope.json --type common.Envelope --output anchor_update_envelope.pb

    peer channel update -f anchor_update_envelope.pb -c ${channel} -o ${orderer} --tls --cafile $ORD_CA
    successln "Anchor Peer para ${org} atualizado!"
    rm *.json *.pb
}
"""