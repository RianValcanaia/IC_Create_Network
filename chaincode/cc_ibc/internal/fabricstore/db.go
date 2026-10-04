/*
FabricDB: o banco de dados do Cosmos SDK (dbm.DB) em cima do WorldState do
Fabric.

O ibc-go grava tudo por meio de KVStores do Cosmos SDK. Aqui cada operação
vira a chamada correspondente do stub do chaincode:

	Get -> GetState, Set -> PutState, Delete -> DelState,
	Iterator -> GetStateByRange.

Chaves em hex: o Cosmos SDK usa bytes arbitrários como chave, mas o Fabric
exige texto (por causa do CouchDB). Cada chave vira hex antes de ir para o
stub. Como o hex preserva a ordem dos bytes, a iteração ordenada continua
funcionando.

pending: o GetState do Fabric devolve o valor do ledger, e não o que a
própria transação acabou de escrever. O mapa pending guarda as escritas da
transação atual, para que um Get logo depois de um Set veja o valor novo.
*/
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

// FabricDB implementa dbm.DB sobre o WorldState do Fabric (ver o topo do
// arquivo).
type FabricDB struct {
	stub    shim.ChaincodeStubInterface
	pending map[string][]byte // chave hex-encoded -> valor; nil = deletado
}

var _ dbm.DB = (*FabricDB)(nil)

// NewFabricDB cria o banco em cima do stub da transação atual.
func NewFabricDB(stub shim.ChaincodeStubInterface) *FabricDB {
	return &FabricDB{stub: stub, pending: make(map[string][]byte)}
}

// encodeKey converte a chave para hex (formato aceito pelo Fabric).
func encodeKey(key []byte) string {
	return hex.EncodeToString(key)
}

// decodeKey converte uma chave hex de volta para bytes.
func decodeKey(key string) []byte {
	bz, err := hex.DecodeString(key)
	if err != nil {
		panic(err)
	}
	return bz
}

// Get lê uma chave: primeiro nas escritas desta transação (pending), depois no
// WorldState.
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

// Has devolve true se a chave existe.
func (db *FabricDB) Has(key []byte) (bool, error) {
	v, err := db.Get(key)
	if err != nil {
		return false, err
	}
	return v != nil, nil
}

// Set grava no WorldState (PutState) e guarda o valor em pending.
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

// SetSync é igual ao Set (o Fabric não tem escrita síncrona separada).
func (db *FabricDB) SetSync(key, value []byte) error {
	return db.Set(key, value)
}

// Delete apaga do WorldState (DelState) e marca a chave como apagada em
// pending.
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

// DeleteSync é igual ao Delete.
func (db *FabricDB) DeleteSync(key []byte) error {
	return db.Delete(key)
}

// Iterator percorre as chaves de [start, end) em ordem crescente. Como o hex
// preserva a ordem, o intervalo [hex(start), hex(end)) do GetStateByRange é o
// mesmo intervalo em bytes.
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

// ReverseIterator é igual ao Iterator, mas em ordem decrescente.
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

// Close não tem o que fechar: o stub pertence à transação.
func (db *FabricDB) Close() error { return nil }

// NewBatch cria um lote de escritas que só é aplicado no Write.
func (db *FabricDB) NewBatch() dbm.Batch {
	return &fabricBatch{db: db}
}

// NewBatchWithSize é igual ao NewBatch, reservando espaço para size operações.
func (db *FabricDB) NewBatchWithSize(size int) dbm.Batch {
	return &fabricBatch{db: db, ops: make([]batchOp, 0, size)}
}

// Print não é implementado.
func (db *FabricDB) Print() error {
	return errors.New("fabricstore: Print not implemented")
}

// Stats não tem estatísticas e devolve um mapa vazio.
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

// Set enfileira uma escrita no lote.
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

// Delete enfileira uma remoção no lote.
func (b *fabricBatch) Delete(key []byte) error {
	if len(key) == 0 {
		return errKeyEmpty
	}
	b.ops = append(b.ops, batchOp{del: true, key: key})
	return nil
}

// Write aplica as operações do lote, em ordem, no FabricDB.
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

// WriteSync é igual ao Write.
func (b *fabricBatch) WriteSync() error { return b.Write() }

// Close descarta as operações que ainda não foram aplicadas.
func (b *fabricBatch) Close() error {
	b.ops = nil
	return nil
}

// GetByteSize soma o tamanho das chaves e valores enfileirados.
func (b *fabricBatch) GetByteSize() (int, error) {
	n := 0
	for _, op := range b.ops {
		n += len(op.key) + len(op.value)
	}
	return n, nil
}

// fabricIterator adapta o iterador do Fabric (que só anda para frente) ao
// dbm.Iterator. Os itens ficam todos em memória, o que permite iterar ao
// contrário; é aceitável para o volume de dados de um light client IBC.
type fabricIterator struct {
	items   []kvItem
	current int
}

type kvItem struct {
	key   []byte
	value []byte
}

var _ dbm.Iterator = (*fabricIterator)(nil)

// newIterator lê todo o resultado do GetStateByRange para a memória,
// decodificando as chaves hex, e inverte a lista se for iteração reversa (o
// Fabric não itera ao contrário).
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

// Domain não guarda o intervalo e devolve nil.
func (it *fabricIterator) Domain() (start, end []byte) { return nil, nil }

// Valid devolve true enquanto houver item na posição atual.
func (it *fabricIterator) Valid() bool {
	return it.current >= 0 && it.current < len(it.items)
}

// Next avança para o próximo item.
func (it *fabricIterator) Next() {
	it.current++
}

// Key devolve a chave do item atual.
func (it *fabricIterator) Key() []byte {
	return it.items[it.current].key
}

// Value devolve o valor do item atual.
func (it *fabricIterator) Value() []byte {
	return it.items[it.current].value
}

// Error devolve nil: o iterador não acumula erros.
func (it *fabricIterator) Error() error { return nil }

// Close não tem o que liberar.
func (it *fabricIterator) Close() error { return nil }
