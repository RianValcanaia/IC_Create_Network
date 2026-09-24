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
	ccID := os.Getenv("CORE_CHAINCODE_ID_NAME")      // ex: calc_do_1.0:abc123...

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
		CCID:     ccID,
		Address:  address,
		CC:       chaincode,
		TLSProps: ccaasTLS(), // TLS de servidor — connection.json gerado pelo deploy.py exige TLS
	}

	fmt.Printf("Chaincode calc-do iniciando em %s (ID: %s)\n", address, ccID)

	if err := server.Start(); err != nil {
		log.Fatalf("Erro ao iniciar ChaincodeServer: %v", err)
	}
}

// ccaasTLS lê o certificado de servidor montado pelo deploy.py
// (CHAINCODE_TLS_KEY_FILE / CHAINCODE_TLS_CERT_FILE). Sem as variáveis, o
// servidor sobe sem TLS — o connection.json gerado exige TLS, então o peer
// recusará a conexão nesse caso.
func ccaasTLS() shim.TLSProperties {
	keyFile, certFile := os.Getenv("CHAINCODE_TLS_KEY_FILE"), os.Getenv("CHAINCODE_TLS_CERT_FILE")
	if keyFile == "" || certFile == "" {
		log.Println("AVISO: CHAINCODE_TLS_KEY_FILE/CHAINCODE_TLS_CERT_FILE ausentes — servidor CCAAS sem TLS")
		return shim.TLSProperties{Disabled: true}
	}
	key, err := os.ReadFile(keyFile)
	if err != nil {
		log.Fatalf("Erro ao ler a chave TLS %s: %v", keyFile, err)
	}
	cert, err := os.ReadFile(certFile)
	if err != nil {
		log.Fatalf("Erro ao ler o certificado TLS %s: %v", certFile, err)
	}
	return shim.TLSProperties{Disabled: false, Key: key, Cert: cert}
}
