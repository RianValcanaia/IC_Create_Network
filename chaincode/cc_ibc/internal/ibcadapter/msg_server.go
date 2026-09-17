package ibcadapter

import (
	"context"

	errorsmod "cosmossdk.io/errors"

	sdk "github.com/cosmos/cosmos-sdk/types"

	clienttypes "github.com/cosmos/ibc-go/v8/modules/core/02-client/types"
	connectiontypes "github.com/cosmos/ibc-go/v8/modules/core/03-connection/types"
	channeltypes "github.com/cosmos/ibc-go/v8/modules/core/04-channel/types"
	porttypes "github.com/cosmos/ibc-go/v8/modules/core/05-port/types"
)

func relayerAddress(signer string) sdk.AccAddress {
	if addr, err := sdk.AccAddressFromBech32(signer); err == nil {
		return addr
	}
	return sdk.AccAddress(signer)
}

// CreateClient defines a rpc handler method for MsgCreateClient.
func (k Keeper) CreateClient(goCtx context.Context, msg *clienttypes.MsgCreateClient) (*clienttypes.MsgCreateClientResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	clientState, err := clienttypes.UnpackClientState(msg.ClientState)
	if err != nil {
		return nil, err
	}

	consensusState, err := clienttypes.UnpackConsensusState(msg.ConsensusState)
	if err != nil {
		return nil, err
	}

	if _, err = k.ClientKeeper.CreateClient(ctx, clientState, consensusState); err != nil {
		return nil, err
	}

	return &clienttypes.MsgCreateClientResponse{}, nil
}

// UpdateClient defines a rpc handler method for MsgUpdateClient.
func (k Keeper) UpdateClient(goCtx context.Context, msg *clienttypes.MsgUpdateClient) (*clienttypes.MsgUpdateClientResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	clientMsg, err := clienttypes.UnpackClientMessage(msg.ClientMessage)
	if err != nil {
		return nil, err
	}

	if err = k.ClientKeeper.UpdateClient(ctx, msg.ClientId, clientMsg); err != nil {
		return nil, err
	}

	return &clienttypes.MsgUpdateClientResponse{}, nil
}

// ConnectionOpenInit defines a rpc handler method for MsgConnectionOpenInit.
func (k Keeper) ConnectionOpenInit(goCtx context.Context, msg *connectiontypes.MsgConnectionOpenInit) (*connectiontypes.MsgConnectionOpenInitResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	if _, err := k.ConnectionKeeper.ConnOpenInit(ctx, msg.ClientId, msg.Counterparty, msg.Version, msg.DelayPeriod); err != nil {
		return nil, errorsmod.Wrap(err, "connection handshake open init failed")
	}

	return &connectiontypes.MsgConnectionOpenInitResponse{}, nil
}

// ConnectionOpenTry defines a rpc handler method for MsgConnectionOpenTry.
func (k Keeper) ConnectionOpenTry(goCtx context.Context, msg *connectiontypes.MsgConnectionOpenTry) (*connectiontypes.MsgConnectionOpenTryResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	targetClient, err := clienttypes.UnpackClientState(msg.ClientState)
	if err != nil {
		return nil, err
	}

	if _, err := k.ConnectionKeeper.ConnOpenTry(
		ctx, msg.Counterparty, msg.DelayPeriod, msg.ClientId, targetClient,
		msg.CounterpartyVersions, msg.ProofInit, msg.ProofClient, msg.ProofConsensus,
		msg.ProofHeight, msg.ConsensusHeight,
	); err != nil {
		return nil, errorsmod.Wrap(err, "connection handshake open try failed")
	}

	return &connectiontypes.MsgConnectionOpenTryResponse{}, nil
}

// ConnectionOpenAck defines a rpc handler method for MsgConnectionOpenAck.
func (k Keeper) ConnectionOpenAck(goCtx context.Context, msg *connectiontypes.MsgConnectionOpenAck) (*connectiontypes.MsgConnectionOpenAckResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	targetClient, err := clienttypes.UnpackClientState(msg.ClientState)
	if err != nil {
		return nil, err
	}

	if err := k.ConnectionKeeper.ConnOpenAck(
		ctx, msg.ConnectionId, targetClient, msg.Version, msg.CounterpartyConnectionId,
		msg.ProofTry, msg.ProofClient, msg.ProofConsensus,
		msg.ProofHeight, msg.ConsensusHeight,
	); err != nil {
		return nil, errorsmod.Wrap(err, "connection handshake open ack failed")
	}

	return &connectiontypes.MsgConnectionOpenAckResponse{}, nil
}

