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
  Em modo distribuído, o container CCAAS não é iniciado por deploy_chaincode.sh — é
  responsabilidade de generate_ccaas_start_script(), rodado na máquina correta via
  '--start --machine X --phase ccaas'. Sem 'machines' (modo local), o comportamento
  é idêntico ao original.
"""

import ipaddress
import os
import stat
import json
import tarfile
import io
from ..utils import Colors as co

class ChaincodeDeployGenerator:
    def __init__(self, config, paths, distributed=False):
        self.config = config
        self.paths = paths

        # quando True, usa os IPs reais da seção 'machines' do network.yaml;
        # quando False (padrão / modo local), todos os endereços usam 'localhost'.
        self.distributed = distributed

        self.script_saida = self.paths.scripts_dir / "deploy_chaincode.sh"
        # subnet fixa da rede (YAML) -> chaincodes ganham IP estático .30+
        self.subnet = self.config['network_topology']['network'].get('subnet')
        self._generate_collections_json()

    def _cc_ip_flag(self, cc_idx):
        """Flag --ip do docker run: IP estático .30+ na subnet (vazia sem subnet)"""
        if not self.subnet:
            return ""
        return f"--ip {ipaddress.ip_network(self.subnet)[0] + 30 + cc_idx} "

    def _peer_address(self, peer, machines):
        """Retorna HOST:PORTA do peer (IP real em modo distribuído, localhost em modo local)."""
        machine_name = peer.get('machine')
        if machine_name and machine_name in machines:
            return f"{machines[machine_name]['ip']}:{peer['port']}"
        return f"localhost:{peer['port']}"

    def _orderer_address(self, orderer, machines):
        """Retorna HOST:PORTA do orderer (usado nas flags -o de approve/commit)."""
        machine_name = orderer.get('machine')
        if machine_name and machine_name in machines:
            return f"{machines[machine_name]['ip']}:{orderer['port']}"
        return f"localhost:{orderer['port']}"

    def generate(self):
        # em modo local (distributed=False), machines fica vazio e todos os
        # endereços caem no fallback 'localhost' dos helpers.
        machines = self.config['network_topology'].get('machines', {}) if self.distributed else {}

        linhas = [
            "#!/bin/bash",
            "set -e",
            f"source {self.paths.scripts_dir}/utils.sh",
            f"export FABRIC_CFG_PATH={self.paths.network_dir}/compose/peercfg",
            f"export PATH={self.paths.base_dir}/bin:$PATH\n",
            "infoln '--- Iniciando Deploy de Chaincode ---'"
        ]

        for cc_idx, cc in enumerate(self.config['network_topology']['chaincodes']):
            domain = self.config['network_topology']['network']['domain']
            orderer = self.config['network_topology']['orderer']['nodes'][0]

            network_name = self.config['network_topology']['network']['name']
            img_prefix = self.config['env_versions']['images']['org_hyperledger']
            fabric_version = self.config['env_versions']['versions']['fabric']

            package_file = (self.paths.chaincode_dir / f"{cc['name']}.tar.gz").resolve()
            # sem PDC no YAML, nenhum arquivo de collections é gerado (ver
            # _generate_collections_json) — a flag --collections-config é omitida.
            has_pdc = bool(cc.get('pdc'))
            collections_flag = ""
            if has_pdc:
                pdc_config = (self.paths.chaincode_dir / f"{cc['name']}_collections.json").resolve()
                collections_flag = f"--collections-config {pdc_config} "

            # caminho absoluto da pasta do chaincode: usa o campo 'path' do YAML
            # quando presente (permite pasta com nome diferente do chaincode),
            # senão cai no padrão chaincode/<name>
            abs_cc_path = ((self.paths.base_dir / cc['path']).resolve()
                           if cc.get('path') else (self.paths.chaincode_dir / cc['name']))
            
            # porta do chaincode (cada cc tem a sua própria)
            cc_port = cc['port']

            # compilação local do chaincode para Linux AMD64
            co.infoln(f"Compilando chaincode {cc['name']} localmente para Linux...")
            compile_cmd = (
                f"cd {abs_cc_path} && "
                f"GOOS=linux GOARCH=amd64 go build -o chaincode"
            )
            os.system(compile_cmd)

            self._create_ccaas_package(cc, package_file)

            # --- instalação ---
            for org in self.config['network_topology']['organizations']:
                for peer in org['peers']:
                    p_full = f"{peer['name']}.{org['name']}.{domain}"
                    linhas.append(f"infoln 'Instalando em {p_full} ({self._peer_address(peer, machines)})...'")
                    linhas.extend(self._get_peer_env(org, peer, domain, machines))
                    linhas.append(f"peer lifecycle chaincode install {package_file}\n")

            # --- PACKAGE ID ---
            linhas.append(f"PACKAGE_ID=$(peer lifecycle chaincode queryinstalled | grep '{cc['name']}_{cc['version']}' | head -n 1 | sed -n 's/^Package ID: //; s/, Label:.*$//p')")

            cc_service = f"{cc['name']}.{cc['channel']}"

            # Em modo local, o container CCAAS sobe aqui mesmo, antes do approve.
            # Em modo distribuído, o container é gerenciado pela fase 'ccaas' do
            # SLURM (start_chaincodes.sh via --start --phase ccaas), rodando na
            # máquina correta (cc['machine']) — subir aqui deployaria na máquina
            # errada quando cc['machine'] != coordenador.
            if not self.distributed:
                linhas.append(f"docker rm -f {cc_service} 2>/dev/null || true")

                # usando caminho absoluto direto do PathManager
                linhas.append(f"fix_permissions '{abs_cc_path}'")

                # cada chaincode expõe sua própria porta (cc_port)
                linhas.append(f"docker run -d --name {cc_service} --network {network_name}_net "
                            f"{self._cc_ip_flag(cc_idx)}"
                            f"--dns 8.8.8.8 "
                            f"-p {cc_port}:{cc_port} "
                            f"-e CHAINCODE_SERVER_ADDRESS=0.0.0.0:{cc_port} "
                            f"-e CORE_CHAINCODE_ID_NAME=$PACKAGE_ID "
                            f"-v {abs_cc_path}:/opt/gopath/src/chaincode "
                            f"-w /opt/gopath/src/chaincode "
                            f"{img_prefix}/fabric-ccenv:{fabric_version} "
                            f"./chaincode")

            # --- aprovação e Commit ---
            ord_tls_ca = (self.paths.network_dir / "organizations" / "ordererOrganizations" / domain / "orderers" / f"{orderer['name']}.{domain}" / "tls" / "ca.crt").resolve()
            ord_addr = self._orderer_address(orderer, machines)

            for org in self.config['network_topology']['organizations']:
                linhas.append(f"\ninfoln 'Aprovando definição para {org['name']}...'")
                linhas.extend(self._get_peer_env(org, org['peers'][0], domain, machines))

                approve_cmd = (
                    f"peer lifecycle chaincode approveformyorg "
                    f"-o {ord_addr} --ordererTLSHostnameOverride {orderer['name']}.{domain} "
                    f"--tls --cafile {ord_tls_ca} --channelID {cc['channel']} --name {cc['name']} "
                    f"--version {cc['version']} --package-id $PACKAGE_ID --sequence {cc['sequence']} "
                    f"{collections_flag}"
                    f"--signature-policy \"{cc['endorsement_policy']}\""
                )
                linhas.append(approve_cmd)

            # montagem do Commit
            peer_addresses = ""
            tls_root_cas = ""
            for org in self.config['network_topology']['organizations']:
                peer = org['peers'][0]
                peer_addresses += f" --peerAddresses {self._peer_address(peer, machines)}"
                tls_ca = (self.paths.network_dir / "organizations" / "peerOrganizations" / f"{org['name']}.{domain}" / "peers" / f"{peer['name']}.{org['name']}.{domain}" / "tls" / "ca.crt").resolve()
                tls_root_cas += f" --tlsRootCertFiles {tls_ca}"

            commit_cmd = (
                f"peer lifecycle chaincode commit "
                f"-o {ord_addr} --ordererTLSHostnameOverride {orderer['name']}.{domain} "
                f"--tls --cafile {ord_tls_ca} --channelID {cc['channel']} --name {cc['name']} "
                f"--version {cc['version']} --sequence {cc['sequence']} "
                f"{collections_flag}"
                f"--signature-policy \"{cc['endorsement_policy']}\" "
                f"{peer_addresses} {tls_root_cas}"
            )
            linhas.append(commit_cmd)
            linhas.append(f"\nsuccessln 'Deploy do chaincode {cc['name']} concluído com sucesso!'")

        # escrita do arquivo movida para o final (após processar todos os CCs)
        with open(self.script_saida, 'w') as f:
            f.write("\n".join(linhas))
        os.chmod(self.script_saida, os.stat(self.script_saida).st_mode | stat.S_IEXEC)

    # ──────────────────────────────────────────────────────────────────────────
    # Atualização (redeploy) de chaincode em rede já ativa
    # ──────────────────────────────────────────────────────────────────────────

    def generate_redeploy(self):
        """
        Gera redeploy_chaincode.sh: atualiza chaincode(s) de uma rede já ativa
        sem derrubar os demais componentes. Modo e alvo chegam via env
        (CC_REDEPLOY_MODE/TARGET_CC), injetados por main.py --redeploy-cc/--cc-name.

          MODE=code   — recompila o binário Go, reempacota o CCAAS e reinicia
                        apenas o container do chaincode. Não toca no ciclo de
                        vida do Fabric (nem install/approve/commit).
          MODE=ledger — faz tudo do 'code' e também reinstala o pacote em todos
                        os peers e roda approveformyorg/commit com a nova
                        'version'/'sequence' do network.yaml (que devem ter
                        sido incrementadas manualmente antes de rodar).

        TARGET_CC filtra um chaincode específico pelo nome; vazio atualiza todos.
        """
        machines = self.config['network_topology'].get('machines', {}) if self.distributed else {}
        redeploy_script = self.paths.scripts_dir / "redeploy_chaincode.sh"

        linhas = [
            "#!/bin/bash",
            "set -e",
            f"source {self.paths.scripts_dir}/utils.sh",
            f"export FABRIC_CFG_PATH={self.paths.network_dir}/compose/peercfg",
            f"export PATH={self.paths.base_dir}/bin:$PATH\n",
            "# Modo enviado pelo extra_env do Python (main.py --redeploy-cc). Padrão 'code'.",
            'MODE=${CC_REDEPLOY_MODE:-"code"}',
            'infoln "--- Iniciando Atualização de Chaincode (Modo: $MODE) ---"'
        ]

        for cc_idx, cc in enumerate(self.config['network_topology']['chaincodes']):
            linhas.append(f"\nif [ -n \"$TARGET_CC\" ] && [ \"$TARGET_CC\" != \"{cc['name']}\" ]; then")
            linhas.append(f"    infoln 'Pulando {cc['name']} (alvo diferente solicitado)'")
            linhas.append("else")

            domain = self.config['network_topology']['network']['domain']
            orderer = self.config['network_topology']['orderer']['nodes'][0]
            network_name = self.config['network_topology']['network']['name']
            img_prefix = self.config['env_versions']['images']['org_hyperledger']
            fabric_version = self.config['env_versions']['versions']['fabric']

            package_file = (self.paths.chaincode_dir / f"{cc['name']}.tar.gz").resolve()
            has_pdc = bool(cc.get('pdc'))
            collections_flag = ""
            if has_pdc:
                pdc_config = (self.paths.chaincode_dir / f"{cc['name']}_collections.json").resolve()
                collections_flag = f"--collections-config {pdc_config} "

            abs_cc_path = ((self.paths.base_dir / cc['path']).resolve()
                           if cc.get('path') else (self.paths.chaincode_dir / cc['name']))
            cc_port = cc['port']

            # o código-fonte pode ter mudado desde o --up: sempre recompila
            co.infoln(f"Recompilando chaincode {cc['name']} localmente para Linux...")
            compile_cmd = f"cd {abs_cc_path} && GOOS=linux GOARCH=amd64 go build -o chaincode"
            os.system(compile_cmd)

            self._create_ccaas_package(cc, package_file)

            # --- ETAPA 1: reinstalação nos peers (só em modo 'ledger') ---
            linhas.append('\nif [ "$MODE" == "ledger" ]; then')
            for org in self.config['network_topology']['organizations']:
                for peer in org['peers']:
                    p_full = f"{peer['name']}.{org['name']}.{domain}"
                    linhas.append(f"    infoln 'Instalando novo pacote em {p_full} ({self._peer_address(peer, machines)})...'")
                    linhas.extend([f"    {l}" for l in self._get_peer_env(org, peer, domain, machines)])
                    linhas.append(f"    peer lifecycle chaincode install {package_file}\n")
            linhas.append("fi")

            # --- ETAPA 2: captura do PACKAGE_ID já instalado (existe desde o --up) ---
            first_org = self.config['network_topology']['organizations'][0]
            first_peer = first_org['peers'][0]
            linhas.append("\n# Ambiente temporário para consultar o Package ID já instalado")
            linhas.extend(self._get_peer_env(first_org, first_peer, domain, machines))
            linhas.append(f"PACKAGE_ID=$(peer lifecycle chaincode queryinstalled | "
                          f"grep '{cc['name']}_{cc['version']}' | head -n 1 | sed -n 's/^Package ID: //; s/, Label:.*$//p')")
            linhas.append('\nif [ -z "$PACKAGE_ID" ]; then')
            linhas.append("    errorln 'PACKAGE_ID não encontrado no ledger. Rode com --redeploy-cc ledger primeiro.'")
            linhas.append("    exit 1")
            linhas.append("fi")

            # --- ETAPA 3: reinício do container CCAAS (sempre, em modo local) ---
            cc_service = f"{cc['name']}.{cc['channel']}"
            if not self.distributed:
                linhas.append(f"\ninfoln 'Reiniciando container do chaincode: {cc_service}'")
                linhas.append(f"docker rm -f {cc_service} 2>/dev/null || true")
                linhas.append(f"fix_permissions '{abs_cc_path}'")
                linhas.append(f"docker run -d --name {cc_service} --network {network_name}_net "
                            f"{self._cc_ip_flag(cc_idx)}"
                            f"--dns 8.8.8.8 "
                            f"-p {cc_port}:{cc_port} "
                            f"-e CHAINCODE_SERVER_ADDRESS=0.0.0.0:{cc_port} "
                            f"-e CORE_CHAINCODE_ID_NAME=$PACKAGE_ID "
                            f"-v {abs_cc_path}:/opt/gopath/src/chaincode "
                            f"-w /opt/gopath/src/chaincode "
                            f"{img_prefix}/fabric-ccenv:{fabric_version} "
                            f"./chaincode")
            else:
                linhas.append(f"\ninfoln 'Modo distribuído: reinicie o container de {cc_service} na máquina responsável "
                              f"(--start --machine <nome> --phase ccaas).'")

            # --- ETAPA 4: aprovação e commit (só em modo 'ledger') ---
            linhas.append('\nif [ "$MODE" == "ledger" ]; then')
            ord_tls_ca = (self.paths.network_dir / "organizations" / "ordererOrganizations" / domain / "orderers" / f"{orderer['name']}.{domain}" / "tls" / "ca.crt").resolve()
            ord_addr = self._orderer_address(orderer, machines)

            for org in self.config['network_topology']['organizations']:
                linhas.append(f"    infoln 'Aprovando nova definição para {org['name']}...'")
                linhas.extend([f"    {l}" for l in self._get_peer_env(org, org['peers'][0], domain, machines)])
                approve_cmd = (
                    f"    peer lifecycle chaincode approveformyorg "
                    f"-o {ord_addr} --ordererTLSHostnameOverride {orderer['name']}.{domain} "
                    f"--tls --cafile {ord_tls_ca} --channelID {cc['channel']} --name {cc['name']} "
                    f"--version {cc['version']} --package-id $PACKAGE_ID --sequence {cc['sequence']} "
                    f"{collections_flag}"
                    f"--signature-policy \"{cc['endorsement_policy']}\""
                )
                linhas.append(approve_cmd)

            peer_addresses = ""
            tls_root_cas = ""
            for org in self.config['network_topology']['organizations']:
                peer = org['peers'][0]
                peer_addresses += f" --peerAddresses {self._peer_address(peer, machines)}"
                tls_ca = (self.paths.network_dir / "organizations" / "peerOrganizations" / f"{org['name']}.{domain}" / "peers" / f"{peer['name']}.{org['name']}.{domain}" / "tls" / "ca.crt").resolve()
                tls_root_cas += f" --tlsRootCertFiles {tls_ca}"

            commit_cmd = (
                f"    peer lifecycle chaincode commit "
                f"-o {ord_addr} --ordererTLSHostnameOverride {orderer['name']}.{domain} "
                f"--tls --cafile {ord_tls_ca} --channelID {cc['channel']} --name {cc['name']} "
                f"--version {cc['version']} --sequence {cc['sequence']} "
                f"{collections_flag}"
                f"--signature-policy \"{cc['endorsement_policy']}\" "
                f"{peer_addresses} {tls_root_cas}"
            )
            linhas.append(commit_cmd)
            linhas.append("fi")

            linhas.append(f"\nsuccessln 'Atualização do chaincode {cc['name']} concluída com sucesso!'")
            linhas.append("fi")

        with open(redeploy_script, 'w') as f:
            f.write("\n".join(linhas))
        os.chmod(redeploy_script, os.stat(redeploy_script).st_mode | stat.S_IEXEC)
        co.successln(f"Script de redeploy gerado em: {redeploy_script}")

    # ──────────────────────────────────────────────────────────────────────────
    # Script de startup CCAAS para modo distribuído
    # ──────────────────────────────────────────────────────────────────────────

    def generate_ccaas_start_script(self, machine):
        """
        Gera start_chaincodes.sh com apenas os `docker run` dos chaincodes
        atribuídos a `machine`. Usado no fluxo distribuído (--start --machine X
        --phase ccaas), onde o lifecycle (install/approve/commit) já foi
        executado por deploy_chaincode.sh a partir do coordenador.

        O PACKAGE_ID é obtido consultando um peer local (já em execução na
        máquina), que tem o chaincode instalado desde o deploy. O ID é
        determinístico (hash do pacote), portanto igual em todos os peers.
        """
        machines = self.config['network_topology'].get('machines', {})
        network_name = self.config['network_topology']['network']['name']
        img_prefix = self.config['env_versions']['images']['org_hyperledger']
        fabric_version = self.config['env_versions']['versions']['fabric']
        domain = self.config['network_topology']['network']['domain']

        local_ccs = [
            cc for cc in self.config['network_topology'].get('chaincodes', [])
            if cc.get('machine') == machine
        ]
        if not local_ccs:
            co.warnln(f"Nenhum chaincode atribuído a '{machine}' — start_chaincodes.sh não gerado.")
            return

        # Encontra o primeiro peer local para consultar o PACKAGE_ID.
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

        for cc_idx, cc in enumerate(local_ccs):
            cc_service = f"{cc['name']}.{cc['channel']}"
            cc_port = cc['port']
            abs_cc_path = ((self.paths.base_dir / cc['path']).resolve()
                           if cc.get('path') else (self.paths.chaincode_dir / cc['name']).resolve())

            linhas.append(f"\ninfoln 'Iniciando chaincode {cc['name']} (porta {cc_port})...'")

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
                f"{self._cc_ip_flag(cc_idx)}"
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

    # helper para importar variaveis de ambiente do peer
    def _get_peer_env(self, org, peer, domain, machines=None):
        machines = machines or {}
        p_full = f"{peer['name']}.{org['name']}.{domain}"
        peer_base = (self.paths.network_dir / "organizations" / "peerOrganizations" / f"{org['name']}.{domain}").resolve()
        return [
            f"export CORE_PEER_TLS_ENABLED=true",
            f"export CORE_PEER_LOCALMSPID={org['msp_id']}",
            f"export CORE_PEER_TLS_ROOTCERT_FILE={peer_base}/peers/{p_full}/tls/ca.crt",
            f"export CORE_PEER_MSPCONFIGPATH={peer_base}/users/Admin@{org['name']}.{domain}/msp",
            f"export CORE_PEER_ADDRESS={self._peer_address(peer, machines)}"
        ]

    def _generate_collections_json(self):
        for cc in self.config['network_topology']['chaincodes']:
            pdc_list = cc.get('pdc', [])
            output_path = self.paths.chaincode_dir / f"{cc['name']}_collections.json"

            # sem PDC configurada, não há collections-config a aprovar/commitar:
            # não gera o arquivo (e remove um eventual arquivo obsoleto de uma
            # config anterior do mesmo chaincode que tinha PDC e deixou de ter).
            if not pdc_list:
                if output_path.exists():
                    output_path.unlink()
                continue

            collections = [
                {
                    "name": pdc_info['name'],
                    "policy": pdc_info['policy'],
                    "requiredPeerCount": pdc_info['required_peer_count'],
                    "maxPeerCount": pdc_info['max_peer_count'],
                    "blockToLive": pdc_info['block_to_live'],
                    "memberOnlyRead": self._resolve_bool_field(pdc_info.get('member_only_read', False)),
                    "memberOnlyWrite": self._resolve_bool_field(pdc_info.get('member_only_write', False))
                }
                for pdc_info in pdc_list
            ]
            with open(output_path, 'w') as f:
                json.dump(collections, f, indent=4)

    def _create_ccaas_package(self, cc, output_path):
        connection = {
            "address": f"{cc['name']}.{cc['channel']}:{cc['port']}",  # porta dinâmica por chaincode
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

    def _resolve_bool_field(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return 'member' in value
        return False