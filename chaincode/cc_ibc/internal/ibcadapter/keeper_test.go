package ibcadapter_test

import (
	"testing"
	"time"

	"cosmossdk.io/log"

	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	"github.com/cosmos/cosmos-sdk/codec"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"

	clienttypes "github.com/cosmos/ibc-go/v8/modules/core/02-client/types"
	connectiontypes "github.com/cosmos/ibc-go/v8/modules/core/03-connection/types"
	commitmenttypes "github.com/cosmos/ibc-go/v8/modules/core/23-commitment/types"
	ibctm "github.com/cosmos/ibc-go/v8/modules/light-clients/07-tendermint"
	ibctesting "github.com/cosmos/ibc-go/v8/testing"

	"github.com/rianvalcanaia/cc_ibc/internal/fabricstore"
	"github.com/rianvalcanaia/cc_ibc/internal/ibcadapter"
)

const (
	trustingPeriod = 100000 * time.Second
	ubdPeriod      = 200000 * time.Second
	maxClockDrift  = 10 * time.Second
)

func newTestKeeper(t *testing.T) (*ibcadapter.Keeper, sdk.Context) {
	t.Helper()
	stub := newMockStub()

	registry := codectypes.NewInterfaceRegistry()
	ibctm.RegisterInterfaces(registry)
	cdc := codec.NewProtoCodec(registry)

	db := fabricstore.NewFabricDB(stub)
	keys := ibcadapter.StoreKeys()
	memKeys := ibcadapter.MemStoreKeys()
	ms := fabricstore.NewMultiStore(db, keys, memKeys)

	k := ibcadapter.NewKeeper(cdc, ms, keys, memKeys, 0, 0, db)
	k.SetupRouter()

	ctx := sdk.NewContext(ms, cmtproto.Header{ChainID: "fabric-msp-channel-all", Time: time.Now()}, false, log.NewNopLogger())
	return k, ctx
}

// TestKeeperConstruction confirma que os 4 keepers (client/connection/
// channel/capability) inicializam sem panic sobre o fabricstore.
func TestKeeperConstruction(t *testing.T) {
	k, _ := newTestKeeper(t)
	if k.PortKeeper == nil || k.Router == nil || k.CapabilityKeeper == nil {
		t.Fatal("esperava todos os keepers/router construídos")
	}
}

func newRealTendermintClientAndConsensusState(t *testing.T, chain *ibctesting.TestChain, header *ibctm.Header) (*ibctm.ClientState, *ibctm.ConsensusState) {
	t.Helper()
	clientState := ibctm.NewClientState(
		chain.ChainID,
		ibctm.DefaultTrustLevel,
		trustingPeriod, ubdPeriod, maxClockDrift,
		header.GetHeight().(clienttypes.Height),
		commitmenttypes.GetSDKSpecs(),
		[]string{"upgradedIBCState"},
	)
	consensusState := ibctm.NewConsensusState(
		header.GetTime(),
		commitmenttypes.NewMerkleRoot(header.Header.GetAppHash()),
		header.Header.GetValidatorsHash(),
	)
	return clientState, consensusState
}

