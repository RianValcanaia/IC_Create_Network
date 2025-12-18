#!/bin/bash

source $(dirname "$0")/utils.sh

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# remove arquivos especificos da pasta config/
SCRIPTS_DIR="$PROJECT_ROOT/config"
remove_if_exists "$SCRIPTS_DIR/register_enroll.sh"
remove_if_exists "$SCRIPTS_DIR/create_artifacts.sh"

infoln "Removendo arquivos docker-compose gerados..."

# docker compose down
CA_COMPOSE="$PROJECT_ROOT/network/compose/compose-ca.yaml"
if [ -f "$CA_COMPOSE" ]; then
    infoln "Encontrado compose-ca.yaml. Derrubando containers..."
    docker-compose -f "$CA_COMPOSE" -p "fabric_network" down --volumes --remove-orphans
    if [ $? -eq 0 ]; then
        successln "Containers e volumes removidos com sucesso."
    else
        errorln "Falha ao executar docker-compose down. Pode haver resíduos."
    fi
else
    warnln "Arquivo $CA_COMPOSE não encontrado. Pulando etapa de shutdown do Docker."
fi

# limpa a pasta network/ (organizations, compose, genesis block)
if [ -d "$PROJECT_ROOT/network" ]; then
    infoln "Removendo conteúdo gerado em network/..."

    # container Alpine temporário para apagar os arquivos.
    docker run --rm -v "$PROJECT_ROOT/network":/data alpine sh -c 'rm -rf /data/*'
    
    # se falhar o anterior tenta apagar diretamente
    rm -rf "$PROJECT_ROOT/network"/* 2>/dev/null || true
    
    successln "Pasta network/ limpa."
else
    warnln "Pasta network/ não existe. Nada a limpar."
fi

successln "Limpeza concluída!"
