#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License

# Executa uma limpeza profunda no ambiente: infraestrutura Docker de TODAS as
# redes (layout network/<pasta>), artefatos gerados e scripts gerados.
# NÃO remove builders/ — é versionado no git e necessário para o modelo CCAAS;
# ao contrário de bin/ (binários do Fabric), nada recria builders/ automaticamente.

source $(dirname "$0")/utils.sh

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

infoln "Limpando ambiente no diretório: $PROJECT_ROOT"

# remove pasta bin/ (binários do Fabric, redownload automático via check_reqs.sh)
if [ -d "$PROJECT_ROOT/bin" ]; then
    infoln "Removendo pasta bin/..."
    rm -rf "$PROJECT_ROOT/bin"
    successln "bin/ removida."
else
    warnln "bin/ não existe. Ignorando."
fi

# remove arquivos especificos
SCRIPTS_DIR="$PROJECT_ROOT/scripts"

remove_if_exists "$SCRIPTS_DIR/register_enroll.sh"
remove_if_exists "$SCRIPTS_DIR/create_artifacts.sh"
remove_if_exists "$SCRIPTS_DIR/create_channel.sh"
remove_if_exists "$SCRIPTS_DIR/deploy_chaincode.sh"
remove_if_exists "$SCRIPTS_DIR/redeploy_chaincode.sh"
remove_if_exists "$SCRIPTS_DIR/start_chaincodes.sh"

# remove artefatos de chaincode gerados pelo ChaincodeDeployGenerator
# (pacote CCAAS e configuração de PDC; recriados a partir do nome no YAML a cada --up)
infoln "Removendo artefatos de chaincode gerados (*.tar.gz / *_collections.json)..."
find "$PROJECT_ROOT/chaincode" -maxdepth 1 -type f \( -name "*.tar.gz" -o -name "*_collections.json" \) -delete 2>/dev/null || true
successln "Artefatos de chaincode gerados removidos."

infoln "Removendo infraestrutura Docker de todas as redes..."

# itera sobre cada rede em network/<pasta> limpando containers, volumes e rede Docker
for NET_DIR in "$PROJECT_ROOT"/network/*/; do
    [ -d "$NET_DIR" ] || continue
    NET_BASE="$(jq -r '.network // empty' "$NET_DIR/contexto_ativo.json" 2>/dev/null)"
    [ -n "$NET_BASE" ] || NET_BASE="$(basename "$NET_DIR")"
 
    # derruba via Docker Compose todos os compose files encontrados (CA e nodes)
    for CA_COMPOSE in "$NET_DIR"compose/compose-ca*.yaml; do
        [ -f "$CA_COMPOSE" ] || continue
        infoln "[$NET_BASE] Derrubando containers CA ($CA_COMPOSE)..."
        docker-compose -f "$CA_COMPOSE" -p "${NET_BASE}_ca" down --volumes --remove-orphans \
            || errorln "Falha ao derrubar $CA_COMPOSE. Pode haver resíduos."
    done

    # derruba via Docker Compose todos os compose files encontrados (CA e nodes)
    for NODE_COMPOSE in "$NET_DIR"compose/compose-nodes*.yaml; do
        [ -f "$NODE_COMPOSE" ] || continue
        infoln "[$NET_BASE] Derrubando containers de nós ($NODE_COMPOSE)..."
        docker-compose -f "$NODE_COMPOSE" -p "${NET_BASE}_net" down --volumes --remove-orphans \
            || errorln "Falha ao derrubar $NODE_COMPOSE. Pode haver resíduos."
    done

    # Purga volumes nomeados do projeto por padrao
    infoln "[$NET_BASE] Removendo volumes nomeados (${NET_BASE}_net_* / _ca_*)..."
    docker volume ls -q | grep -E "^${NET_BASE}_(net|ca)_" | xargs -r docker volume rm -f 2>/dev/null || true

    # remove a docker network da rede
    if docker network inspect "${NET_BASE}_net" >/dev/null 2>&1; then
        infoln "[$NET_BASE] Removendo Docker network ${NET_BASE}_net..."
        docker network rm "${NET_BASE}_net" 2>/dev/null || true
    fi
done

# limpa a pasta network/ (organizations, compose, genesis block de TODAS as redes)
if [ -d "$PROJECT_ROOT/network" ]; then
    infoln "Removendo conteúdo gerado em network/..."

    fix_permissions "$PROJECT_ROOT/network"

    # container Alpine temporario para apagar os arquivos.
    docker run --rm -v "$PROJECT_ROOT/network":/data alpine sh -c 'rm -rf /data/*'

    # se caso falhar o anterior, tenta apagar diretamente
    rm -rf "$PROJECT_ROOT/network"/* 2>/dev/null || true

    successln "Pasta network/ limpa."
else
    warnln "Pasta network/ não existe. Nada a limpar."
fi

# remove pastas __pycache__ geradas pelo Python (somente na limpeza total)
infoln "Removendo pastas __pycache__..."
find "$PROJECT_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
successln "Pastas __pycache__ removidas."
infoln "Limpando containers de Chaincode (CCAAS) remanescentes..."
docker ps -a --format '{{.Names}}' | grep -E "\.channel-" | xargs -I {} docker rm -f {} 2>/dev/null || true
successln "Containers de chaincode removidos."

successln "Limpeza concluída!"