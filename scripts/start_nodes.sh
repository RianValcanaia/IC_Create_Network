#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
# Script bash estático que utiliza o Docker Compose para subir os containers dos Orderers e dos Peers da rede.

source $(dirname "$0")/utils.sh 

COMPOSE_FILE="$NETWORK_DIR/compose/compose-nodes.yaml" 

if [ ! -f "$COMPOSE_FILE" ]; then
    errorln "Arquivo não encontrado: $COMPOSE_FILE"
    exit 1
fi

infoln "Subindo Orderers e Peers..."
NETWORK_BASE=${NETWORK_NAME:-$(yq -r '.network.name' "$NETWORK_DIR/../project_config/network.yaml")}
docker-compose -f "$COMPOSE_FILE" -p "${NETWORK_BASE}_net" up -d

if [ $? -eq 0 ]; then
    successln "Nós da rede iniciados com sucesso."
else
    errorln "Falha ao subir contêineres dos nós."
    exit 1
fi