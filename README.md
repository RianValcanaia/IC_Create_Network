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
- [🧱 Arquitetura de geradores](#-arquitetura-de-geradores)
- [🧰 Funcionalidades Atuais](#-funcionalidades-atuais)
- [📂 Como executar](#-como-executar)
  - [Modo local (desenvolvimento)](#modo-local-desenvolvimento)
  - [Modo distribuído manual](#modo-distribuído-manual)
  - [Modo distribuído via SLURM](#modo-distribuído-via-slurm)
- [⚙️ Referência de comandos](#️-referência-de-comandos)
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
| `ComposeGenerator` | Cria os arquivos YAML para subir os serviços de CA, peers e orderers. Em modo distribuído injeta `extra_hosts` com os IPs reais dos nós remotos. |
| `CryptoGenerator` | Gera `register_enroll.sh` usando o `fabric-ca-client`. Em modo distribuído usa os IPs reais de cada CA. |
| `ConfigTxGenerator` | Traduz a topologia para o `configtx.yaml` e gera os perfis de canal (Raft ou BFT). |
| `ChannelScriptGenerator` | Gera `create_channel.sh` para join de orderers (`osnadmin`) e peers. Em modo distribuído usa IPs reais. |
| `ChaincodeDeployGenerator` | Gera `deploy_chaincode.sh` (lifecycle completo) e `start_chaincodes.sh` (containers CCAAS). |
| `SlurmDeployGenerator` | Orquestra o deploy distribuído submetendo jobs SLURM encadeados por dependência. |
| `ConfigParser` | Valida se a configuração é semanticamente correta (ex: portas únicas, domínios válidos). |

[⬆ Voltar ao topo](#topo)

## 🧰 Funcionalidades Atuais
- **Validação Semântica**: Verifica erros comuns no `network.yaml` antes de iniciar a rede.
- **Orquestração de CAs**: Geração automática de containers Docker para cada autoridade certificadora.
- **Crypto Automatizado**: Scripting para registro de identidades com suporte a NodeOUs.
- **Geração de Artefatos**: Criação do bloco de gênese e arquivos `.tx` de canal. *Em Desenvolvimento*.

[⬆ Voltar ao topo](#topo)

## 📂 Como executar

### Pré-requisitos

- Python 3.10+
- Docker e Docker Compose (nos nós de compute)
- Go 1.22+ (para compilação local dos chaincodes)
- `fabric-ca-client`, `peer`, `osnadmin`, `configtxgen` no `$PATH` (baixados automaticamente na primeira execução)
- Para deploy distribuído via SLURM: acesso de usuário ao `sbatch` no cluster e filesystem compartilhado entre todos os nós

---

### Modo local (desenvolvimento)

Sobe toda a rede em uma única máquina. Ideal para testes e desenvolvimento.

**1. Defina a topologia em `project_config/network.yaml`.**

**2. Suba a rede:**
```bash
python3 main.py --up
```

O comando executa automaticamente: verificação de pré-requisitos → geração de certificados → artefatos de canal → peers e orderers → canais → chaincode lifecycle → containers CCAAS.

**3. Limpar a rede:**
```bash
python3 main.py --clean net   # derruba containers e remove artefatos gerados
python3 main.py --clean all   # idem + remove binários do Fabric
```

---

### Modo distribuído manual

Útil quando você quer controlar manualmente quais containers sobem em cada máquina. Requer que o setup (enrollment, artefatos, canais, chaincode lifecycle) já tenha sido executado a partir de uma máquina com acesso a todas as CAs.

**1. Configure `machines` no `network.yaml`**, atribuindo cada componente a uma máquina:

```yaml
machines:
  maquina_1:
    ip: "192.168.1.10"
    coordinator: true
  maquina_2:
    ip: "192.168.1.11"

organizations:
  - name: "Org1"
    ca:
      machine: "maquina_1"
    peers:
      - name: "peer0"
        machine: "maquina_1"
```

**2. Execute o setup completo uma vez** (de qualquer máquina com acesso à LAN):
```bash
python3 main.py --up   # sem --machine: roda enrollment, canais e chaincode completo
```

**3. Em cada máquina, suba apenas seus containers:**
```bash
# Na maquina_1:
python3 main.py --up --machine maquina_1

# Na maquina_2:
python3 main.py --up --machine maquina_2
```

Os `docker-compose` gerados incluem `extra_hosts` apontando os hostnames remotos para os IPs reais do cluster, garantindo conectividade entre containers em máquinas diferentes.

---

### Modo distribuído via SLURM

Gera **um único script** com todas as fases do deploy, submetido como um job SLURM a partir do nó de login. O job roda nos nós de compute sobre o diretório compartilhado (NFS) definido em `slurm.cluster_project_dir`.

**1. Configure `network.yaml`** com `slurm.cluster_project_dir` e, em cada máquina, `ip`, `slurm_node` e exatamente um `coordinator`:

```yaml
slurm:
  cluster_project_dir: "/mnt/prj/<usuario>/<projeto>/IC_Create_Network"

machines:
  maquina_1:
    ip: "10.10.20.151"
    slurm_node: "baia1"    # nome do nó no SLURM (sbatch --nodelist)
    coordinator: true      # executa enrollment, canais e lifecycle do chaincode
  maquina_2:
    ip: "10.10.20.152"
    slurm_node: "baia2"
```

**2. Gere o script** (a partir do diretório do projeto no NFS):
```bash
python3 main.py --slurm-deploy --time 03:00:00   # gera network/logs/fabric-deploy.sh
```

**3. Submeta e acompanhe:**
```bash
sbatch network/logs/fabric-deploy.sh
squeue -u $USER
tail -f network/logs/slurm-<jobid>-fabric-deploy.log   # erros em slurm-<jobid>-fabric-deploy.err
```

Se o script for gerado fora do cluster, copie-o antes para `<cluster_project_dir>/network/logs/` (o `main.py` imprime o `scp` exato).

Fases executadas dentro do job (via `srun`, chamando `main.py --start`/`--setup`):

| Fase | Etapa | Executa em |
|:---:|:---|:---|
| -2 | Limpeza dos containers | Todos os nós (paralelo) |
| -1 | Limpeza dos artefatos gerados (preserva `bin/`) | Coordenador |
| 0 | Pré-requisitos (baixa os binários do Fabric se faltarem) | Coordenador |
| 1 | CAs | Todos os nós (paralelo) |
| 2 | Enrollment | Coordenador |
| 3 | Artefatos de canal | Coordenador |
| 4 | Peers e orderers | Todos os nós (paralelo) |
| 5 | Configuração de canais | Coordenador |
| 6 | Chaincode lifecycle | Coordenador |
| 7 | Containers CCAAS | Nós com chaincode atribuído |

> **Requisito:** todos os nós devem acessar o mesmo diretório do projeto via filesystem compartilhado (NFS, Lustre, etc.). Certificados, artefatos e logs ficam em `network/` e são lidos por todos os nós sem cópia manual.

### Artefatos gerados (não versionados)

Tudo o que é produzido em execução fica fora do git (`.gitignore`) e é recriado pelo próprio fluxo:

| Caminho | Origem |
|:---|:---|
| `bin/` | Binários do Fabric, baixados por `scripts/check_reqs.sh` (fase de pré-requisitos) |
| `network/` | Crypto, compose, artefatos de canal, `contexto_ativo.json`, `fabric-deploy.sh` e logs do SLURM |
| `chaincode/*/chaincode`, `chaincode/*.tar.gz` | Chaincode compilado e pacotes CCAAS (`deploy_chaincode.sh`) |
| `network/ccaas-tls/` | CA e certificados de servidor TLS dos chaincodes CCAAS |
| `scripts/{register_enroll,create_artifacts,create_channel,deploy_chaincode,start_chaincodes}.sh` | Scripts gerados pelos geradores a cada execução |

### Chaincode como serviço (CCAAS) com TLS

Os chaincodes rodam em containers próprios (CCAAS, Fabric 3.x) e o canal peer → chaincode usa **TLS de servidor**:

- O gerador cria uma CA do CCAAS e um certificado por chaincode em `network/ccaas-tls/`, com SAN igual ao hostname do container (`<chaincode>.<canal>`).
- O `connection.json` do pacote traz `"tls_required": true` e o `root_cert` dessa CA — o peer verifica o certificado do chaincode.
- O container recebe a chave e o certificado (`CHAINCODE_TLS_KEY_FILE` / `CHAINCODE_TLS_CERT_FILE`) e o `shim.ChaincodeServer` sobe com TLS (`ccaasTLS()` em cada chaincode).

[⬆ Voltar ao topo](#topo)

## ⚙️ Referência de comandos

```
python3 main.py [COMANDO] [OPÇÕES]

Comandos principais (mutuamente exclusivos):
  --up                    Sobe a rede completa localmente.
                          Com --machine: sobe apenas os containers daquela máquina.
  --start                 Inicia uma fase de containers numa máquina (usado pelo job SLURM).
                          Requer: --machine <nome> --phase [clean|cas|nodes|ccaas]
  --setup                 Executa uma fase de setup no coordenador (usado pelo job SLURM).
                          Requer: --phase [clean|prereqs|enroll|artifacts|channels|chaincode]
  --slurm-deploy          Gera network/logs/fabric-deploy.sh para submeter com sbatch.
                          Requer: --time HH:MM:SS

Opções auxiliares:
  --machine <nome>        Máquina definida em network.yaml > machines.
  --phase <fase>          Fase a executar (ver --start e --setup acima).
  --time HH:MM:SS         Duração máxima do job SLURM (com --slurm-deploy).
  --clean [all|net]       Limpa a infraestrutura.
  --log                   Salva saída dos scripts em network/logs/.
  -n, --network <path>    Caminho alternativo para o network.yaml.
```

[⬆ Voltar ao topo](#topo)

## 📄 Código-fonte

🔗 [https://github.com/RianValcanaia/IC_Create_Network](https://github.com/RianValcanaia/IC_Create_Network)

[⬆ Voltar ao topo](#topo)