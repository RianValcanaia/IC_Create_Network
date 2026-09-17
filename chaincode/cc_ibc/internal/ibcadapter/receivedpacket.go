package ibcadapter

import (
	"encoding/binary"
	"encoding/json"
	"fmt"

	channeltypes "github.com/cosmos/ibc-go/v8/modules/core/04-channel/types"

	"github.com/rianvalcanaia/cc_ibc/internal/fabricstore"
)

// ReceivedPacketStore persiste, por (destPort, destChannel, sequence), o
// Packet recebido e a Acknowledgement escrita pro ele - mesmo problema
// do SentPacketStore, mas do lado receptor: o ChannelKeeper real só
// grava o hash (CommitAcknowledgement) no state, nunca a
// Acknowledgement em si, e o Cosmos reconstrói via busca de eventos ABCI
// (Chain.queryReceivedPacket/queryWrittenAcknowledgement em
// src_codes/yui-relayer/chains/tendermint/query.go) - sem esse índice
// aqui, a Acknowledgement que esta chain escreve nunca poderia ser
// relayada de volta pro remetente original (`tx relay-acknowledgements`).
//
// Canais ICS-20 são UNORDERED (validateTransferChannelParams,
// transferapp.go), então NextSequenceRecv não serve pra enumerar "quais
// sequences já foram recebidas" (fica travado em 1 em canais unordered,
// por spec). Por isso este store também mantém um high-water mark
// separado (a maior sequence já recebida) só pra dar ao relayer um
// limite até onde iterar - MVP: assume sequences aproximadamente
// sequenciais (verdade nos fluxos deste projeto, um remetente por
// canal), não uma varredura genérica de sequences esparsas.
type ReceivedPacketStore struct {
	db *fabricstore.FabricDB
}

func NewReceivedPacketStore(db *fabricstore.FabricDB) ReceivedPacketStore {
	return ReceivedPacketStore{db: db}
}

type receivedPacketRecord struct {
	Packet          channeltypes.Packet `json:"packet"`
	Acknowledgement []byte              `json:"acknowledgement"`
}

func receivedPacketKey(portID, channelID string, sequence uint64) []byte {
	return []byte(fmt.Sprintf("ics04/recvpacket/%s/%s/%d", portID, channelID, sequence))
}

func receivedHighKey(portID, channelID string) []byte {
	return []byte(fmt.Sprintf("ics04/recvhigh/%s/%s", portID, channelID))
}

// Put grava o Packet recebido e a Acknowledgement gravada pra ele, e
// avança o high-water mark se essa sequence for a maior vista até agora.
func (s ReceivedPacketStore) Put(portID, channelID string, packet channeltypes.Packet, ack []byte) error {
	record := receivedPacketRecord{Packet: packet, Acknowledgement: ack}
	bz, err := json.Marshal(&record)
	if err != nil {
		return err
	}
	if err := s.db.Set(receivedPacketKey(portID, channelID, packet.Sequence), bz); err != nil {
		return err
	}

	high, err := s.HighSequence(portID, channelID)
	if err != nil {
		return err
	}
	if packet.Sequence > high {
		highBz := make([]byte, 8)
		binary.BigEndian.PutUint64(highBz, packet.Sequence)
		if err := s.db.Set(receivedHighKey(portID, channelID), highBz); err != nil {
			return err
		}
	}
	return nil
}

// Get devolve o Packet e a Acknowledgement gravados pra essa sequence.
func (s ReceivedPacketStore) Get(portID, channelID string, sequence uint64) (channeltypes.Packet, []byte, bool, error) {
	bz, err := s.db.Get(receivedPacketKey(portID, channelID, sequence))
	if err != nil {
		return channeltypes.Packet{}, nil, false, err
	}
	if bz == nil {
		return channeltypes.Packet{}, nil, false, nil
	}
	var record receivedPacketRecord
	if err := json.Unmarshal(bz, &record); err != nil {
		return channeltypes.Packet{}, nil, false, err
	}
	return record.Packet, record.Acknowledgement, true, nil
}

// HighSequence devolve a maior sequence já recebida (0 se nenhuma
// ainda).
func (s ReceivedPacketStore) HighSequence(portID, channelID string) (uint64, error) {
	bz, err := s.db.Get(receivedHighKey(portID, channelID))
	if err != nil {
		return 0, err
	}
	if bz == nil {
		return 0, nil
	}
	return binary.BigEndian.Uint64(bz), nil
}
