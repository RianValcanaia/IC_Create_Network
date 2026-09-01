package ibcadapter

import (
	errorsmod "cosmossdk.io/errors"

	sdk "github.com/cosmos/cosmos-sdk/types"

	clientkeeper "github.com/cosmos/ibc-go/v8/modules/core/02-client/keeper"
	clienttypes "github.com/cosmos/ibc-go/v8/modules/core/02-client/types"
	ibcerrors "github.com/cosmos/ibc-go/v8/modules/core/errors"
	"github.com/cosmos/ibc-go/v8/modules/core/exported"

	fabricmsp "github.com/rianvalcanaia/cosmos-yui-app/lightclients/fabric-msp"
)

const FabricMSPClientType = "fabric-msp"

type selfAwareClientKeeper struct {
	clientkeeper.Keeper

	// selfSequenceValue/selfSequenceTimestamp: Sequence atual do Fabric
	// (fora do store do ibc-go, lido direto do stub em cc_ibc.go) - usado
	// só por GetSelfConsensusState abaixo.
	selfSequenceValue     uint64
	selfSequenceTimestamp int64
}

func (k selfAwareClientKeeper) ValidateSelfClient(_ sdk.Context, clientState exported.ClientState) error {
	if clientState == nil {
		return errNotSupported
	}
	if clientState.ClientType() != FabricMSPClientType {
		return clientTypeMismatchErr{got: clientState.ClientType()}
	}
	return nil
}

func (k selfAwareClientKeeper) GetSelfConsensusState(_ sdk.Context, height exported.Height) (exported.ConsensusState, error) {
	seqHeight, ok := height.(clienttypes.Height)
	if !ok {
		return nil, errorsmod.Wrapf(ibcerrors.ErrInvalidType, "expected %T, got %T", clienttypes.Height{}, height)
	}
	if seqHeight.RevisionHeight != k.selfSequenceValue {
		return nil, errorsmod.Wrapf(clienttypes.ErrConsensusStateNotFound, "fabric sequence %d not found (self sequence atual: %d)", seqHeight.RevisionHeight, k.selfSequenceValue)
	}
	return fabricmsp.NewConsensusState(k.selfSequenceTimestamp), nil
}

type clientTypeMismatchErr struct{ got string }

func (e clientTypeMismatchErr) Error() string {
	return "ibcadapter: client must be a fabric-msp client, got: " + e.got
}
