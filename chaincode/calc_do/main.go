package main

import (
	"fmt"
	"log"
	"os"

	"github.com/hyperledger/fabric-chaincode-go/shim"
	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

func main() {
	// Lê as envs injetadas pelo deploy.py via docker run
	address := os.Getenv("CHAINCODE_SERVER_ADDRESS") // ex: 0.0.0.0:10000
	ccID := os.Getenv("CORE_CHAINCODE_ID_NAME")       // ex: calc_do_1.0:abc123...

	if address == "" || ccID == "" {
		log.Fatal("CHAINCODE_SERVER_ADDRESS e CORE_CHAINCODE_ID_NAME são obrigatórios")
	}

	// Instancia o contrato
	contract := new(CalcDoContract)

	chaincode, err := contractapi.NewChaincode(contract)
	if err != nil {
		log.Fatalf("Erro ao criar chaincode: %v", err)
	}

	// Modo CCAAS: shim.ChaincodeServer ao invés de shim.Start
	server := shim.ChaincodeServer{
		CCID:    ccID,
		Address: address,
		CC:      chaincode,
		TLSProps: shim.TLSProperties{
			Disabled: true, // tls_required: false — conforme connection.json gerado pelo deploy.py
		},
	}

	fmt.Printf("Chaincode calc-do iniciando em %s (ID: %s)\n", address, ccID)

	if err := server.Start(); err != nil {
		log.Fatalf("Erro ao iniciar ChaincodeServer: %v", err)
	}
}