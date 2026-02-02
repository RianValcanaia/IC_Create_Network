#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
# CLI do ledger para pequenos testes 

# USO: ./scripts/ledger_cli.sh Org1 peer0 create asset1 blue 5 Tom 100

if [ -n "$ZSH_VERSION" ]; then SCRIPT_PATH="${(%):-%x}"; else SCRIPT_PATH="${BASH_SOURCE[0]}"; fi
SCRIPT_DIR=$(cd "$(dirname "$SCRIPT_PATH")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

source "$SCRIPT_DIR/set_env.sh" "$1" "$2"
if [ $? -ne 0 ]; then exit 1; fi

ACTION=$3
ID=$4

CHANNEL_NAME="channel-all"
CC_NAME="basic_asset"
ORDERER_CA="$PROJECT_ROOT/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/ca.crt"

PEER_ARGS="--peerAddresses localhost:7051 --tlsRootCertFiles $PROJECT_ROOT/network/organizations/peerOrganizations/Org1.exemplo.com/peers/peer0.Org1.exemplo.com/tls/ca.crt"
PEER_ARGS="$PEER_ARGS --peerAddresses localhost:9051 --tlsRootCertFiles $PROJECT_ROOT/network/organizations/peerOrganizations/Org2.exemplo.com/peers/peer0.Org2.exemplo.com/tls/ca.crt"

case $ACTION in
    init)
        # ./scripts/ledger_cli.sh Org1 peer0 init
        infoln "Inicializando Ledger..."
        peer chaincode invoke -o localhost:7050 --ordererTLSHostnameOverride orderer0.exemplo.com --tls --cafile "$ORDERER_CA" -C "$CHANNEL_NAME" -n "$CC_NAME" $PEER_ARGS -c '{"function":"InitLedger","Args":[]}'
        ;;
    create)
        # ./scripts/ledger_cli.sh Org1 peer0 create asset10 blue 5 Rian 100
        # Args: ID, Color, Size, Owner, AppraisedValue
        infoln "Criando Asset $ID..."
        peer chaincode invoke -o localhost:7050 --ordererTLSHostnameOverride orderer0.exemplo.com --tls --cafile "$ORDERER_CA" -C "$CHANNEL_NAME" -n "$CC_NAME" $PEER_ARGS -c "{\"function\":\"CreateAsset\",\"Args\":[\"$ID\",\"$5\",\"$6\",\"$7\",\"$8\"]}"
        ;;
    read)
        # ./scripts/ledger_cli.sh Org1 peer0 read asset10
        infoln "Lendo Asset $ID..."
        peer chaincode query -C "$CHANNEL_NAME" -n "$CC_NAME" -c "{\"function\":\"ReadAsset\",\"Args\":[\"$ID\"]}"
        ;;
    update)
        # ./scripts/ledger_cli.sh Org1 peer0 update asset10 green 20 Admin 200
        infoln "Atualizando Asset $ID..."
        peer chaincode invoke -o localhost:7050 --ordererTLSHostnameOverride orderer0.exemplo.com --tls --cafile "$ORDERER_CA" -C "$CHANNEL_NAME" -n "$CC_NAME" $PEER_ARGS -c "{\"function\":\"UpdateAsset\",\"Args\":[\"$ID\",\"$5\",\"$6\",\"$7\",\"$8\"]}"
        ;;
    all)
        # ./scripts/ledger_cli.sh Org1 peer0 all
        infoln "Listando todos os Assets..."
        peer chaincode query -C "$CHANNEL_NAME" -n "$CC_NAME" -c '{"function":"GetAllAssets","Args":[]}'
        ;;
    *)
        echo "Uso: $0 <Org> <Peer> <action> [args...]"
        echo "Ações: init, create, read, update, all"
        echo "Exemplo Create: $0 Org1 peer0 create asset7 green 10 Rian 500"
        ;;
esac