// ConnectionOpenConfirm defines a rpc handler method for MsgConnectionOpenConfirm.
func (k Keeper) ConnectionOpenConfirm(goCtx context.Context, msg *connectiontypes.MsgConnectionOpenConfirm) (*connectiontypes.MsgConnectionOpenConfirmResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	if err := k.ConnectionKeeper.ConnOpenConfirm(
		ctx, msg.ConnectionId, msg.ProofAck, msg.ProofHeight,
	); err != nil {
		return nil, errorsmod.Wrap(err, "connection handshake open confirm failed")
	}

	return &connectiontypes.MsgConnectionOpenConfirmResponse{}, nil
}

// ChannelOpenInit defines a rpc handler method for MsgChannelOpenInit.
func (k Keeper) ChannelOpenInit(goCtx context.Context, msg *channeltypes.MsgChannelOpenInit) (*channeltypes.MsgChannelOpenInitResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	module, portCap, err := k.PortKeeper.LookupModuleByPort(ctx, msg.PortId)
	if err != nil {
		return nil, errorsmod.Wrap(err, "could not retrieve module from port-id")
	}

	cbs, ok := k.Router.GetRoute(module)
	if !ok {
		return nil, errorsmod.Wrapf(porttypes.ErrInvalidRoute, "route not found to module: %s", module)
	}

	channelID, capability, err := k.ChannelKeeper.ChanOpenInit(
		ctx, msg.Channel.Ordering, msg.Channel.ConnectionHops, msg.PortId,
		portCap, msg.Channel.Counterparty, msg.Channel.Version,
	)
	if err != nil {
		return nil, errorsmod.Wrap(err, "channel handshake open init failed")
	}

	version, err := cbs.OnChanOpenInit(ctx, msg.Channel.Ordering, msg.Channel.ConnectionHops, msg.PortId, channelID, capability, msg.Channel.Counterparty, msg.Channel.Version)
	if err != nil {
		return nil, errorsmod.Wrapf(err, "channel open init callback failed for port ID: %s, channel ID: %s", msg.PortId, channelID)
	}

	k.ChannelKeeper.WriteOpenInitChannel(ctx, msg.PortId, channelID, msg.Channel.Ordering, msg.Channel.ConnectionHops, msg.Channel.Counterparty, version)

	return &channeltypes.MsgChannelOpenInitResponse{
		ChannelId: channelID,
		Version:   version,
	}, nil
}

// ChannelOpenTry defines a rpc handler method for MsgChannelOpenTry.
func (k Keeper) ChannelOpenTry(goCtx context.Context, msg *channeltypes.MsgChannelOpenTry) (*channeltypes.MsgChannelOpenTryResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	module, portCap, err := k.PortKeeper.LookupModuleByPort(ctx, msg.PortId)
	if err != nil {
		return nil, errorsmod.Wrap(err, "could not retrieve module from port-id")
	}

	cbs, ok := k.Router.GetRoute(module)
	if !ok {
		return nil, errorsmod.Wrapf(porttypes.ErrInvalidRoute, "route not found to module: %s", module)
	}

	channelID, capability, err := k.ChannelKeeper.ChanOpenTry(ctx, msg.Channel.Ordering, msg.Channel.ConnectionHops, msg.PortId,
		portCap, msg.Channel.Counterparty, msg.CounterpartyVersion, msg.ProofInit, msg.ProofHeight,
	)
	if err != nil {
		return nil, errorsmod.Wrap(err, "channel handshake open try failed")
	}

	version, err := cbs.OnChanOpenTry(ctx, msg.Channel.Ordering, msg.Channel.ConnectionHops, msg.PortId, channelID, capability, msg.Channel.Counterparty, msg.CounterpartyVersion)
	if err != nil {
		return nil, errorsmod.Wrapf(err, "channel open try callback failed for port ID: %s, channel ID: %s", msg.PortId, channelID)
	}

	k.ChannelKeeper.WriteOpenTryChannel(ctx, msg.PortId, channelID, msg.Channel.Ordering, msg.Channel.ConnectionHops, msg.Channel.Counterparty, version)

	return &channeltypes.MsgChannelOpenTryResponse{
		ChannelId: channelID,
		Version:   version,
	}, nil
}

