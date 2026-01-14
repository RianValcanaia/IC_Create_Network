package main

import (
	"encoding/json"
	"fmt"
	"log"

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

// cria um novo asset na pdc - C
func (s *SmartContract) CreateAsset(ctx contractapi.TransactionContextInterface) error {
	transMap, err := ctx.GetStub().GetTransient()
	if err != nil {
		return fmt.Errorf("erro ao recuperar transient map: %v", err)
	}

	assetData, ok := transMap["asset_properties"]
	if !ok {
		return fmt.Errorf("o campo 'asset_properties' deve estar presente no transient map")
	}

	var asset Asset
	err = json.Unmarshal(assetData, &asset)
	if err != nil {
		return fmt.Errorf("erro ao unmarshal asset: %v", err)
	}

	// grava o asset na PDC
	err = ctx.GetStub().PutPrivateData("collectionPrivate", asset.ID, assetData)
	if err != nil {
		return fmt.Errorf("erro ao gravar na PDC: %v", err)
	}

	return nil
}

// le um asset da pdc - R
func (s *SmartContract) ReadAsset(ctx contractapi.TransactionContextInterface, id string) (*Asset, error) {
	assetJSON, err := ctx.GetStub().GetPrivateData("collectionPrivate", id)
	if err != nil {
		return nil, fmt.Errorf("falha ao ler da PDC: %v", err)
	}
	if assetJSON == nil {
		return nil, fmt.Errorf("o asset %s nao existe na colecao privada", id)
	}

	var asset Asset
	err = json.Unmarshal(assetJSON, &asset)
	if err != nil {
		return nil, err
	}

	return &asset, nil
}

// atualiza um asset existente na pdc - U
func (s *SmartContract) UpdateAsset(ctx contractapi.TransactionContextInterface) error {
	transMap, _ := ctx.GetStub().GetTransient()
	assetData, ok := transMap["asset_properties"]
	if !ok {
		return fmt.Errorf("dados ausentes no transient map")
	}

	var asset Asset
	json.Unmarshal(assetData, &asset)

	// verifica se existe antes de atualizar
	existing, err := ctx.GetStub().GetPrivateData("collectionPrivate", asset.ID)
	if err != nil || existing == nil {
		return fmt.Errorf("asset nao encontrado para atualizacao")
	}

	return ctx.GetStub().PutPrivateData("collectionPrivate", asset.ID, assetData)
}

func main() {
	assetChaincode, err := contractapi.NewChaincode(&SmartContract{})
	if err != nil {
		log.Panicf("Erro ao criar basic_asset chaincode: %v", err)
	}

	if err := assetChaincode.Start(); err != nil {
		log.Panicf("Erro ao iniciar basic_asset chaincode: %v", err)
	}
}
