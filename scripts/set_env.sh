#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
# set_env.sh <ORG> <PEER>

# 1. Detecta o diretório onde o script está
if [ -n "$ZSH_VERSION" ]; then SCRIPT_PATH="${(%):-%x}"; else SCRIPT_PATH="${BASH_SOURCE[0]}"; fi
SCRIPT_DIR=$(cd "$(dirname "$SCRIPT_PATH")" && pwd)

# 2. Define o ROOT do projeto (subindo apenas 1 nível de 'scripts/')
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

# 3. Define o caminho do arquivo de contexto usando o ROOT absoluto
CONTEXT_FILE="$PROJECT_ROOT/network/contexto_ativo.json"

ORG=$1
PEER=$2

# Validação se o arquivo existe antes de chamar o jq
if [ ! -f "$CONTEXT_FILE" ]; then
    echo -e "\033[1;31m[ERRO]\033[0m Arquivo não encontrado: $CONTEXT_FILE"
    return 1 # Use return pois você está dando 'source'
fi

# 4. Extração de dados (adicionando aspas nas variáveis do jq para segurança)
DOMAIN=$(jq -r '.domain' "$CONTEXT_FILE")
MSP_ID=$(jq -r ".orgs[\"$ORG\"].msp_id" "$CONTEXT_FILE")
PORT=$(jq -r ".orgs[\"$ORG\"].peers[\"$PEER\"].port" "$CONTEXT_FILE")

# 5. Export de variáveis do Fabric
export PATH="$PATH:$PROJECT_ROOT/bin"
export FABRIC_CFG_PATH="$PROJECT_ROOT/network/compose/peercfg"
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID="$MSP_ID"
export CORE_PEER_ADDRESS="localhost:$PORT"
export CORE_PEER_TLS_ROOTCERT_FILE="$PROJECT_ROOT/network/organizations/peerOrganizations/${ORG}.${DOMAIN}/peers/${PEER}.${ORG}.${DOMAIN}/tls/ca.crt"
export CORE_PEER_MSPCONFIGPATH="$PROJECT_ROOT/network/organizations/peerOrganizations/${ORG}.${DOMAIN}/users/Admin@${ORG}.${DOMAIN}/msp"

echo -e "\033[1;32m[SUCESSO]\033[0m Ambiente configurado: $ORG ($PEER) -> porta $PORT"