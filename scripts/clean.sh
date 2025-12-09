#!/bin/bash


source $(dirname "$0")/colors.sh

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

infoln "Limpando ambiente no diretório: $PROJECT_ROOT"

# REMOVER pasta bin/
if [ -d "$PROJECT_ROOT/bin" ]; then
    infoln "Removendo pasta bin/..."
    rm -rf "$PROJECT_ROOT/bin"
    successln "bin/ removida."
else
    warnln "bin/ não existe. Ignorando."
fi

# REMOVER pasta builders/
if [ -d "$PROJECT_ROOT/builders" ]; then
    infoln "Removendo pasta builders/..."
    rm -rf "$PROJECT_ROOT/builders"
    successln "builders/ removida."
else
    warnln "builders/ não existe. Ignorando."
fi

# LIMPAR conteúdo da pasta network/
if [ -d "$PROJECT_ROOT/network" ]; then
    infoln "Limpando pasta network/..."
    rm -rf "$PROJECT_ROOT/network"/*
    successln "network/ limpa."
else
    warnln "network/ não existe. Ignorando."
fi

# REMOVER arquivos específicos da pasta config/
CONFIG_DIR="$PROJECT_ROOT/config"

remove_if_exists() {
    local file="$1"
    if [ -f "$file" ]; then
        infoln "Removendo $(basename "$file")..."
        rm -f "$file"
        successln "$(basename "$file") removido."
    else
        warnln "$(basename "$file") não existe."
    fi
}

remove_if_exists "$CONFIG_DIR/configtx.yaml"
remove_if_exists "$CONFIG_DIR/core.yaml"
remove_if_exists "$CONFIG_DIR/orderer.yaml"

infoln "Limpeza concluída!"
