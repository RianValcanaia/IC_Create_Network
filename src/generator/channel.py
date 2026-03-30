# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
Responsável pela orquestração da entrada dos nós nos canais
através do script create_channel.sh. Ele automatiza o uso do
osnadmin para o join dos Orderers e do comando peer channel
join para que os Peers participem dos canais definidos na topologia.

Suporte a deploy distribuído:
  Quando a seção 'machines' está definida no network.yaml e cada componente
  possui o campo 'machine', os endereços de orderers e peers são gerados com
  os IPs reais de cada máquina em vez de 'localhost'. Isso permite executar
  create_channel.sh de qualquer nó do cluster com acesso à LAN. Sem
  'machines', o comportamento é idêntico ao original (localhost).
"""
import os
import stat
from ..utils import Colors as co

class ChannelScriptGenerator:
    def __init__(self, config, paths, distributed=False):
        # inicializa a referencia de caminhos
        self.config = config
        self.paths = paths

        # quando True, usa os IPs reais da seção 'machines' do network.yaml;
        # quando False (padrão / modo local), todos os endereços usam 'localhost'.
        self.distributed = distributed

        # caminho do script de saída
        self.script_saida = self.paths.scripts_dir / "create_channel.sh"

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers de endereçamento distribuído
    # ──────────────────────────────────────────────────────────────────────────

    def _peer_address(self, peer, machines):
        """
        Retorna HOST:PORTA do peer para CORE_PEER_ADDRESS.

        Em modo local retorna 'localhost:{porta}'. Em modo distribuído retorna
        '{ip_real}:{porta}', permitindo que 'peer channel join' alcance peers
        em outras máquinas da LAN a partir da máquina que executa o script.
        """
        machine_name = peer.get('machine')
        if machine_name and machine_name in machines:
            return f"{machines[machine_name]['ip']}:{peer['port']}"
        return f"localhost:{peer['port']}"

    def _orderer_grpc_address(self, node, machines):
        """
        Retorna HOST:PORTA do orderer para a porta GRPC principal.
        Usada em 'peer channel fetch config -o' e 'peer channel update -o'
        (dentro da função updateAnchorPeer do script bash gerado).
        """
        machine_name = node.get('machine')
        if machine_name and machine_name in machines:
            return f"{machines[machine_name]['ip']}:{node['port']}"
        return f"localhost:{node['port']}"

    def _orderer_admin_address(self, node, machines):
        """
        Retorna HOST:PORTA do orderer para a porta de administração (admin_port).
        Usada em 'osnadmin channel join -o' e no loop de health check (curl).
        A porta admin é separada da GRPC principal no Fabric v3 com osnadmin.
        """
        machine_name = node.get('machine')
        if machine_name and machine_name in machines:
            return f"{machines[machine_name]['ip']}:{node['admin_port']}"
        return f"localhost:{node['admin_port']}"

    # ──────────────────────────────────────────────────────────────────────────
    # Geração do script de configuração de canais
    # ──────────────────────────────────────────────────────────────────────────

    def generate_channel_script(self):
        # coleta dados da topologia
        channels = self.config['network_topology'].get('channels', [])
        domain = self.config['network_topology']['network']['domain']
        orderer_node = self.config['network_topology']['orderer']['nodes'][0]

        # em modo local (distributed=False), machines fica vazio e todos os
        # endereços caem no fallback 'localhost' dos helpers.
        machines = self.config['network_topology'].get('machines', {}) if self.distributed else {}

        linhas = [
            "#!/bin/bash",
            "set -e",  # para a execucao em caso de erro
            f"source {self.paths.scripts_dir}/utils.sh",
            f"export PATH={self.paths.base_dir}/bin:$PATH",
            f"export FABRIC_CFG_PATH={self.paths.network_dir}/compose/peercfg\n",
            self._get_anchor_peer_bash_function(domain),
            "headerln 'Iniciando Configuração de Canais (Fabric v3)'"
        ]

        # endereço GRPC do orderer principal usado em peer channel fetch/update
        # (dentro da função bash updateAnchorPeer). Em modo distribuído usa IP real.
        ord_full    = f"{orderer_node['name']}.{domain}"
        ord_tls_path = f"{self.paths.network_dir}/organizations/ordererOrganizations/{domain}/orderers/{ord_full}/tls"
        ord_address = self._orderer_grpc_address(orderer_node, machines)

        linhas.append(f"export ORD_CA={ord_tls_path}/ca.crt")
        linhas.append(f"export ORD_ADMIN_CERT={ord_tls_path}/server.crt")
        linhas.append(f"export ORD_ADMIN_KEY={ord_tls_path}/server.key\n")

        # loop de health check: aguarda cada orderer responder na porta admin antes
        # de tentar o join. Em modo distribuído usa o IP real de cada máquina.
        for node in self.config['network_topology']['orderer']['nodes']:
            node_full  = f"{node['name']}.{domain}"
            node_tls   = f"{self.paths.network_dir}/organizations/ordererOrganizations/{domain}/orderers/{node_full}/tls"
            node_name  = node['name']
            admin_addr = self._orderer_admin_address(node, machines)
            linhas.append(
                f"until curl -sk "
                f"--cert {node_tls}/server.crt "
                f"--key {node_tls}/server.key "
                f"--cacert {node_tls}/ca.crt "
                f"https://{admin_addr}/participation/v1/channels "
                f">/dev/null 2>&1; do "
                f"echo 'Aguardando {node_name}...'; sleep 2; done"
            )

        # itera sobre os canais definidos na topologia
        for ch in channels:
            ch_name = ch['name']
            block_path = f"{self.paths.network_dir}/channel-artifacts/{ch_name}.block"
            
            linhas.append(f"infoln '>> Configurando Canal: {ch_name} <<'")
            
            # 1. faz todos os orderers entrarem no canal usando osnadmin
            # osnadmin usa a porta admin (não a GRPC), endereçada pelo IP real
            # de cada máquina em modo distribuído.
            for node in self.config['network_topology']['orderer']['nodes']:
                node_full     = f"{node['name']}.{domain}"
                node_tls_path = f"{self.paths.network_dir}/organizations/ordererOrganizations/{domain}/orderers/{node_full}/tls"
                admin_addr    = self._orderer_admin_address(node, machines)

                cmd_osn = (
                    f"osnadmin channel join --channelID {ch_name} "
                    f"--config-block {block_path} -o {admin_addr} "
                    f"--ca-file {node_tls_path}/ca.crt "
                    f"--client-cert {node_tls_path}/server.crt "
                    f"--client-key {node_tls_path}/server.key"
                )
                linhas.append(cmd_osn)

            linhas.append("sleep 2") # pausa para a estabilizacao da rede

            # 2. Faz os peers entrarem no canal
            # CORE_PEER_ADDRESS usa o IP real de cada peer em modo distribuído,
            # permitindo que o comando 'peer channel join' alcance peers remotos.
            for org_name in ch['participating_orgs']:
                org_data = next(o for o in self.config['network_topology']['organizations'] if o['name'] == org_name)

                for idx, peer in enumerate(org_data['peers']):
                    p_full    = f"{peer['name']}.{org_name}.{domain}"
                    peer_base = f"{self.paths.network_dir}/organizations/peerOrganizations/{org_name}.{domain}"

                    linhas.append(f"\n# --- Configurando Peer {p_full} ({self._peer_address(peer, machines)}) ---")
                    linhas.append(f"export CORE_PEER_LOCALMSPID={org_data['msp_id']}")
                    linhas.append(f"export CORE_PEER_TLS_ROOTCERT_FILE={peer_base}/peers/{p_full}/tls/ca.crt")
                    linhas.append(f"export CORE_PEER_MSPCONFIGPATH={peer_base}/users/Admin@{org_name}.{domain}/msp")
                    linhas.append(f"export CORE_PEER_ADDRESS={self._peer_address(peer, machines)}")

                    linhas.append(f"peer channel join -b {block_path}")

                    if idx == 0:
                        linhas.append(f"updateAnchorPeer '{org_name}' '{org_data['msp_id']}' '{ch_name}' '{peer['name']}' '{peer['port']}' '{ord_address}'")

        # salva o arquivo
        with open(self.script_saida, 'w') as f:
            f.write("\n".join(linhas))
        os.chmod(self.script_saida, os.stat(self.script_saida).st_mode | stat.S_IEXEC)

    def _get_anchor_peer_bash_function(self, domain):
        # o domínio é injetado em tempo de geração do script (Python), não em
        # tempo de execução bash — assim o script funciona para qualquer domínio
        # definido no network.yaml, sem hardcode.
        template = (
            "\nfunction updateAnchorPeer() {\n"
            "    local org=$1; local msp=$2; local channel=$3; local peer_name=$4; local port=$5; local orderer=$6\n"
            '    infoln "Definindo Anchor Peer para ${org} no canal ${channel}..."\n'
            "\n"
            "    # 1. Fetch config\n"
            "    peer channel fetch config config_block.pb -o ${orderer} -c ${channel} --tls --cafile $ORD_CA\n"
            "    \n"
            "    # 2. Decode e extrair a parte da config\n"
            "    configtxlator proto_decode --input config_block.pb --type common.Block --output config_block.json\n"
            "    jq '.data.data[0].payload.data.config' config_block.json > config.json\n"
            "\n"
            "    # 3. Adicionar o anchor peer no JSON\n"
            "    jq '.channel_group.groups.Application.groups.'${msp}'.values += {\"AnchorPeers\": {\"mod_policy\": \"Admins\",\"value\": {\"anchor_peers\": [{\"host\": \"'${peer_name}.${org}'.NETWORK_DOMAIN\",\"port\": '${port}'}]},\"version\": \"0\"}}' config.json > config_updated.json\n"
            "\n"
            "    # 4. Re-encode e calcular delta\n"
            "    configtxlator proto_encode --input config.json --type common.Config --output config.pb\n"
            "    configtxlator proto_encode --input config_updated.json --type common.Config --output config_updated.pb\n"
            "    configtxlator compute_update --channel_id ${channel} --original config.pb --updated config_updated.pb --output anchor_update.pb\n"
            "\n"
            "    # 5. Criar envelope e submeter\n"
            "    configtxlator proto_decode --input anchor_update.pb --type common.ConfigUpdate --output anchor_update.json\n"
            '    echo \'{"payload":{"header":{"channel_header":{"channel_id":"\'$channel\'", "type":2}},"data":{"config_update":\'$(cat anchor_update.json)\'}}}\' | jq . > anchor_update_envelope.json\n'
            "    configtxlator proto_encode --input anchor_update_envelope.json --type common.Envelope --output anchor_update_envelope.pb\n"
            "\n"
            "    peer channel update -f anchor_update_envelope.pb -c ${channel} -o ${orderer} --tls --cafile $ORD_CA\n"
            '    successln "Anchor Peer para ${org} atualizado!"\n'
            "    rm *.json *.pb\n"
            "}\n"
        )
        return template.replace('NETWORK_DOMAIN', domain)