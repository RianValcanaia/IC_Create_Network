// Package fabricstore adapta o KVStore do Fabric (shim.ChaincodeStubInterface)
// para as interfaces de armazenamento que o ibc-go/cosmos-sdk esperam, mesma
// técnica do fork antigo
package fabricstore

import (
	"encoding/hex"
	"errors"

	dbm "github.com/cosmos/cosmos-db"
	"github.com/hyperledger/fabric-chaincode-go/v2/shim"
)

var (
	errKeyEmpty = errors.New("fabricstore: key cannot be empty")
	errValueNil = errors.New("fabricstore: value cannot be nil")
)

// FabricDB implementa dbm.DB sobre o WorldState do Fabric, via
// GetState/PutState/DelState/GetStateByRange do stub. Chaves sempre
// hex-encoded antes de chegar no stub - Fabric exige chaves imprimíveis
// (CouchDB) e keys do cosmos-sdk são bytes arbitrários.
type FabricDB struct {
	stub    shim.ChaincodeStubInterface
	pending map[string][]byte // chave hex-encoded -> valor; nil = deletado
}

var _ dbm.DB = (*FabricDB)(nil)

func NewFabricDB(stub shim.ChaincodeStubInterface) *FabricDB {
	return &FabricDB{stub: stub, pending: make(map[string][]byte)}
}

func encodeKey(key []byte) string {
	return hex.EncodeToString(key)
}

func decodeKey(key string) []byte {
	bz, err := hex.DecodeString(key)
	if err != nil {
		panic(err)
	}
	return bz
}

func (db *FabricDB) Get(key []byte) ([]byte, error) {
	if len(key) == 0 {
		return nil, errKeyEmpty
	}
	encoded := encodeKey(key)
	if v, touched := db.pending[encoded]; touched {
		return v, nil
	}
	return db.stub.GetState(encoded)
}

func (db *FabricDB) Has(key []byte) (bool, error) {
	v, err := db.Get(key)
	if err != nil {
		return false, err
	}
	return v != nil, nil
}

func (db *FabricDB) Set(key, value []byte) error {
	if len(key) == 0 {
		return errKeyEmpty
	}
	if value == nil {
		return errValueNil
	}
	encoded := encodeKey(key)
	if err := db.stub.PutState(encoded, value); err != nil {
		return err
	}
	db.pending[encoded] = value
	return nil
}

func (db *FabricDB) SetSync(key, value []byte) error {
	return db.Set(key, value)
}

func (db *FabricDB) Delete(key []byte) error {
	if len(key) == 0 {
		return errKeyEmpty
	}
	encoded := encodeKey(key)
	if err := db.stub.DelState(encoded); err != nil {
		return err
	}
	db.pending[encoded] = nil
	return nil
}

func (db *FabricDB) DeleteSync(key []byte) error {
	return db.Delete(key)
}

// Iterator/ReverseIterator: hex-encoding preserva ordem lexicográfica de
// bytes (cada byte vira 2 chars hex, monotonicamente), então o range
// [hex(start), hex(end)) do GetStateByRange corresponde exatamente ao
// range [start, end) em bytes crus - sem isso, iteração ordenada (usada
// pelo cosmos-sdk pra prefix scans) quebraria.
func (db *FabricDB) Iterator(start, end []byte) (dbm.Iterator, error) {
	s, e := "", ""
	if start != nil {
		s = encodeKey(start)
	}
	if end != nil {
		e = encodeKey(end)
	}
	iter, err := db.stub.GetStateByRange(s, e)
	if err != nil {
		return nil, err
	}
	return newIterator(iter, false)
}

func (db *FabricDB) ReverseIterator(start, end []byte) (dbm.Iterator, error) {
	s, e := "", ""
	if start != nil {
		s = encodeKey(start)
	}
	if end != nil {
		e = encodeKey(end)
	}
	iter, err := db.stub.GetStateByRange(s, e)
	if err != nil {
		return nil, err
	}
	return newIterator(iter, true)
}

