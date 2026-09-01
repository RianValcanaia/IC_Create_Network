// cc_ibc é o chaincode CCaaS que expõe o núcleo do ibc-go v8.2.1
// como transações Fabric
//
// Cada transação recebe/devolve o Msg/Response correspondente do ibc-go
// serializado em protobuf binário, base64-encoded. O Keeper (internal/ibcadapter)
// é reconstruído do zero a cada invocação, sobre o WorldState atual do
// stub.
package main

import (
	"encoding/base64"
	"fmt"
	stdlog "log"
	"os"
	"strconv"
	"time"

	"cosmossdk.io/log"

	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	"github.com/cosmos/cosmos-sdk/codec"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"

	clienttypes "github.com/cosmos/ibc-go/v8/modules/core/02-client/types"
	connectiontypes "github.com/cosmos/ibc-go/v8/modules/core/03-connection/types"
	channeltypes "github.com/cosmos/ibc-go/v8/modules/core/04-channel/types"
	ibctm "github.com/cosmos/ibc-go/v8/modules/light-clients/07-tendermint"

	"github.com/hyperledger/fabric-chaincode-go/v2/shim"
	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"

	fabricmsp "github.com/rianvalcanaia/cosmos-yui-app/lightclients/fabric-msp"

	"github.com/rianvalcanaia/cc_ibc/internal/fabricstore"
	"github.com/rianvalcanaia/cc_ibc/internal/ibcadapter"
)

// FabricChainID é o "chain-id" que este adaptador declara pra si mesmo no
// sdk.Context - só usado internamente (logs, ctx.ChainID()); não afeta a
// verificação do 07-tendermint, que valida contra o chain-id real dentro
// do próprio Header/ClientState assinado por cosmos_chain_0.
const FabricChainID = "fabric-msp-channel-all"

func newCodec() *codec.ProtoCodec {
	registry := codectypes.NewInterfaceRegistry()
	ibctm.RegisterInterfaces(registry)
	fabricmsp.RegisterInterfaces(registry)
	return codec.NewProtoCodec(registry)
}

var cdc = newCodec()

// SmartContract expõe o núcleo do ibc-go como transações Fabric.
type SmartContract struct {
	contractapi.Contract
}

func newKeeper(stub shim.ChaincodeStubInterface) (*ibcadapter.Keeper, sdk.Context) {
	db := fabricstore.NewFabricDB(stub)
	keys := ibcadapter.StoreKeys()
	memKeys := ibcadapter.MemStoreKeys()
	ms := fabricstore.NewMultiStore(db, keys, memKeys)

	seqValue, seqTimestamp := currentSequence(stub)
	k := ibcadapter.NewKeeper(cdc, ms, keys, memKeys, seqValue, seqTimestamp, db)
	k.SetupRouter()

	ctx := sdk.NewContext(ms, cmtproto.Header{ChainID: FabricChainID, Height: int64(seqValue) + 1, Time: time.Now()}, false, log.NewNopLogger())

	k.InitCapabilities(ctx)

	if err := k.BindTransferPort(ctx); err != nil {
		panic(fmt.Errorf("cc_ibc: failed to bind transfer port: %w", err))
	}
	return k, ctx
}

func currentSequence(stub shim.ChaincodeStubInterface) (value uint64, timestamp int64) {
	bz, err := stub.GetState(SequenceCommitmentKey)
	if err != nil || len(bz) == 0 {
		return 0, 0
	}
	value, timestamp, err = decodeSequenceValue(bz)
	if err != nil {
		return 0, 0
	}
	return value, timestamp
}

func decodeArg[T any](b64 string, msg *T) error {
	bz, err := base64.StdEncoding.DecodeString(b64)
	if err != nil {
		return fmt.Errorf("cc_ibc: invalid base64 argument: %w", err)
	}
	if m, ok := any(msg).(interface{ Reset() }); ok {
		m.Reset()
	}
	if unmarshaler, ok := any(msg).(codecUnmarshaler); ok {
		return cdc.Unmarshal(bz, unmarshaler)
	}
	return fmt.Errorf("cc_ibc: type %T is not a proto message", msg)
}

type codecUnmarshaler interface {
	Reset()
	String() string
	ProtoMessage()
}

func encodeResp(resp interface{ Marshal() ([]byte, error) }) (string, error) {
	bz, err := resp.Marshal()
	if err != nil {
		return "", err
	}
	return base64.StdEncoding.EncodeToString(bz), nil
}

