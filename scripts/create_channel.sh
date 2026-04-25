#!/bin/bash
set -e
source /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/scripts/utils.sh
export PATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/bin:$PATH
export FABRIC_CFG_PATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/compose/peercfg


function updateAnchorPeer() {
    local org=$1; local msp=$2; local channel=$3; local peer_name=$4; local port=$5; local orderer=$6
    infoln "Definindo Anchor Peer para ${org} no canal ${channel}..."

    # 1. Fetch config
    peer channel fetch config config_block.pb -o ${orderer} -c ${channel} --tls --cafile $ORD_CA
    
    # 2. Decode e extrair a parte da config
    configtxlator proto_decode --input config_block.pb --type common.Block --output config_block.json
    jq '.data.data[0].payload.data.config' config_block.json > config.json

    # 3. Adicionar o anchor peer no JSON
    jq '.channel_group.groups.Application.groups.'${msp}'.values += {"AnchorPeers": {"mod_policy": "Admins","value": {"anchor_peers": [{"host": "'${peer_name}.${org}'.exemplo.com","port": '${port}'}]},"version": "0"}}' config.json > config_updated.json

    # 4. Re-encode e calcular delta
    configtxlator proto_encode --input config.json --type common.Config --output config.pb
    configtxlator proto_encode --input config_updated.json --type common.Config --output config_updated.pb
    configtxlator compute_update --channel_id ${channel} --original config.pb --updated config_updated.pb --output anchor_update.pb

    # 5. Criar envelope e submeter
    configtxlator proto_decode --input anchor_update.pb --type common.ConfigUpdate --output anchor_update.json
    echo '{"payload":{"header":{"channel_header":{"channel_id":"'$channel'", "type":2}},"data":{"config_update":'$(cat anchor_update.json)'}}}' | jq . > anchor_update_envelope.json
    configtxlator proto_encode --input anchor_update_envelope.json --type common.Envelope --output anchor_update_envelope.pb

    peer channel update -f anchor_update_envelope.pb -c ${channel} -o ${orderer} --tls --cafile $ORD_CA
    successln "Anchor Peer para ${org} atualizado!"
    rm *.json *.pb
}

headerln 'Iniciando Configuração de Canais (Fabric v3)'
export ORD_CA=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/ca.crt
export ORD_ADMIN_CERT=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/server.crt
export ORD_ADMIN_KEY=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/server.key

until curl -sk --cert /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/server.crt --key /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/server.key --cacert /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/ca.crt https://10.10.20.151:7061/participation/v1/channels >/dev/null 2>&1; do echo 'Aguardando orderer0...'; sleep 2; done
until curl -sk --cert /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer1.exemplo.com/tls/server.crt --key /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer1.exemplo.com/tls/server.key --cacert /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer1.exemplo.com/tls/ca.crt https://10.10.20.151:7063/participation/v1/channels >/dev/null 2>&1; do echo 'Aguardando orderer1...'; sleep 2; done
until curl -sk --cert /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer2.exemplo.com/tls/server.crt --key /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer2.exemplo.com/tls/server.key --cacert /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer2.exemplo.com/tls/ca.crt https://10.10.20.152:7065/participation/v1/channels >/dev/null 2>&1; do echo 'Aguardando orderer2...'; sleep 2; done
until curl -sk --cert /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer3.exemplo.com/tls/server.crt --key /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer3.exemplo.com/tls/server.key --cacert /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer3.exemplo.com/tls/ca.crt https://10.10.20.152:7067/participation/v1/channels >/dev/null 2>&1; do echo 'Aguardando orderer3...'; sleep 2; done
infoln '>> Configurando Canal: channel-all <<'
osnadmin channel join --channelID channel-all --config-block /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel-all.block -o 10.10.20.151:7061 --ca-file /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/ca.crt --client-cert /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/server.crt --client-key /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/server.key
osnadmin channel join --channelID channel-all --config-block /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel-all.block -o 10.10.20.151:7063 --ca-file /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer1.exemplo.com/tls/ca.crt --client-cert /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer1.exemplo.com/tls/server.crt --client-key /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer1.exemplo.com/tls/server.key
osnadmin channel join --channelID channel-all --config-block /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel-all.block -o 10.10.20.152:7065 --ca-file /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer2.exemplo.com/tls/ca.crt --client-cert /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer2.exemplo.com/tls/server.crt --client-key /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer2.exemplo.com/tls/server.key
osnadmin channel join --channelID channel-all --config-block /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel-all.block -o 10.10.20.152:7067 --ca-file /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer3.exemplo.com/tls/ca.crt --client-cert /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer3.exemplo.com/tls/server.crt --client-key /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer3.exemplo.com/tls/server.key
sleep 2

# --- Configurando Peer peer0.Org1.exemplo.com (10.10.20.151:7051) ---
export CORE_PEER_LOCALMSPID=Org1MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/peers/peer0.Org1.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/users/Admin@Org1.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:7051
peer channel join -b /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel-all.block
updateAnchorPeer 'Org1' 'Org1MSP' 'channel-all' 'peer0' '7051' '10.10.20.151:7060'