// ChannelOpenAck defines a rpc handler method for MsgChannelOpenAck.
func (k Keeper) ChannelOpenAck(goCtx context.Context, msg *channeltypes.MsgChannelOpenAck) (*channeltypes.MsgChannelOpenAckResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	module, capability, err := k.ChannelKeeper.LookupModuleByChannel(ctx, msg.PortId, msg.ChannelId)
	if err != nil {
		return nil, errorsmod.Wrap(err, "could not retrieve module from port-id")
	}

	cbs, ok := k.Router.GetRoute(module)
	if !ok {
		return nil, errorsmod.Wrapf(porttypes.ErrInvalidRoute, "route not found to module: %s", module)
	}

	if err = k.ChannelKeeper.ChanOpenAck(
		ctx, msg.PortId, msg.ChannelId, capability, msg.CounterpartyVersion, msg.CounterpartyChannelId, msg.ProofTry, msg.ProofHeight,
	); err != nil {
		return nil, errorsmod.Wrap(err, "channel handshake open ack failed")
	}

	k.ChannelKeeper.WriteOpenAckChannel(ctx, msg.PortId, msg.ChannelId, msg.CounterpartyVersion, msg.CounterpartyChannelId)

	if err = cbs.OnChanOpenAck(ctx, msg.PortId, msg.ChannelId, msg.CounterpartyChannelId, msg.CounterpartyVersion); err != nil {
		return nil, errorsmod.Wrapf(err, "channel open ack callback failed for port ID: %s, channel ID: %s", msg.PortId, msg.ChannelId)
	}

	return &channeltypes.MsgChannelOpenAckResponse{}, nil
}

// ChannelOpenConfirm defines a rpc handler method for MsgChannelOpenConfirm.
func (k Keeper) ChannelOpenConfirm(goCtx context.Context, msg *channeltypes.MsgChannelOpenConfirm) (*channeltypes.MsgChannelOpenConfirmResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	module, capability, err := k.ChannelKeeper.LookupModuleByChannel(ctx, msg.PortId, msg.ChannelId)
	if err != nil {
		return nil, errorsmod.Wrap(err, "could not retrieve module from port-id")
	}

	cbs, ok := k.Router.GetRoute(module)
	if !ok {
		return nil, errorsmod.Wrapf(porttypes.ErrInvalidRoute, "route not found to module: %s", module)
	}

	if err = k.ChannelKeeper.ChanOpenConfirm(ctx, msg.PortId, msg.ChannelId, capability, msg.ProofAck, msg.ProofHeight); err != nil {
		return nil, errorsmod.Wrap(err, "channel handshake open confirm failed")
	}

	k.ChannelKeeper.WriteOpenConfirmChannel(ctx, msg.PortId, msg.ChannelId)

	if err = cbs.OnChanOpenConfirm(ctx, msg.PortId, msg.ChannelId); err != nil {
		return nil, errorsmod.Wrapf(err, "channel open confirm callback failed for port ID: %s, channel ID: %s", msg.PortId, msg.ChannelId)
	}

	return &channeltypes.MsgChannelOpenConfirmResponse{}, nil
}

// RecvPacket defines a rpc handler method for MsgRecvPacket.
func (k Keeper) RecvPacket(goCtx context.Context, msg *channeltypes.MsgRecvPacket) (*channeltypes.MsgRecvPacketResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	relayer := relayerAddress(msg.Signer)

	module, capability, err := k.ChannelKeeper.LookupModuleByChannel(ctx, msg.Packet.DestinationPort, msg.Packet.DestinationChannel)
	if err != nil {
		return nil, errorsmod.Wrap(err, "could not retrieve module from port-id")
	}

	cbs, ok := k.Router.GetRoute(module)
	if !ok {
		return nil, errorsmod.Wrapf(porttypes.ErrInvalidRoute, "route not found to module: %s", module)
	}

	cacheCtx, writeFn := ctx.CacheContext()
	err = k.ChannelKeeper.RecvPacket(cacheCtx, capability, msg.Packet, msg.ProofCommitment, msg.ProofHeight)

	switch err {
	case nil:
		writeFn()
	case channeltypes.ErrNoOpMsg:
		return &channeltypes.MsgRecvPacketResponse{Result: channeltypes.NOOP}, nil
	default:
		return nil, errorsmod.Wrap(err, "receive packet verification failed")
	}

	cacheCtx, writeFn = ctx.CacheContext()
	ack := cbs.OnRecvPacket(cacheCtx, msg.Packet, relayer)
	if ack == nil || ack.Success() {
		writeFn()
	} else {
		ctx.EventManager().EmitEvents(cacheCtx.EventManager().Events())
	}

	if ack != nil {
		if err := k.ChannelKeeper.WriteAcknowledgement(ctx, capability, msg.Packet, ack); err != nil {
			return nil, err
		}
		// Guarda o Packet + Acknowledgement reais - o ChannelKeeper só
		// grava o hash (CommitAcknowledgement) no state, então sem isso
		// a Acknowledgement que acabou de ser escrita nunca poderia ser
		// relayada de volta pro remetente original (`tx
		// relay-acknowledgements`, QueryUnfinalizedRelayAcknowledgements
		// em relayer/chains/fabric/chain.go).
		if err := k.Received.Put(msg.Packet.DestinationPort, msg.Packet.DestinationChannel, msg.Packet, ack.Acknowledgement()); err != nil {
			return nil, err
		}
	}

	return &channeltypes.MsgRecvPacketResponse{Result: channeltypes.SUCCESS}, nil
}

