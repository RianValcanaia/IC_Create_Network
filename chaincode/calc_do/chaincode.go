package main

import (
	"encoding/json"
	"fmt"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// CalcDoContract define o contrato de ancoragem de resultados ICR.
type CalcDoContract struct {
	contractapi.Contract
}

// ─── AnchorCalcResult ─────────────────────────────────────────────────────────

// AnchorCalcResult ancora o hash de um resultado de cálculo ICR no ledger.
//
// Apenas o hash e os participantIds dos workers são persistidos on-chain.
// O resultado completo fica off-chain no MongoDB.
//
// Argumentos:
//   - argsJSON: JSON serializado de AnchorCalcResultArgs (calcId, hash, anchoredAt, workers)
//
// A chave no world state é: "ANCHOR_{calcId}"
func (c *CalcDoContract) AnchorCalcResult(ctx contractapi.TransactionContextInterface, argsJSON string) error {
	var args AnchorCalcResultArgs
	if err := json.Unmarshal([]byte(argsJSON), &args); err != nil {
		return fmt.Errorf("falha ao parsear argsJSON: %w", err)
	}

	if args.CalcID == "" || args.Hash == "" || args.AnchoredAt == 0 {
		return fmt.Errorf("campos obrigatórios ausentes: calcId, hash ou anchoredAt")
	}

	// Idempotência — não permite sobrescrever uma ancoragem existente
	key := anchorKey(args.CalcID)
	existing, err := ctx.GetStub().GetState(key)
	if err != nil {
		return fmt.Errorf("erro ao verificar estado existente: %w", err)
	}
	if existing != nil {
		return fmt.Errorf("calcId %s já foi ancorado — operação idempotente negada", args.CalcID)
	}

	record := AnchorRecord{
		DocType:    "anchor",
		CalcID:     args.CalcID,
		Hash:       args.Hash,
		AnchoredAt: args.AnchoredAt,
		Workers:    args.Workers,
	}

	recordBytes, err := json.Marshal(record)
	if err != nil {
		return fmt.Errorf("erro ao serializar AnchorRecord: %w", err)
	}

	if err := ctx.GetStub().PutState(key, recordBytes); err != nil {
		return fmt.Errorf("erro ao persistir no ledger: %w", err)
	}

	return nil
}

// ─── QueryCalcDo ─────────────────────────────────────────────────────────────

// QueryCalcDo retorna o AnchorRecord de um cálculo pelo seu calcId.
func (c *CalcDoContract) QueryCalcDo(ctx contractapi.TransactionContextInterface, calcID string) (*AnchorRecord, error) {
	if calcID == "" {
		return nil, fmt.Errorf("calcId não pode ser vazio")
	}

	recordBytes, err := ctx.GetStub().GetState(anchorKey(calcID))
	if err != nil {
		return nil, fmt.Errorf("erro ao buscar estado: %w", err)
	}
	if recordBytes == nil {
		return nil, fmt.Errorf("calcId %s não encontrado no ledger", calcID)
	}

	var record AnchorRecord
	if err := json.Unmarshal(recordBytes, &record); err != nil {
		return nil, fmt.Errorf("erro ao deserializar AnchorRecord: %w", err)
	}

	return &record, nil
}

// ─── GetAllAnchored ───────────────────────────────────────────────────────────

// GetAllAnchored retorna todos os AnchorRecords persistidos no ledger.
func (c *CalcDoContract) GetAllAnchored(ctx contractapi.TransactionContextInterface) ([]*AnchorRecord, error) {
	iterator, err := ctx.GetStub().GetStateByRange("ANCHOR_", "ANCHOR_~")
	if err != nil {
		return nil, fmt.Errorf("erro ao iniciar range query: %w", err)
	}
	defer iterator.Close()

	var records []*AnchorRecord

	for iterator.HasNext() {
		queryResponse, err := iterator.Next()
		if err != nil {
			return nil, fmt.Errorf("erro ao iterar resultados: %w", err)
		}

		var record AnchorRecord
		if err := json.Unmarshal(queryResponse.Value, &record); err != nil {
			return nil, fmt.Errorf("erro ao deserializar registro %s: %w", queryResponse.Key, err)
		}

		records = append(records, &record)
	}

	return records, nil
}

// ─── Helper ───────────────────────────────────────────────────────────────────

func anchorKey(calcID string) string {
	return "ANCHOR_" + calcID
}