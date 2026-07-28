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

type Asset struct {
	ID    string `json:"id"`
	Owner string `json:"owner"`
	Value int    `json:"value"`
}

type PublicAsset struct {
	ID    string `json:"id"`
	Owner string `json:"owner"`
}

type PrivateAsset struct {
	Value int `json:"value"`
}

// CreateAsset - Cria um asset gravando ID/Owner no World State e Value na PDC
func (s *SmartContract) CreateAsset(
	ctx contractapi.TransactionContextInterface,
	pID string,
	pOwner string,
	pValue int,
) error {

	if pID == "" || pOwner == "" {
		return fmt.Errorf("id e owner são obrigatórios")
	}

	existing, err := ctx.GetStub().GetState(pID)
	if err != nil {
		return fmt.Errorf("erro ao verificar asset: %w", err)
	}

	if existing != nil {
		return fmt.Errorf("asset %s já existe", pID)
	}

	publicAsset := PublicAsset{
		ID:    pID,
		Owner: pOwner,
	}

	publicJSON, err := json.Marshal(publicAsset)
	if err != nil {
		return err
	}

	if err := ctx.GetStub().PutState(pID, publicJSON); err != nil {
		return err
	}

	privateAsset := PrivateAsset{
		Value: pValue,
	}

	privateJSON, err := json.Marshal(privateAsset)
	if err != nil {
		return err
	}

	if err := ctx.GetStub().PutPrivateData("collectionPrivate", pID, privateJSON); err != nil {
		return err
	}

	return nil
}

// ReadAsset - Lê o asset público e tenta recuperar o valor privado
func (s *SmartContract) ReadAsset(
	ctx contractapi.TransactionContextInterface,
	id string,
) (map[string]interface{}, error) {
	publicJSON, err := ctx.GetStub().GetState(id)
	if err != nil {
		return nil, err
	}

	if publicJSON == nil {
		return nil, fmt.Errorf("asset %s não encontrado", id)
	}

	var publicAsset PublicAsset

	if err := json.Unmarshal(publicJSON, &publicAsset); err != nil {
		return nil, err
	}

	result := map[string]interface{}{
		"id":    publicAsset.ID,
		"owner": publicAsset.Owner,
	}

	privateJSON, err := ctx.GetStub().GetPrivateData("collectionPrivate", id)

	if err == nil && privateJSON != nil {
		var privateAsset PrivateAsset

		if err := json.Unmarshal(privateJSON, &privateAsset); err == nil {
			result["value"] = privateAsset.Value
		} else {
			result["value"] = "CONFIDENTIAL"
		}
	} else {
		result["value"] = "CONFIDENTIAL"
	}

	return result, nil
}

// UpdateAsset - Atualiza os dados públicos e privados do asset
func (s *SmartContract) UpdateAsset(
	ctx contractapi.TransactionContextInterface,
) error {

	transientMap, err := ctx.GetStub().GetTransient()
	if err != nil {
		return err
	}

	assetData, ok := transientMap["asset_properties"]
	if !ok {
		return fmt.Errorf("asset_properties ausente no transient map")
	}

	var asset Asset

	if err := json.Unmarshal(assetData, &asset); err != nil {
		return err
	}

	existing, err := ctx.GetStub().GetState(asset.ID)
	if err != nil {
		return err
	}

	if existing == nil {
		return fmt.Errorf("asset %s não encontrado", asset.ID)
	}

	publicAsset := PublicAsset{
		ID:    asset.ID,
		Owner: asset.Owner,
	}

	publicJSON, err := json.Marshal(publicAsset)
	if err != nil {
		return err
	}

	if err := ctx.GetStub().PutState(asset.ID, publicJSON); err != nil {
		return err
	}

	privateAsset := PrivateAsset{
		Value: asset.Value,
	}

	privateJSON, err := json.Marshal(privateAsset)
	if err != nil {
		return err
	}

	return ctx.GetStub().PutPrivateData(
		"collectionPrivate",
		asset.ID,
		privateJSON,
	)
}

// GetAllAssets - Retorna todos os assets
func (s *SmartContract) GetAllAssets(
	ctx contractapi.TransactionContextInterface,
) ([]map[string]interface{}, error) {

	resultsIterator, err := ctx.GetStub().GetStateByRange("", "")
	if err != nil {
		return nil, err
	}

	defer resultsIterator.Close()

	var assets []map[string]interface{}

	for resultsIterator.HasNext() {

		queryResponse, err := resultsIterator.Next()
		if err != nil {
			return nil, err
		}

		asset, err := s.ReadAsset(ctx, queryResponse.Key)
		if err != nil {
			return nil, err
		}

		assets = append(assets, asset)
	}

	return assets, nil
}

// InitLedger - Inicializa o ledger utilizando CreateAsset()
func (s *SmartContract) InitLedger(
	ctx contractapi.TransactionContextInterface,
) error {

	assets := []Asset{
		{ID: "asset1", Owner: "Org1", Value: 100},
		{ID: "asset2", Owner: "Org2", Value: 200},
		{ID: "asset3", Owner: "Org1", Value: 300},
	}

	for _, asset := range assets {

		if err := s.CreateAsset(
			ctx,
			asset.ID,
			asset.Owner,
			asset.Value,
		); err != nil {
			return err
		}
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
