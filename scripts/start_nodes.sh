#!/bin/bash
# estatico

source $(dirname "$0")/utils.sh 

COMPOSE_FILE="$NETWORK_DIR/compose/compose-nodes.yaml" 

if [ ! -f "$COMPOSE_FILE" ]; then
    errorln "Arquivo não encontrado: $COMPOSE_FILE"
    exit 1
fi

infoln "Subindo Orderers e Peers..."
docker-compose -f "$COMPOSE_FILE" -p "fabric_net" up -d 

if [ $? -eq 0 ]; then
    successln "Nós da rede iniciados com sucesso."
else
    errorln "Falha ao subir contêineres dos nós."
    exit 1
fi