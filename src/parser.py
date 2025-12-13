"""
Validador sintático e semântico da configuração da rede (network.yaml).

Verifica a existência de chaves obrigatórias, tipos de dados corretos (portas
como inteiros) e consistência lógica (ex: se uma org referenciada em um canal
realmente foi definida). Também aplica valores padrão (defaults) onde permitido.

Rever: valida_chaincode
"""
import os
from .utils import Colors as co

class ConfigParser:
    # O ConfigLoader retorna um dict com 'network_topology' e 'env_versions'
    # Estamos interessados apenas na topologia da rede.
    def __init__(self, config_completa):
        self.topologia = config_completa.get('network_topology', {})
        self.erros = []
        self.avisos = []
        
        # Cache para validação semântica (nomes das orgs encontradas)
        self.orgs_definidas = set()

    # Executa todas as verificações. Retorna True se aprovado, False se houver erros.
    def valida(self):
        if not self.topologia:
            self.erros.append("O arquivo network.yaml parece estar vazio ou mal formatado.")
            return self._print_results()

        # Executa a sequência de validações
        self._valida_chaves_raizes()
        self._valida_secao_network()
        self._valida_organizacoes() 
        self._valida_orderer()
        self._valida_canais()       
        # ainda não implementei o chaincode, futuramente preciso ver isso
        # self._valida_chaincodes()   

        return self._print_results()

    # Exibe os erros e avisos acumulados.
    def _print_results(self):
        if self.avisos:
            for a in self.avisos:
                co.warnln(f" [Aviso] {a}")

        if self.erros:
            for e in self.erros:
                co.errorln(f"{e}")
            co.errorln(f"Validação falhou. Encontrados {len(self.erros)} erro(s) na definição da rede.")
            return False
        
        co.successln("Validação concluída com sucesso. Nenhum erro encontrado.")
        return True

    # Verifica se chaves obrigatórias existem em um dicionário, retorna true se todas existem
    def _chaves_obrigatorias(self, dado, chaves_obrigatorias, contexto):
        if not isinstance(dado, dict):
            self.erros.append(f"Em '{contexto}': Esperado um objeto (dict), recebeu {type(dado).__name__}.")
            return False
        
        faltando = [chave for chave in chaves_obrigatorias if chave not in dado]
        if faltando:
            self.erros.append(f"Em '{contexto}': Chaves obrigatórias faltando: {faltando}")
            return False
        return True

    # ---------------------- Validadores Específicos -------------------------
    # valida se temos network, organizations, orderer na raiz
    def _valida_chaves_raizes(self):
        obrigatorios = ['network', 'organizations', 'orderer']
        # 'channels' e 'chaincodes' são tecnicamente opcionais para subir a infra, mas recomendados
        self._chaves_obrigatorias(self.topologia, obrigatorios, "Raiz do network.yaml")

        
    # valida a seção network
    def _valida_secao_network(self):
        net = self.topologia.get('network', {})
        if self._chaves_obrigatorias(net, ['name', 'domain'], "seção 'network'"):
            # verifica se o domain não tem espaços, erro comum de digitação
            if ' ' in net['domain']:
                self.erros.append(f"Network Domain '{net['domain']}' não deve conter espaços.")

    # valida a seção organizations
    def _valida_organizacoes(self):
        orgs = self.topologia.get('organizations', [])
        if not isinstance(orgs, list) or len(orgs) == 0:
            self.erros.append("A seção 'organizations' deve ser uma lista e conter pelo menos uma organização.")
            return

        for i, org in enumerate(orgs):
            # Tenta pegar o nome para mensagens de erro melhores, ou usa indice
            org_name = org.get('name', f"Org[{i}]")
            contexto_org = f"Organização '{org_name}'"

            # 1. Chaves Básicas da Org
            if not self._chaves_obrigatorias(org, ['name', 'msp_id','ca', 'peers'], contexto_org):
                continue
            
            self.orgs_definidas.add(org['name'])

            # 2. Validação da CA (Obrigatória)
            ca = org.get('ca')
            if not ca:
                self.erros.append(f"{contexto_org} não possui CA definida (obrigatório).")
            else:
                self._chaves_obrigatorias(ca, ['name', 'host', 'port'], f"CA de {org_name}")

            # 3. Validação dos Peers
            peers = org.get('peers', [])
            if not isinstance(peers, list) or len(peers) < 1:
                self.erros.append(f"{contexto_org} deve ter no mínimo 1 Peer definido.")
                continue

            for p in peers:
                p_name = p.get('name', 'unnamed')
                contexto_peer = f"Peer '{p_name}' em {org_name}"

                # Chaves obrigatórias do Peer
                chaves_obrigatorias_peers = ['name', 'host', 'port', 'chaincode_port']
                if not self._chaves_obrigatorias(p, chaves_obrigatorias_peers, contexto_peer):
                    continue

                # Validação de Tipos (Portas devem ser inteiros)
                if not isinstance(p['port'], int) or not isinstance(p['chaincode_port'], int):
                    self.erros.append(f"{contexto_peer}: Portas devem ser números inteiros.")

                # --- Lógica de Banco de Dados (State DB) ---
                # Se 'state_db' não foi definido, aplica o DEFAULT
                if 'state_db' not in p:
                    p['state_db'] = 'GoLevelDB' # Injeção de valor padrão
                
                dp_tipo = p['state_db']

                if dp_tipo == 'CouchDB':
                    # Se escolheu CouchDB, a porta é obrigatória
                    if 'couchdb_port' not in p:
                        self.erros.append(f"{contexto_peer}: 'couchdb_port' é obrigatório quando state_db é CouchDB.")
                    elif not isinstance(p['couchdb_port'], int):
                        self.erros.append(f"{contexto_peer}: 'couchdb_port' deve ser um número inteiro.")
                
                elif dp_tipo == 'GoLevelDB':
                    # GoLevelDB não precisa de porta extra
                    pass 
                
                else:
                    self.erros.append(f"{contexto_peer}: state_db inválido ('{dp_tipo}'). Use 'CouchDB' ou 'GoLevelDB'.")

    # valida a seção orderer
    def _valida_orderer(self):
        ord_secao = self.topologia.get('orderer', {})
        if self._chaves_obrigatorias(ord_secao, ['type', 'nodes', 'batch_timeout', 'batch_size'], "seção 'orderer'"):
            
            # Valida tipo de consenso
            tipos_validos = ['etcdraft', 'BFT']
            if ord_secao['type'] not in tipos_validos:
                self.erros.append(f"Tipo de orderer inválido: '{ord_secao['type']}'. Permitidos: {tipos_validos}")

            # valida tam_lote
            tam_lot = ord_secao['batch_size']
            if self._chaves_obrigatorias(tam_lot, ['max_message_count', 'absolute_max_bytes', 'preferred_max_bytes'], "batch_size do orderer"):
                if not isinstance(tam_lot['max_message_count'], int):
                    self.erros.append("orderer.batch_size.max_message_count deve ser um inteiro.")

            # Valida nós
            nodes = ord_secao.get('nodes', [])
            if not nodes:
                self.erros.append("Orderer deve ter pelo menos um nó definido.")
            
            for node in nodes:
                if self._chaves_obrigatorias(node, ['name', 'host', 'port', 'admin_port'], "nodes do Orderer"):
                     if not isinstance(node['port'], int) or not isinstance(node['admin_port'], int):
                        self.erros.append(f"Orderer node '{node.get('name')}' tem portas inválidas (devem ser inteiros).")

    # valida a seção canais
    def _valida_canais(self):
        canais = self.topologia.get('channels', [])
        # Canais são opcionais na validação inicial, mas se existirem, devem estar corretos
        if len(canais) < 1:
            self.erros.append("Nenhum canal definido na seção 'channels'. Definir pelo menos um canal.")
            return
        
        if not isinstance(canais, list):
            self.erros.append("A seção 'channels' deve ser uma lista.")
            return

        for c in canais:
            if self._chaves_obrigatorias(c, ['name', 'participating_orgs'], f"Seção channels - {c.get('name', '')}"):
                # Validação Semântica: As orgs do canal existem?
                part_orgs = c['participating_orgs']
                for org_name in part_orgs:
                    if org_name not in self.orgs_definidas:
                        self.erros.append(f"Canal '{c['name']}' referencia a organização '{org_name}', mas ela não foi definida em 'organizations'.")

    # valida a seção chaincodes
    def _valida_chaincodes(self):
        ccs = self.topologia.get('chaincodes', [])
        if len(ccs) < 1:
            self.erros.append("Nenhum chaincode definido na seção 'chaincodes'. Definir pelo menos um chaincode.")
            return 
        
        for cc in ccs:
            if self._chaves_obrigatorias(cc, ['name', 'path', 'version', 'lang', 'sequence', 'endorsement_policy'], f"seção 'chaincodes' - '{cc['name']}'"):
                if not os.path.exists(cc['path']):
                    self.erros.append(f"Chaincode '{cc['name']}' não existe: {cc['path']} não encontrado.")
                
                # Valida Private Data Collections se houver
                if 'pdc' in cc:
                    if not isinstance(cc['pdc'], list):
                        self.erros.append(f"PDC do chaincode '{cc['name']}' deve ser uma lista.")
                    else:
                        for pdc in cc['pdc']:
                            self._chaves_obrigatorias(pdc, ['name', 'policy', 'required_peer_count', 'max_peer_count', 'block_to_live', 'member_only_read', 'member_only_write'], f"PDC do chaincode {cc['name']}")