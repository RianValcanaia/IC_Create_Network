#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License

# Configura o ambiente para o uso do Fabric CLI.
# set_env.sh <ORG> <PEER>

# Detecta o diretório onde o script está
if [ -n "$ZSH_VERSION" ]; then SCRIPT_PATH="${(%):-%x}"; else SCRIPT_PATH="${BASH_SOURCE[0]}"; fi
SCRIPT_DIR=$(cd "$(dirname "$SCRIPT_PATH")" && pwd)

# Define o ROOT do projeto (subindo apenas 1 nível de 'scripts/')
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

ORG=$1
PEER=$2

# Localiza o contexto da rede que contém a ORG (layout network/<Rede>/contexto_ativo.json)
CONTEXT_FILE=""
for f in "$PROJECT_ROOT"/network/*/contexto_ativo.json "$PROJECT_ROOT/network/contexto_ativo.json"; do
    if [ -f "$f" ] && jq -e --arg org "$ORG" '.orgs[$org]' "$f" >/dev/null 2>&1; then
        CONTEXT_FILE="$f"
        break
    fi
done

# Validação se o arquivo existe antes de chamar o jq
if [ -z "$CONTEXT_FILE" ]; then
    echo -e "\033[1;31m[ERRO]\033[0m Nenhum contexto_ativo.json com a org '$ORG' em $PROJECT_ROOT/network/"
    return 1 # return pois está dando source
fi
NETWORK_DIR=$(dirname "$CONTEXT_FILE")

# Extração de dados 
DOMAIN=$(jq -r '.domain' "$CONTEXT_FILE")
MSP_ID=$(jq -r ".orgs[\"$ORG\"].msp_id" "$CONTEXT_FILE")
PORT=$(jq -r ".orgs[\"$ORG\"].peers[\"$PEER\"].port" "$CONTEXT_FILE")

# Export de variáveis do Fabric
export PATH="$PATH:$PROJECT_ROOT/bin"
export FABRIC_CFG_PATH="$NETWORK_DIR/compose/peercfg"
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID="$MSP_ID"
export CORE_PEER_ADDRESS="localhost:$PORT"
export CORE_PEER_TLS_ROOTCERT_FILE="$NETWORK_DIR/organizations/peerOrganizations/${ORG}.${DOMAIN}/peers/${PEER}.${ORG}.${DOMAIN}/tls/ca.crt"
export CORE_PEER_MSPCONFIGPATH="$NETWORK_DIR/organizations/peerOrganizations/${ORG}.${DOMAIN}/users/Admin@${ORG}.${DOMAIN}/msp"

echo -e "\033[1;32m[SUCESSO]\033[0m Ambiente configurado: $ORG ($PEER) -> porta $PORT"