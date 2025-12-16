#!/bin/bash


source $(dirname "$0")/utils.sh

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
remove_if_exists "scripts/register_enroll.sh"

infoln "Removendo arquivos docker-compose gerados..."

# Docker compose down
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

# Limpa a pasta network/ (organizations, compose, genesis block)
if [ -d "$PROJECT_ROOT/network" ]; then
    infoln "Removendo conteúdo gerado em network/..."

    # TRUQUE: Usamos um container Alpine temporário para apagar os arquivos.
    # Como o Docker roda como root, ele tem permissão para apagar os arquivos das CAs.
    # Montamos a pasta 'network' do host em '/data' dentro do container.
    docker run --rm -v "$PROJECT_ROOT/network":/data alpine sh -c 'rm -rf /data/*'
    
    # Se o comando docker acima falhar (ex: imagem alpine não baixada), 
    # tentamos o rm normal como fallback, ignorando erros.
    rm -rf "$PROJECT_ROOT/network"/* 2>/dev/null || true
    
    successln "Pasta network/ limpa."
else
    warnln "Pasta network/ não existe. Nada a limpar."
fi

successln "Limpeza concluída!"
