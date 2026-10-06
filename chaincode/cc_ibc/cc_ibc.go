/*
cc_ibc: chaincode que coloca o núcleo do IBC (ibc-go v8.2.1) dentro do
Hyperledger Fabric.

O Fabric não tem IBC nativo. Este chaincode roda os keepers reais do ibc-go
(clients, connections, channels) e uma aplicação ICS-20 própria, e expõe cada
mensagem IBC como uma transação Fabric. O relayer chama essas transações pelo
fabric-gateway.

Como funciona uma chamada:
 1. o argumento chega como a Msg do ibc-go em protobuf, codificada em base64;
 2. newKeeper monta os keepers do zero sobre o WorldState atual (nada fica
    guardado em memória entre uma chamada e outra);
 3. o keeper executa a Msg; o que ele lê e escreve vira o read-write set da
    transação, que o Fabric endossa e grava no ledger.

Tipos de light client que o chaincode sabe decodificar (newCodec):
07-tendermint (Cosmos), hb-qbft (Besu) e fabric-msp (o client que a outra
chain tem deste Fabric, conferido no handshake).

Roda como CCaaS (chaincode as a service): main sobe um servidor gRPC que o
peer chama.
*/
package main

import (
	"encoding/base64"
	"encoding/json"
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

	besuprovermodule "github.com/datachainlab/besu-ibc-relay-prover/module"

	"github.com/rianvalcanaia/cc_ibc/internal/fabricstore"
	"github.com/rianvalcanaia/cc_ibc/internal/ibcadapter"
)

// FabricChainID é o "chain-id" que este adaptador declara pra si mesmo no
// sdk.Context - só usado internamente (logs, ctx.ChainID()); não afeta a
// verificação do 07-tendermint, que valida contra o chain-id real dentro
// do próprio Header/ClientState assinado por cosmos_chain_0.
const FabricChainID = "fabric-msp-channel-all"

// newCodec registra os tipos que o chaincode precisa abrir de dentro de um
// Any: os três light clients (07-tendermint, fabric-msp e hb-qbft).
func newCodec() *codec.ProtoCodec {
	registry := codectypes.NewInterfaceRegistry()
	ibctm.RegisterInterfaces(registry)
	fabricmsp.RegisterInterfaces(registry)
	// light client hb-qbft (Besu)
	besuprovermodule.Module{}.RegisterInterfaces(registry)
	return codec.NewProtoCodec(registry)
}

var cdc = newCodec()

// SmartContract expõe o núcleo do ibc-go como transações Fabric.
type SmartContract struct {
	contractapi.Contract
}

// newKeeper monta tudo que uma transação precisa: o banco sobre o WorldState,
// as stores, os keepers do ibc-go e o sdk.Context (com altura = sequência do
// Fabric + 1). Também carrega as capabilities e garante a porta transfer
// ligada ao ICS-20.
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

// currentSequence lê a sequência atual do Fabric (valor e timestamp) em
// fabric-msp/sequence; devolve 0, 0 se ainda não existir.
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

// decodeArg decodifica um argumento em base64 para a Msg protobuf do ibc-go.
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

// encodeResp serializa a resposta em protobuf e devolve em base64.
func encodeResp(resp interface{ Marshal() ([]byte, error) }) (string, error) {
	bz, err := resp.Marshal()
	if err != nil {
		return "", err
	}
	return base64.StdEncoding.EncodeToString(bz), nil
}

// CreateClient (MsgCreateClient) cria, dentro do Fabric, um light client da
// outra chain. Devolve o client-id criado (ex.: 07-tendermint-0), que o
// relayer usa no resto do handshake.
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

// UpdateClient (MsgUpdateClient) atualiza um light client com um header novo
// da outra chain; o light client verifica o header.
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

// ConnectionOpenInit é o 1º passo do handshake de connection, no lado que
// inicia. Devolve o connection-id criado.
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

// ConnectionOpenTry é o 2º passo, no lado que responde: verifica as provas do
// outro lado e devolve o connection-id criado.
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

// ConnectionOpenAck é o 3º passo: o lado que iniciou verifica as provas do Try
// e abre a connection.
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

// ConnectionOpenConfirm é o 4º passo: o lado que respondeu verifica que o
// outro abriu e abre também.
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

// ChannelOpenInit é o 1º passo do handshake de channel, no lado que inicia.
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

// ChannelOpenTry é o 2º passo do handshake de channel, no lado que responde.
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

// ChannelOpenAck é o 3º passo: o lado que iniciou abre o channel.
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

