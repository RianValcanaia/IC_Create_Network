#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
# Contém funções auxiliares em shell script para exibição de mensagens coloridas e remoção segura de arquivos.

# Cores ANSI
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
BLUE="\033[0;34m"
CYAN="\033[0;36m"
RESET="\033[0m"

# funcao de info (azul)
infoln() {
    echo -e "${BLUE}[INFO] $1${RESET}"
}

# funcao de sucesso (verde)
successln() {
    echo -e "${GREEN}[SUCESSO] $1${RESET}"
}

# funcao de aviso (amarelo)
warnln() {
    echo -e "${YELLOW}[AVISO] $1${RESET}"
}

# funcao de erro (vermelho)
errorln() {
    echo -e "${RED}[ERRO] $1${RESET}"
}

remove_if_exists() {
    local file="$1"
    if [ -f "$file" ]; then
        infoln "Removendo $(basename "$file")..."
        rm -f "$file"
        successln "$(basename "$file") removido."
    fi
}

fix_permissions() {
    local target_dir=$1
    USER_ID=$(id -u)
    GROUP_ID=$(id -g)
    infoln "Corrigindo permissões em: $target_dir"
    docker run --rm -v "$target_dir":/data alpine chown -R $USER_ID:$GROUP_ID /data
}