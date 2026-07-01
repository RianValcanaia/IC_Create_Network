#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
# Realiza a limpeza da infraestrutura atual, derrubando containers de CA, Peers e Orderers, removendo volumes e limpando a rede Docker

source $(dirname "$0")/utils.sh
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NETWORK_BASE=${NETWORK_NAME:-$(yq -r '.network.name' "$PROJECT_ROOT/project_config/network.yaml")}
NETWORK_NAME="${NETWORK_BASE}_net"

infoln "Iniciando limpeza da infraestrutura para a rede: $NETWORK_BASE"

# derrubar via Docker Compose (cobre modo local e distribuído com nomes por máquina)
for CA_COMPOSE in "$PROJECT_ROOT"/network/compose/compose-ca*.yaml; do
    [ -f "$CA_COMPOSE" ] || continue
    infoln "Derrubando containers CA ($CA_COMPOSE)..."
    docker-compose -f "$CA_COMPOSE" -p "${NETWORK_BASE}_ca" down --volumes --remove-orphans || true
done

for NODE_COMPOSE in "$PROJECT_ROOT"/network/compose/compose-nodes*.yaml; do
    [ -f "$NODE_COMPOSE" ] || continue
    infoln "Derrubando containers de nós ($NODE_COMPOSE)..."
    docker-compose -f "$NODE_COMPOSE" -p "${NETWORK_BASE}_net" down --volumes --remove-orphans || true
done

# Purga volumes nomeados do projeto por PADRÃO — robusto a compose ausente/renomeado.
# Evita o 405 "channel already exists" no redeploy: o estado de canal do orderer vive
# num volume nomeado (${NETWORK_BASE}_net_ordererN.dominio) que o `down` só remove se
# o compose que o declarou ainda existir na hora do clean.
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

# limpar arquivos gerados — preserva network/logs/ (contém fabric-deploy.sh e logs do SLURM)
if [ -d "$PROJECT_ROOT/network" ]; then
    infoln "Limpando diretório network/ (preservando logs/)..."
    fix_permissions "$PROJECT_ROOT/network"
    docker run --rm -v "$PROJECT_ROOT/network":/data alpine sh -c \
        'find /data -mindepth 1 -maxdepth 1 ! -name logs -exec rm -rf {} +'
    find "$PROJECT_ROOT/network" -mindepth 1 -maxdepth 1 ! -name logs -exec rm -rf {} + 2>/dev/null || true
fi

# limpar scripts gerados 
remove_if_exists "$PROJECT_ROOT/scripts/register_enroll.sh" 
remove_if_exists "$PROJECT_ROOT/scripts/create_artifacts.sh" 
remove_if_exists "$PROJECT_ROOT/scripts/create_channel.sh" 
remove_if_exists "$PROJECT_ROOT/scripts/deploy_chaincode.sh" 

successln "Limpeza da rede concluída com sucesso!" 
