#!/bin/bash
set -e
source /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/scripts/utils.sh
export FABRIC_CFG_PATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/compose/peercfg
export PATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/bin:$PATH

infoln '--- Iniciando containers CCAAS locais ---'

# Configura o peer local para consultar os PACKAGE_IDs instalados.
# O peer já deve estar em execução (iniciado por start_nodes.sh).
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org1MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/peers/peer0.Org1.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/users/Admin@Org1.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:7051

infoln 'Iniciando chaincode basic_asset (porta 9999)...'
PACKAGE_ID=$(peer lifecycle chaincode queryinstalled | grep 'basic_asset_1.0' | head -n 1 | sed -n 's/^Package ID: //; s/, Label:.*$//p')
if [ -z "$PACKAGE_ID" ]; then errorln 'PACKAGE_ID não encontrado para basic_asset_1.0. O chaincode foi instalado neste peer?'; exit 1; fi
infoln 'Package ID: '$PACKAGE_ID
docker rm -f basic_asset.channel-all 2>/dev/null || true
fix_permissions '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/basic_asset'
docker run -d --name basic_asset.channel-all --network FabricNetwork_net --dns 8.8.8.8 -p 9999:9999 -e CHAINCODE_SERVER_ADDRESS=0.0.0.0:9999 -e CORE_CHAINCODE_ID_NAME=$PACKAGE_ID -v /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/basic_asset:/opt/gopath/src/chaincode -w /opt/gopath/src/chaincode hyperledger/fabric-ccenv:3.1.1 ./chaincode
successln 'Chaincode basic_asset iniciado na porta 9999.'

infoln 'Iniciando chaincode calc_do (porta 10000)...'
PACKAGE_ID=$(peer lifecycle chaincode queryinstalled | grep 'calc_do_1.0' | head -n 1 | sed -n 's/^Package ID: //; s/, Label:.*$//p')
if [ -z "$PACKAGE_ID" ]; then errorln 'PACKAGE_ID não encontrado para calc_do_1.0. O chaincode foi instalado neste peer?'; exit 1; fi
infoln 'Package ID: '$PACKAGE_ID
docker rm -f calc_do.channel-all 2>/dev/null || true
fix_permissions '/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/calc_do'
docker run -d --name calc_do.channel-all --network FabricNetwork_net --dns 8.8.8.8 -p 10000:10000 -e CHAINCODE_SERVER_ADDRESS=0.0.0.0:10000 -e CORE_CHAINCODE_ID_NAME=$PACKAGE_ID -v /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/calc_do:/opt/gopath/src/chaincode -w /opt/gopath/src/chaincode hyperledger/fabric-ccenv:3.1.1 ./chaincode
successln 'Chaincode calc_do iniciado na porta 10000.'