// ChannelOpenConfirm é o 4º passo: o lado que respondeu abre o channel.
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

// RecvPacket (MsgRecvPacket) recebe um pacote da outra chain, depois que o
// light client verifica a prova, e o entrega ao ICS-20.
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

// Acknowledgement (MsgAcknowledgement) processa o ack de um pacote que esta
// chain enviou; se o ack for de erro, os tokens voltam ao remetente.
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

// Timeout (MsgTimeout) trata um pacote enviado que não foi recebido a tempo:
// os tokens voltam ao remetente.
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

// Transfer inicia uma transferência ICS-20 a partir do Fabric: debita o
// remetente e grava o pacote. Devolve a sequence do pacote.
func (s *SmartContract) Transfer(ctx contractapi.TransactionContextInterface, portID, channelID, denom, amount, sender, receiver string, timeoutRevisionNumber, timeoutRevisionHeight, timeoutTimestamp uint64) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	timeoutHeight := clienttypes.NewHeight(timeoutRevisionNumber, timeoutRevisionHeight)
	seq, err := k.SendTransfer(sdkCtx, portID, channelID, denom, amount, sender, receiver, timeoutHeight, timeoutTimestamp)
	if err != nil {
		return "", err
	}
	return strconv.FormatUint(seq, 10), nil
}

// QueryBalance devolve o saldo de uma conta num denom (ledger de saldos do
// ICS-20).
func (s *SmartContract) QueryBalance(ctx contractapi.TransactionContextInterface, account, denom string) (string, error) {
	k, _ := newKeeper(ctx.GetStub())
	amount, err := k.Bank.GetBalance(denom, account)
	if err != nil {
		return "", err
	}
	return amount.String(), nil
}

// QueryClientState devolve o ClientState de um client (Any em protobuf,
// base64); o relayer usa para montar o handshake.
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

// QueryConnection devolve a ConnectionEnd de uma connection (protobuf,
// base64).
func (s *SmartContract) QueryConnection(ctx contractapi.TransactionContextInterface, connectionID string) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	conn, found := k.ConnectionKeeper.GetConnection(sdkCtx, connectionID)
	if !found {
		return "", fmt.Errorf("cc_ibc: connection %s not found", connectionID)
	}
	return encodeResp(&conn)
}

// QueryChannel devolve o Channel de um port/channel (protobuf, base64).
func (s *SmartContract) QueryChannel(ctx contractapi.TransactionContextInterface, portID, channelID string) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	ch, found := k.ChannelKeeper.GetChannel(sdkCtx, portID, channelID)
	if !found {
		return "", fmt.Errorf("cc_ibc: channel %s/%s not found", portID, channelID)
	}
	return encodeResp(&ch)
}

// QueryClientConsensusState devolve o ConsensusState de um client numa altura
// (Any em protobuf, base64).
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

// QueryNextSequenceReceive devolve a próxima sequence esperada no recebimento
// (só avança em channel ORDERED).
func (s *SmartContract) QueryNextSequenceReceive(ctx contractapi.TransactionContextInterface, portID, channelID string) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	seq, found := k.ChannelKeeper.GetNextSequenceRecv(sdkCtx, portID, channelID)
	if !found {
		return "", fmt.Errorf("cc_ibc: next sequence recv not found for %s/%s", portID, channelID)
	}
	return strconv.FormatUint(seq, 10), nil
}

// QueryNextSequenceSend devolve a próxima sequence de envio do channel; o
// relayer usa como limite ao procurar pacotes enviados ainda não entregues.
func (s *SmartContract) QueryNextSequenceSend(ctx contractapi.TransactionContextInterface, portID, channelID string) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	seq, found := k.ChannelKeeper.GetNextSequenceSend(sdkCtx, portID, channelID)
	if !found {
		return "", fmt.Errorf("cc_ibc: next sequence send not found for %s/%s", portID, channelID)
	}
	return strconv.FormatUint(seq, 10), nil
}

// QuerySentPacket devolve, em JSON, o pacote completo enviado numa sequence. O
// ibc-go só guarda o hash do pacote; o pacote em si fica no SentPacketStore.
func (s *SmartContract) QuerySentPacket(ctx contractapi.TransactionContextInterface, portID, channelID string, sequence uint64) (string, error) {
	k, _ := newKeeper(ctx.GetStub())
	packet, found, err := k.Sent.Get(portID, channelID, sequence)
	if err != nil {
		return "", err
	}
	if !found {
		return "", fmt.Errorf("cc_ibc: sent packet not found for %s/%s/%d", portID, channelID, sequence)
	}
	bz, err := json.Marshal(&packet)
	if err != nil {
		return "", err
	}
	return string(bz), nil
}

