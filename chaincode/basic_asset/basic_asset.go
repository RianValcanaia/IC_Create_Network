// Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"

	"github.com/hyperledger/fabric-chaincode-go/shim"
	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

type SmartContract struct {
	contractapi.Contract
}

// definicao do asset
type Asset struct {
	ID    string `json:"id"`
	Owner string `json:"owner"`
	Value int    `json:"value"` // dado secreto do pdc
}

// CreateAsset - Grava ID/Owner no público e Value no privado - C
func (s *SmartContract) CreateAsset(ctx contractapi.TransactionContextInterface) error {
	transMap, _ := ctx.GetStub().GetTransient()
	assetData, ok := transMap["asset_properties"]
	if !ok {
		return fmt.Errorf("dados ausentes no transient map")
	}

	var asset Asset
	if err := json.Unmarshal(assetData, &asset); err != nil {
		return err
	}

	// Grava no Ledger publico
	publicData := map[string]string{
		"id":    asset.ID,
		"owner": asset.Owner,
	}
	publicJSON, _ := json.Marshal(publicData)
	ctx.GetStub().PutState(asset.ID, publicJSON)

	// Grava o Value na PDC
	privateData := map[string]int{"value": asset.Value}
	privateJSON, _ := json.Marshal(privateData)
	return ctx.GetStub().PutPrivateData("collectionPrivate", asset.ID, privateJSON)
}

// ReadAsset - Tenta ler ID/Owner e opcionalmente o Value
func (s *SmartContract) ReadAsset(ctx contractapi.TransactionContextInterface, id string) (map[string]interface{}, error) {
	publicJSON, _ := ctx.GetStub().GetState(id)
	if publicJSON == nil {
		return nil, fmt.Errorf("asset %s nao encontrado no ledger publico", id)
	}

	var result map[string]interface{}
	json.Unmarshal(publicJSON, &result)

	// Tenta ler o valor privado
	privateJSON, err := ctx.GetStub().GetPrivateData("collectionPrivate", id)

	if err == nil && privateJSON != nil {
		var pData map[string]int
		json.Unmarshal(privateJSON, &pData)
		result["value"] = pData["value"]
	} else {
		// Se for outra Org (sem permissao), retorna metadados com aviso
		result["value"] = "CONFIDENTIAL"
	}

	return result, nil
}

// UpdateAsset - Atualiza metadados publicos e o valor privado
func (s *SmartContract) UpdateAsset(ctx contractapi.TransactionContextInterface) error {
	transMap, _ := ctx.GetStub().GetTransient()
	assetData, ok := transMap["asset_properties"]
	if !ok {
		return fmt.Errorf("dados ausentes")
	}

	var asset Asset
	json.Unmarshal(assetData, &asset)

	// Verifica se existe no publico primeiro
	existing, _ := ctx.GetStub().GetState(asset.ID)
	if existing == nil {
		return fmt.Errorf("asset nao encontrado")
	}

	// Atualiza publico
	publicData := map[string]string{"id": asset.ID, "owner": asset.Owner}
	pJSON, _ := json.Marshal(publicData)
	ctx.GetStub().PutState(asset.ID, pJSON)

	// Atualiza privado (apenas se for Org autorizada)
	privateData := map[string]int{"value": asset.Value}
	prJSON, _ := json.Marshal(privateData)
	return ctx.GetStub().PutPrivateData("collectionPrivate", asset.ID, prJSON)
}

func (s *SmartContract) GetAllAssets(ctx contractapi.TransactionContextInterface) ([]map[string]interface{}, error) {
	// Agora varre o World State (ID e Owner estao aqui)
	resultsIterator, err := ctx.GetStub().GetStateByRange("", "")
	if err != nil {
		return nil, err
	}
	defer resultsIterator.Close()

	var assets []map[string]interface{}
	for resultsIterator.HasNext() {
		queryResponse, _ := resultsIterator.Next()
		// Usa o ReadAsset que ja trata a privacidade do Value
		asset, _ := s.ReadAsset(ctx, queryResponse.Key)
		assets = append(assets, asset)
	}
	return assets, nil
}

func (s *SmartContract) InitLedger(ctx contractapi.TransactionContextInterface) error {
	assets := []Asset{
		{ID: "asset1", Owner: "Org1", Value: 100},
		{ID: "asset2", Owner: "Org2", Value: 200},
		{ID: "asset3", Owner: "Org1", Value: 300},
	}

	for _, asset := range assets {
		// Grava no publico (obrigatorio para GetAllAssets funcionar)
		publicData := map[string]string{"id": asset.ID, "owner": asset.Owner}
		pJSON, _ := json.Marshal(publicData)
		ctx.GetStub().PutState(asset.ID, pJSON)

		// Grava no privado
		privateData := map[string]int{"value": asset.Value}
		prJSON, _ := json.Marshal(privateData)
		ctx.GetStub().PutPrivateData("collectionPrivate", asset.ID, prJSON)
	}
	return nil
}

func main() {
	smartContract := new(SmartContract)
	cc, err := contractapi.NewChaincode(smartContract)
	if err != nil {
		log.Panicf("Erro ao criar chaincode: %v", err)
	}

	server := &shim.ChaincodeServer{
		CCID:     os.Getenv("CORE_CHAINCODE_ID_NAME"),
		Address:  os.Getenv("CHAINCODE_SERVER_ADDRESS"),
		CC:       cc,
		TLSProps: shim.TLSProperties{Disabled: true},
	}

	if err := server.Start(); err != nil {
		log.Panicf("Erro ao iniciar servidor: %v", err)
	}
}
