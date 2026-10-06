/*
TransferApp: a aplicação ICS-20 (transferência de tokens) do Fabric.

Implementa os callbacks que o núcleo IBC chama na porta "transfer": abertura
de channel, recebimento de pacote, ack e timeout. Usa os tipos e as regras do
próprio ibc-go (FungibleTokenPacketData no mesmo JSON, ReceiverChainIsSource,
SenderChainIsSource, prefixo de denom), seguindo
modules/apps/transfer/keeper/relay.go. A única parte nova é a contabilidade,
feita no BankKeeper (bankstore.go), porque um chaincode não tem o módulo bank
do Cosmos.

Regra dos tokens (a mesma do ICS-20):
  - token nativo daqui saindo: vai para a conta de escrow do channel;
  - token nativo daqui voltando: sai do escrow para o destinatário;
  - token de fora chegando: cria um voucher "transfer/<channel>/<denom>";
  - voucher voltando para a origem: é queimado no envio.
*/
package ibcadapter

import (
	"fmt"

	sdkmath "cosmossdk.io/math"
	sdk "github.com/cosmos/cosmos-sdk/types"

	capabilitykeeper "github.com/cosmos/ibc-go/modules/capability/keeper"
	capabilitytypes "github.com/cosmos/ibc-go/modules/capability/types"
	ibctransfertypes "github.com/cosmos/ibc-go/v8/modules/apps/transfer/types"
	channeltypes "github.com/cosmos/ibc-go/v8/modules/core/04-channel/types"
	porttypes "github.com/cosmos/ibc-go/v8/modules/core/05-port/types"
	host "github.com/cosmos/ibc-go/v8/modules/core/24-host"
	"github.com/cosmos/ibc-go/v8/modules/core/exported"
)

// TransferApp é a porttypes.IBCModule ligada à porta "transfer" (ver o topo
// do arquivo).
type TransferApp struct {
	Scope capabilitykeeper.ScopedKeeper
	Bank  BankKeeper
}

var _ porttypes.IBCModule = TransferApp{}

// EscrowAccount devolve a conta de escrow de um port/channel: um identificador
// fixo (não uma identidade Fabric) onde ficam os tokens nativos enviados por
// esse channel.
func EscrowAccount(portID, channelID string) string {
	return fmt.Sprintf("ics20-escrow/%s/%s", portID, channelID)
}

// validateTransferChannelParams exige o que o ICS-20 pede: channel UNORDERED e
// versão ics20-1.
func validateTransferChannelParams(order channeltypes.Order, version string) error {
	if order != channeltypes.UNORDERED {
		return fmt.Errorf("ibcadapter: invalid channel ordering %s for ICS-20, expected %s", order, channeltypes.UNORDERED)
	}
	if version != "" && version != ibctransfertypes.Version {
		return fmt.Errorf("ibcadapter: invalid ICS-20 version %q, expected %q", version, ibctransfertypes.Version)
	}
	return nil
}

// OnChanOpenInit valida ordem e versão, guarda a capability do channel e
// devolve a versão (ics20-1 se vier vazia).
func (a TransferApp) OnChanOpenInit(ctx sdk.Context, order channeltypes.Order, _ []string, portID string, channelID string, chanCap *capabilitytypes.Capability, _ channeltypes.Counterparty, version string) (string, error) {
	if err := validateTransferChannelParams(order, version); err != nil {
		return "", err
	}
	if err := a.Scope.ClaimCapability(ctx, chanCap, host.ChannelCapabilityPath(portID, channelID)); err != nil {
		return "", err
	}
	if version == "" {
		return ibctransfertypes.Version, nil
	}
	return version, nil
}

// OnChanOpenTry valida ordem e versão do outro lado, guarda a capability do
// channel e devolve ics20-1.
func (a TransferApp) OnChanOpenTry(ctx sdk.Context, order channeltypes.Order, _ []string, portID, channelID string, chanCap *capabilitytypes.Capability, _ channeltypes.Counterparty, counterpartyVersion string) (string, error) {
	if err := validateTransferChannelParams(order, counterpartyVersion); err != nil {
		return "", err
	}
	if err := a.Scope.ClaimCapability(ctx, chanCap, host.ChannelCapabilityPath(portID, channelID)); err != nil {
		return "", err
	}
	return ibctransfertypes.Version, nil
}

// OnChanOpenAck não tem nada a fazer.
func (TransferApp) OnChanOpenAck(_ sdk.Context, _, _ string, _ string, _ string) error {
	return nil
}

// OnChanOpenConfirm não tem nada a fazer.
func (TransferApp) OnChanOpenConfirm(_ sdk.Context, _, _ string) error { return nil }

// OnChanCloseInit não tem nada a fazer (fechar channel não é usado).
func (TransferApp) OnChanCloseInit(_ sdk.Context, _, _ string) error { return nil }

// OnChanCloseConfirm não tem nada a fazer (fechar channel não é usado).
func (TransferApp) OnChanCloseConfirm(_ sdk.Context, _, _ string) error { return nil }