// QueryReceivedHighSequence devolve a maior sequence já recebida no channel; o
// relayer usa como limite ao procurar acks para levar de volta (em channel
// UNORDERED o NextSequenceRecv não avança).
func (s *SmartContract) QueryReceivedHighSequence(ctx contractapi.TransactionContextInterface, portID, channelID string) (string, error) {
	k, _ := newKeeper(ctx.GetStub())
	high, err := k.Received.HighSequence(portID, channelID)
	if err != nil {
		return "", err
	}
	return strconv.FormatUint(high, 10), nil
}

// QueryReceivedPacket devolve, em JSON, o pacote recebido e o ack escrito para
// ele, guardados no ReceivedPacketStore (o ibc-go só guarda o hash do ack).
func (s *SmartContract) QueryReceivedPacket(ctx contractapi.TransactionContextInterface, portID, channelID string, sequence uint64) (string, error) {
	k, _ := newKeeper(ctx.GetStub())
	packet, ack, found, err := k.Received.Get(portID, channelID, sequence)
	if err != nil {
		return "", err
	}
	if !found {
		return "", fmt.Errorf("cc_ibc: received packet not found for %s/%s/%d", portID, channelID, sequence)
	}
	resp := struct {
		Packet          channeltypes.Packet `json:"packet"`
		Acknowledgement []byte              `json:"acknowledgement"`
	}{Packet: packet, Acknowledgement: ack}
	bz, err := json.Marshal(&resp)
	if err != nil {
		return "", err
	}
	return string(bz), nil
}

// QueryPacketCommitment devolve o hash (commitment) de um pacote enviado que
// ainda não foi confirmado.
func (s *SmartContract) QueryPacketCommitment(ctx contractapi.TransactionContextInterface, portID, channelID string, sequence uint64) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	commitment := k.ChannelKeeper.GetPacketCommitment(sdkCtx, portID, channelID, sequence)
	if len(commitment) == 0 {
		return "", fmt.Errorf("cc_ibc: packet commitment not found for %s/%s/%d", portID, channelID, sequence)
	}
	return base64.StdEncoding.EncodeToString(commitment), nil
}

// QueryPacketReceipt devolve true se o pacote dessa sequence já foi recebido.
func (s *SmartContract) QueryPacketReceipt(ctx contractapi.TransactionContextInterface, portID, channelID string, sequence uint64) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	_, found := k.ChannelKeeper.GetPacketReceipt(sdkCtx, portID, channelID, sequence)
	return strconv.FormatBool(found), nil
}

// QueryPacketAck devolve o hash (commitment) do ack escrito para um pacote
// recebido.
func (s *SmartContract) QueryPacketAck(ctx contractapi.TransactionContextInterface, portID, channelID string, sequence uint64) (string, error) {
	k, sdkCtx := newKeeper(ctx.GetStub())
	ack, found := k.ChannelKeeper.GetPacketAcknowledgement(sdkCtx, portID, channelID, sequence)
	if !found {
		return "", fmt.Errorf("cc_ibc: packet ack not found for %s/%s/%d", portID, channelID, sequence)
	}
	return base64.StdEncoding.EncodeToString(ack), nil
}

// QuerySequence devolve a sequência atual do Fabric no formato
// "valor,timestamp".
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

// ProveCommitment relê o valor de uma chave da store ibc e grava o mesmo valor
// de novo, só para ele aparecer no write-set desta transação. O endosso dessa
// transação é a prova que o light client fabric-msp verifica do outro lado, já
// que o Fabric não tem árvore Merkle.
func (s *SmartContract) ProveCommitment(ctx contractapi.TransactionContextInterface, key string) (string, error) {
	store := fabricstore.StoreByName(fabricstore.NewFabricDB(ctx.GetStub()), ibcadapter.StoreKeyIBC)
	value := store.Get([]byte(key))
	if value == nil {
		return "", fmt.Errorf("cc_ibc: key %q not found", key)
	}
	store.Set([]byte(key), value)
	return base64.StdEncoding.EncodeToString(value), nil
}

// AdvanceSequence incrementa a sequência do Fabric (a "altura" que os light
// clients do outro lado acompanham) e grava junto o timestamp atual.
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

// main sobe o chaincode como servidor CCaaS, com o id e o endereço vindos das
// variáveis de ambiente que o peer configura.
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
