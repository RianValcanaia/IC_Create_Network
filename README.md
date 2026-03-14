<div align="center" id="topo">

<img src="https://media.giphy.com/media/iIqmM5tTjmpOB9mpbn/giphy.gif" width="200px" alt="Gif animado"/>

# <code><strong> Hyperledger Fabric Network Automator </strong></code>

<em>Orquestrador inteligente que automatiza a criação de Redes Hyperledger Fabric a partir de uma única definição YAML.</em>

[![Python Usage](https://img.shields.io/badge/Python-3.12+-blue?style=for-the-badge&logo=python)]()
[![Fabric Version](https://img.shields.io/badge/Fabric-3.1.1-orange?style=for-the-badge)]()
[![Fabric CA](https://img.shields.io/badge/Fabric_CA-1.5.13-orange?style=for-the-badge)]()
[![Go Version](https://img.shields.io/badge/Go-1.22.0-00ADD8?style=for-the-badge&logo=go)]()
[![Docker Version](https://img.shields.io/badge/Docker-20.10-2496ED?style=for-the-badge&logo=docker)]()

[![Docker Compose](https://img.shields.io/badge/Docker_Compose-2.20-2496ED?style=for-the-badge&logo=docker)]()
[![Status](https://img.shields.io/badge/Status-Em%20Andamento-yellow?style=for-the-badge)]()
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Visite%20meu%20perfil-blue?style=for-the-badge&logo=linkedin)](https://www.linkedin.com/in/rian-carlos-valcanaia-b2b487168/)
</div>

## Índice

- [📌 Objetivos](#-objetivos)
- [📥 Entradas do sistema](#-entradas-do-sistema)
- [🧰 Funcionalidades Atuais](#-funcionalidades-atuais)
- [📂 Como executar](#-como-executar)
- [⚙️ Guia de Configuração](#config)
- [📄 Código-fonte](#-código-fonte)

## 📌 Objetivos
O objetivo final deste projeto é fornecer uma ferramenta de linha de comando que, dado um arquivo `network.yaml`, execute o provisionamento ponta a ponta:
* **Geração de Infraestrutura**: Criação de CAs e Docker Compose dinâmicos.
* **Gestão de Identidade**: Registro e matrícula (Enrollment) automática de Peer, Orderer e Admins.
* **Artefatos de Rede**: Criação do bloco gênese e transações de canal baseadas na topologia.
* **Ciclo de Vida de Chaincode**: Instalação e definição de contratos inteligentes nos canais especificados.

[⬆ Voltar ao topo](#topo)

## 📥 Entradas do sistema

O sistema é alimentado por dois arquivos de configuração principais na pasta `/config`:
* `network.yaml`: Define a topologia (Organizações, Peers, Orderers, Canais e Chaincodes).
* `versions.yaml`: Controla as versões do Fabric, Fabric-CA e Go.

[⬆ Voltar ao topo](#topo)

## 🧱 Arquitetura de geradores

O projeto utiliza uma abordagem modular de geradores para construir a rede:

| Gerador | Função |
| :--- | :--- |
| `ComposeGenerator` | Cria os arquivos YAML para subir os serviços de CA das organizações e do orderer. |
| `CryptoGenerator` | Gera scripts Bash que utilizam o `fabric-ca-client` para criar toda a árvore de certificados MSP e TLS |
| `ConfigTxGenerator` | Traduz a topologia para o `configtx.yaml` e gera os perfis de canal (Raft ou BFT). |
| `ChannelScriptGenerator` | Automatiza o join dos canais via `osadmin` (Orderes) e define Anchors Peers dinamicamente. |
| `ChaincodeDeployGenerator` | Orquestra o ciclo de vida do chaincode no modelo CCAAS, gerindo opacotes, aprovações e o container Docker do contrato. | 
| `Parser` | Valida se a configuração é semanticamente correta (ex: portas únicas, domínios válidos)

[⬆ Voltar ao topo](#topo)

## 🧰 Funcionalidades Atuais
- **Rede local**: Sobe a topologia em containers, futuramente será implementado a distribuição com docker Swarm.
- **Validação Semântica**: Verifica erros comuns no `network.yaml` antes de iniciar a rede.
- **Suporte a Consensus BFT e RAFT(CFT)**: Configuração completa para o protocolo SmartBFT (requer Fabric v3.x).
- **Gestão de canais**: Criação de Múltiplos canais com diferentes organizações participantes e atualização automática de Anchor Peers.
- **Chaincode-as-a-Service (CCAAS)**: Deploy simplificado onde o contrato roda em seu próprio container, facilitando o debug e eliminando a dependência do Docker Socket pelo Peer.
- **Geração de CCP**: Criação automática de pergis de conexão para integração com aplicações (Node.js/Go).
- **Limpeza Profunda**: Comandos integrados para reover volumes, container e binários remanescentes.

[⬆ Voltar ao topo](#topo)

## ⚙️ Guia de Configuração <a id="config"></a>
O arquivo network.yaml é o "cérebro" da sua rede. Ele define desde o nome do domínio até as políticas de coleções privadas dos contratos inteligentes.

### 1. Configuração Geral da Rede
Define a identidade global e o escopo de domínio da infraestrutura.
```yaml
network:
  # Nome base utilizado como prefixo para os recursos no Docker.
  name: "FabricNetwork"
  # Domínio base para a resolução de nomes. Todos os nós seguirão o padrão: nome.dominio.
  domain: "exemplo.com"
```
### 2. Serviço de Ordenação (Orderer)
Configura o consendo e os limites de criação de blocos. O Projeto suporta EtcdRaft e SmartBFT.

```yaml
orderer:
  # Define o consenso: 'etcdraft' (CFT) ou 'BFT' (Byzantine Fault Tolerant).
  type: "BFT"            
  # Tempo máximo de espera para fechar um bloco, mesmo que não atinja o tamanho máximo.
  batch_timeout: "2s"    
  batch_size:
    # Quantidade máxima de transações individuais dentro de um único bloco.
    max_message_count: 500     
    # Tamanho máximo em bytes que um bloco pode ter.
    absolute_max_bytes: "10MB"  
    # Tamanho preferencial; se atingido, o bloco pode ser fechado antes do timeout.
    preferred_max_bytes: "2MB"  
  
  # Definição dos nós do Orderer. Para BFT, são necessários n=3f+1 (mínimo 4 para tolerar 1 falha).
  nodes:                 
    - name: "orderer0"   
      host: "orderer0.exemplo.com" 
      # Porta principal de comunicação do serviço.
      port: 7060
      # Porta administrativa usada pelo comando 'osnadmin' para gerenciar canais.
      admin_port: 7061
    # ... repete-se para os demais nós (orderer1, 2, 3)
  # Configuração da Autoridade Certificadora exclusiva para a Organização Orderer.
  ca:
    name: "ca-orderer"
    host: "ca.orderer.exemplo.com" 
    port: 7054
```

### 3. Organizações, CAs e Peers
Define os participantes da rede e seus respectivos nós de processamento.
```yaml
organizations:
  - name: "Org1"
    # Identificador único da organização dentro da rede (MSP).
    msp_id: "Org1MSP"
    # CA da organização, usada para emitir certificados de peers, admins e usuários.
    ca:
      name: "ca-org1"
      host: "ca.org1.exemplo.com"
      port: 8054
    peers:
      - name: "peer0"
        host: "peer0.org1.exemplo.com"
        # Porta de comunicação gRPC do Peer.
        port: 7051
        # Porta específica para o modelo CCAAS; o Peer se comunica com o Chaincode por aqui.
        chaincode_port: 7052
    # ... repete-se para outras orgs (Org2, Org3, Org4)
```
### 4. Configuração de Canais 
Define quais organizações colaboram em quais canais. **Atenção**: É obrigatório que pelo menos um canal contenha todas as organizações para o bootstrap da rede.
```yaml
channels:
  # É obrigatório que pelo menos um canal contenha TODAS as orgs para o bootstrap.
  - name: "channel-all"
    participating_orgs: ["Org1", "Org2", "Org3", "Org4"]
    # Política de assinatura necessária para alterações no consórcio do canal.
    consenter_policy: "AND('OrdererMSP.member')"
  - name : "channel12"
    participating_orgs: ["Org1", "Org2"]
    consenter_policy: "AND('OrdererMSP.member')"
```

### 5. Deploy de Chaincodes (CCAAS)
Configura os contratos inteligentes no modelo Chaincode-as-a-Service.
```yaml
chaincodes:
  - name: "basic_asset"
    # Caminho local para o código-fonte (necessário para o builder CCAAS).
    path: "./chaincode/basic_asset" 
    channel: "channel-all"
    lang: "go"                       
    version: "1.0"
    sequence: 1
    # Porta em que o container isolado do chaincode estará escutando (CCAAS).
    port: 9999                        
    # Regra que define quais orgs precisam assinar para validar uma transação.
    endorsement_policy: "AND('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member', 'Org4MSP.member')"
    
    # Configurações de Private Data Collections (PDC).
    pdc: 
      - name: "collectionPrivate"
        policy: "OR('Org1MSP.member')"
        required_peer_count: 1
        max_peer_count: 3
        block_to_live: 1000
        member_only_read: true
        member_only_write: true
```
[⬆ Voltar ao topo](#topo)


## 📂 Como executar

### 1. Preparar Ambiente
Certifique-se de ter o Docker e Python 3.12+ instalados. O script interno verificará e baixará os binários do Fabric automaticamente se necessário.

### 2. Comandos Principais
O automatizador utiliza argumentos via CLI para facilitar o controle:
- Subir a rede completa:
```bash
python3 main.py --network ./project_config/network_BFT.yaml --up
```
(Opcional: adicione `--log` para salvar a saída em arquivos ao invés do terminal)
- Limpar Infraestrutura (Containares/Redes):
```bash
python3 main.py --network ./project_config/network_BFT.yaml --clean net
```
- Limpeza total (incluido binários e ferramentas baixadas):
```bash
python3 main.py --network ./project_config/network_BFT.yaml --clean all
```
### 3. Interagir com o Ledger
Após a rede estar ativa, você pode usar o utilitário CLI incluso para realizar transações rápidas:
- Iniciar o Ledger:
```bash
./scripts/ledger_cli.sh Org1 peer0 init 
```
* Criar um novo Asset:
```bash
./scripts/ledger_cli.sh Org1 peer0 create asset7 blue 5 "Rian" 100 
```
- Listar todos os Assets:
```bash
./scripts/ledger_cli.sh Org1 peer0 all
```
- Invocação Genérica (em qualquer chaincode):
```bash
./scripts/ledger_cli.sh Org1 peer0 invoke meu_contrato '{"function":"MinhaFuncao","Args":["arg1"]}'
```

Isso irá criar a network apresentando logs a cada passo da criação. Por enquanto não há uma opção para limpar a network, caso queira limpar tudo basta rodar o script em `scripts/clean_all.yaml` ou se quiser limpar somente os artefatos da network utilize `scripts/clean_network.yaml`

[⬆ Voltar ao topo](#topo)

## 📄 Código-fonte

🔗 [https://github.com/RianValcanaia/IC_Create_Network](https://github.com/RianValcanaia/IC_Create_Network)

[⬆ Voltar ao topo](#topo)