// OnRecvPacket decodifica o pacote ICS-20 e credita o destinatário: se é um
// token desta chain voltando, tira do escrow; senão cria o voucher com o
// prefixo do channel daqui. Qualquer falha vira um ack de erro, que faz o
// remetente receber os tokens de volta.
func (a TransferApp) OnRecvPacket(_ sdk.Context, packet channeltypes.Packet, _ sdk.AccAddress) exported.Acknowledgement {
	var data ibctransfertypes.FungibleTokenPacketData
	if err := ibctransfertypes.ModuleCdc.UnmarshalJSON(packet.GetData(), &data); err != nil {
		return channeltypes.NewErrorAcknowledgement(fmt.Errorf("ibcadapter: cannot unmarshal ICS-20 packet data: %w", err))
	}
	if err := data.ValidateBasic(); err != nil {
		return channeltypes.NewErrorAcknowledgement(err)
	}
	amount, ok := sdkmath.NewIntFromString(data.Amount)
	if !ok {
		return channeltypes.NewErrorAcknowledgement(fmt.Errorf("ibcadapter: invalid transfer amount %q", data.Amount))
	}

	if ibctransfertypes.ReceiverChainIsSource(packet.GetSourcePort(), packet.GetSourceChannel(), data.Denom) {
		// Voucher voltando pra origem: remove o prefixo e desescrowa.
		voucherPrefix := ibctransfertypes.GetDenomPrefix(packet.GetSourcePort(), packet.GetSourceChannel())
		denom := data.Denom[len(voucherPrefix):]
		escrow := EscrowAccount(packet.GetDestPort(), packet.GetDestChannel())
		if err := a.Bank.SubBalance(denom, escrow, amount); err != nil {
			return channeltypes.NewErrorAcknowledgement(err)
		}
		if err := a.Bank.AddBalance(denom, data.Receiver, amount); err != nil {
			return channeltypes.NewErrorAcknowledgement(err)
		}
		return channeltypes.NewResultAcknowledgement([]byte{1})
	}

	// Chain remetente é a origem: minta um voucher novo, prefixado com o
	// port/channel desta própria chain (mesma convenção do ibc-go real).
	voucherDenom := ibctransfertypes.GetDenomPrefix(packet.GetDestPort(), packet.GetDestChannel()) + data.Denom
	if err := a.Bank.AddBalance(voucherDenom, data.Receiver, amount); err != nil {
		return channeltypes.NewErrorAcknowledgement(err)
	}
	return channeltypes.NewResultAcknowledgement([]byte{1})
}

// OnAcknowledgementPacket não faz nada se o ack é de sucesso; se é de erro,
// devolve os tokens ao remetente (refund).
func (a TransferApp) OnAcknowledgementPacket(_ sdk.Context, packet channeltypes.Packet, acknowledgement []byte, _ sdk.AccAddress) error {
	var ack channeltypes.Acknowledgement
	if err := ibctransfertypes.ModuleCdc.UnmarshalJSON(acknowledgement, &ack); err != nil {
		return fmt.Errorf("ibcadapter: cannot unmarshal ICS-20 acknowledgement: %w", err)
	}
	if ack.Success() {
		return nil
	}
	var data ibctransfertypes.FungibleTokenPacketData
	if err := ibctransfertypes.ModuleCdc.UnmarshalJSON(packet.GetData(), &data); err != nil {
		return fmt.Errorf("ibcadapter: cannot unmarshal ICS-20 packet data: %w", err)
	}
	return a.refund(packet, data)
}

// OnTimeoutPacket trata um pacote que expirou sem ser recebido: devolve os
// tokens ao remetente.
func (a TransferApp) OnTimeoutPacket(_ sdk.Context, packet channeltypes.Packet, _ sdk.AccAddress) error {
	var data ibctransfertypes.FungibleTokenPacketData
	if err := ibctransfertypes.ModuleCdc.UnmarshalJSON(packet.GetData(), &data); err != nil {
		return fmt.Errorf("ibcadapter: cannot unmarshal ICS-20 packet data: %w", err)
	}
	return a.refund(packet, data)
}

// refund desfaz um envio: se o token é desta chain, tira do escrow e devolve
// ao remetente; se era um voucher (queimado no envio), cria de novo para o
// remetente.
func (a TransferApp) refund(packet channeltypes.Packet, data ibctransfertypes.FungibleTokenPacketData) error {
	amount, ok := sdkmath.NewIntFromString(data.Amount)
	if !ok {
		return fmt.Errorf("ibcadapter: invalid transfer amount %q", data.Amount)
	}
	if ibctransfertypes.SenderChainIsSource(packet.GetSourcePort(), packet.GetSourceChannel(), data.Denom) {
		escrow := EscrowAccount(packet.GetSourcePort(), packet.GetSourceChannel())
		if err := a.Bank.SubBalance(data.Denom, escrow, amount); err != nil {
			return err
		}
		return a.Bank.AddBalance(data.Denom, data.Sender, amount)
	}
	return a.Bank.AddBalance(data.Denom, data.Sender, amount)
}
