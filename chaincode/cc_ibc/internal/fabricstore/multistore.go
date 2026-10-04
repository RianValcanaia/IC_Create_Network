/*
MultiStore: o conjunto de stores do Cosmos SDK em cima do FabricDB.

Os keepers do ibc-go pedem uma store por nome (StoreKey). Aqui cada nome vira
uma "gaveta" separada dentro do mesmo WorldState, isolada por prefixo: a
store "ibc" grava suas chaves em s/k:ibc/... e a "capability" em
s/k:capability/.... As stores de memória (MemoryStoreKey) ficam só na RAM do
processo.

Diferente de um nó Cosmos, não há árvore IAVL, versões nem app hash: a
integridade do estado do Fabric vem do endosso e do ledger. O light client
fabric-msp do outro lado verifica o read-write set endossado, e não uma
prova Merkle.
*/
package fabricstore

import (
	"fmt"
	"io"

	"cosmossdk.io/store/cachemulti"
	"cosmossdk.io/store/dbadapter"
	"cosmossdk.io/store/mem"
	storetypes "cosmossdk.io/store/types"
	dbm "github.com/cosmos/cosmos-db"
)

// MultiStore guarda uma KVStore por StoreKey, todas sobre o mesmo FabricDB
// (ver o topo do arquivo).
type MultiStore struct {
	db     *FabricDB
	stores map[storetypes.StoreKey]storetypes.KVStore

	traceWriter  io.Writer
	traceContext storetypes.TraceContext
}

var _ storetypes.MultiStore = (*MultiStore)(nil)

// NewMultiStore cria uma KVStore persistente (prefixo próprio no FabricDB)
// para cada StoreKey e uma KVStore em RAM para cada MemoryStoreKey. A RAM
// basta porque cada chamada do chaincode recomeça do zero, e é isso que o
// capability keeper espera da store de memória.
func NewMultiStore(db *FabricDB, keys map[string]storetypes.StoreKey, memKeys map[string]*storetypes.MemoryStoreKey) *MultiStore {
	ms := &MultiStore{
		db:     db,
		stores: make(map[storetypes.StoreKey]storetypes.KVStore, len(keys)+len(memKeys)),
	}
	for name, key := range keys {
		ms.stores[key] = StoreByName(db, name)
	}
	for _, key := range memKeys {
		ms.stores[key] = mem.NewStore()
	}
	return ms
}

// StoreByName devolve a KVStore de uma store pelo nome (prefixo s/k:<nome>/).
// O ProveCommitment usa direto, porque só precisa da store ibc crua.
func StoreByName(db *FabricDB, name string) storetypes.KVStore {
	return dbadapter.Store{DB: dbm.NewPrefixDB(db, []byte("s/k:"+name+"/"))}
}

// GetStoreType devolve o tipo da store raiz (StoreTypeDB).
func (ms *MultiStore) GetStoreType() storetypes.StoreType {
	return storetypes.StoreTypeDB
}

// CacheWrap devolve uma cópia em cache do multistore (ver CacheMultiStore).
func (ms *MultiStore) CacheWrap() storetypes.CacheWrap {
	return ms.CacheMultiStore().(storetypes.CacheWrap)
}

// CacheWrapWithTrace é igual ao CacheWrap; o trace é ignorado.
func (ms *MultiStore) CacheWrapWithTrace(_ io.Writer, _ storetypes.TraceContext) storetypes.CacheWrap {
	return ms.CacheWrap()
}

// CacheMultiStore cria um multistore em cache: as escritas ficam numa camada
// temporária e só chegam ao FabricDB quando confirmadas (Write). O ibc-go usa
// isso para descartar o efeito de uma operação que falhou.
func (ms *MultiStore) CacheMultiStore() storetypes.CacheMultiStore {
	stores := make(map[storetypes.StoreKey]storetypes.CacheWrapper, len(ms.stores))
	keysByName := make(map[string]storetypes.StoreKey, len(ms.stores))
	for k, v := range ms.stores {
		stores[k] = v
		keysByName[k.Name()] = k
	}
	return cachemulti.NewStore(ms.db, stores, keysByName, ms.traceWriter, ms.traceContext)
}

// CacheMultiStoreWithVersion só aceita a versão 0: existe apenas o estado
// atual do Fabric, sem histórico.
func (ms *MultiStore) CacheMultiStoreWithVersion(version int64) (storetypes.CacheMultiStore, error) {
	if version != 0 {
		return nil, fmt.Errorf("fabricstore: versioned queries not supported (got version %d), only the current Fabric world state is available", version)
	}
	return ms.CacheMultiStore(), nil
}

// GetStore devolve a store de uma StoreKey (panic se não existir).
func (ms *MultiStore) GetStore(key storetypes.StoreKey) storetypes.Store {
	store, ok := ms.stores[key]
	if !ok {
		panic(fmt.Sprintf("fabricstore: store does not exist for key: %s", key))
	}
	return store
}

// GetKVStore é igual ao GetStore, já como KVStore.
func (ms *MultiStore) GetKVStore(key storetypes.StoreKey) storetypes.KVStore {
	store, ok := ms.stores[key]
	if !ok {
		panic(fmt.Sprintf("fabricstore: store does not exist for key: %s", key))
	}
	return store
}

// TracingEnabled devolve true se há um writer de trace configurado.
func (ms *MultiStore) TracingEnabled() bool {
	return ms.traceWriter != nil
}

// SetTracer configura o writer de trace.
func (ms *MultiStore) SetTracer(w io.Writer) storetypes.MultiStore {
	ms.traceWriter = w
	return ms
}

// SetTracingContext junta o contexto de trace informado ao atual.
func (ms *MultiStore) SetTracingContext(tc storetypes.TraceContext) storetypes.MultiStore {
	if ms.traceContext != nil {
		for k, v := range tc {
			ms.traceContext[k] = v
		}
	} else {
		ms.traceContext = tc
	}
	return ms
}

// LatestVersion devolve sempre 0: não há versionamento.
func (ms *MultiStore) LatestVersion() int64 {
	return 0
}