// Acknowledgement defines a rpc handler method for MsgAcknowledgement.
func (k Keeper) Acknowledgement(goCtx context.Context, msg *channeltypes.MsgAcknowledgement) (*channeltypes.MsgAcknowledgementResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	relayer := relayerAddress(msg.Signer)

	module, capability, err := k.ChannelKeeper.LookupModuleByChannel(ctx, msg.Packet.SourcePort, msg.Packet.SourceChannel)
	if err != nil {
		return nil, errorsmod.Wrap(err, "could not retrieve module from port-id")
	}

	cbs, ok := k.Router.GetRoute(module)
	if !ok {
		return nil, errorsmod.Wrapf(porttypes.ErrInvalidRoute, "route not found to module: %s", module)
	}

	cacheCtx, writeFn := ctx.CacheContext()
	err = k.ChannelKeeper.AcknowledgePacket(cacheCtx, capability, msg.Packet, msg.Acknowledgement, msg.ProofAcked, msg.ProofHeight)

	switch err {
	case nil:
		writeFn()
	case channeltypes.ErrNoOpMsg:
		return &channeltypes.MsgAcknowledgementResponse{Result: channeltypes.NOOP}, nil
	default:
		return nil, errorsmod.Wrap(err, "acknowledge packet verification failed")
	}

	if err = cbs.OnAcknowledgementPacket(ctx, msg.Packet, msg.Acknowledgement, relayer); err != nil {
		return nil, errorsmod.Wrap(err, "acknowledge packet callback failed")
	}

	return &channeltypes.MsgAcknowledgementResponse{Result: channeltypes.SUCCESS}, nil
}

// Timeout defines a rpc handler method for MsgTimeout.
func (k Keeper) Timeout(goCtx context.Context, msg *channeltypes.MsgTimeout) (*channeltypes.MsgTimeoutResponse, error) {
	ctx := sdk.UnwrapSDKContext(goCtx)

	relayer := relayerAddress(msg.Signer)

	module, capability, err := k.ChannelKeeper.LookupModuleByChannel(ctx, msg.Packet.SourcePort, msg.Packet.SourceChannel)
	if err != nil {
		return nil, errorsmod.Wrap(err, "could not retrieve module from port-id")
	}

	cbs, ok := k.Router.GetRoute(module)
	if !ok {
		return nil, errorsmod.Wrapf(porttypes.ErrInvalidRoute, "route not found to module: %s", module)
	}

	cacheCtx, writeFn := ctx.CacheContext()
	err = k.ChannelKeeper.TimeoutPacket(cacheCtx, msg.Packet, msg.ProofUnreceived, msg.ProofHeight, msg.NextSequenceRecv)

	switch err {
	case nil:
		writeFn()
	case channeltypes.ErrNoOpMsg:
		return &channeltypes.MsgTimeoutResponse{Result: channeltypes.NOOP}, nil
	default:
		return nil, errorsmod.Wrap(err, "timeout packet verification failed")
	}

	if err = k.ChannelKeeper.TimeoutExecuted(ctx, capability, msg.Packet); err != nil {
		return nil, err
	}

	if err = cbs.OnTimeoutPacket(ctx, msg.Packet, relayer); err != nil {
		return nil, errorsmod.Wrap(err, "timeout packet callback failed")
	}

	return &channeltypes.MsgTimeoutResponse{Result: channeltypes.SUCCESS}, nil
}
