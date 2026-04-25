#!/bin/bash
set -e
source /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/scripts/utils.sh
export PATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/bin:$PATH
export FABRIC_CFG_PATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network

# cria Genesis Block
infoln "--- Gerando Blocos de Configuração (Fabric v3) ---"
mkdir -p /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts
infoln 'Gerando Genesis Block (channel-all)...'
configtxgen -profile Channel-allProfile -channelID channel-all -outputBlock /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/genesis.block
# Copiando genesis block para o canal channel-all
cp /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/genesis.block /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel-all.block

# gerando bloco para o canal channel12
infoln 'Gerando Block: /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel12.block'
configtxgen -profile Channel12Profile -channelID channel12 -outputBlock /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel12.block

successln "Artefatos criados com sucesso!"