// TestCreateAndUpdateClient_RealTendermint prova, com um chain de teste
// que CreateClient/UpdateClient funcionam de ponta a
// ponta dentro do adaptador contra um Header Tendermint genuíno
func TestCreateAndUpdateClient_RealTendermint(t *testing.T) {
	coord := ibctesting.NewCoordinator(t, 1)
	chain := coord.GetChain(ibctesting.GetChainID(1))

	k, ctx := newTestKeeper(t)

	header := chain.CurrentTMClientHeader()
	clientState, consensusState := newRealTendermintClientAndConsensusState(t, chain, header)

	ctx = ctx.WithBlockTime(header.GetTime())

	anyClientState, err := clienttypes.PackClientState(clientState)
	if err != nil {
		t.Fatal(err)
	}
	anyConsState, err := clienttypes.PackConsensusState(consensusState)
	if err != nil {
		t.Fatal(err)
	}

	if _, err := k.CreateClient(ctx, &clienttypes.MsgCreateClient{ClientState: anyClientState, ConsensusState: anyConsState}); err != nil {
		t.Fatalf("esperava CreateClient aceitar um ClientState/Header Tendermint reais, erro: %v", err)
	}

	clientID := "07-tendermint-0"
	if cs, found := k.ClientKeeper.GetClientState(ctx, clientID); !found {
		t.Fatal("esperava client criado em 07-tendermint-0")
	} else if cs.GetLatestHeight().GetRevisionHeight() != uint64(header.Header.Height) {
		t.Fatalf("altura inesperada: %v", cs.GetLatestHeight())
	}

	coord.CommitBlock(chain) // avança altura E tempo (chain.NextBlock() sozinho não avança o tempo, ver coordinator.go)
	trustedHeight := header.GetHeight().(clienttypes.Height)
	updateHeader := chain.CreateTMClientHeader(
		chain.ChainID, chain.CurrentHeader.Height, trustedHeight, chain.CurrentHeader.Time,
		chain.Vals, chain.NextVals, chain.Vals, chain.Signers,
	)
	anyUpdateHeader, err := clienttypes.PackClientMessage(updateHeader)
	if err != nil {
		t.Fatal(err)
	}
	ctx = ctx.WithBlockTime(updateHeader.GetTime())

	if _, err := k.UpdateClient(ctx, &clienttypes.MsgUpdateClient{ClientId: clientID, ClientMessage: anyUpdateHeader}); err != nil {
		t.Fatalf("esperava UpdateClient aceitar um Header Tendermint real de avanço, erro: %v", err)
	}

	if cs, found := k.ClientKeeper.GetClientState(ctx, clientID); !found {
		t.Fatal("client sumiu depois do UpdateClient")
	} else if cs.GetLatestHeight().GetRevisionHeight() != uint64(updateHeader.Header.Height) {
		t.Fatalf("esperava altura avançada pra %d, ficou %v", updateHeader.Header.Height, cs.GetLatestHeight())
	}
}

// TestConnectionOpenInit confirma o wiring do connectionKeeper (não
// depende de nenhuma prova externa - ConnOpenInit só grava o estado
// inicial da connection do lado que inicia o handshake).
func TestConnectionOpenInit(t *testing.T) {
	coord := ibctesting.NewCoordinator(t, 1)
	chain := coord.GetChain(ibctesting.GetChainID(1))

	k, ctx := newTestKeeper(t)

	header := chain.CurrentTMClientHeader()
	clientState, consensusState := newRealTendermintClientAndConsensusState(t, chain, header)
	ctx = ctx.WithBlockTime(header.GetTime())
	anyClientState, _ := clienttypes.PackClientState(clientState)
	anyConsState, _ := clienttypes.PackConsensusState(consensusState)
	if _, err := k.CreateClient(ctx, &clienttypes.MsgCreateClient{ClientState: anyClientState, ConsensusState: anyConsState}); err != nil {
		t.Fatal(err)
	}

	_, err := k.ConnectionOpenInit(ctx, &connectiontypes.MsgConnectionOpenInit{
		ClientId: "07-tendermint-0",
		Counterparty: connectiontypes.Counterparty{
			ClientId:     "fabric-msp-0",
			ConnectionId: "",
			Prefix:       commitmenttypes.NewMerklePrefix([]byte("ibc")),
		},
		Version:     nil,
		DelayPeriod: 0,
		Signer:      "fabric-chaincode",
	})
	if err != nil {
		t.Fatalf("esperava ConnectionOpenInit aceitar, erro: %v", err)
	}

	if _, found := k.ConnectionKeeper.GetConnection(ctx, "connection-0"); !found {
		t.Fatal("esperava connection-0 gravada")
	}
}
