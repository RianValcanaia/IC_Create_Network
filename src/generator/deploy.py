# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
Gerencia o ciclo de vida do chaincode no modelo Chaincode-as-a-Service (CCAAS).
Ele cria o pacote do chaincode, gera o script deploy_chaincode.sh para instalação,
aprovação e commit da definição no canal, além de iniciar o container do chaincode
via Docker.

Suporte a deploy distribuído:
  Quando a seção 'machines' está definida no network.yaml e cada componente possui
  o campo 'machine', os comandos CLI do Fabric (install, approve, commit) são gerados
  com os IPs reais de cada peer/orderer na LAN, em vez de 'localhost'. Isso permite
  que o script seja executado de qualquer máquina do cluster e alcance todos os nós.
  Sem a seção 'machines' (modo local), o comportamento é idêntico ao original.
"""

import os
import stat
import json
import tarfile
import io
from ..utils import Colors as co

# ── Constantes para atribuição automática de portas de operações (métricas) ──
PEER_OPS_PORT_BASE    = 9200
ORDERER_OPS_PORT_BASE = 9210


def assign_ops_ports(config: dict) -> dict:
    """
    Atribui automaticamente portas de operações (Prometheus) a peers e orderers.
    Chamado logo após o load() em main.py para que o ComposeGenerator já receba
    o config com ops_port em cada nó.
    """
    port = PEER_OPS_PORT_BASE
    for org in config.get('network_topology', config).get('organizations', []):
        for peer in org.get('peers', []):
            port += 1
            peer['ops_port'] = port

    port = ORDERER_OPS_PORT_BASE
    orderer_cfg = config.get('network_topology', config).get('orderer', {})
    for orderer in orderer_cfg.get('nodes', []):
        port += 1
        orderer['ops_port'] = port

    return config


class ChaincodeDeployGenerator:
    def __init__(self, config, paths, distributed=False):
        self.config = config
        self.paths = paths

        # quando True, usa os IPs reais da seção 'machines' do network.yaml;
        # quando False (padrão / modo local), todos os endereços usam 'localhost'.
        self.distributed = distributed

        self.script_saida = self.paths.scripts_dir / "deploy_chaincode.sh"
        self._generate_collections_json()

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers de endereçamento distribuído
    # ──────────────────────────────────────────────────────────────────────────

    def _peer_address(self, peer, machines):
        """
        Retorna o endereço de rede de um peer no formato HOST:PORTA.

        Em modo local (campo 'machine' ausente no peer ou seção 'machines'
        ausente no network.yaml), retorna 'localhost:{porta}' — comportamento
        original, sem quebrar deployments locais existentes.

        Em modo distribuído, retorna '{ip_real}:{porta}', onde o IP vem da
        seção 'machines' do network.yaml. Isso permite que comandos CLI como
        'peer lifecycle chaincode install' e 'peer lifecycle chaincode commit'
        sejam executados de qualquer ponto da LAN e alcancem o peer correto,
        independentemente de em qual máquina o script está rodando.
        """
        machine_name = peer.get('machine')
        if machine_name and machine_name in machines:
            return f"{machines[machine_name]['ip']}:{peer['port']}"
        return f"localhost:{peer['port']}"

    def _orderer_address(self, orderer, machines):
        """
        Retorna o endereço de rede de um orderer no formato HOST:PORTA.

        Mesma lógica de _peer_address: fallback para 'localhost' em modo local,
        IP real em modo distribuído. Usado nas flags '-o' dos comandos
        'approveformyorg' e 'commit'.
        """
        machine_name = orderer.get('machine')
        if machine_name and machine_name in machines:
            return f"{machines[machine_name]['ip']}:{orderer['port']}"
        return f"localhost:{orderer['port']}"

    # ──────────────────────────────────────────────────────────────────────────
    # Geração do script de deploy completo (lifecycle + startup do container)
    # ──────────────────────────────────────────────────────────────────────────

    def generate(self):
        """
        Gera deploy_chaincode.sh com o ciclo de vida completo de cada chaincode:
          1. Compilação local (Go → Linux AMD64)
          2. Empacotamento CCAAS (.tar.gz)
          3. Install em cada peer de cada org
          4. Startup do container CCAAS
          5. Approve por org
          6. Commit no canal

        Em modo distribuído, cada peer e orderer é endereçado pelo IP real da
        sua máquina (via _peer_address / _orderer_address), permitindo que o
        script rode de qualquer nó do cluster.
        """
        # em modo local (distributed=False), machines fica vazio e todos os
        # endereços caem no fallback 'localhost' dos helpers.
        machines = self.config['network_topology'].get('machines', {}) if self.distributed else {}

        domain       = self.config['network_topology']['network']['domain']
        network_name = self.config['network_topology']['network']['name']
        img_prefix   = self.config['env_versions']['images']['org_hyperledger']
        fabric_version = self.config['env_versions']['versions']['fabric']

        # Orderer usado para approve e commit — usa o primeiro da lista.
        # Em SmartBFT qualquer orderer pode receber transações de gestão.
        orderer = self.config['network_topology']['orderer']['nodes'][0]

        linhas = [
            "#!/bin/bash",
            "set -e",
            f"source {self.paths.scripts_dir}/utils.sh",
            f"export FABRIC_CFG_PATH={self.paths.network_dir}/compose/peercfg",
            f"export PATH={self.paths.base_dir}/bin:$PATH\n",
            "infoln '--- Iniciando Deploy de Chaincode ---'"
        ]

        for cc in self.config['network_topology']['chaincodes']:
            package_file = (self.paths.chaincode_dir / f"{cc['name']}.tar.gz").resolve()
            pdc_config   = (self.paths.chaincode_dir / f"{cc['name']}_collections.json").resolve()
            abs_cc_path  = self.paths.chaincode_dir / cc['name']
            cc_port      = cc['port']
            cc_service   = f"{cc['name']}.{cc['channel']}"

            # TLS CA do orderer usado em approve/commit
            ord_tls_ca = (
                self.paths.network_dir / "organizations" / "ordererOrganizations"
                / domain / "orderers" / f"{orderer['name']}.{domain}" / "tls" / "ca.crt"
            ).resolve()

            # Compila o binário Go localmente para Linux antes de empacotar
            # go_bin_dir: procura Go em <base_dir>/../go/bin (NFS do cluster)
            # e cai no PATH do sistema se não encontrar.
            go_bin_dir = self.paths.base_dir.parent / "go" / "bin"
            go_cmd = str(go_bin_dir / "go") if (go_bin_dir / "go").exists() else "go"
            co.infoln(f"Compilando chaincode {cc['name']} localmente para Linux...")
            os.system(
                f"cd {abs_cc_path} && "
                f"GOOS=linux GOARCH=amd64 {go_cmd} build -o chaincode"
            )

            self._create_ccaas_package(cc, package_file)

            # ── 1. Install em cada peer de cada org ───────────────────────────
            # Cada peer precisa ter o pacote instalado individualmente.
            # CORE_PEER_ADDRESS aponta para o IP real do peer (ou localhost em
            # modo local), garantindo alcance em deployments distribuídos.
            cc_name    = cc['name']
            cc_channel = cc['channel']
            linhas.append(f"\ninfoln '=== Chaincode: {cc_name} ==='")
            for org in self.config['network_topology']['organizations']:
                for peer in org['peers']:
                    p_full = f"{peer['name']}.{org['name']}.{domain}"
                    linhas.append(f"infoln 'Instalando em {p_full} ({self._peer_address(peer, machines)})...'")
                    linhas.extend(self._get_peer_env(org, peer, domain, machines))
                    linhas.append(f"peer lifecycle chaincode install {package_file}\n")

            # ── 2. Captura do PACKAGE_ID ──────────────────────────────────────
            # Consultado no último peer configurado (variáveis de ambiente ainda
            # ativas do loop anterior). O ID é determinístico — deriva do hash
            # do pacote — então é igual em todos os peers.
            linhas.append(
                f"PACKAGE_ID=$(peer lifecycle chaincode queryinstalled "
                f"| grep '{cc['name']}_{cc['version']}' "
                f"| head -n 1 "
                f"| sed -n 's/^Package ID: //; s/, Label:.*$//p')"
            )
            linhas.append(f"infoln 'Package ID: '$PACKAGE_ID")

            # ── 3. Startup do container CCAAS ─────────────────────────────────
            # Em modo local: o container sobe aqui mesmo, antes do approve.
            # Em modo distribuído: o container é gerenciado pela fase 7 do SLURM
            # (start_chaincodes.sh via --start --phase ccaas), que roda na
            # máquina correta (cc['machine']). Subir o container aqui causaria
            # deploy na máquina errada quando cc['machine'] != coordenador.
            if not self.distributed:
                linhas.append(f"\ninfoln 'Iniciando container CCAAS {cc_service}...'")
                linhas.append(f"docker rm -f {cc_service} 2>/dev/null || true")
                linhas.append(f"fix_permissions '{abs_cc_path}'")
                linhas.append(
                    f"docker run -d --name {cc_service} --network {network_name}_net "
                    f"--dns 8.8.8.8 "
                    f"-p {cc_port}:{cc_port} "
                    f"-e CHAINCODE_SERVER_ADDRESS=0.0.0.0:{cc_port} "
                    f"-e CORE_CHAINCODE_ID_NAME=$PACKAGE_ID "
                    f"-v {abs_cc_path}:/opt/gopath/src/chaincode "
                    f"-w /opt/gopath/src/chaincode "
                    f"{img_prefix}/fabric-ccenv:{fabric_version} "
                    f"./chaincode"
                )

            # ── 4. Approve por org ────────────────────────────────────────────
            # Cada org aprova a definição do chaincode usando o primeiro peer
            # da org como representante. O orderer é endereçado pelo IP real
            # em modo distribuído (flag -o).
            ord_addr = self._orderer_address(orderer, machines)
            for org in self.config['network_topology']['organizations']:
                org_name    = org['name']
                first_peer  = org['peers'][0]
                peer_addr   = self._peer_address(first_peer, machines)
                linhas.append(f"\ninfoln 'Aprovando para {org_name} (peer: {peer_addr})...'")
                linhas.extend(self._get_peer_env(org, org['peers'][0], domain, machines))
                linhas.append(
                    f"peer lifecycle chaincode approveformyorg "
                    f"-o {ord_addr} --ordererTLSHostnameOverride {orderer['name']}.{domain} "
                    f"--tls --cafile {ord_tls_ca} --channelID {cc['channel']} --name {cc['name']} "
                    f"--version {cc['version']} --package-id $PACKAGE_ID --sequence {cc['sequence']} "
                    f"--collections-config {pdc_config} "
                    f"--signature-policy \"{cc['endorsement_policy']}\""
                )

            # ── 5. Commit ─────────────────────────────────────────────────────
            # O commit precisa de endorsement de um peer por org simultaneamente.
            # --peerAddresses lista todos os peers (um por org) com seus IPs reais,
            # cada um acompanhado do seu --tlsRootCertFiles correspondente.
            # A ordem de --peerAddresses e --tlsRootCertFiles deve ser a mesma.
            peer_addresses = ""
            tls_root_cas   = ""
            for org in self.config['network_topology']['organizations']:
                peer = org['peers'][0]
                peer_addresses += f" --peerAddresses {self._peer_address(peer, machines)}"
                tls_ca = (
                    self.paths.network_dir / "organizations" / "peerOrganizations"
                    / f"{org['name']}.{domain}" / "peers"
                    / f"{peer['name']}.{org['name']}.{domain}" / "tls" / "ca.crt"
                ).resolve()
                tls_root_cas += f" --tlsRootCertFiles {tls_ca}"

            linhas.append(f"\ninfoln 'Commitando chaincode {cc_name} no canal {cc_channel}...'")
            linhas.append(
                f"peer lifecycle chaincode commit "
                f"-o {ord_addr} --ordererTLSHostnameOverride {orderer['name']}.{domain} "
                f"--tls --cafile {ord_tls_ca} --channelID {cc['channel']} --name {cc['name']} "
                f"--version {cc['version']} --sequence {cc['sequence']} "
                f"--collections-config {pdc_config} "
                f"--signature-policy \"{cc['endorsement_policy']}\" "
                f"{peer_addresses} {tls_root_cas}"
            )
            linhas.append(f"\nsuccessln 'Deploy do chaincode {cc['name']} concluído com sucesso!'")

        with open(self.script_saida, 'w') as f:
            f.write("\n".join(linhas))
        os.chmod(self.script_saida, os.stat(self.script_saida).st_mode | stat.S_IEXEC)

    # ──────────────────────────────────────────────────────────────────────────
    # Script de startup CCAAS para modo distribuído
    # ──────────────────────────────────────────────────────────────────────────

    def generate_ccaas_start_script(self, machine):
        """
        Gera start_chaincodes.sh com apenas os `docker run` dos chaincodes
        atribuídos a `machine`. Usado no fluxo distribuído (--up --machine X),
        onde o lifecycle (install/approve/commit) já foi executado pelo script
        deploy_chaincode.sh a partir de qualquer nó com acesso à rede.

        O PACKAGE_ID é obtido consultando um peer local (já em execução na
        máquina), que tem o chaincode instalado desde o deploy. O ID é
        determinístico (hash do pacote), portanto igual em todos os peers.
        """
        machines      = self.config['network_topology'].get('machines', {})
        network_name  = self.config['network_topology']['network']['name']
        img_prefix    = self.config['env_versions']['images']['org_hyperledger']
        fabric_version = self.config['env_versions']['versions']['fabric']
        domain        = self.config['network_topology']['network']['domain']

        local_ccs = [
            cc for cc in self.config['network_topology'].get('chaincodes', [])
            if cc.get('machine') == machine
        ]

        if not local_ccs:
            co.warnln(f"Nenhum chaincode atribuído a '{machine}' — start_chaincodes.sh não gerado.")
            return

        # Encontra o primeiro peer local para consultar o PACKAGE_ID.
        # Em modo distribuído cada máquina tem pelo menos um peer (por design),
        # então essa busca deve sempre encontrar um resultado.
        local_peers = [
            (org, peer)
            for org in self.config['network_topology']['organizations']
            for peer in org['peers']
            if peer.get('machine') == machine
        ]
        if not local_peers:
            co.warnln(
                f"Nenhum peer local encontrado em '{machine}'. "
                f"O PACKAGE_ID não poderá ser consultado — start_chaincodes.sh não gerado."
            )
            return

        query_org, query_peer = local_peers[0]
        peer_base = (
            self.paths.network_dir / "organizations" / "peerOrganizations"
            / f"{query_org['name']}.{domain}"
        ).resolve()

        linhas = [
            "#!/bin/bash",
            "set -e",
            f"source {self.paths.scripts_dir}/utils.sh",
            f"export FABRIC_CFG_PATH={self.paths.network_dir}/compose/peercfg",
            f"export PATH={self.paths.base_dir}/bin:$PATH\n",
            "infoln '--- Iniciando containers CCAAS locais ---'",
            "",
            "# Configura o peer local para consultar os PACKAGE_IDs instalados.",
            "# O peer já deve estar em execução (iniciado por start_nodes.sh).",
            f"export CORE_PEER_TLS_ENABLED=true",
            f"export CORE_PEER_LOCALMSPID={query_org['msp_id']}",
            f"export CORE_PEER_TLS_ROOTCERT_FILE={peer_base}/peers/{query_peer['name']}.{query_org['name']}.{domain}/tls/ca.crt",
            f"export CORE_PEER_MSPCONFIGPATH={peer_base}/users/Admin@{query_org['name']}.{domain}/msp",
            f"export CORE_PEER_ADDRESS={self._peer_address(query_peer, machines)}",
        ]

        for cc in local_ccs:
            cc_service  = f"{cc['name']}.{cc['channel']}"
            cc_port     = cc['port']
            abs_cc_path = (self.paths.chaincode_dir / cc['name']).resolve()

            linhas.append(f"\ninfoln 'Iniciando chaincode {cc['name']} (porta {cc_port})...'")

            # Consulta o PACKAGE_ID no peer local. O chaincode foi instalado
            # pelo deploy_chaincode.sh na etapa de lifecycle (executada pelo
            # nó orquestrador via --up sem --machine, ou manualmente).
            linhas.append(
                f"PACKAGE_ID=$(peer lifecycle chaincode queryinstalled "
                f"| grep '{cc['name']}_{cc['version']}' "
                f"| head -n 1 "
                f"| sed -n 's/^Package ID: //; s/, Label:.*$//p')"
            )
            cc_label = f"{cc['name']}_{cc['version']}"
            linhas.append(
                f"if [ -z \"$PACKAGE_ID\" ]; then "
                f"errorln 'PACKAGE_ID não encontrado para {cc_label}. "
                f"O chaincode foi instalado neste peer?'; exit 1; fi"
            )
            linhas.append(f"infoln 'Package ID: '$PACKAGE_ID")

            linhas.append(f"docker rm -f {cc_service} 2>/dev/null || true")
            linhas.append(f"fix_permissions '{abs_cc_path}'")
            linhas.append(
                f"docker run -d --name {cc_service} --network {network_name}_net "
                f"--dns 8.8.8.8 "
                f"-p {cc_port}:{cc_port} "
                f"-e CHAINCODE_SERVER_ADDRESS=0.0.0.0:{cc_port} "
                f"-e CORE_CHAINCODE_ID_NAME=$PACKAGE_ID "
                f"-v {abs_cc_path}:/opt/gopath/src/chaincode "
                f"-w /opt/gopath/src/chaincode "
                f"{img_prefix}/fabric-ccenv:{fabric_version} "
                f"./chaincode"
            )
            linhas.append(f"successln 'Chaincode {cc['name']} iniciado na porta {cc_port}.'")

        script_path = self.paths.scripts_dir / "start_chaincodes.sh"
        with open(script_path, 'w') as f:
            f.write("\n".join(linhas))
        os.chmod(script_path, os.stat(script_path).st_mode | stat.S_IEXEC)
        co.successln(f"Script gerado: {script_path}")

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers internos
    # ──────────────────────────────────────────────────────────────────────────

    def _get_peer_env(self, org, peer, domain, machines=None):
        """
        Retorna as variáveis de ambiente necessárias para que o CLI do Fabric
        (peer) opere como administrador da org e se conecte ao peer correto.

        O parâmetro `machines` (dict opcional) habilita o modo distribuído:
        CORE_PEER_ADDRESS recebe o IP real da máquina do peer em vez de
        'localhost', permitindo que comandos de install e approve alcancem
        peers em outras máquinas da LAN.
        """
        machines = machines or {}
        p_full    = f"{peer['name']}.{org['name']}.{domain}"
        peer_base = (
            self.paths.network_dir / "organizations" / "peerOrganizations"
            / f"{org['name']}.{domain}"
        ).resolve()
        return [
            f"export CORE_PEER_TLS_ENABLED=true",
            f"export CORE_PEER_LOCALMSPID={org['msp_id']}",
            f"export CORE_PEER_TLS_ROOTCERT_FILE={peer_base}/peers/{p_full}/tls/ca.crt",
            f"export CORE_PEER_MSPCONFIGPATH={peer_base}/users/Admin@{org['name']}.{domain}/msp",
            f"export CORE_PEER_ADDRESS={self._peer_address(peer, machines)}"
        ]

    def _generate_collections_json(self):
        """Gera um arquivo JSON de coleções privadas para cada chaincode."""
        for cc in self.config['network_topology']['chaincodes']:
            collections = []
            for pdc_info in cc.get('pdc', []):
                collections.append({
                    "name":               pdc_info['name'],
                    "policy":             pdc_info['policy'],
                    "requiredPeerCount":  pdc_info['required_peer_count'],
                    "maxPeerCount":       pdc_info['max_peer_count'],
                    "blockToLive":        pdc_info['block_to_live'],
                    "memberOnlyRead":     self._resolve_bool_field(pdc_info.get('member_only_read', False)),
                    "memberOnlyWrite":    self._resolve_bool_field(pdc_info.get('member_only_write', False))
                })
            output_path = self.paths.chaincode_dir / f"{cc['name']}_collections.json"
            with open(output_path, 'w') as f:
                json.dump(collections, f, indent=4)

    def _create_ccaas_package(self, cc, output_path):
        """
        Cria o pacote .tar.gz do chaincode no formato CCAAS esperado pelo Fabric.
        O connection.json aponta para o hostname Docker do container chaincode
        (resolvido via extra_hosts nos peers em modo distribuído).
        """
        connection = {
            "address":      f"{cc['name']}.{cc['channel']}:{cc['port']}",
            "dial_timeout": "10s",
            "tls_required": False
        }
        metadata = {
            "type":  "ccaas",
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

        co.successln(f"Pacote CCAAS gerado em: {output_path}")

    def _resolve_bool_field(self, value):
        """Normaliza valores booleanos que podem vir como bool ou string do YAML."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return 'member' in value
        return False