func (db *FabricDB) Close() error { return nil }

func (db *FabricDB) NewBatch() dbm.Batch {
	return &fabricBatch{db: db}
}

func (db *FabricDB) NewBatchWithSize(size int) dbm.Batch {
	return &fabricBatch{db: db, ops: make([]batchOp, 0, size)}
}

func (db *FabricDB) Print() error {
	return errors.New("fabricstore: Print not implemented")
}

func (db *FabricDB) Stats() map[string]string {
	return map[string]string{}
}

// fabricBatch: sem transação atômica real do lado Fabric (cada
// PutState/DelState já é aplicado no write-set da transação chaincode em
// andamento, que o próprio Fabric torna atômica na validação/commit) -
// só acumula e aplica em ordem no Write().
type fabricBatch struct {
	db  *FabricDB
	ops []batchOp
}

type batchOp struct {
	del   bool
	key   []byte
	value []byte
}

var _ dbm.Batch = (*fabricBatch)(nil)

func (b *fabricBatch) Set(key, value []byte) error {
	if len(key) == 0 {
		return errKeyEmpty
	}
	if value == nil {
		return errValueNil
	}
	b.ops = append(b.ops, batchOp{key: key, value: value})
	return nil
}

func (b *fabricBatch) Delete(key []byte) error {
	if len(key) == 0 {
		return errKeyEmpty
	}
	b.ops = append(b.ops, batchOp{del: true, key: key})
	return nil
}

func (b *fabricBatch) Write() error {
	for _, op := range b.ops {
		if op.del {
			if err := b.db.Delete(op.key); err != nil {
				return err
			}
			continue
		}
		if err := b.db.Set(op.key, op.value); err != nil {
			return err
		}
	}
	return nil
}

func (b *fabricBatch) WriteSync() error { return b.Write() }

func (b *fabricBatch) Close() error {
	b.ops = nil
	return nil
}

func (b *fabricBatch) GetByteSize() (int, error) {
	n := 0
	for _, op := range b.ops {
		n += len(op.key) + len(op.value)
	}
	return n, nil
}

// fabricIterator adapta shim.StateQueryIteratorInterface (avança só pra
// frente) para dbm.Iterator. Reverse: como o stub do Fabric não suporta
// iteração reversa nativa, materializa tudo em memória e inverte - mesma
// solução do fork antigo (aceitável pro volume de dados de um light
// client/handshake IBC, não um full table scan de produção).
type fabricIterator struct {
	items   []kvItem
	current int
}

type kvItem struct {
	key   []byte
	value []byte
}

var _ dbm.Iterator = (*fabricIterator)(nil)

func newIterator(qi shim.StateQueryIteratorInterface, reverse bool) (*fabricIterator, error) {
	defer qi.Close()
	var items []kvItem
	for qi.HasNext() {
		kv, err := qi.Next()
		if err != nil {
			return nil, err
		}
		items = append(items, kvItem{key: decodeKey(kv.Key), value: kv.Value})
	}
	// GetStateByRange já devolve em ordem ascendente de chave (garantia do
	// Fabric) - reverse só precisa inverter a ordem, não reordenar.
	if reverse {
		for i, j := 0, len(items)-1; i < j; i, j = i+1, j-1 {
			items[i], items[j] = items[j], items[i]
		}
	}
	return &fabricIterator{items: items}, nil
}

func (it *fabricIterator) Domain() (start, end []byte) { return nil, nil }

func (it *fabricIterator) Valid() bool {
	return it.current >= 0 && it.current < len(it.items)
}

func (it *fabricIterator) Next() {
	it.current++
}

func (it *fabricIterator) Key() []byte {
	return it.items[it.current].key
}

func (it *fabricIterator) Value() []byte {
	return it.items[it.current].value
}

func (it *fabricIterator) Error() error { return nil }

func (it *fabricIterator) Close() error { return nil }
