/*
ReceivedPacketStore: guarda cada pacote recebido e o ack escrito para ele,
por (port, channel, sequence).

Mesmo problema do SentPacketStore, do lado de quem recebe: o ibc-go só grava o
hash do ack. Sem este store, o relayer não conseguiria levar o ack de volta
para quem enviou o pacote.

Também guarda a maior sequence recebida em cada channel. Em channel UNORDERED
(o caso do ICS-20) o NextSequenceRecv não avança, então o relayer usa esse
valor como limite ao procurar acks. Isso supõe sequences quase contínuas, o
que vale nos fluxos do projeto (um remetente por channel).
*/
package ibcadapter

import (
	"encoding/binary"
	"encoding/json"
	"fmt"

	channeltypes "github.com/cosmos/ibc-go/v8/modules/core/04-channel/types"

	"github.com/rianvalcanaia/cc_ibc/internal/fabricstore"
)

// ReceivedPacketStore guarda os pacotes recebidos e seus acks (ver o topo
// do arquivo).
type ReceivedPacketStore struct {
	db *fabricstore.FabricDB
}

// NewReceivedPacketStore cria o store sobre o FabricDB.
func NewReceivedPacketStore(db *fabricstore.FabricDB) ReceivedPacketStore {
	return ReceivedPacketStore{db: db}
}

type receivedPacketRecord struct {
	Packet          channeltypes.Packet `json:"packet"`
	Acknowledgement []byte              `json:"acknowledgement"`
}

// receivedPacketKey monta a chave
// ics04/recvpacket/<port>/<channel>/<sequence>.
func receivedPacketKey(portID, channelID string, sequence uint64) []byte {
	return []byte(fmt.Sprintf("ics04/recvpacket/%s/%s/%d", portID, channelID, sequence))
}

// receivedHighKey monta a chave ics04/recvhigh/<port>/<channel>, onde fica a
// maior sequence recebida.
func receivedHighKey(portID, channelID string) []byte {
	return []byte(fmt.Sprintf("ics04/recvhigh/%s/%s", portID, channelID))
}

// Put grava pacote + ack e atualiza a maior sequence recebida, se essa for
// maior.
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

// Get devolve o pacote e o ack de uma sequence.
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

// HighSequence devolve a maior sequence recebida no channel (0 se nenhuma).
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