// CreateClient recebe um clienttypes.MsgCreateClient serializado
// (protobuf, base64) e devolve o MsgCreateClientResponse no mesmo
// formato.
// CreateClient devolve o client-id recém-criado como string simples
// o relayer precisa saber esse ID pra continuar o handshake (ConnectionOpenInit
// referencia o client acabado de criar)
func (s *SmartContract) CreateClient(ctx contractapi.TransactionContextInterface, msgB64 string) (string, error) {
	var msg clienttypes.MsgCreateClient
	if err := decodeArg(msgB64, &msg); err != nil {
		return "", err
	}
	clientState, err := clienttypes.UnpackClientState(msg.ClientState)
	if err != nil {
		return "", err
	}
	k, sdkCtx := newKeeper(ctx.GetStub())
	if _, err := k.CreateClient(sdkCtx, &msg); err != nil {
		return "", err
	}
	seq := k.ClientKeeper.GetNextClientSequence(sdkCtx) - 1
	clientID := clienttypes.FormatClientIdentifier(clientState.ClientType(), seq)
	return clientID, nil
}

func (s *SmartContract) UpdateClient(ctx contractapi.TransactionContextInterface, msgB64 string) (string, error) {
	var msg clienttypes.MsgUpdateClient
	if err := decodeArg(msgB64, &msg); err != nil {
		return "", err
	}
	k, sdkCtx := newKeeper(ctx.GetStub())
	resp, err := k.UpdateClient(sdkCtx, &msg)
	if err != nil {
		return "", err
	}
	return encodeResp(resp)
}

// ConnectionOpenInit/Try devolvem o connection-id recém-criado como
// string simples - mesmo raciocínio de CreateClient acima
// (MsgConnectionOpen{Init,Try}Response reais são vazios no ibc-go,
// GenerateConnectionIdentifier usa GetNextConnectionSequence ANTES de
// incrementar).
func (s *SmartContract) ConnectionOpenInit(ctx contractapi.TransactionContextInterface, msgB64 string) (string, error) {
	var msg connectiontypes.MsgConnectionOpenInit
	if err := decodeArg(msgB64, &msg); err != nil {
		return "", err
	}
	k, sdkCtx := newKeeper(ctx.GetStub())
	if _, err := k.ConnectionOpenInit(sdkCtx, &msg); err != nil {
		return "", err
	}
	seq := k.ConnectionKeeper.GetNextConnectionSequence(sdkCtx) - 1
	return connectiontypes.FormatConnectionIdentifier(seq), nil
}

func (s *SmartContract) ConnectionOpenTry(ctx contractapi.TransactionContextInterface, msgB64 string) (string, error) {
	var msg connectiontypes.MsgConnectionOpenTry
	if err := decodeArg(msgB64, &msg); err != nil {
		return "", err
	}
	k, sdkCtx := newKeeper(ctx.GetStub())
	if _, err := k.ConnectionOpenTry(sdkCtx, &msg); err != nil {
		return "", err
	}
	seq := k.ConnectionKeeper.GetNextConnectionSequence(sdkCtx) - 1
	return connectiontypes.FormatConnectionIdentifier(seq), nil
}

func (s *SmartContract) ConnectionOpenAck(ctx contractapi.TransactionContextInterface, msgB64 string) (string, error) {
	var msg connectiontypes.MsgConnectionOpenAck
	if err := decodeArg(msgB64, &msg); err != nil {
		return "", err
	}
	k, sdkCtx := newKeeper(ctx.GetStub())
	resp, err := k.ConnectionOpenAck(sdkCtx, &msg)
	if err != nil {
		return "", err
	}
	return encodeResp(resp)
}

func (s *SmartContract) ConnectionOpenConfirm(ctx contractapi.TransactionContextInterface, msgB64 string) (string, error) {
	var msg connectiontypes.MsgConnectionOpenConfirm
	if err := decodeArg(msgB64, &msg); err != nil {
		return "", err
	}
	k, sdkCtx := newKeeper(ctx.GetStub())
	resp, err := k.ConnectionOpenConfirm(sdkCtx, &msg)
	if err != nil {
		return "", err
	}
	return encodeResp(resp)
}

func (s *SmartContract) ChannelOpenInit(ctx contractapi.TransactionContextInterface, msgB64 string) (string, error) {
	var msg channeltypes.MsgChannelOpenInit
	if err := decodeArg(msgB64, &msg); err != nil {
		return "", err
	}
	k, sdkCtx := newKeeper(ctx.GetStub())
	resp, err := k.ChannelOpenInit(sdkCtx, &msg)
	if err != nil {
		return "", err
	}
	return encodeResp(resp)
}

func (s *SmartContract) ChannelOpenTry(ctx contractapi.TransactionContextInterface, msgB64 string) (string, error) {
	var msg channeltypes.MsgChannelOpenTry
	if err := decodeArg(msgB64, &msg); err != nil {
		return "", err
	}
	k, sdkCtx := newKeeper(ctx.GetStub())
	resp, err := k.ChannelOpenTry(sdkCtx, &msg)
	if err != nil {
		return "", err
	}
	return encodeResp(resp)
}

