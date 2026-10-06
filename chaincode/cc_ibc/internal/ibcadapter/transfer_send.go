/*
Envio de uma transferência ICS-20 a partir do Fabric. É o que a transação
Transfer do cc_ibc.go executa.
*/
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

// SendTransfer debita o remetente (escrow se o token é daqui, queima se é um
// voucher voltando para a origem), cria o pacote pelo ChannelKeeper.SendPacket
// do ibc-go (que grava o commitment) e guarda o pacote completo no
// SentPacketStore para o relayer. Devolve a sequence.
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