# --- Configurando Peer peer1.Org1.exemplo.com (10.10.20.151:8051) ---
export CORE_PEER_LOCALMSPID=Org1MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/peers/peer1.Org1.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/users/Admin@Org1.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:8051
peer channel join -b /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel-all.block

# --- Configurando Peer peer0.Org2.exemplo.com (10.10.20.151:9051) ---
export CORE_PEER_LOCALMSPID=Org2MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/peers/peer0.Org2.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/users/Admin@Org2.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:9051
peer channel join -b /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel-all.block
updateAnchorPeer 'Org2' 'Org2MSP' 'channel-all' 'peer0' '9051' '10.10.20.151:7060'

# --- Configurando Peer peer1.Org2.exemplo.com (10.10.20.151:10051) ---
export CORE_PEER_LOCALMSPID=Org2MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/peers/peer1.Org2.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/users/Admin@Org2.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:10051
peer channel join -b /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel-all.block

# --- Configurando Peer peer0.Org3.exemplo.com (10.10.20.152:11051) ---
export CORE_PEER_LOCALMSPID=Org3MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/peers/peer0.Org3.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/users/Admin@Org3.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.152:11051
peer channel join -b /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel-all.block
updateAnchorPeer 'Org3' 'Org3MSP' 'channel-all' 'peer0' '11051' '10.10.20.151:7060'

# --- Configurando Peer peer1.Org3.exemplo.com (10.10.20.152:12051) ---
export CORE_PEER_LOCALMSPID=Org3MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/peers/peer1.Org3.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/users/Admin@Org3.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.152:12051
peer channel join -b /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel-all.block

# --- Configurando Peer peer0.Org4.exemplo.com (10.10.20.152:13051) ---
export CORE_PEER_LOCALMSPID=Org4MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/peers/peer0.Org4.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/users/Admin@Org4.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.152:13051
peer channel join -b /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel-all.block
updateAnchorPeer 'Org4' 'Org4MSP' 'channel-all' 'peer0' '13051' '10.10.20.151:7060'

# --- Configurando Peer peer1.Org4.exemplo.com (10.10.20.152:14051) ---
export CORE_PEER_LOCALMSPID=Org4MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/peers/peer1.Org4.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/users/Admin@Org4.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.152:14051
peer channel join -b /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel-all.block
infoln '>> Configurando Canal: channel12 <<'
osnadmin channel join --channelID channel12 --config-block /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel12.block -o 10.10.20.151:7061 --ca-file /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/ca.crt --client-cert /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/server.crt --client-key /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/server.key
osnadmin channel join --channelID channel12 --config-block /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel12.block -o 10.10.20.151:7063 --ca-file /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer1.exemplo.com/tls/ca.crt --client-cert /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer1.exemplo.com/tls/server.crt --client-key /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer1.exemplo.com/tls/server.key
osnadmin channel join --channelID channel12 --config-block /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel12.block -o 10.10.20.152:7065 --ca-file /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer2.exemplo.com/tls/ca.crt --client-cert /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer2.exemplo.com/tls/server.crt --client-key /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer2.exemplo.com/tls/server.key
osnadmin channel join --channelID channel12 --config-block /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel12.block -o 10.10.20.152:7067 --ca-file /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer3.exemplo.com/tls/ca.crt --client-cert /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer3.exemplo.com/tls/server.crt --client-key /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer3.exemplo.com/tls/server.key
sleep 2

# --- Configurando Peer peer0.Org1.exemplo.com (10.10.20.151:7051) ---
export CORE_PEER_LOCALMSPID=Org1MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/peers/peer0.Org1.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/users/Admin@Org1.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:7051
peer channel join -b /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel12.block
updateAnchorPeer 'Org1' 'Org1MSP' 'channel12' 'peer0' '7051' '10.10.20.151:7060'

# --- Configurando Peer peer1.Org1.exemplo.com (10.10.20.151:8051) ---
export CORE_PEER_LOCALMSPID=Org1MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/peers/peer1.Org1.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/users/Admin@Org1.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:8051
peer channel join -b /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel12.block

# --- Configurando Peer peer0.Org2.exemplo.com (10.10.20.151:9051) ---
export CORE_PEER_LOCALMSPID=Org2MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/peers/peer0.Org2.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/users/Admin@Org2.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:9051
peer channel join -b /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel12.block
updateAnchorPeer 'Org2' 'Org2MSP' 'channel12' 'peer0' '9051' '10.10.20.151:7060'

# --- Configurando Peer peer1.Org2.exemplo.com (10.10.20.151:10051) ---
export CORE_PEER_LOCALMSPID=Org2MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/peers/peer1.Org2.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/users/Admin@Org2.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:10051
peer channel join -b /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/channel-artifacts/channel12.block