#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
# Verifica se os pré-requisitos do sistema (Docker, Go, binários do Fabric) estão instalados 
#e em versões compatíveis. Caso necessário, realiza o download automático dos binários do Hyperledger Fabric.

source $(dirname "$0")/utils.sh

# Define o diretório raiz do projeto
# Se NETWORK_DIR vier do Python, usamos o pai dele como raiz, ou o diretório atual
PROJECT_ROOT=${NETWORK_DIR%/network} # remove '/network' do final para pegar a raiz
if [ -z "$PROJECT_ROOT" ]; then
    PROJECT_ROOT="."
fi

# adiciona ./bin local ao PATH temporariamente para verificação
export PATH="$PROJECT_ROOT/bin:$PATH"

infoln "Verificando pré-requisitos..."

# verificar Docker
if ! command -v docker &> /dev/null; then
    errorln "Docker não encontrado! Instale o Docker Desktop ou Engine."
    exit 1
fi
DOCKER_V=$(docker --version)
successln "Docker encontrado: $DOCKER_V"

# verificar Go
if command -v go &> /dev/null; then
    CURRENT_GO=$(go version | awk '{print $3}' | sed 's/go//')
    if [[ "$CURRENT_GO" < "$GO_VERSION" ]]; then
        warnln "AVISO: Versão do Go ($CURRENT_GO) é menor que a recomendada ($GO_VERSION)"
    else
        successln "Go versão $CURRENT_GO compatível."
    fi
else
    warnln "Go não instalado (OK se não for compilar Chaincode em Go)"
fi

# verificar e baixar binários do Fabric
NEED_INSTALL=false
if command -v configtxgen &> /dev/null; then
    FABRIC_BIN_VER=$(configtxgen -version | grep "Version:" | awk '{print $2}' | sed "s/^v//")
    if [[ "$FABRIC_BIN_VER" != "$FABRIC_VERSION" ]]; then
        warnln "Versão local ($FABRIC_BIN_VER) difere da desejada ($FABRIC_VERSION)."
        NEED_INSTALL=true
    else
        successln "Binários Fabric ($FABRIC_BIN_VER) compatíveis."
    fi
else
    infoln "Binários não encontrados."
    NEED_INSTALL=true
fi

# verificar versao do Fabric-CA
if command -v fabric-ca-client &> /dev/null; then
    CA_BIN_VER=$(fabric-ca-client version | grep "Version:" | awk '{print $2}' | sed "s/^v//")
    if [[ "$CA_BIN_VER" != "$CA_VERSION" ]]; then
        warnln "Fabric-CA local ($CA_BIN_VER) difere da desejada ($CA_VERSION)."
        NEED_INSTALL=true
    else
        successln "Fabric-CA ($CA_BIN_VER) compatível."
    fi
else
    infoln "Fabric-CA não encontrado."
    NEED_INSTALL=true
fi

# instala se necessário

if [ "$NEED_INSTALL" = true ]; then
    infoln "Baixando Fabric $FABRIC_VERSION e CA $CA_VERSION..."
    
    pushd "$PROJECT_ROOT" > /dev/null
    curl -sSL https://raw.githubusercontent.com/hyperledger/fabric/main/scripts/install-fabric.sh -o install-fabric.sh
    chmod +x install-fabric.sh
    
    # baixa binários para a pasta ./bin
    ./install-fabric.sh --fabric-version $FABRIC_VERSION --ca-version $CA_VERSION binary docker
    
    popd > /dev/null
    rm install-fabric.sh
    
    successln "Instalação concluída em $PROJECT_ROOT/bin"
fi

CONFIG_DIR="$PROJECT_ROOT/config"

# Remove apenas o que o Fabric baixou para não poluir
if [ -d "$CONFIG_DIR" ]; then
    infoln "Limpando configurações padrão baixadas pelo Fabric..."
    rm -rf "$CONFIG_DIR"
fi

successln "--- Check Finalizado ---"