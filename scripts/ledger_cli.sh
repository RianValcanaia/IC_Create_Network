#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License

# Script para invocar funções de chaincode via CLI do peer, usando o contexto da rede ativa (contexto_ativo.json) para descobrir certificados TLS e portas dos peers.
# Endossa somente com o <Peer> da <Org> passados como argumento (visão desse peer no ledger) — não pede endosso de nenhum outro peer/org.
# Uso: ./ledger_cli.sh <Org> <Peer> <channel> <chaincode> '<json payload>'

# --- Configurações de Caminho ---
if [ -n "$ZSH_VERSION" ]; then SCRIPT_PATH="${(%):-%x}"; else SCRIPT_PATH="${BASH_SOURCE[0]}"; fi
SCRIPT_DIR=$(cd "$(dirname "$SCRIPT_PATH")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

# --- Cores para Output ---
infon() { echo -e "\033[1;34m[INFO]\033[0m $1"; }

# --- Carregar Ambiente do Peer Atual ---
# set_env.sh já exporta CORE_PEER_ADDRESS/CORE_PEER_TLS_ROOTCERT_FILE do <Org> <Peer>
# pedidos — são reaproveitados abaixo como único endossador da invocação.
source "$SCRIPT_DIR/set_env.sh" "$1" "$2"
if [ $? -ne 0 ]; then exit 1; fi

CONTEXT_FILE="$NETWORK_DIR/contexto_ativo.json"

# --- Variáveis Dinâmicas via JQ ---
DOMAIN=$(jq -r '.domain' "$CONTEXT_FILE")
ORDERER_PORT=$(jq -r '.orderers[0].port' "$CONTEXT_FILE")
ORDERER_NAME=$(jq -r '.orderers[0].name' "$CONTEXT_FILE")
ORDERER_CA="$NETWORK_DIR/organizations/ordererOrganizations/${DOMAIN}/orderers/${ORDERER_NAME}.${DOMAIN}/tls/ca.crt"

# --- Preparar Argumentos ---
# Uso: ./ledger_cli.sh <Org> <Peer> <channel> <chaincode> '<json payload>'
# Exemplo: ./ledger_cli.sh Org1 peer0 channel-all cc_basic_asset '{"function":"InitLedger","Args":[]}'
INVOKE_CHANNEL=$3
INVOKE_CC=$4
INVOKE_PAYLOAD=$5
if [ -z "$INVOKE_CHANNEL" ] || [ -z "$INVOKE_CC" ] || [ -z "$INVOKE_PAYLOAD" ]; then
    echo "Uso: $0 <Org> <Peer> <channel> <chaincode> '<json payload>'"
    echo ""
    echo "Exemplo:"
    echo "  $0 Org1 peer0 channel-all cc_basic_asset '{\"function\":\"InitLedger\",\"Args\":[]}'"
    echo "  $0 Org1 peer0 channel-all cc_basic_asset '{\"function\":\"GetAllAssets\",\"Args\":[]}'"
    exit 1
fi

infon "Invocando função em $INVOKE_CC (canal $INVOKE_CHANNEL) usando somente $1/$2 como endossador..."
peer chaincode invoke \
    -o localhost:${ORDERER_PORT} \
    --ordererTLSHostnameOverride ${ORDERER_NAME}.${DOMAIN} \
    --tls --cafile "$ORDERER_CA" \
    -C "$INVOKE_CHANNEL" -n "$INVOKE_CC" \
    --peerAddresses "$CORE_PEER_ADDRESS" --tlsRootCertFiles "$CORE_PEER_TLS_ROOTCERT_FILE" \
    -c "$INVOKE_PAYLOAD"
