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

func newMockStub() *mockStub {
	return &mockStub{state: make(map[string][]byte)}
}

func (m *mockStub) GetState(key string) ([]byte, error) {
	return m.state[key], nil
}

func (m *mockStub) GetMultipleStates(keys ...string) ([][]byte, error) {
	out := make([][]byte, len(keys))
	for i, k := range keys {
		out[i] = m.state[k]
	}
	return out, nil
}

func (m *mockStub) PutState(key string, value []byte) error {
	m.state[key] = value
	return nil
}

func (m *mockStub) DelState(key string) error {
	delete(m.state, key)
	return nil
}

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

// GetArgs/GetStringArgs/GetFunctionAndParameters/GetArgsSlice: cc_ibc.go
// nunca invoca funções via nome+string args (contractapi resolve tudo
// via reflection nos métodos do SmartContract, não usa GetArgs) - sem
// uso real nestes testes.
func (m *mockStub) GetArgs() [][]byte                            { return nil }
func (m *mockStub) GetStringArgs() []string                      { return nil }
func (m *mockStub) GetFunctionAndParameters() (string, []string) { return "", nil }
func (m *mockStub) GetArgsSlice() ([]byte, error)                { return nil, nil }
func (m *mockStub) GetTxID() string                              { return "mock-tx" }
func (m *mockStub) GetChannelID() string                         { return "mock-channel" }
func (m *mockStub) GetCreator() ([]byte, error)                  { return nil, nil }
func (m *mockStub) GetTransient() (map[string][]byte, error)     { return nil, nil }
func (m *mockStub) GetBinding() ([]byte, error)                  { return nil, nil }
func (m *mockStub) GetDecorations() map[string][]byte            { return nil }
func (m *mockStub) GetSignedProposal() (*peer.SignedProposal, error) {
	return nil, nil
}
func (m *mockStub) GetTxTimestamp() (*timestamppb.Timestamp, error) {
	return timestamppb.Now(), nil
}
func (m *mockStub) SetEvent(name string, payload []byte) error { return nil }
func (m *mockStub) StartWriteBatch()                           {}
func (m *mockStub) FinishWriteBatch() error                    { return nil }

func (m *mockStub) InvokeChaincode(chaincodeName string, args [][]byte, channel string) *peer.Response {
	return &peer.Response{Status: 500, Message: errMockNotImplemented.Error()}
}
func (m *mockStub) SetStateValidationParameter(key string, ep []byte) error {
	return errMockNotImplemented
}
func (m *mockStub) GetStateValidationParameter(key string) ([]byte, error) {
	return nil, errMockNotImplemented
}
func (m *mockStub) GetStateByRangeWithPagination(startKey, endKey string, pageSize int32, bookmark string) (shim.StateQueryIteratorInterface, *peer.QueryResponseMetadata, error) {
	return nil, nil, errMockNotImplemented
}
func (m *mockStub) GetStateByPartialCompositeKey(objectType string, keys []string) (shim.StateQueryIteratorInterface, error) {
	return nil, errMockNotImplemented
}
func (m *mockStub) GetStateByPartialCompositeKeyWithPagination(objectType string, keys []string, pageSize int32, bookmark string) (shim.StateQueryIteratorInterface, *peer.QueryResponseMetadata, error) {
	return nil, nil, errMockNotImplemented
}
func (m *mockStub) GetAllStatesCompositeKeyWithPagination(pageSize int32, bookmark string) (shim.StateQueryIteratorInterface, *peer.QueryResponseMetadata, error) {
	return nil, nil, errMockNotImplemented
}
func (m *mockStub) CreateCompositeKey(objectType string, attributes []string) (string, error) {
	return "", errMockNotImplemented
}
func (m *mockStub) SplitCompositeKey(compositeKey string) (string, []string, error) {
	return "", nil, errMockNotImplemented
}
func (m *mockStub) GetQueryResult(query string) (shim.StateQueryIteratorInterface, error) {
	return nil, errMockNotImplemented
}
func (m *mockStub) GetQueryResultWithPagination(query string, pageSize int32, bookmark string) (shim.StateQueryIteratorInterface, *peer.QueryResponseMetadata, error) {
	return nil, nil, errMockNotImplemented
}
func (m *mockStub) GetHistoryForKey(key string) (shim.HistoryQueryIteratorInterface, error) {
	return nil, errMockNotImplemented
}
func (m *mockStub) GetPrivateData(collection, key string) ([]byte, error) {
	return nil, errMockNotImplemented
}
func (m *mockStub) GetMultiplePrivateData(collection string, keys ...string) ([][]byte, error) {
	return nil, errMockNotImplemented
}
func (m *mockStub) GetPrivateDataHash(collection, key string) ([]byte, error) {
	return nil, errMockNotImplemented
}
func (m *mockStub) PutPrivateData(collection string, key string, value []byte) error {
	return errMockNotImplemented
}
func (m *mockStub) DelPrivateData(collection, key string) error   { return errMockNotImplemented }
func (m *mockStub) PurgePrivateData(collection, key string) error { return errMockNotImplemented }
func (m *mockStub) SetPrivateDataValidationParameter(collection, key string, ep []byte) error {
	return errMockNotImplemented
}
func (m *mockStub) GetPrivateDataValidationParameter(collection, key string) ([]byte, error) {
	return nil, errMockNotImplemented
}
func (m *mockStub) GetPrivateDataByRange(collection, startKey, endKey string) (shim.StateQueryIteratorInterface, error) {
	return nil, errMockNotImplemented
}
func (m *mockStub) GetPrivateDataByPartialCompositeKey(collection, objectType string, keys []string) (shim.StateQueryIteratorInterface, error) {
	return nil, errMockNotImplemented
}
func (m *mockStub) GetPrivateDataQueryResult(collection, query string) (shim.StateQueryIteratorInterface, error) {
	return nil, errMockNotImplemented
}

type mockIterator struct {
	items []*queryresult.KV
	pos   int
}

var _ shim.StateQueryIteratorInterface = (*mockIterator)(nil)

func (it *mockIterator) HasNext() bool { return it.pos < len(it.items) }

func (it *mockIterator) Next() (*queryresult.KV, error) {
	if !it.HasNext() {
		return nil, errors.New("mockIterator: sem próximo item")
	}
	kv := it.items[it.pos]
	it.pos++
	return kv, nil
}

func (it *mockIterator) Close() error { return nil }
