package main

// ─── Tipos específicos do chaincode ──────────────────────────────────────────

// WorkerSummary representa um resumo do worker que participou do cálculo.
type WorkerSummary struct {
	ParticipantID string `json:"participantId"`
}

// AnchorRecord é o documento persistido no world state para cada ancoragem.
type AnchorRecord struct {
	DocType    string          `json:"docType"`    // "anchor"
	CalcID     string          `json:"calcId"`
	Hash       string          `json:"hash"`       // SHA256 hex gerado pelo Hermes
	AnchoredAt int64           `json:"anchoredAt"` // Unix ms
	Workers    []WorkerSummary `json:"workers"`    // participantes do cálculo
}

// AnchorCalcResultArgs é o payload JSON recebido como argumento da transação.
type AnchorCalcResultArgs struct {
	CalcID     string          `json:"calcId"`
	Hash       string          `json:"hash"`
	AnchoredAt int64           `json:"anchoredAt"`
	Workers    []WorkerSummary `json:"workers"`
}