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

// TransferApp é a porttypes.IBCModule real bindada na porta "transfer"
// , substituindo StubTransferApp (que nunca decodificava o pacote
// e sempre devolvia ack de sucesso). Reaproveita os tipos/funções reais
// do próprio ibc-go (FungibleTokenPacketData, ibctransfertypes.ModuleCdc
// - mesmo formato JSON que o transfer module real de cosmos_chain_0 já
// fala, GetDenomPrefix/SenderChainIsSource/ReceiverChainIsSource) -
// só a contabilidade (mint/burn/escrow) é código novo, via BankKeeper
// (bankstore.go), porque não existe bankkeeper.Keeper dentro de um
// chaincode Fabric. Semântica espelha modules/apps/transfer/keeper/
// relay.go (ibc-go v8.2.1) linha a linha, só trocando o backend de
// contabilidade.
type TransferApp struct {
	Scope capabilitykeeper.ScopedKeeper
	Bank  BankKeeper
}

var _ porttypes.IBCModule = TransferApp{}

// EscrowAccount é a "conta" de escrow desta chain para um port/channel -
// um identificador opaco determinístico (não uma identidade Fabric real),
// mesmo papel do endereço ADR-028 do ibc-go ou do
// keccak256(this, channelId) do ICS20Transfer.sol.
func EscrowAccount(portID, channelID string) string {
	return fmt.Sprintf("ics20-escrow/%s/%s", portID, channelID)
}

func validateTransferChannelParams(order channeltypes.Order, version string) error {
	if order != channeltypes.UNORDERED {
		return fmt.Errorf("ibcadapter: invalid channel ordering %s for ICS-20, expected %s", order, channeltypes.UNORDERED)
	}
	if version != "" && version != ibctransfertypes.Version {
		return fmt.Errorf("ibcadapter: invalid ICS-20 version %q, expected %q", version, ibctransfertypes.Version)
	}
	return nil
}

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

func (a TransferApp) OnChanOpenTry(ctx sdk.Context, order channeltypes.Order, _ []string, portID, channelID string, chanCap *capabilitytypes.Capability, _ channeltypes.Counterparty, counterpartyVersion string) (string, error) {
	if err := validateTransferChannelParams(order, counterpartyVersion); err != nil {
		return "", err
	}
	if err := a.Scope.ClaimCapability(ctx, chanCap, host.ChannelCapabilityPath(portID, channelID)); err != nil {
		return "", err
	}
	return ibctransfertypes.Version, nil
}

func (TransferApp) OnChanOpenAck(_ sdk.Context, _, _ string, _ string, _ string) error {
	return nil
}

func (TransferApp) OnChanOpenConfirm(_ sdk.Context, _, _ string) error { return nil }

func (TransferApp) OnChanCloseInit(_ sdk.Context, _, _ string) error { return nil }

func (TransferApp) OnChanCloseConfirm(_ sdk.Context, _, _ string) error { return nil }

// OnRecvPacket decodifica um FungibleTokenPacketData real (mesmo formato
// JSON que cosmos_chain_0 já produz de verdade) e credita a conta
// destino - mirror exato de keeper.Keeper.OnRecvPacket (ibc-go
// relay.go): "ReceiverChainIsSource" decide entre unescrow (voucher
// voltando) ou mint de um voucher novo prefixado com o port/channel
// desta chain. Devolve ack de ERRO real em caso de falha (saldo de
// escrow insuficiente, denom inválido) - corrige o bug do stub antigo,
// que sempre devolvia sucesso sem olhar o pacote.
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

func (a TransferApp) OnTimeoutPacket(_ sdk.Context, packet channeltypes.Packet, _ sdk.AccAddress) error {
	var data ibctransfertypes.FungibleTokenPacketData
	if err := ibctransfertypes.ModuleCdc.UnmarshalJSON(packet.GetData(), &data); err != nil {
		return fmt.Errorf("ibcadapter: cannot unmarshal ICS-20 packet data: %w", err)
	}
	return a.refund(packet, data)
}

// refund espelha refundPacketToken do ibc-go real: desescrowa de volta
// pro remetente se esta chain era a origem do denom, ou re-credita
// (mint de volta) se não era - simétrico ao burn feito no envio
// (Keeper.SendTransfer, transfer_send.go).
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
