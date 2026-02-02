#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
# Executa uma limpeza profunda no ambiente, removendo não apenas a infraestrutura Docker, mas também os binários baixados e as pastas de builders.

source $(dirname "$0")/utils.sh

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NETWORK_BASE=${NETWORK_NAME:-$(yq -r '.network.name' "$PROJECT_ROOT/project_config/network.yaml")}
PROJECT_CA="${NETWORK_BASE}_ca"
PROJECT_NET="${NETWORK_BASE}_net"

infoln "Limpando ambiente no diretório: $PROJECT_ROOT"

# remove pasta bin/
if [ -d "$PROJECT_ROOT/bin" ]; then
    infoln "Removendo pasta bin/..."
    rm -rf "$PROJECT_ROOT/bin"
    successln "bin/ removida."
else
    warnln "bin/ não existe. Ignorando."
fi

# remove pasta builders/
if [ -d "$PROJECT_ROOT/builders" ]; then
    infoln "Removendo pasta builders/..."
    rm -rf "$PROJECT_ROOT/builders"
    successln "builders/ removida."
else
    warnln "builders/ não existe. Ignorando."
fi


# remove arquivos especificos
SCRIPTS_DIR="$PROJECT_ROOT/scripts"

remove_if_exists "$SCRIPTS_DIR/register_enroll.sh"
remove_if_exists "$SCRIPTS_DIR/create_artifacts.sh"
remove_if_exists "$SCRIPTS_DIR/create_channel.sh"
remove_if_exists "$SCRIPTS_DIR/deploy_chaincode.sh"


infoln "Removendo arquivos docker-compose gerados..."

# docker compose down
CA_COMPOSE="$PROJECT_ROOT/network/compose/compose-ca.yaml"
if [ -f "$CA_COMPOSE" ]; then
    infoln "Encontrado compose-ca.yaml. Derrubando containers..."
    docker-compose -f "$CA_COMPOSE" -p "$PROJECT_CA" down --volumes --remove-orphans
    if [ $? -eq 0 ]; then
        successln "Containers e volumes removidos com sucesso."
    else
        errorln "Falha ao executar docker-compose down. Pode haver resíduos."
    fi
else
    warnln "Arquivo $CA_COMPOSE não encontrado. Pulando etapa de shutdown do Docker."
fi

# docker compose down
NODE_COMPOSE="$PROJECT_ROOT/network/compose/compose-nodes.yaml"
if [ -f "$NODE_COMPOSE" ]; then
    infoln "Encontrado compose-nodes.yaml. Derrubando containers..."
    docker-compose -f "$NODE_COMPOSE" -p "$PROJECT_NET" down --volumes --remove-orphans
    if [ $? -eq 0 ]; then
        successln "Containers e volumes removidos com sucesso."
    else
        errorln "Falha ao executar docker-compose down. Pode haver resíduos."
    fi
else
    warnln "Arquivo $NODE_COMPOSE não encontrado. Pulando etapa de shutdown do Docker."
fi

# limpa a pasta network/ (organizations, compose, genesis block)
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

infoln "Limpando containers de Chaincode (CCAAS)..."
docker ps -a --format '{{.Names}}' | grep -E "\.channel-all|\.channel12" | xargs -I {} docker rm -f {} 2>/dev/null || true
successln "Containers de chaincode removidos."

# Remove Docker network criada

PROJECT_NET="${NETWORK_BASE}_net"

if docker network inspect "$PROJECT_NET" >/dev/null 2>&1; then
    infoln "Removendo Docker network $PROJECT_NET..."
    docker network rm "$PROJECT_NET"
    successln "Network $PROJECT_NET removida."
else
    warnln "Docker network $PROJECT_NET não existe."
fi
successln "Limpeza concluída!"