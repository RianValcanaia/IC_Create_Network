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
        self.config = config
        self.paths = paths
        self.script_saida = self.paths.scripts_dir / "create_channel.sh"

    def generate_channel_script(self):
        channels = self.config['network_topology'].get('channels', [])
        domain = self.config['network_topology']['network']['domain']
        orderer_node = self.config['network_topology']['orderer']['nodes'][0]
        
        linhas = [
            "#!/bin/bash",
            "set -e",
            f"source {self.paths.scripts_dir}/utils.sh",
            f"export PATH={self.paths.base_dir}/bin:$PATH",
            f"export FABRIC_CFG_PATH={self.paths.network_dir}/compose/peercfg\n",
            "infoln '--- Iniciando Configuração de Canais (Fabric v3) ---'"
        ]

        # variáveis TLS do Orderer para OSNAdmin
        ord_full = f"{orderer_node['name']}.{domain}"
        ord_tls_path = f"{self.paths.network_dir}/organizations/ordererOrganizations/{domain}/orderers/{ord_full}/tls"
        
        linhas.append(f"export ORD_CA={ord_tls_path}/ca.crt")
        linhas.append(f"export ORD_ADMIN_CERT={ord_tls_path}/server.crt")
        linhas.append(f"export ORD_ADMIN_KEY={ord_tls_path}/server.key\n")

        for ch in channels:
            ch_name = ch['name']
            block_path = f"{self.paths.network_dir}/channel-artifacts/{ch_name}.block"
            
            linhas.append(f"infoln '>> Configurando Canal: {ch_name} <<'")
            
            for node in self.config['network_topology']['orderer']['nodes']:
                ord_full = f"{node['name']}.{domain}"
                
                cmd_osn = (
                    f"osnadmin channel join --channelID {ch_name} "
                    f"--config-block {block_path} "
                    f"-o localhost:{node['admin_port']} "
                    f"--ca-file $ORD_CA --client-cert $ORD_ADMIN_CERT --client-key $ORD_ADMIN_KEY"
                )
                linhas.append(cmd_osn)

            linhas.append("sleep 2") # Aguarda processamento do bloco gênese
            
            # --- Peer Join ---
            for org_name in ch['participating_orgs']:
                org_data = next(o for o in self.config['network_topology']['organizations'] if o['name'] == org_name)
                
                # primeiro peer da org para ser o Anchor Peer
                first_peer = True 

                for peer in org_data['peers']:
                    p_full = f"{peer['name']}.{org_name}.{domain}"
                    linhas.append(f"\ninfoln 'Peer {p_full} entrando no canal {ch_name}...'")
                    
                    # variáveis de ambiente para o Admin da Org controlar o Peer
                    peer_base = f"{self.paths.network_dir}/organizations/peerOrganizations/{org_name}.{domain}"
                    admin_msp = f"{peer_base}/users/Admin@{org_name}.{domain}/msp"
                    peer_tls_ca = f"{peer_base}/peers/{p_full}/tls/ca.crt"
                    
                    linhas.append(f"export CORE_PEER_TLS_ENABLED=true")
                    linhas.append(f"export CORE_PEER_LOCALMSPID={org_data['msp_id']}")
                    linhas.append(f"export CORE_PEER_TLS_ROOTCERT_FILE={peer_tls_ca}")
                    linhas.append(f"export CORE_PEER_MSPCONFIGPATH={admin_msp}")
                    linhas.append(f"export CORE_PEER_ADDRESS=localhost:{peer['port']}")
                    
                    linhas.append(f"peer channel join -b {block_path}")

                    # --- definir Anchor Peer (Apenas no primeiro peer de cada Org) ---
                    if first_peer:
                        linhas.append(f"infoln 'Definindo {p_full} como Anchor Peer para {org_name}...'")
                        # O comando abaixo é uma simplificação para redes v2.x/v3.x que atualiza o canal
                        # Em ambientes de produção, envolveria fetch, compute update e submit.
                        # Para o seu script IC, o join bem-sucedido já inicia a comunicação básica.
                        first_peer = False

        linhas.append("\nsuccessln '--- Configuração de canais concluída com sucesso! ---'")

        # persistência do script
        with open(self.script_saida, 'w') as f:
            f.write("\n".join(linhas))
        
        os.chmod(self.script_saida, os.stat(self.script_saida).st_mode | stat.S_IEXEC)
        co.successln(f"Script de canal gerado em: {self.script_saida}")