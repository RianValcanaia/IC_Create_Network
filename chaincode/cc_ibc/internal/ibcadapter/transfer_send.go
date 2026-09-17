package ibcadapter

import (
	"fmt"

	sdkmath "cosmossdk.io/math"
	sdk "github.com/cosmos/cosmos-sdk/types"

	ibctransfertypes "github.com/cosmos/ibc-go/v8/modules/apps/transfer/types"
	clienttypes "github.com/cosmos/ibc-go/v8/modules/core/02-client/types"
	channeltypes "github.com/cosmos/ibc-go/v8/modules/core/04-channel/types"
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

	channel, found := k.ChannelKeeper.GetChannel(ctx, portID, channelID)
	if !found {
		return 0, fmt.Errorf("ibcadapter: channel not found for %s/%s", portID, channelID)
	}

	sequence, err := k.ChannelKeeper.SendPacket(ctx, chanCap, portID, channelID, timeoutHeight, timeoutTimestamp, data.GetBytes())
	if err != nil {
		return 0, err
	}

	// Guarda o Packet completo que acabou de ser commitado - o
	// ChannelKeeper real só grava o hash (CommitPacket) no state, então
	// sem isso o relayer nunca teria como reconstruir este pacote pra
	// relayá-lo (QueryUnfinalizedRelayPackets em
	// relayer/chains/fabric/chain.go depende disso). Precisa ser
	// byte-a-byte igual ao que SendPacket usou internamente pra computar
	// o commitment (mesmos portID/channelID/timeout/data, e o
	// destPort/destChannel vêm do Counterparty do canal, mesma
	// convenção do ibc-go core).
	packet := channeltypes.NewPacket(data.GetBytes(), sequence, portID, channelID, channel.Counterparty.PortId, channel.Counterparty.ChannelId, timeoutHeight, timeoutTimestamp)
	if err := k.Sent.Put(portID, channelID, packet); err != nil {
		return 0, err
	}

	return sequence, nil
}
