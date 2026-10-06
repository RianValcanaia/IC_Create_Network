/*
mockStub: um stub de chaincode falso, em memória, para os testes.

Implementa de verdade só o que o fabricstore usa (GetState, PutState,
DelState e GetStateByRange, com as chaves em ordem). Os outros métodos existem
só para satisfazer a interface shim.ChaincodeStubInterface: devolvem um valor
fixo ou errMockNotImplemented.
*/
package ibcadapter_test

import (
	"errors"
	"sort"

	"github.com/hyperledger/fabric-chaincode-go/v2/shim"
	"github.com/hyperledger/fabric-protos-go-apiv2/ledger/queryresult"
	"github.com/hyperledger/fabric-protos-go-apiv2/peer"
	"google.golang.org/protobuf/types/known/timestamppb"
)

var errMockNotImplemented = errors.New("mockStub: método não implementado no mock de teste")

type mockStub struct {
	state map[string][]byte
}

var _ shim.ChaincodeStubInterface = (*mockStub)(nil)

// newMockStub cria o stub com o estado vazio.
func newMockStub() *mockStub {
	return &mockStub{state: make(map[string][]byte)}
}

// GetState lê a chave do mapa.
func (m *mockStub) GetState(key string) ([]byte, error) {
	return m.state[key], nil
}

// GetMultipleStates lê várias chaves de uma vez.
func (m *mockStub) GetMultipleStates(keys ...string) ([][]byte, error) {
	out := make([][]byte, len(keys))
	for i, k := range keys {
		out[i] = m.state[k]
	}
	return out, nil
}

// PutState grava a chave no mapa.
func (m *mockStub) PutState(key string, value []byte) error {
	m.state[key] = value
	return nil
}

// DelState apaga a chave do mapa.
func (m *mockStub) DelState(key string) error {
	delete(m.state, key)
	return nil
}

// GetStateByRange devolve as chaves de [startKey, endKey) em ordem, como o
// Fabric faz.
func (m *mockStub) GetStateByRange(startKey, endKey string) (shim.StateQueryIteratorInterface, error) {
	keys := make([]string, 0, len(m.state))
	for k := range m.state {
		if startKey != "" && k < startKey {
			continue
		}
		if endKey != "" && k >= endKey {
			continue
		}
		keys = append(keys, k)
	}
	sort.Strings(keys)
	items := make([]*queryresult.KV, 0, len(keys))
	for _, k := range keys {
		items = append(items, &queryresult.KV{Key: k, Value: m.state[k]})
	}
	return &mockIterator{items: items}, nil
}

// GetArgs não é usado pelos testes: devolve um valor fixo.
func (m *mockStub) GetArgs() [][]byte { return nil }

// GetStringArgs não é usado pelos testes: devolve um valor fixo.
func (m *mockStub) GetStringArgs() []string { return nil }

// GetFunctionAndParameters não é usado pelos testes: devolve um valor fixo.
func (m *mockStub) GetFunctionAndParameters() (string, []string) { return "", nil }

// GetArgsSlice não é usado pelos testes: devolve um valor fixo.
func (m *mockStub) GetArgsSlice() ([]byte, error) { return nil, nil }

// GetTxID não é usado pelos testes: devolve um valor fixo.
func (m *mockStub) GetTxID() string { return "mock-tx" }

// GetChannelID não é usado pelos testes: devolve um valor fixo.
func (m *mockStub) GetChannelID() string { return "mock-channel" }

// GetCreator não é usado pelos testes: devolve um valor fixo.
func (m *mockStub) GetCreator() ([]byte, error) { return nil, nil }

// GetTransient não é usado pelos testes: devolve um valor fixo.
func (m *mockStub) GetTransient() (map[string][]byte, error) { return nil, nil }

// GetBinding não é usado pelos testes: devolve um valor fixo.
func (m *mockStub) GetBinding() ([]byte, error) { return nil, nil }

// GetDecorations não é usado pelos testes: devolve um valor fixo.
func (m *mockStub) GetDecorations() map[string][]byte { return nil }

// GetSignedProposal não é usado pelos testes: devolve um valor fixo.
func (m *mockStub) GetSignedProposal() (*peer.SignedProposal, error) {
	return nil, nil
}

// GetTxTimestamp não é usado pelos testes: devolve um valor fixo.
func (m *mockStub) GetTxTimestamp() (*timestamppb.Timestamp, error) {
	return timestamppb.Now(), nil
}

// SetEvent não é usado pelos testes: devolve um valor fixo.
func (m *mockStub) SetEvent(name string, payload []byte) error { return nil }

// StartWriteBatch não é usado pelos testes: devolve um valor fixo.
func (m *mockStub) StartWriteBatch() {}

// FinishWriteBatch não é usado pelos testes: devolve um valor fixo.
func (m *mockStub) FinishWriteBatch() error { return nil }

// InvokeChaincode não é usado pelos testes: devolve errMockNotImplemented.
func (m *mockStub) InvokeChaincode(chaincodeName string, args [][]byte, channel string) *peer.Response {
	return &peer.Response{Status: 500, Message: errMockNotImplemented.Error()}
}

// SetStateValidationParameter não é usado pelos testes: devolve
// errMockNotImplemented.
func (m *mockStub) SetStateValidationParameter(key string, ep []byte) error {
	return errMockNotImplemented
}

// GetStateValidationParameter não é usado pelos testes: devolve
// errMockNotImplemented.
func (m *mockStub) GetStateValidationParameter(key string) ([]byte, error) {
	return nil, errMockNotImplemented
}

