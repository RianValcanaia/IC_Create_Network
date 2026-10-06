/*
SentPacketStore: guarda o pacote completo de cada envio, por
(port, channel, sequence).

O ibc-go só grava o hash (commitment) do pacote. Num nó Cosmos o relayer
recupera o pacote original pelos eventos da transação; o Fabric não oferece
essa busca por eventos ao relayer. Sem este store, o relayer não teria como
remontar o pacote para entregá-lo na outra chain (o hash não é reversível).
*/
package ibcadapter

import (
	"encoding/json"
	"fmt"

	channeltypes "github.com/cosmos/ibc-go/v8/modules/core/04-channel/types"

	"github.com/rianvalcanaia/cc_ibc/internal/fabricstore"
)

// SentPacketStore guarda o pacote completo de cada envio (ver o topo do
// arquivo).
type SentPacketStore struct {
	db *fabricstore.FabricDB
}

// NewSentPacketStore cria o store sobre o FabricDB.
func NewSentPacketStore(db *fabricstore.FabricDB) SentPacketStore {
	return SentPacketStore{db: db}
}

// sentPacketKey monta a chave ics04/sentpacket/<port>/<channel>/<sequence>.
func sentPacketKey(portID, channelID string, sequence uint64) []byte {
	return []byte(fmt.Sprintf("ics04/sentpacket/%s/%s/%d", portID, channelID, sequence))
}

// Put grava o pacote em JSON. Ele precisa ser idêntico ao usado no SendPacket,
// senão a prova do commitment falha do outro lado.
func (s SentPacketStore) Put(portID, channelID string, packet channeltypes.Packet) error {
	bz, err := json.Marshal(&packet)
	if err != nil {
		return err
	}
	return s.db.Set(sentPacketKey(portID, channelID, packet.Sequence), bz)
}

// Get devolve o pacote enviado nessa sequence. Ele nunca é apagado, ao
// contrário do commitment, que some depois do ack ou do timeout.
func (s SentPacketStore) Get(portID, channelID string, sequence uint64) (channeltypes.Packet, bool, error) {
	bz, err := s.db.Get(sentPacketKey(portID, channelID, sequence))
	if err != nil {
		return channeltypes.Packet{}, false, err
	}
	if bz == nil {
		return channeltypes.Packet{}, false, nil
	}
	var packet channeltypes.Packet
	if err := json.Unmarshal(bz, &packet); err != nil {
		return channeltypes.Packet{}, false, err
	}
	return packet, true, nil
}
