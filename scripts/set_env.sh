#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
# Seta variáveis de ambiente passados por linha de comando <NOME_ORG> <NOME_PEER>

source $(dirname "$0")/utils.sh

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Uso: source ./scripts/set_env.sh <NOME_ORG> <NOME_PEER>"
    return 1
fi

if [ -n "$ZSH_VERSION" ]; then
    SCRIPT_PATH="${(%):-%x}"
else
    SCRIPT_PATH="${BASH_SOURCE[0]}"
fi

SCRIPT_DIR=$(cd "$(dirname "$SCRIPT_PATH")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
CONFIG_FILE="$PROJECT_ROOT/project_config/network.yaml"
NETWORK_DIR="$PROJECT_ROOT/network"

export PATH="$PROJECT_ROOT/bin:$PATH"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "[ERRO] Não encontrei o arquivo em: $CONFIG_FILE"
    return 1
fi

ORG_NAME=$1
PEER_NAME=$2

DOMAIN=$(yq -r '.network.domain' "$CONFIG_FILE")
MSP_ID=$(yq -r ".organizations[] | select(.name == \"$ORG_NAME\") | .msp_id" "$CONFIG_FILE")
PEER_PORT=$(yq -r ".organizations[] | select(.name == \"$ORG_NAME\") | .peers[] | select(.name == \"$PEER_NAME\") | .port" "$CONFIG_FILE")

if [ "$MSP_ID" = "null" ] || [ "$PEER_PORT" = "null" ]; then
    echo "[ERRO] Org ou Peer não encontrados em $CONFIG_FILE"
    return 1
fi

export FABRIC_CFG_PATH="$NETWORK_DIR/compose/peercfg"
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID="$MSP_ID"

PEER_FULL_NAME="${PEER_NAME}.${ORG_NAME}.${DOMAIN}"
ORG_PATH="$NETWORK_DIR/organizations/peerOrganizations/${ORG_NAME}.${DOMAIN}"

export CORE_PEER_TLS_ROOTCERT_FILE="${ORG_PATH}/peers/${PEER_FULL_NAME}/tls/ca.crt"
export CORE_PEER_MSPCONFIGPATH="${ORG_PATH}/users/Admin@${ORG_NAME}.${DOMAIN}/msp"
export CORE_PEER_ADDRESS="localhost:${PEER_PORT}"

echo "[SUCESSO] Ambiente configurado para $ORG_NAME ($PEER_NAME)"