func (s *SmartContract) ChannelOpenAck(ctx contractapi.TransactionContextInterface, msgB64 string) (string, error) {
	var msg channeltypes.MsgChannelOpenAck
	if err := decodeArg(msgB64, &msg); err != nil {
		return "", err
	}
	k, sdkCtx := newKeeper(ctx.GetStub())
	resp, err := k.ChannelOpenAck(sdkCtx, &msg)
	if err != nil {
		return "", err
	}
	return encodeResp(resp)
}

func (s *SmartContract) ChannelOpenConfirm(ctx contractapi.TransactionContextInterface, msgB64 string) (string, error) {
	var msg channeltypes.MsgChannelOpenConfirm
	if err := decodeArg(msgB64, &msg); err != nil {
		return "", err
	}
	k, sdkCtx := newKeeper(ctx.GetStub())
	resp, err := k.ChannelOpenConfirm(sdkCtx, &msg)
	if err != nil {
		return "", err
	}
	return encodeResp(resp)
}

func (s *SmartContract) RecvPacket(ctx contractapi.TransactionContextInterface, msgB64 string) (string, error) {
	var msg channeltypes.MsgRecvPacket
	if err := decodeArg(msgB64, &msg); err != nil {
		return "", err
	}
	k, sdkCtx := newKeeper(ctx.GetStub())
	resp, err := k.RecvPacket(sdkCtx, &msg)
	if err != nil {
		return "", err
	}
	return encodeResp(resp)
}

func (s *SmartContract) Acknowledgement(ctx contractapi.TransactionContextInterface, msgB64 string) (string, error) {
	var msg channeltypes.MsgAcknowledgement
	if err := decodeArg(msgB64, &msg); err != nil {
		return "", err
	}
	k, sdkCtx := newKeeper(ctx.GetStub())
	resp, err := k.Acknowledgement(sdkCtx, &msg)
	if err != nil {
		return "", err
	}
	return encodeResp(resp)
}

func (s *SmartContract) Timeout(ctx contractapi.TransactionContextInterface, msgB64 string) (string, error) {
	var msg channeltypes.MsgTimeout
	if err := decodeArg(msgB64, &msg); err != nil {
		return "", err
	}
	k, sdkCtx := newKeeper(ctx.GetStub())
	resp, err := k.Timeout(sdkCtx, &msg)
	if err != nil {
		return "", err
	}
	return encodeResp(resp)
}

// Transfer envia um ICS-20 a partir do Fabric
func (s *SmartContract) Transfer(ctx contractapi.TransactionContextInterface, portID, channelID, denom, amount, sender, receiver string, timeoutRevisionNumber, timeoutRevisionHeight, timeoutTimestamp uint64) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	timeoutHeight := clienttypes.NewHeight(timeoutRevisionNumber, timeoutRevisionHeight)
	seq, err := k.SendTransfer(sdkCtx, portID, channelID, denom, amount, sender, receiver, timeoutHeight, timeoutTimestamp)
	if err != nil {
		return "", err
	}
	return strconv.FormatUint(seq, 10), nil
}

// QueryBalance devolve o saldo de account no denom
func (s *SmartContract) QueryBalance(ctx contractapi.TransactionContextInterface, account, denom string) (string, error) {
	k, _ := newKeeper(ctx.GetStub())
	amount, err := k.Bank.GetBalance(denom, account)
	if err != nil {
		return "", err
	}
	return amount.String(), nil
}

// QueryClientState devolve o ClientState armazenado (protobuf, base64)
// necessário pro relayer montar as próximas mensagens do
// handshake.
func (s *SmartContract) QueryClientState(ctx contractapi.TransactionContextInterface, clientID string) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	cs, found := k.ClientKeeper.GetClientState(sdkCtx, clientID)
	if !found {
		return "", fmt.Errorf("cc_ibc: client %s not found", clientID)
	}
	any, err := clienttypes.PackClientState(cs)
	if err != nil {
		return "", err
	}
	return encodeResp(any)
}

func (s *SmartContract) QueryConnection(ctx contractapi.TransactionContextInterface, connectionID string) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	conn, found := k.ConnectionKeeper.GetConnection(sdkCtx, connectionID)
	if !found {
		return "", fmt.Errorf("cc_ibc: connection %s not found", connectionID)
	}
	return encodeResp(&conn)
}

func (s *SmartContract) QueryChannel(ctx contractapi.TransactionContextInterface, portID, channelID string) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	ch, found := k.ChannelKeeper.GetChannel(sdkCtx, portID, channelID)
	if !found {
		return "", fmt.Errorf("cc_ibc: channel %s/%s not found", portID, channelID)
	}
	return encodeResp(&ch)
}

