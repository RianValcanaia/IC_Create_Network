package ibcadapter

import (
	"fmt"

	sdkmath "cosmossdk.io/math"
	sdk "github.com/cosmos/cosmos-sdk/types"

	ibctransfertypes "github.com/cosmos/ibc-go/v8/modules/apps/transfer/types"
	clienttypes "github.com/cosmos/ibc-go/v8/modules/core/02-client/types"
	host "github.com/cosmos/ibc-go/v8/modules/core/24-host"
)

// SendTransfer envia um ICS-20 real a partir desta chain: faz a
// contabilidade de envio (escrow se esta chain é a origem do denom,
// burn se é um voucher voltando - mesma lógica de
// ibctransfertypes.SenderChainIsSource que o Keeper.sendTransfer real do
// ibc-go usa) e escreve o commitment do pacote via
// ChannelKeeper.SendPacket real - a mesma chamada que o sendTransfer do
// ibc-go faz por baixo, sem reimplementar nada de sequence/commitment.
// A transação "Transfer" do chaincode (cc_ibc.go) é um wrapper fino em
// cima disto.
func (k *Keeper) SendTransfer(ctx sdk.Context, portID, channelID, denom, amount, sender, receiver string, timeoutHeight clienttypes.Height, timeoutTimestamp uint64) (uint64, error) {
	amt, ok := sdkmath.NewIntFromString(amount)
	if !ok || !amt.IsPositive() {
		return 0, fmt.Errorf("ibcadapter: invalid transfer amount %q", amount)
	}

	if err := k.Bank.SubBalance(denom, sender, amt); err != nil {
		return 0, err
	}
	if ibctransfertypes.SenderChainIsSource(portID, channelID, denom) {
		if err := k.Bank.AddBalance(denom, EscrowAccount(portID, channelID), amt); err != nil {
			return 0, err
		}
	}
	// Se a chain não é a origem (devolvendo um voucher recebido), o
	// SubBalance acima já é a "queima" - nada mais a creditar.

	data := ibctransfertypes.NewFungibleTokenPacketData(denom, amount, sender, receiver, "")
	if err := data.ValidateBasic(); err != nil {
		return 0, err
	}

	chanCap, ok := k.transferScope.GetCapability(ctx, host.ChannelCapabilityPath(portID, channelID))
	if !ok {
		return 0, fmt.Errorf("ibcadapter: channel capability not found for %s/%s", portID, channelID)
	}

	return k.ChannelKeeper.SendPacket(ctx, chanCap, portID, channelID, timeoutHeight, timeoutTimestamp, data.GetBytes())
}
