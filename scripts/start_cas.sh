#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
# Script responsável por criar a rede Docker e iniciar os containers das Autoridades Certificadoras (CAs), além de corrigir permissões de pastas geradas pelo Docker.

source $(dirname "$0")/utils.sh

# define o diretório 'network' caso não tenha sido injetado pelo Python
if [ -z "$NETWORK_DIR" ]; then
    NETWORK_DIR="$(cd "$(dirname "$0")/../network" && pwd)"
fi

COMPOSE_FILE="$NETWORK_DIR/compose/compose-ca.yaml"

# verificacao de seguranca
if [ ! -f "$COMPOSE_FILE" ]; then
    errorln "Arquivo não encontrado: $COMPOSE_FILE"
    errorln "O gerador Python (src/generator/compose.py) rodou com sucesso?"
    exit 1
fi

# criar a network, como este eh o primeiro docker-compose criamos aqui mesmo
NETWORK_BASE=${NETWORK_NAME:-$(yq -r '.network.name' "$NETWORK_DIR/../project_config/network.yaml")}
infoln "Criando a network ${NETWORK_BASE}_net"
docker network create "${NETWORK_BASE}_net" || true

# executa o docker compose
infoln "Subindo containers..."
docker-compose -f "$COMPOSE_FILE" -p "${NETWORK_BASE}_ca" up -d

if [ $? -ne 0 ]; then
    errorln "Falha ao executar docker-compose up."
    exit 1
fi

# verifica se os containers estao rodando
sleep 3

USER_ID=$(id -u)
GROUP_ID=$(id -g)

# roda um container Alpine que monta a pasta network e muda o dono
docker run --rm -v "$NETWORK_DIR":/data alpine chown -R $USER_ID:$GROUP_ID /data
if [ $? -eq 0 ]; then
    successln "Permissões corrigidas com sucesso."
else
    warnln "Falha ao corrigir permissões automaticamente. Talvez precise de sudo manual."
fi


if docker ps --format '{{.Names}} {{.Image}}' | grep -q "fabric-ca"; then
    successln "--- CAs Iniciadas com Sucesso ---"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep "ca-" # filtra container que começam com ca-, se no network escrever de outra forma, dara erro aqui
else
    warnln "Aviso: O docker-compose retornou sucesso, mas não encontrei containers 'fabric-ca' rodando."
    warnln "Verifique os logs com: docker-compose -f $COMPOSE_FILE logs"
fi