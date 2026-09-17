package ibcadapter

import (
	"encoding/json"
	"fmt"

	channeltypes "github.com/cosmos/ibc-go/v8/modules/core/04-channel/types"

	"github.com/rianvalcanaia/cc_ibc/internal/fabricstore"
)

// SentPacketStore persiste o channeltypes.Packet completo de cada envio,
// indexado por sequence. O ChannelKeeper.SendPacket real (ibc-go) só
// grava o commitment (hash) no estado - por design, porque no Cosmos o
// relayer reconstrói o Packet original lendo os eventos ABCI da tx que
// o emitiu (ver Chain.querySentPacket em
// src_codes/yui-relayer/chains/tendermint/query.go). O Fabric não tem
// um índice de eventos por tx equivalente exposto ao relayer via
// fabric-gateway, então sem esse store o lado Fabric nunca teria como
// devolver o Packet original pra montar um MsgRecvPacket - só o hash,
// que não é reversível.
type SentPacketStore struct {
	db *fabricstore.FabricDB
}

func NewSentPacketStore(db *fabricstore.FabricDB) SentPacketStore {
	return SentPacketStore{db: db}
}

func sentPacketKey(portID, channelID string, sequence uint64) []byte {
	return []byte(fmt.Sprintf("ics04/sentpacket/%s/%s/%d", portID, channelID, sequence))
}

// Put grava o Packet exatamente como foi passado a ChannelKeeper.SendPacket
// (mesmos bytes de Data/timeout que entraram no CommitPacket) - qualquer
// divergência aqui faz a prova de commitment falhar na chain de destino.
func (s SentPacketStore) Put(portID, channelID string, packet channeltypes.Packet) error {
	bz, err := json.Marshal(&packet)
	if err != nil {
		return err
	}
	return s.db.Set(sentPacketKey(portID, channelID, packet.Sequence), bz)
}

// Get devolve o Packet enviado nessa sequence, se ainda estiver
// armazenado (nunca é removido - ao contrário do commitment, que some
// do state após o ack/timeout ser processado).
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
