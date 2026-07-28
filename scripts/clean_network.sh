#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License

# Realiza a limpeza da infraestrutura atual, derrubando containers de CA, Peers e Orderers, removendo volumes e limpando a rede Docker

source $(dirname "$0")/utils.sh
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NETWORK_BASE=${NETWORK_NAME:-$(yq -r '.network.name' "${NETWORK_CONFIG:-$PROJECT_ROOT/project_config/network.yaml}")}
NETWORK_NAME="${NETWORK_BASE}_net"
# diretório de runtime DESTA rede (layout network/<pasta>, a limpeza é escopada a ele para não derrubar outras redes coexistentes
NET_DIR="${NETWORK_DIR:-$PROJECT_ROOT/network/${NETWORK_FOLDER:-$NETWORK_BASE}}"

infoln "Iniciando limpeza da infraestrutura para a rede: $NETWORK_BASE"

# derrubar via Docker Compose
CA_COMPOSE="$NET_DIR/compose/compose-ca.yaml"
if [ -f "$CA_COMPOSE" ]; then
    infoln "Derrubando containers da CA..."
    docker-compose -f "$CA_COMPOSE" -p "${NETWORK_BASE}_ca" down --volumes --remove-orphans
fi

NODE_COMPOSE="$NET_DIR/compose/compose-nodes.yaml"
if [ -f "$NODE_COMPOSE" ]; then
    infoln "Derrubando containers dos nós..."
    docker-compose -f "$NODE_COMPOSE" -p "${NETWORK_BASE}_net" down --volumes --remove-orphans
fi

# Purga volumes nomeados do projeto por padrao
infoln "Removendo volumes nomeados do projeto (${NETWORK_BASE}_net_* / _ca_*)..."
docker volume ls -q | grep -E "^${NETWORK_BASE}_(net|ca)_" | xargs -r docker volume rm -f 2>/dev/null || true

# forçar parada de qualquer container órfão na rede
infoln "Limpando containers remanescentes na rede $NETWORK_NAME..."
docker ps -a --filter network="$NETWORK_NAME" -q | xargs -r docker rm -f 

# remover a rede Docker 
if docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then 
    infoln "Removendo Docker network $NETWORK_NAME..." 
    docker network rm "$NETWORK_NAME" 
fi

# limpar arquivos gerados (somente desta rede)
if [ -d "$NET_DIR" ]; then
    infoln "Limpando diretório $NET_DIR..."
    fix_permissions "$NET_DIR"
    docker run --rm -v "$NET_DIR":/data alpine sh -c 'rm -rf /data/*'
    rm -rf "$NET_DIR" 2>/dev/null || true
fi

# limpar scripts gerados 
remove_if_exists "$PROJECT_ROOT/scripts/register_enroll.sh" 
remove_if_exists "$PROJECT_ROOT/scripts/create_artifacts.sh" 
remove_if_exists "$PROJECT_ROOT/scripts/create_channel.sh" 
remove_if_exists "$PROJECT_ROOT/scripts/deploy_chaincode.sh" 

successln "Limpeza da rede concluída com sucesso!" 
