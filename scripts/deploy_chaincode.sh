#!/bin/bash
set -e
source /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/scripts/utils.sh
export FABRIC_CFG_PATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/compose/peercfg
export PATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/bin:$PATH

infoln '--- Iniciando Deploy de Chaincode ---'

infoln '=== Chaincode: basic_asset ==='
infoln 'Instalando em peer0.Org1.exemplo.com (10.10.20.151:7051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org1MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/peers/peer0.Org1.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/users/Admin@Org1.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:7051
peer lifecycle chaincode install /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/basic_asset.tar.gz

infoln 'Instalando em peer1.Org1.exemplo.com (10.10.20.151:8051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org1MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/peers/peer1.Org1.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/users/Admin@Org1.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:8051
peer lifecycle chaincode install /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/basic_asset.tar.gz

infoln 'Instalando em peer0.Org2.exemplo.com (10.10.20.151:9051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org2MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/peers/peer0.Org2.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/users/Admin@Org2.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:9051
peer lifecycle chaincode install /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/basic_asset.tar.gz

infoln 'Instalando em peer1.Org2.exemplo.com (10.10.20.151:10051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org2MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/peers/peer1.Org2.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/users/Admin@Org2.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:10051
peer lifecycle chaincode install /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/basic_asset.tar.gz

infoln 'Instalando em peer0.Org3.exemplo.com (10.10.20.152:11051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org3MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/peers/peer0.Org3.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/users/Admin@Org3.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.152:11051
peer lifecycle chaincode install /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/basic_asset.tar.gz

infoln 'Instalando em peer1.Org3.exemplo.com (10.10.20.152:12051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org3MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/peers/peer1.Org3.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/users/Admin@Org3.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.152:12051
peer lifecycle chaincode install /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/basic_asset.tar.gz

infoln 'Instalando em peer0.Org4.exemplo.com (10.10.20.152:13051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org4MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/peers/peer0.Org4.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/users/Admin@Org4.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.152:13051
peer lifecycle chaincode install /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/basic_asset.tar.gz

infoln 'Instalando em peer1.Org4.exemplo.com (10.10.20.152:14051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org4MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/peers/peer1.Org4.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/users/Admin@Org4.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.152:14051
peer lifecycle chaincode install /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/basic_asset.tar.gz

PACKAGE_ID=$(peer lifecycle chaincode queryinstalled | grep 'basic_asset_1.0' | head -n 1 | sed -n 's/^Package ID: //; s/, Label:.*$//p')
infoln 'Package ID: '$PACKAGE_ID

infoln 'Aprovando para Org1 (peer: 10.10.20.151:7051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org1MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/peers/peer0.Org1.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/users/Admin@Org1.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:7051
peer lifecycle chaincode approveformyorg -o 10.10.20.151:7060 --ordererTLSHostnameOverride orderer0.exemplo.com --tls --cafile /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/ca.crt --channelID channel-all --name basic_asset --version 1.0 --package-id $PACKAGE_ID --sequence 1 --collections-config /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/basic_asset_collections.json --signature-policy "AND('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member', 'Org4MSP.member')"

infoln 'Aprovando para Org2 (peer: 10.10.20.151:9051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org2MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/peers/peer0.Org2.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/users/Admin@Org2.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:9051
peer lifecycle chaincode approveformyorg -o 10.10.20.151:7060 --ordererTLSHostnameOverride orderer0.exemplo.com --tls --cafile /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/ca.crt --channelID channel-all --name basic_asset --version 1.0 --package-id $PACKAGE_ID --sequence 1 --collections-config /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/basic_asset_collections.json --signature-policy "AND('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member', 'Org4MSP.member')"

infoln 'Aprovando para Org3 (peer: 10.10.20.152:11051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org3MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/peers/peer0.Org3.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/users/Admin@Org3.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.152:11051
peer lifecycle chaincode approveformyorg -o 10.10.20.151:7060 --ordererTLSHostnameOverride orderer0.exemplo.com --tls --cafile /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/ca.crt --channelID channel-all --name basic_asset --version 1.0 --package-id $PACKAGE_ID --sequence 1 --collections-config /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/basic_asset_collections.json --signature-policy "AND('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member', 'Org4MSP.member')"

