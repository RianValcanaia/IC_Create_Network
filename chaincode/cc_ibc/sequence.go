package main

import (
	"fmt"

	"google.golang.org/protobuf/encoding/protowire"
)

const SequenceCommitmentKey = "fabric-msp/sequence"

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
