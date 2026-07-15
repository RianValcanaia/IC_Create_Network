#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
# Realiza a limpeza da infraestrutura atual, derrubando containers de CA, Peers e Orderers, removendo volumes e limpando a rede Docker

source $(dirname "$0")/utils.sh
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NETWORK_BASE=${NETWORK_NAME:-$(yq -r '.network.name' "${NETWORK_CONFIG:-$PROJECT_ROOT/project_config/network.yaml}")}

# caminhos isolados por rede, com fallback caso o script rode fora do orquestrador
NETWORK_DIR="${NETWORK_DIR:-$PROJECT_ROOT/network/$NETWORK_BASE}"
GENERATED_SCRIPTS_DIR="$PROJECT_ROOT/scripts/$NETWORK_BASE"
DOCKER_NET_NAME="${NETWORK_BASE}_net"

infoln "Iniciando limpeza da infraestrutura para a rede: $NETWORK_BASE"
infoln "  NETWORK_DIR: $NETWORK_DIR"
infoln "  SCRIPTS_DIR: $GENERATED_SCRIPTS_DIR"

# derrubar via Docker Compose 
CA_COMPOSE="$NETWORK_DIR/compose/compose-ca.yaml"
if [ -f "$CA_COMPOSE" ]; then 
    infoln "Derrubando containers da CA..." 
    docker-compose -f "$CA_COMPOSE" -p "${NETWORK_BASE}_ca" down --volumes --remove-orphans 
fi

NODE_COMPOSE="$NETWORK_DIR/compose/compose-nodes.yaml"
if [ -f "$NODE_COMPOSE" ]; then 
    infoln "Derrubando containers dos nós..." 
    docker-compose -f "$NODE_COMPOSE" -p "${NETWORK_BASE}_net" down --volumes --remove-orphans 
fi

# forçar parada de qualquer container órfão na rede 
infoln "Limpando containers remanescentes na rede $DOCKER_NET_NAME..."
docker ps -a --filter network="$DOCKER_NET_NAME" -q | xargs -r docker rm -f 

# remover a rede Docker 
if docker network inspect "$DOCKER_NET_NAME" >/dev/null 2>&1; then 
    infoln "Removendo Docker network $DOCKER_NET_NAME..." 
    docker network rm "$DOCKER_NET_NAME" 
fi

# limpar arquivos gerados 
if [ -d "$NETWORK_DIR" ]; then 
    infoln "Limpando diretório $NETWORK_DIR..." 
    fix_permissions "$NETWORK_DIR" 
    docker run --rm -v "$NETWORK_DIR":/data alpine sh -c 'rm -rf /data/*' 
    rm -rf "$NETWORK_DIR"/* 2>/dev/null || true 
fi

# limpar scripts gerados 
if [ -d "$GENERATED_SCRIPTS_DIR" ]; then
    infoln "Limpando scripts gerados em $GENERATED_SCRIPTS_DIR..."
    remove_if_exists "$GENERATED_SCRIPTS_DIR/register_enroll.sh" 
    remove_if_exists "$GENERATED_SCRIPTS_DIR/create_artifacts.sh" 
    remove_if_exists "$GENERATED_SCRIPTS_DIR/create_channel.sh" 
    remove_if_exists "$GENERATED_SCRIPTS_DIR/deploy_chaincode.sh"
    rmdir "$GENERATED_SCRIPTS_DIR" 2>/dev/null || true   # remove a pasta se ficou vazia
fi

successln "Limpeza da rede concluída com sucesso!" 
