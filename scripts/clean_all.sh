#!/bin/bash
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
# Executa uma limpeza profunda no ambiente, removendo não apenas a infraestrutura Docker, mas também os binários baixados e as pastas de builders.

source $(dirname "$0")/utils.sh

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NETWORKS_ROOT="$PROJECT_ROOT/network"
SCRIPTS_ROOT="$PROJECT_ROOT/scripts"

infoln "Limpando ambiente no diretório: $PROJECT_ROOT"

# derruba cada rede individualmente
if [ -d "$NETWORKS_ROOT" ]; then
    for NETWORK_DIR in "$NETWORKS_ROOT"/*/; do
        [ -d "$NETWORK_DIR" ] || continue   # nenhuma subpasta encontrada
        NETWORK_DIR="${NETWORK_DIR%/}"       # remove barra final
        NETWORK_BASE="$(basename "$NETWORK_DIR")"
        DOCKER_NET_NAME="${NETWORK_BASE}_net"

        infoln "Derrubando rede: $NETWORK_BASE"

        CA_COMPOSE="$NETWORK_DIR/compose/compose-ca.yaml"
        if [ -f "$CA_COMPOSE" ]; then
            infoln "Derrubando containers da CA ($NETWORK_BASE)..."
            docker-compose -f "$CA_COMPOSE" -p "${NETWORK_BASE}_ca" down --volumes --remove-orphans \
                && successln "CA de $NETWORK_BASE removida." \
                || errorln "Falha ao derrubar CA de $NETWORK_BASE. Pode haver resíduos."
        fi

        NODE_COMPOSE="$NETWORK_DIR/compose/compose-nodes.yaml"
        if [ -f "$NODE_COMPOSE" ]; then
            infoln "Derrubando containers dos nós ($NETWORK_BASE)..."
            docker-compose -f "$NODE_COMPOSE" -p "${NETWORK_BASE}_net" down --volumes --remove-orphans \
                && successln "Nós de $NETWORK_BASE removidos." \
                || errorln "Falha ao derrubar nós de $NETWORK_BASE. Pode haver resíduos."
        fi

        # remove qualquer container remanescente conectado à docker network desta rede
        infoln "Limpando containers remanescentes de $NETWORK_BASE..."
        docker ps -a --filter network="$DOCKER_NET_NAME" -q | xargs -r docker rm -f

        # remove a docker network desta rede
        if docker network inspect "$DOCKER_NET_NAME" >/dev/null 2>&1; then
            infoln "Removendo Docker network $DOCKER_NET_NAME..."
            docker network rm "$DOCKER_NET_NAME"
        fi
    done
else
    warnln "Pasta $NETWORKS_ROOT não existe. Nenhuma rede para derrubar."
fi

# verificação extra
infoln "Verificando containers/networks órfãos com sufixo '_net' ou '_ca'..."
docker ps -a --format '{{.Names}} {{.Networks}}' | awk '{print $1}' \
    | while read -r cname; do
        cnets=$(docker inspect --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$cname" 2>/dev/null)
        for n in $cnets; do
            if [[ "$n" == *_net ]]; then
                warnln "Removendo container órfão '$cname' (rede $n)..."
                docker rm -f "$cname" >/dev/null 2>&1
                break
            fi
        done
    done

# remove pasta bin/
if [ -d "$PROJECT_ROOT/bin" ]; then
    infoln "Removendo pasta bin/..."
    rm -rf "$PROJECT_ROOT/bin"
    successln "bin/ removida."
else
    warnln "bin/ não existe. Ignorando."
fi

# remove pasta builders/
if [ -d "$PROJECT_ROOT/builders" ]; then
    infoln "Removendo pasta builders/..."
    rm -rf "$PROJECT_ROOT/builders"
    successln "builders/ removida."
else
    warnln "builders/ não existe. Ignorando."
fi

# limpa pacotes de chaincode gerados
CHAINCODE_DIR="$PROJECT_ROOT/chaincode"
if [ -d "$CHAINCODE_DIR" ]; then
    infoln "Limpando pacotes de chaincode gerados em $CHAINCODE_DIR..."
    find "$CHAINCODE_DIR" -maxdepth 1 -type f \( -name "*.tar.gz" -o -name "*_collections.json" \) -print -delete
    successln "Pacotes de chaincode removidos."
fi

# limpa pasta network/
if [ -d "$NETWORKS_ROOT" ]; then
    infoln "Removendo todo o conteúdo de $NETWORKS_ROOT..."
    fix_permissions "$NETWORKS_ROOT"
    docker run --rm -v "$NETWORKS_ROOT":/data alpine sh -c 'rm -rf /data/*'
    rm -rf "$NETWORKS_ROOT"/* 2>/dev/null || true
    successln "Pasta $NETWORKS_ROOT limpa."
else
    warnln "Pasta $NETWORKS_ROOT não existe. Nada a limpar."
fi

# apaga subpastas de scripts gerados
if [ -d "$SCRIPTS_ROOT" ]; then
    infoln "Removendo scripts gerados de todas as redes..."
    for GEN_DIR in "$SCRIPTS_ROOT"/*/; do
        [ -d "$GEN_DIR" ] || continue
        GEN_DIR="${GEN_DIR%/}"
        infoln "Removendo $GEN_DIR..."
        rm -rf "$GEN_DIR"
    done
    successln "Scripts gerados removidos."
fi

successln "Limpeza concluída!"