#!/bin/bash
# estatico

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