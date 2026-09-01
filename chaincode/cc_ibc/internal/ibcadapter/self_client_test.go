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

func (fakeFabricMSPClientState) ClientType() string { return FabricMSPClientType }

type fakeOtherClientState struct {
	exported.ClientState
}

func (fakeOtherClientState) ClientType() string { return "something-else" }

func TestValidateSelfClient_FabricMSPOverride(t *testing.T) {
	registry := codectypes.NewInterfaceRegistry()
	ibctm.RegisterInterfaces(registry)
	cdc := codec.NewProtoCodec(registry)

	storeKey := storetypes.NewKVStoreKey(StoreKeyIBC)
	ctx := sdk.NewContext(nil, cmtproto.Header{}, false, nil)

	realKeeper := clientkeeper.NewKeeper(cdc, storeKey, noopParamSubspace{}, noopStakingKeeper{}, noopUpgradeKeeper{})

	// 1. Confirma o bloqueio real: o keeper puro do ibc-go rejeita um
	// client fabric-msp - exatamente o achado documentado no plano.
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
