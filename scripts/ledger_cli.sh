#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
# Uso: ./ledger_cli.sh <Org> <Peer> <action> [args...]
# --- Configurações de Caminho ---
if [ -n "$ZSH_VERSION" ]; then SCRIPT_PATH="${(%):-%x}"; else SCRIPT_PATH="${BASH_SOURCE[0]}"; fi
SCRIPT_DIR=$(cd "$(dirname "$SCRIPT_PATH")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
CONTEXT_FILE="$PROJECT_ROOT/network/contexto_ativo.json"
# --- Cores para Output ---
infon() { echo -e "\033[1;34m[INFO]\033[0m $1"; }
# --- Validação de Contexto ---
if [ ! -f "$CONTEXT_FILE" ]; then
    echo "Erro: Arquivo contexto_ativo.json não encontrado em $PROJECT_ROOT/network/"
    exit 1
fi
# --- Carregar Ambiente do Peer Atual ---
source "$SCRIPT_DIR/set_env.sh" "$1" "$2"
if [ $? -ne 0 ]; then exit 1; fi
# --- Variáveis Dinâmicas via JQ ---
DOMAIN=$(jq -r '.domain' "$CONTEXT_FILE")
CHANNEL_NAME="channel-all"
CC_NAME="basic_asset"
# Depois (dinâmico):
ORDERER_PORT=$(jq -r '.orderers[0].port' "$CONTEXT_FILE")
ORDERER_NAME=$(jq -r '.orderers[0].name' "$CONTEXT_FILE")
ORDERER_CA="$PROJECT_ROOT/network/organizations/ordererOrganizations/${DOMAIN}/orderers/${ORDERER_NAME}.${DOMAIN}/tls/ca.crt"
# --- Função para Montar Flags de Endosso (Dinamismo Puro) ---
# Esta função percorre todas as Orgs do JSON e pega o primeiro peer de cada uma
generate_peer_args() {
    local ARGS=""
    ORGS=$(jq -r '.orgs | keys[]' "$CONTEXT_FILE")
    
    for ORG in $ORGS; do
        # Pega o primeiro peer da lista desta Org
        FIRST_PEER=$(jq -r ".orgs[\"$ORG\"].peers | keys[0]" "$CONTEXT_FILE")
        PORT=$(jq -r ".orgs[\"$ORG\"].peers[\"$FIRST_PEER\"].port" "$CONTEXT_FILE")
        
        # Constrói o caminho do certificado TLS
        TLS_PATH="$PROJECT_ROOT/network/organizations/peerOrganizations/${ORG}.${DOMAIN}/peers/${FIRST_PEER}.${ORG}.${DOMAIN}/tls/ca.crt"
        
        ARGS="$ARGS --peerAddresses localhost:${PORT} --tlsRootCertFiles ${TLS_PATH}"
    done
    echo "$ARGS"
}
# --- Preparar Argumentos ---
ACTION=$3
ID=$4
PEER_ARGS=$(generate_peer_args)
case $ACTION in
    init)
        infon "Inicializando Ledger em todas as Orgs..."
        peer chaincode invoke -o localhost:${ORDERER_PORT} --ordererTLSHostnameOverride ${ORDERER_NAME}.${DOMAIN} --tls --cafile "$ORDERER_CA" -C "$CHANNEL_NAME" -n "$CC_NAME" $PEER_ARGS -c '{"function":"InitLedger","Args":[]}' 
        ;;
    create)
        infon "Criando Asset $ID..."
        peer chaincode invoke -o localhost:${ORDERER_PORT} --ordererTLSHostnameOverride ${ORDERER_NAME}.${DOMAIN} --tls --cafile "$ORDERER_CA" -C "$CHANNEL_NAME" -n "$CC_NAME" $PEER_ARGS -c "{\"function\":\"CreateAsset\",\"Args\":[\"$ID\",\"$5\",\"$6\",\"$7\",\"$8\"]}"
        ;;
    read)
        infon "Lendo Asset $ID (Consulta Local)..."
        peer chaincode query -C "$CHANNEL_NAME" -n "$CC_NAME" -c "{\"function\":\"ReadAsset\",\"Args\":[\"$ID\"]}"
        ;;
    update)
        infon "Atualizando Asset $ID..."
        peer chaincode invoke -o localhost:${ORDERER_PORT} --ordererTLSHostnameOverride ${ORDERER_NAME}.${DOMAIN} --tls --cafile "$ORDERER_CA" -C "$CHANNEL_NAME" -n "$CC_NAME" $PEER_ARGS -c "{\"function\":\"UpdateAsset\",\"Args\":[\"$ID\",\"$5\",\"$6\",\"$7\",\"$8\"]}"
        ;;
    all)
        infon "Listando todos os Assets..."
        peer chaincode query -C "$CHANNEL_NAME" -n "$CC_NAME" -c '{"function":"GetAllAssets","Args":[]}'
        ;;
    invoke)
        # Uso: ./ledger_cli.sh <Org> <Peer> invoke <chaincode> '<json payload>'
        # Exemplo: ./ledger_cli.sh Org1 peer0 invoke calc_do '{"function":"AnchorCalcResult","Args":["..."]}'
        INVOKE_CC=$4
        INVOKE_PAYLOAD=$5
        if [ -z "$INVOKE_CC" ] || [ -z "$INVOKE_PAYLOAD" ]; then
            echo "Uso: $0 <Org> <Peer> invoke <chaincode> '<json payload>'"
            exit 1
        fi
        infon "Invocando função em $INVOKE_CC..."
        peer chaincode invoke \
            -o localhost:${ORDERER_PORT} \
            --ordererTLSHostnameOverride ${ORDERER_NAME}.${DOMAIN} \
            --tls --cafile "$ORDERER_CA" \
            -C "$CHANNEL_NAME" -n "$INVOKE_CC" \
            $PEER_ARGS \
            -c "$INVOKE_PAYLOAD"
        ;;
    query)
        # Uso: ./ledger_cli.sh <Org> <Peer> query <chaincode> '<json payload>'
        # Exemplo: ./ledger_cli.sh Org1 peer0 query calc_do '{"function":"QueryCalcDo","Args":["test-001"]}'
        QUERY_CC=$4
        QUERY_PAYLOAD=$5
        if [ -z "$QUERY_CC" ] || [ -z "$QUERY_PAYLOAD" ]; then
            echo "Uso: $0 <Org> <Peer> query <chaincode> '<json payload>'"
            exit 1
        fi
        infon "Consultando $QUERY_CC..."
        peer chaincode query \
            -C "$CHANNEL_NAME" -n "$QUERY_CC" \
            -c "$QUERY_PAYLOAD"
        ;;
    *)
        echo "Uso: $0 <Org> <Peer> <action> [args...]"
        echo ""
        echo "Actions existentes:"
        echo "  init                             — InitLedger no basic_asset"
        echo "  create  <id> <c> <d> <e> <f>    — CreateAsset no basic_asset"
        echo "  read    <id>                     — ReadAsset no basic_asset"
        echo "  update  <id> <c> <d> <e> <f>    — UpdateAsset no basic_asset"
        echo "  all                              — GetAllAssets no basic_asset"
        echo ""
        echo "Actions genéricas:"
        echo "  invoke  <chaincode> '<payload>'  — Invoke em qualquer chaincode"
        echo "  query   <chaincode> '<payload>'  — Query em qualquer chaincode"
        echo ""
        echo "Exemplos:"
        echo "  $0 Org1 peer0 invoke calc_do '{\"function\":\"AnchorCalcResult\",\"Args\":[\"...\"]}"
        echo "  $0 Org1 peer0 query  calc_do '{\"function\":\"QueryCalcDo\",\"Args\":[\"test-001\"]}'"
        ;;
esac