func (s *SmartContract) QueryClientConsensusState(ctx contractapi.TransactionContextInterface, clientID string, revisionNumber, revisionHeight uint64) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	height := clienttypes.NewHeight(revisionNumber, revisionHeight)
	cs, found := k.ClientKeeper.GetClientConsensusState(sdkCtx, clientID, height)
	if !found {
		return "", fmt.Errorf("cc_ibc: consensus state not found for client %s at %s", clientID, height)
	}
	any, err := clienttypes.PackConsensusState(cs)
	if err != nil {
		return "", err
	}
	return encodeResp(any)
}

func (s *SmartContract) QueryNextSequenceReceive(ctx contractapi.TransactionContextInterface, portID, channelID string) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	seq, found := k.ChannelKeeper.GetNextSequenceRecv(sdkCtx, portID, channelID)
	if !found {
		return "", fmt.Errorf("cc_ibc: next sequence recv not found for %s/%s", portID, channelID)
	}
	return strconv.FormatUint(seq, 10), nil
}

func (s *SmartContract) QueryPacketCommitment(ctx contractapi.TransactionContextInterface, portID, channelID string, sequence uint64) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	commitment := k.ChannelKeeper.GetPacketCommitment(sdkCtx, portID, channelID, sequence)
	if len(commitment) == 0 {
		return "", fmt.Errorf("cc_ibc: packet commitment not found for %s/%s/%d", portID, channelID, sequence)
	}
	return base64.StdEncoding.EncodeToString(commitment), nil
}

func (s *SmartContract) QueryPacketReceipt(ctx contractapi.TransactionContextInterface, portID, channelID string, sequence uint64) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	_, found := k.ChannelKeeper.GetPacketReceipt(sdkCtx, portID, channelID, sequence)
	return strconv.FormatBool(found), nil
}

func (s *SmartContract) QueryPacketAck(ctx contractapi.TransactionContextInterface, portID, channelID string, sequence uint64) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	ack, found := k.ChannelKeeper.GetPacketAcknowledgement(sdkCtx, portID, channelID, sequence)
	if !found {
		return "", fmt.Errorf("cc_ibc: packet ack not found for %s/%s/%d", portID, channelID, sequence)
	}
	return base64.StdEncoding.EncodeToString(ack), nil
}

func (s *SmartContract) QuerySequence(ctx contractapi.TransactionContextInterface) (string, error) {
	current, err := ctx.GetStub().GetState(SequenceCommitmentKey)
	if err != nil {
		return "", err
	}
	if current == nil {
		return "0,0", nil
	}
	value, timestamp, err := decodeSequenceValue(current)
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%d,%d", value, timestamp), nil
}

// ProveCommitment relê o valor atual em key e o regrava só pra produzir um novo write-set
// endossado contendo (key, value). Necessário porque VerifyEndorsedCommitment
// (lado Cosmos) verifica uma prova contra o write-set de uma transação
// endossada, não uma prova Merkle contra uma raiz.
func (s *SmartContract) ProveCommitment(ctx contractapi.TransactionContextInterface, key string) (string, error) {
	store := fabricstore.StoreByName(fabricstore.NewFabricDB(ctx.GetStub()), ibcadapter.StoreKeyIBC)
	value := store.Get([]byte(key))
	if value == nil {
		return "", fmt.Errorf("cc_ibc: key %q not found", key)
	}
	store.Set([]byte(key), value)
	return base64.StdEncoding.EncodeToString(value), nil
}

func (s *SmartContract) AdvanceSequence(ctx contractapi.TransactionContextInterface) (string, error) {
	current, err := ctx.GetStub().GetState(SequenceCommitmentKey)
	if err != nil {
		return "", err
	}
	nextValue := uint64(1)
	if current != nil {
		v, _, err := decodeSequenceValue(current)
		if err != nil {
			return "", err
		}
		nextValue = v + 1
	}
	timestamp := time.Now().Unix()
	sequenceBytes := encodeSequence(nextValue, timestamp)
	if err := ctx.GetStub().PutState(SequenceCommitmentKey, sequenceBytes); err != nil {
		return "", err
	}
	return base64.StdEncoding.EncodeToString(sequenceBytes), nil
}

func main() {
	smartContract := new(SmartContract)

	cc, err := contractapi.NewChaincode(smartContract)
	if err != nil {
		stdlog.Panicf("Erro ao criar chaincode: %v", err)
	}

	server := &shim.ChaincodeServer{
		CCID:     os.Getenv("CORE_CHAINCODE_ID_NAME"),
		Address:  os.Getenv("CHAINCODE_SERVER_ADDRESS"),
		CC:       cc,
		TLSProps: shim.TLSProperties{Disabled: true},
	}

	if err := server.Start(); err != nil {
		stdlog.Panicf("Erro ao iniciar servidor: %v", err)
	}
}
