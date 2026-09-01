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

// MultiStore é um storetypes.MultiStore mínimo sobre o FabricDB: cada
// StoreKey vira um dbadapter.Store isolado por um prefixo próprio
// (dbm.NewPrefixDB) sobre a mesma FabricDB (mesmo WorldState do Fabric).
//
// Sem versionamento/IAVL/commit hash: o Fabric já garante integridade/commitment via
// endosso + ledger; não faz sentido duplicar isso com uma Merkle tree
// Cosmos-side que nunca é consultada por ninguém (o client fabric-msp do
// lado Cosmos, verifica via VerifyEndorsedCommitment contra o
// read-write set do Fabric, não contra um AppHash/IAVL root daqui).
// Mesma técnica (não a versão) do fork antigo, chaincode/store/store.go.
type MultiStore struct {
	db     *FabricDB
	stores map[storetypes.StoreKey]storetypes.KVStore

	traceWriter  io.Writer
	traceContext storetypes.TraceContext
}

var _ storetypes.MultiStore = (*MultiStore)(nil)

// NewMultiStore monta um KVStore por StoreKey persistente (dbadapter.Store
// sobre um prefixo próprio da FabricDB, mesmo WorldState do Fabric) e um
// KVStore em RAM pura (mem.NewStore()) por MemoryStoreKey - mesma
// distinção que rootmulti.Store faz entre StoreTypeDB e StoreTypeMemory.
// Memória em RAM é apropriada aqui porque cada invocação do chaincode já
// recria o processo Go do zero (nada precisa persistir entre invocações
// nesses stores - é exatamente o uso que o capability keeper já dá ao
// seu MemoryStoreKey, mesmo fora deste adaptador).
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

// StoreByName monta o mesmo dbadapter.Store (prefixo "s/k:<name>/" sobre
// a FabricDB) que NewMultiStore usa internamente pra montar cada
// StoreKey - exportado pra quem precisa ler/escrever direto num store
// por nome sem passar pela identidade de ponteiro do storetypes.StoreKey
// (ex.: cc_ibc.go, ProveCommitment/AdvanceSequence, só precisam
// do KVStore "ibc" cru, não dos keepers do ibc-go inteiros).
func StoreByName(db *FabricDB, name string) storetypes.KVStore {
	return dbadapter.Store{DB: dbm.NewPrefixDB(db, []byte("s/k:"+name+"/"))}
}

func (ms *MultiStore) GetStoreType() storetypes.StoreType {
	return storetypes.StoreTypeDB
}

func (ms *MultiStore) CacheWrap() storetypes.CacheWrap {
	return ms.CacheMultiStore().(storetypes.CacheWrap)
}

func (ms *MultiStore) CacheWrapWithTrace(_ io.Writer, _ storetypes.TraceContext) storetypes.CacheWrap {
	return ms.CacheWrap()
}

func (ms *MultiStore) CacheMultiStore() storetypes.CacheMultiStore {
	stores := make(map[storetypes.StoreKey]storetypes.CacheWrapper, len(ms.stores))
	keysByName := make(map[string]storetypes.StoreKey, len(ms.stores))
	for k, v := range ms.stores {
		stores[k] = v
		keysByName[k.Name()] = k
	}
	return cachemulti.NewStore(ms.db, stores, keysByName, ms.traceWriter, ms.traceContext)
}

// CacheMultiStoreWithVersion: não há versionamento histórico aqui (só
// existe "o estado atual do WorldState do Fabric") - qualquer version !=
// 0 (o "latest" implícito) é erro explícito, mesma postura de
// ExportMetadata no-op já documentada no hb-qbft/fabric-msp.
func (ms *MultiStore) CacheMultiStoreWithVersion(version int64) (storetypes.CacheMultiStore, error) {
	if version != 0 {
		return nil, fmt.Errorf("fabricstore: versioned queries not supported (got version %d), only the current Fabric world state is available", version)
	}
	return ms.CacheMultiStore(), nil
}

func (ms *MultiStore) GetStore(key storetypes.StoreKey) storetypes.Store {
	store, ok := ms.stores[key]
	if !ok {
		panic(fmt.Sprintf("fabricstore: store does not exist for key: %s", key))
	}
	return store
}

func (ms *MultiStore) GetKVStore(key storetypes.StoreKey) storetypes.KVStore {
	store, ok := ms.stores[key]
	if !ok {
		panic(fmt.Sprintf("fabricstore: store does not exist for key: %s", key))
	}
	return store
}

func (ms *MultiStore) TracingEnabled() bool {
	return ms.traceWriter != nil
}

func (ms *MultiStore) SetTracer(w io.Writer) storetypes.MultiStore {
	ms.traceWriter = w
	return ms
}

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

func (ms *MultiStore) LatestVersion() int64 {
	return 0
}
