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
| `Parser` | Valida se a configuração é semanticamente correta (ex: portas únicas, domínios válidos)

[⬆ Voltar ao topo](#topo)

## 🧰 Funcionalidades Atuais
- **Validação Semântica**: Verifica erros comuns no `network.yaml` antes de iniciar a rede.
- **Orquestração de CAs**: Geração automática de containers Docker para cada autoridade certificadora.
- **Crypto Automatizado**: Scripting para registro de identidades com suporte a NodeOUs.
- **Geração de Artefatos**: Criação do bloco de gênese e arquivos `.tx` de canal. *Em Desenvolvimento*.

[⬆ Voltar ao topo](#topo)

## 📂 Como executar

### 1. Preparar Ambiente
Certifique-se de ter o Docker instalado. O script interno verificará e baixará os binários do Fabric se necessário. Defina a network fabric que deseja criar em `config/network.yaml`.

### 2. Rodar o Automatizador
```bash
python3 main.py
```
Isso irá criar a network apresentando logs a cada passo da criação. Por enquanto não há uma opção para limpar a network, caso queira limpar tudo basta rodar o script em `scripts/clean_all.yaml` ou se quiser limpar somente os artefatos da network utilize `scripts/clean_network.yaml`

[⬆ Voltar ao topo](#topo)

## 📄 Código-fonte

🔗 [https://github.com/RianValcanaia/IC_Create_Network](https://github.com/RianValcanaia/IC_Create_Network)

[⬆ Voltar ao topo](#topo)