/*
A "altura" do Fabric para o IBC.

O IBC identifica estados por altura de bloco, mas o chaincode não tem uma
altura própria que a outra chain consiga verificar. No lugar dela, o cc_ibc
mantém uma sequência na chave fabric-msp/sequence: um contador mais um
timestamp, incrementado pela transação AdvanceSequence. O light client
fabric-msp do outro lado trata essa sequência como a altura do Fabric.

O valor é gravado no formato protobuf da mensagem Sequence do fabric-msp
(campo 1 = valor, campo 2 = timestamp), para que o outro lado consiga ler a
mesma chave a partir de um endosso.
*/
package main

import (
	"fmt"

	"google.golang.org/protobuf/encoding/protowire"
)

const SequenceCommitmentKey = "fabric-msp/sequence"

// encodeSequence grava (valor, timestamp) no formato protobuf da Sequence;
// campos zerados são omitidos, como no protobuf.
func encodeSequence(value uint64, timestamp int64) []byte {
	var buf []byte
	if value != 0 {
		buf = protowire.AppendTag(buf, 1, protowire.VarintType)
		buf = protowire.AppendVarint(buf, value)
	}
	if timestamp != 0 {
		buf = protowire.AppendTag(buf, 2, protowire.VarintType)
		buf = protowire.AppendVarint(buf, uint64(timestamp))
	}
	return buf
}

// decodeSequenceValue lê os bytes protobuf da Sequence de volta para (valor,
// timestamp).
func decodeSequenceValue(bz []byte) (value uint64, timestamp int64, err error) {
	for len(bz) > 0 {
		num, typ, n := protowire.ConsumeTag(bz)
		if n < 0 {
			return 0, 0, fmt.Errorf("cc_ibc: invalid Sequence encoding")
		}
		bz = bz[n:]
		if typ != protowire.VarintType {
			return 0, 0, fmt.Errorf("cc_ibc: unexpected wire type %v for field %d", typ, num)
		}
		v, n := protowire.ConsumeVarint(bz)
		if n < 0 {
			return 0, 0, fmt.Errorf("cc_ibc: invalid varint for field %d", num)
		}
		bz = bz[n:]
		switch num {
		case 1:
			value = v
		case 2:
			timestamp = int64(v)
		}
	}
	return value, timestamp, nil
}
