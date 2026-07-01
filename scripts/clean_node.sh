#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
# Limpa os containers Docker de um nó específico no deploy distribuído.
# Recebe os paths dos compose files via variáveis de ambiente injetadas pelo Python:
#   COMPOSE_FILE_CA    — compose-ca-{machine}.yaml
#   COMPOSE_FILE_NODES — compose-nodes-{machine}.yaml

source $(dirname "$0")/utils.sh

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NETWORK_BASE=${NETWORK_NAME:-$(yq -r '.network.name' "$PROJECT_ROOT/project_config/network.yaml")}

# ── Derruba CAs ──────────────────────────────────────────────────────────────
if [ -n "${COMPOSE_FILE_CA:-}" ] && [ -f "$COMPOSE_FILE_CA" ]; then
    infoln "Derrubando containers CA ($COMPOSE_FILE_CA)..."
    docker-compose -f "$COMPOSE_FILE_CA" -p "${NETWORK_BASE}_ca" down --volumes --remove-orphans || true
else
    warnln "compose-ca não encontrado para este nó. Pulando."
fi

# ── Derruba peers e orderers ──────────────────────────────────────────────────
if [ -n "${COMPOSE_FILE_NODES:-}" ] && [ -f "$COMPOSE_FILE_NODES" ]; then
    infoln "Derrubando containers de nós ($COMPOSE_FILE_NODES)..."
    docker-compose -f "$COMPOSE_FILE_NODES" -p "${NETWORK_BASE}_net" down --volumes --remove-orphans || true
else
    warnln "compose-nodes não encontrado para este nó. Pulando."
fi

# ── Purga volumes nomeados do projeto por PADRÃO (robusto a compose ausente) ───
# Evita o 405 "channel already exists" no redeploy: o estado de canal do orderer
# vive num volume nomeado que o `down` só remove com o compose original presente.
infoln "Removendo volumes nomeados do projeto (${NETWORK_BASE}_net_* / _ca_*)..."
docker volume ls -q | grep -E "^${NETWORK_BASE}_(net|ca)_" | xargs -r docker volume rm -f 2>/dev/null || true

# ── Remove containers CCAAS órfãos ────────────────────────────────────────────
docker ps -a --format '{{.Names}}' | grep -E "\.channel" | xargs -I {} docker rm -f {} 2>/dev/null || true

# ── Remove rede Docker ────────────────────────────────────────────────────────
DOCKER_NET="${NETWORK_BASE}_net"
if docker network inspect "$DOCKER_NET" >/dev/null 2>&1; then
    infoln "Removendo Docker network $DOCKER_NET..."
    docker network rm "$DOCKER_NET" || true
fi

successln "Limpeza do nó concluída."