infoln 'Aprovando para Org4 (peer: 10.10.20.152:13051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org4MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/peers/peer0.Org4.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/users/Admin@Org4.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.152:13051
peer lifecycle chaincode approveformyorg -o 10.10.20.151:7060 --ordererTLSHostnameOverride orderer0.exemplo.com --tls --cafile /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/ca.crt --channelID channel-all --name basic_asset --version 1.0 --package-id $PACKAGE_ID --sequence 1 --collections-config /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/basic_asset_collections.json --signature-policy "AND('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member', 'Org4MSP.member')"

infoln 'Commitando chaincode basic_asset no canal channel-all...'
peer lifecycle chaincode commit -o 10.10.20.151:7060 --ordererTLSHostnameOverride orderer0.exemplo.com --tls --cafile /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/ca.crt --channelID channel-all --name basic_asset --version 1.0 --sequence 1 --collections-config /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/basic_asset_collections.json --signature-policy "AND('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member', 'Org4MSP.member')"  --peerAddresses 10.10.20.151:7051 --peerAddresses 10.10.20.151:9051 --peerAddresses 10.10.20.152:11051 --peerAddresses 10.10.20.152:13051  --tlsRootCertFiles /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/peers/peer0.Org1.exemplo.com/tls/ca.crt --tlsRootCertFiles /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/peers/peer0.Org2.exemplo.com/tls/ca.crt --tlsRootCertFiles /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/peers/peer0.Org3.exemplo.com/tls/ca.crt --tlsRootCertFiles /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/peers/peer0.Org4.exemplo.com/tls/ca.crt

successln 'Deploy do chaincode basic_asset concluído com sucesso!'

infoln '=== Chaincode: calc_do ==='
infoln 'Instalando em peer0.Org1.exemplo.com (10.10.20.151:7051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org1MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/peers/peer0.Org1.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/users/Admin@Org1.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:7051
peer lifecycle chaincode install /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/calc_do.tar.gz

infoln 'Instalando em peer1.Org1.exemplo.com (10.10.20.151:8051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org1MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/peers/peer1.Org1.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/users/Admin@Org1.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:8051
peer lifecycle chaincode install /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/calc_do.tar.gz

infoln 'Instalando em peer0.Org2.exemplo.com (10.10.20.151:9051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org2MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/peers/peer0.Org2.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/users/Admin@Org2.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:9051
peer lifecycle chaincode install /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/calc_do.tar.gz

infoln 'Instalando em peer1.Org2.exemplo.com (10.10.20.151:10051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org2MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/peers/peer1.Org2.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/users/Admin@Org2.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:10051
peer lifecycle chaincode install /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/calc_do.tar.gz

infoln 'Instalando em peer0.Org3.exemplo.com (10.10.20.152:11051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org3MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/peers/peer0.Org3.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/users/Admin@Org3.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.152:11051
peer lifecycle chaincode install /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/calc_do.tar.gz

infoln 'Instalando em peer1.Org3.exemplo.com (10.10.20.152:12051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org3MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/peers/peer1.Org3.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/users/Admin@Org3.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.152:12051
peer lifecycle chaincode install /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/calc_do.tar.gz

infoln 'Instalando em peer0.Org4.exemplo.com (10.10.20.152:13051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org4MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/peers/peer0.Org4.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/users/Admin@Org4.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.152:13051
peer lifecycle chaincode install /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/calc_do.tar.gz

infoln 'Instalando em peer1.Org4.exemplo.com (10.10.20.152:14051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org4MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/peers/peer1.Org4.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/users/Admin@Org4.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.152:14051
peer lifecycle chaincode install /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/calc_do.tar.gz

