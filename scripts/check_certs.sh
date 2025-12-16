#!/bin/bash

BASE_DIR="../network/organizations"

echo "--- Iniciando Auditoria de Artefatos ---"

check_tls() {
    local node_type=$1
    local path=$2
    local name=$3
    
    echo "Verificando $node_type: $name"
    
    # 1. Verifica se a pasta TLS existe
    if [ ! -d "$path/tls" ]; then
        echo "❌ [ERRO] Pasta TLS não encontrada em: $path"
        return
    fi

    # 2. Verifica arquivos críticos
    if [[ ! -f "$path/tls/server.crt" || ! -f "$path/tls/server.key" || ! -f "$path/tls/ca.crt" ]]; then
        echo "❌ [ERRO] Arquivos de certificado faltando em: $path/tls"
        return
    fi

    # 3. Verifica SANs (DNS Names)
    local sans=$(openssl x509 -in "$path/tls/server.crt" -text -noout | grep "DNS:")
    if [[ $sans == *"$name"* ]]; then
        echo "✅ [OK] Certificado TLS válido com SANs: $sans"
    else
        echo "❌ [ERRO] O certificado não contém o DNS correto ($name). Encontrado: $sans"
    fi
}

# Verificar Peer0 da Org1
check_tls "Peer" "$BASE_DIR/peerOrganizations/Org1.exemplo.com/peers/peer0.Org1.exemplo.com" "peer0.Org1.exemplo.com"

# Verificar Peer0 da Org2
check_tls "Peer" "$BASE_DIR/peerOrganizations/Org2.exemplo.com/peers/peer0.Org2.exemplo.com" "peer0.Org2.exemplo.com"

# Verificar Orderer
check_tls "Orderer" "$BASE_DIR/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com" "orderer0.exemplo.com"

echo "--- Auditoria Finalizada ---"