// GetStateByRangeWithPagination não é usado pelos testes: devolve
// errMockNotImplemented.
func (m *mockStub) GetStateByRangeWithPagination(startKey, endKey string, pageSize int32, bookmark string) (shim.StateQueryIteratorInterface, *peer.QueryResponseMetadata, error) {
	return nil, nil, errMockNotImplemented
}

// GetStateByPartialCompositeKey não é usado pelos testes: devolve
// errMockNotImplemented.
func (m *mockStub) GetStateByPartialCompositeKey(objectType string, keys []string) (shim.StateQueryIteratorInterface, error) {
	return nil, errMockNotImplemented
}

// GetStateByPartialCompositeKeyWithPagination não é usado pelos testes:
// devolve errMockNotImplemented.
func (m *mockStub) GetStateByPartialCompositeKeyWithPagination(objectType string, keys []string, pageSize int32, bookmark string) (shim.StateQueryIteratorInterface, *peer.QueryResponseMetadata, error) {
	return nil, nil, errMockNotImplemented
}

// GetAllStatesCompositeKeyWithPagination não é usado pelos testes: devolve
// errMockNotImplemented.
func (m *mockStub) GetAllStatesCompositeKeyWithPagination(pageSize int32, bookmark string) (shim.StateQueryIteratorInterface, *peer.QueryResponseMetadata, error) {
	return nil, nil, errMockNotImplemented
}

// CreateCompositeKey não é usado pelos testes: devolve errMockNotImplemented.
func (m *mockStub) CreateCompositeKey(objectType string, attributes []string) (string, error) {
	return "", errMockNotImplemented
}

// SplitCompositeKey não é usado pelos testes: devolve errMockNotImplemented.
func (m *mockStub) SplitCompositeKey(compositeKey string) (string, []string, error) {
	return "", nil, errMockNotImplemented
}

// GetQueryResult não é usado pelos testes: devolve errMockNotImplemented.
func (m *mockStub) GetQueryResult(query string) (shim.StateQueryIteratorInterface, error) {
	return nil, errMockNotImplemented
}

// GetQueryResultWithPagination não é usado pelos testes: devolve
// errMockNotImplemented.
func (m *mockStub) GetQueryResultWithPagination(query string, pageSize int32, bookmark string) (shim.StateQueryIteratorInterface, *peer.QueryResponseMetadata, error) {
	return nil, nil, errMockNotImplemented
}

// GetHistoryForKey não é usado pelos testes: devolve errMockNotImplemented.
func (m *mockStub) GetHistoryForKey(key string) (shim.HistoryQueryIteratorInterface, error) {
	return nil, errMockNotImplemented
}

// GetPrivateData não é usado pelos testes: devolve errMockNotImplemented.
func (m *mockStub) GetPrivateData(collection, key string) ([]byte, error) {
	return nil, errMockNotImplemented
}

// GetMultiplePrivateData não é usado pelos testes: devolve
// errMockNotImplemented.
func (m *mockStub) GetMultiplePrivateData(collection string, keys ...string) ([][]byte, error) {
	return nil, errMockNotImplemented
}

// GetPrivateDataHash não é usado pelos testes: devolve errMockNotImplemented.
func (m *mockStub) GetPrivateDataHash(collection, key string) ([]byte, error) {
	return nil, errMockNotImplemented
}

// PutPrivateData não é usado pelos testes: devolve errMockNotImplemented.
func (m *mockStub) PutPrivateData(collection string, key string, value []byte) error {
	return errMockNotImplemented
}

// DelPrivateData não é usado pelos testes: devolve errMockNotImplemented.
func (m *mockStub) DelPrivateData(collection, key string) error { return errMockNotImplemented }

// PurgePrivateData não é usado pelos testes: devolve errMockNotImplemented.
func (m *mockStub) PurgePrivateData(collection, key string) error { return errMockNotImplemented }

// SetPrivateDataValidationParameter não é usado pelos testes: devolve
// errMockNotImplemented.
func (m *mockStub) SetPrivateDataValidationParameter(collection, key string, ep []byte) error {
	return errMockNotImplemented
}

// GetPrivateDataValidationParameter não é usado pelos testes: devolve
// errMockNotImplemented.
func (m *mockStub) GetPrivateDataValidationParameter(collection, key string) ([]byte, error) {
	return nil, errMockNotImplemented
}

// GetPrivateDataByRange não é usado pelos testes: devolve
// errMockNotImplemented.
func (m *mockStub) GetPrivateDataByRange(collection, startKey, endKey string) (shim.StateQueryIteratorInterface, error) {
	return nil, errMockNotImplemented
}

// GetPrivateDataByPartialCompositeKey não é usado pelos testes: devolve
// errMockNotImplemented.
func (m *mockStub) GetPrivateDataByPartialCompositeKey(collection, objectType string, keys []string) (shim.StateQueryIteratorInterface, error) {
	return nil, errMockNotImplemented
}

// GetPrivateDataQueryResult não é usado pelos testes: devolve
// errMockNotImplemented.
func (m *mockStub) GetPrivateDataQueryResult(collection, query string) (shim.StateQueryIteratorInterface, error) {
	return nil, errMockNotImplemented
}

type mockIterator struct {
	items []*queryresult.KV
	pos   int
}

var _ shim.StateQueryIteratorInterface = (*mockIterator)(nil)

// HasNext devolve true se ainda há itens.
func (it *mockIterator) HasNext() bool { return it.pos < len(it.items) }

// Next devolve o item atual e avança.
func (it *mockIterator) Next() (*queryresult.KV, error) {
	if !it.HasNext() {
		return nil, errors.New("mockIterator: sem próximo item")
	}
	kv := it.items[it.pos]
	it.pos++
	return kv, nil
}

// Close não tem o que liberar.
func (it *mockIterator) Close() error { return nil }