PACKAGE_ID=$(peer lifecycle chaincode queryinstalled | grep 'calc_do_1.0' | head -n 1 | sed -n 's/^Package ID: //; s/, Label:.*$//p')
infoln 'Package ID: '$PACKAGE_ID

infoln 'Aprovando para Org1 (peer: 10.10.20.151:7051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org1MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/peers/peer0.Org1.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/users/Admin@Org1.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:7051
peer lifecycle chaincode approveformyorg -o 10.10.20.151:7060 --ordererTLSHostnameOverride orderer0.exemplo.com --tls --cafile /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/ca.crt --channelID channel-all --name calc_do --version 1.0 --package-id $PACKAGE_ID --sequence 1 --collections-config /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/calc_do_collections.json --signature-policy "AND('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member', 'Org4MSP.member')"

infoln 'Aprovando para Org2 (peer: 10.10.20.151:9051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org2MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/peers/peer0.Org2.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/users/Admin@Org2.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.151:9051
peer lifecycle chaincode approveformyorg -o 10.10.20.151:7060 --ordererTLSHostnameOverride orderer0.exemplo.com --tls --cafile /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/ca.crt --channelID channel-all --name calc_do --version 1.0 --package-id $PACKAGE_ID --sequence 1 --collections-config /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/calc_do_collections.json --signature-policy "AND('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member', 'Org4MSP.member')"

infoln 'Aprovando para Org3 (peer: 10.10.20.152:11051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org3MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/peers/peer0.Org3.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/users/Admin@Org3.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.152:11051
peer lifecycle chaincode approveformyorg -o 10.10.20.151:7060 --ordererTLSHostnameOverride orderer0.exemplo.com --tls --cafile /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/ca.crt --channelID channel-all --name calc_do --version 1.0 --package-id $PACKAGE_ID --sequence 1 --collections-config /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/calc_do_collections.json --signature-policy "AND('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member', 'Org4MSP.member')"

infoln 'Aprovando para Org4 (peer: 10.10.20.152:13051)...'
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org4MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/peers/peer0.Org4.exemplo.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/users/Admin@Org4.exemplo.com/msp
export CORE_PEER_ADDRESS=10.10.20.152:13051
peer lifecycle chaincode approveformyorg -o 10.10.20.151:7060 --ordererTLSHostnameOverride orderer0.exemplo.com --tls --cafile /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/ca.crt --channelID channel-all --name calc_do --version 1.0 --package-id $PACKAGE_ID --sequence 1 --collections-config /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/calc_do_collections.json --signature-policy "AND('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member', 'Org4MSP.member')"

infoln 'Commitando chaincode calc_do no canal channel-all...'
peer lifecycle chaincode commit -o 10.10.20.151:7060 --ordererTLSHostnameOverride orderer0.exemplo.com --tls --cafile /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/ordererOrganizations/exemplo.com/orderers/orderer0.exemplo.com/tls/ca.crt --channelID channel-all --name calc_do --version 1.0 --sequence 1 --collections-config /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/chaincode/calc_do_collections.json --signature-policy "AND('Org1MSP.member', 'Org2MSP.member', 'Org3MSP.member', 'Org4MSP.member')"  --peerAddresses 10.10.20.151:7051 --peerAddresses 10.10.20.151:9051 --peerAddresses 10.10.20.152:11051 --peerAddresses 10.10.20.152:13051  --tlsRootCertFiles /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org1.exemplo.com/peers/peer0.Org1.exemplo.com/tls/ca.crt --tlsRootCertFiles /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org2.exemplo.com/peers/peer0.Org2.exemplo.com/tls/ca.crt --tlsRootCertFiles /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org3.exemplo.com/peers/peer0.Org3.exemplo.com/tls/ca.crt --tlsRootCertFiles /mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/organizations/peerOrganizations/Org4.exemplo.com/peers/peer0.Org4.exemplo.com/tls/ca.crt

successln 'Deploy do chaincode calc_do concluído com sucesso!'