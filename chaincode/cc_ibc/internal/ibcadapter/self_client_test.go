/*
Testes do selfAwareClientKeeper: mostram que o keeper original do ibc-go
rejeita um client fabric-msp e que o wrapper aceita só esse tipo.
*/
package ibcadapter

import (
	"testing"

	storetypes "cosmossdk.io/store/types"

	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	"github.com/cosmos/cosmos-sdk/codec"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"

	clientkeeper "github.com/cosmos/ibc-go/v8/modules/core/02-client/keeper"
	"github.com/cosmos/ibc-go/v8/modules/core/exported"
	ibctm "github.com/cosmos/ibc-go/v8/modules/light-clients/07-tendermint"
)

type fakeFabricMSPClientState struct {
	exported.ClientState
}

// ClientType finge ser um client fabric-msp.
func (fakeFabricMSPClientState) ClientType() string { return FabricMSPClientType }

type fakeOtherClientState struct {
	exported.ClientState
}

// ClientType finge ser um client de outro tipo.
func (fakeOtherClientState) ClientType() string { return "something-else" }

// TestValidateSelfClient_FabricMSPOverride: o keeper original rejeita fabric-
// msp; o wrapper aceita fabric-msp e rejeita outros tipos e nil.
func TestValidateSelfClient_FabricMSPOverride(t *testing.T) {
	registry := codectypes.NewInterfaceRegistry()
	ibctm.RegisterInterfaces(registry)
	cdc := codec.NewProtoCodec(registry)

	storeKey := storetypes.NewKVStoreKey(StoreKeyIBC)
	ctx := sdk.NewContext(nil, cmtproto.Header{}, false, nil)

	realKeeper := clientkeeper.NewKeeper(cdc, storeKey, noopParamSubspace{}, noopStakingKeeper{}, noopUpgradeKeeper{})

	// 1. Confirma o problema: o keeper puro do ibc-go rejeita um client
	// fabric-msp (é o motivo de o wrapper existir).
	if err := realKeeper.ValidateSelfClient(ctx, fakeFabricMSPClientState{}); err == nil {
		t.Fatal("esperava que o clientkeeper.Keeper puro rejeitasse um ClientState fabric-msp (client must be a Tendermint client)")
	}

	// 2. O wrapper aceita fabric-msp.
	wrapped := selfAwareClientKeeper{Keeper: realKeeper}
	if err := wrapped.ValidateSelfClient(ctx, fakeFabricMSPClientState{}); err != nil {
		t.Fatalf("esperava que o wrapper aceitasse um ClientState fabric-msp, erro: %v", err)
	}

	// 3. O wrapper continua rejeitando qualquer outro tipo (não virou um
	// "aceita tudo").
	if err := wrapped.ValidateSelfClient(ctx, fakeOtherClientState{}); err == nil {
		t.Fatal("esperava que o wrapper rejeitasse um ClientState que não seja fabric-msp")
	}

	// 4. E também rejeita nil.
	if err := wrapped.ValidateSelfClient(ctx, nil); err == nil {
		t.Fatal("esperava que o wrapper rejeitasse um ClientState nil")
	}
}
