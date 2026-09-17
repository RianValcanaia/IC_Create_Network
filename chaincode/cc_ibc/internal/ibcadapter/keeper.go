// Package ibcadapter monta os keepers reais do núcleo do ibc-go v8.2.1
// (client/connection/channel/capability) rodando dentro do processo do
// chaincode Fabric, backed pelo fabricstore.MultiStore. Não reimplementa
// nenhuma verificação criptográfica, só encanamento: o 07-tendermint real do ibc-go verifica Cosmos sem
// modificação nenhuma; o único ajuste necessário é o override de
// ValidateSelfClient documentado em selfAwareClientKeeper abaixo.
package ibcadapter

import (
	"context"
	"time"

	"cosmossdk.io/log"
	storetypes "cosmossdk.io/store/types"

	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	"github.com/cosmos/cosmos-sdk/codec"
	sdk "github.com/cosmos/cosmos-sdk/types"
	paramtypes "github.com/cosmos/cosmos-sdk/x/params/types"

	upgradetypes "cosmossdk.io/x/upgrade/types"
	stakingtypes "github.com/cosmos/cosmos-sdk/x/staking/types"
	capabilitykeeper "github.com/cosmos/ibc-go/modules/capability/keeper"
	ibctransfertypes "github.com/cosmos/ibc-go/v8/modules/apps/transfer/types"
	clientkeeper "github.com/cosmos/ibc-go/v8/modules/core/02-client/keeper"
	clienttypes "github.com/cosmos/ibc-go/v8/modules/core/02-client/types"
	connectionkeeper "github.com/cosmos/ibc-go/v8/modules/core/03-connection/keeper"
	connectiontypes "github.com/cosmos/ibc-go/v8/modules/core/03-connection/types"
	channelkeeper "github.com/cosmos/ibc-go/v8/modules/core/04-channel/keeper"
	channeltypes "github.com/cosmos/ibc-go/v8/modules/core/04-channel/types"
	portkeeper "github.com/cosmos/ibc-go/v8/modules/core/05-port/keeper"
	porttypes "github.com/cosmos/ibc-go/v8/modules/core/05-port/types"
	host "github.com/cosmos/ibc-go/v8/modules/core/24-host"
	"github.com/cosmos/ibc-go/v8/modules/core/exported"

	"github.com/rianvalcanaia/cc_ibc/internal/fabricstore"
)

// Store key names, um por submódulo do ibc-go core, mesma convenção
// (nomes) que bcs/cosmos/app/simapp/app.go já usa.
const (
	StoreKeyIBC           = "ibc"
	StoreKeyCapability    = "capability"
	MemStoreKeyCapability = "capability_mem"
)

// Keeper agrupa os keepers reais do ibc-go core montados sobre o
// fabricstore. Não é o keeper.Keeper do ibc-go (esse tem campos
// não-exportados e não dá pra construir de fora do pacote dele, nem
// tem ponto de extensão pro selfAwareClientKeeper abaixo) - é um struct
// próprio deste adaptador, com os métodos de Msg portados em
// msg_server.go.
type Keeper struct {
	Cdc codec.BinaryCodec

	ClientKeeper     clientkeeper.Keeper
	ConnectionKeeper connectionkeeper.Keeper
	ChannelKeeper    channelkeeper.Keeper
	PortKeeper       *portkeeper.Keeper
	Router           *porttypes.Router

	CapabilityKeeper *capabilitykeeper.Keeper
	transferScope    capabilitykeeper.ScopedKeeper

	Bank     BankKeeper
	Sent     SentPacketStore
	Received ReceivedPacketStore
}

func NewKeeper(cdc codec.BinaryCodec, ms storetypes.MultiStore, keys map[string]storetypes.StoreKey, memKeys map[string]*storetypes.MemoryStoreKey, selfSeqValue uint64, selfSeqTimestamp int64, bankDB *fabricstore.FabricDB) *Keeper {
	storeKey := keys[StoreKeyIBC]
	if storeKey == nil {
		panic("ibcadapter: missing store key: " + StoreKeyIBC)
	}

	capKeeper := capabilitykeeper.NewKeeper(cdc, keys[StoreKeyCapability], memKeys[MemStoreKeyCapability])
	scopedIBC := capKeeper.ScopeToModule(exported.ModuleName)
	scopedTransfer := capKeeper.ScopeToModule(ibctransfertypes.ModuleName)
	capKeeper.Seal()

	noopParamSubspace := noopParamSubspace{}
	noopStaking := noopStakingKeeper{}
	noopUpgrade := noopUpgradeKeeper{}

	realClientKeeper := clientkeeper.NewKeeper(cdc, storeKey, noopParamSubspace, noopStaking, noopUpgrade)
	wrappedClientKeeper := selfAwareClientKeeper{
		Keeper:                realClientKeeper,
		selfSequenceValue:     selfSeqValue,
		selfSequenceTimestamp: selfSeqTimestamp,
	}

	connectionKeeper := connectionkeeper.NewKeeper(cdc, storeKey, noopParamSubspace, wrappedClientKeeper)
	portKeeper := portkeeper.NewKeeper(scopedIBC)
	channelKeeper := channelkeeper.NewKeeper(cdc, storeKey, realClientKeeper, connectionKeeper, &portKeeper, scopedIBC)

	k := &Keeper{
		Cdc:              cdc,
		ClientKeeper:     realClientKeeper,
		ConnectionKeeper: connectionKeeper,
		ChannelKeeper:    channelKeeper,
		PortKeeper:       &portKeeper,
		CapabilityKeeper: capKeeper,
		transferScope:    scopedTransfer,
		Bank:             NewBankKeeper(bankDB),
		Sent:             NewSentPacketStore(bankDB),
		Received:         NewReceivedPacketStore(bankDB),
	}

	// GetParams (client e connection) e GetNextXSequence (client/
	// connection/channel) panicam se nunca foram setados - normalmente
	// um InitGenesis faz isso uma vez; aqui não há module manager/
	// genesis, e cada invocação do chaincode reconstrói o Keeper do
	// zero. SetParams é seguro chamar sempre (mesmo default,
	// idempotente) - mas as sequências NÃO podem ser resetadas a cada
	// invocação (senão todo CreateClient geraria "07-tendermint-0" de
	// novo) - por isso initSequenceOnce só grava se a chave ainda não
	// existir no WorldState, checando o store direto (as chaves
	// exportadas Key*Sequence de cada submódulo).
	initCtx := sdk.NewContext(ms, cmtproto.Header{}, false, log.NewNopLogger())
	k.ClientKeeper.SetParams(initCtx, clienttypes.DefaultParams())
	k.ConnectionKeeper.SetParams(initCtx, connectiontypes.DefaultParams())

	ibcStore := initCtx.KVStore(storeKey)
	initSequenceOnce(ibcStore, clienttypes.KeyNextClientSequence, func() { k.ClientKeeper.SetNextClientSequence(initCtx, 0) })
	initSequenceOnce(ibcStore, connectiontypes.KeyNextConnectionSequence, func() { k.ConnectionKeeper.SetNextConnectionSequence(initCtx, 0) })
	initSequenceOnce(ibcStore, channeltypes.KeyNextChannelSequence, func() { k.ChannelKeeper.SetNextChannelSequence(initCtx, 0) })

	return k
}

// initSequenceOnce grava o valor inicial de uma sequência só se a chave
// ainda não existir no store - checa direto (Has), sem passar pelo
// getter real (que panica em vez de devolver "não encontrado" quando a
// chave não existe).
func initSequenceOnce(store storetypes.KVStore, key string, setDefault func()) {
	if !store.Has([]byte(key)) {
		setDefault()
	}
}

// StoreKeys/MemStoreKeys devolvem o conjunto de storetypes.StoreKey que
// NewKeeper espera em keys/memKeys - separado pra quem monta o
// fabricstore.MultiStore precisar dos mesmos StoreKey instances (o
// MultiStore indexa por identidade do ponteiro StoreKey, não por nome).
func StoreKeys() map[string]storetypes.StoreKey {
	return map[string]storetypes.StoreKey{
		StoreKeyIBC:        storetypes.NewKVStoreKey(StoreKeyIBC),
		StoreKeyCapability: storetypes.NewKVStoreKey(StoreKeyCapability),
	}
}

func MemStoreKeys() map[string]*storetypes.MemoryStoreKey {
	return storetypes.NewMemoryStoreKeys(MemStoreKeyCapability)
}

// ScopedTransferKeeper devolve o ScopedKeeper da porta "transfer",
// escopado durante NewKeeper (capabilitykeeper.Keeper.ScopeToModule só
// pode ser chamado antes do Seal(), então não dá pra escopar sob
// demanda depois).
func (k *Keeper) ScopedTransferKeeper() capabilitykeeper.ScopedKeeper {
	return k.transferScope
}

func (k *Keeper) InitCapabilities(ctx sdk.Context) {
	k.CapabilityKeeper.InitMemStore(ctx)
}

func (k *Keeper) BindTransferPort(ctx sdk.Context) error {
	if k.PortKeeper.IsBound(ctx, ibctransfertypes.PortID) {
		return nil
	}
	capability := k.PortKeeper.BindPort(ctx, ibctransfertypes.PortID)
	return k.transferScope.ClaimCapability(ctx, capability, host.PortPath(ibctransfertypes.PortID))
}

// SetupRouter monta o porttypes.Router com a TransferApp bindada na
// porta "transfer" e sela o keeper - mesmo
// padrão de ibckeeper.Keeper.SetRouter (k.PortKeeper.Router = rtr;
// k.Router = rtr; k.Router.Seal()).
func (k *Keeper) SetupRouter() {
	rtr := porttypes.NewRouter()
	rtr.AddRoute(ibctransfertypes.ModuleName, TransferApp{Scope: k.transferScope, Bank: k.Bank})
	k.PortKeeper.Router = rtr
	k.Router = rtr
	k.Router.Seal()
}

// --- stubs de dependências que o ibc-go core exige mas que não fazem
// sentido dentro de um chaincode Fabric (sem staking/governança/upgrade
// Cosmos nativos aqui)

type noopParamSubspace struct{}

func (noopParamSubspace) GetParamSet(_ sdk.Context, _ paramtypes.ParamSet) {
	// Nunca invocado no fluxo normal: legacySubspace.GetParamSet só é
	// chamado por migrations.go (migração de versão de módulo), que
	// este adaptador nunca executa (não há module manager/upgrade
	// handler aqui). Confirmado lendo o ibc-go v8.2.1 inteiro.
	panic("ibcadapter: legacy param subspace should never be invoked outside module migrations")
}

type noopStakingKeeper struct{}

func (noopStakingKeeper) GetHistoricalInfo(_ context.Context, _ int64) (stakingtypes.HistoricalInfo, error) {
	return stakingtypes.HistoricalInfo{}, errNotSupported
}

func (noopStakingKeeper) UnbondingTime(_ context.Context) (time.Duration, error) {
	// Usado só por misbehaviour baseado em historical info - fora de
	// escopo (mesmo corte já feito no hb-qbft/fabric-msp). Um valor
	// não-zero evita divisão por zero em cálculos de trusting period
	// default, caso algum caminho indireto leia isso no futuro.
	return 21 * 24 * time.Hour, nil
}

type noopUpgradeKeeper struct{}

func (noopUpgradeKeeper) ClearIBCState(_ context.Context, _ int64) error { return nil }
func (noopUpgradeKeeper) GetUpgradePlan(_ context.Context) (upgradetypes.Plan, error) {
	return upgradetypes.Plan{}, errNotSupported
}
func (noopUpgradeKeeper) GetUpgradedClient(_ context.Context, _ int64) ([]byte, error) {
	return nil, errNotSupported
}
func (noopUpgradeKeeper) SetUpgradedClient(_ context.Context, _ int64, _ []byte) error {
	return errNotSupported
}
func (noopUpgradeKeeper) GetUpgradedConsensusState(_ context.Context, _ int64) ([]byte, error) {
	return nil, errNotSupported
}
func (noopUpgradeKeeper) SetUpgradedConsensusState(_ context.Context, _ int64, _ []byte) error {
	return errNotSupported
}
func (noopUpgradeKeeper) ScheduleUpgrade(_ context.Context, _ upgradetypes.Plan) error {
	return errNotSupported
}

var errNotSupported = clientNotSupportedErr("ibcadapter: client upgrade / misbehaviour-by-historical-info not supported (out of MVP scope, see nextsteps.md T30)")

type clientNotSupportedErr string

func (e clientNotSupportedErr) Error() string { return string(e) }

var _ clienttypes.StakingKeeper = noopStakingKeeper{}
var _ clienttypes.UpgradeKeeper = noopUpgradeKeeper{}
var _ connectiontypes.ParamSubspace = noopParamSubspace{}
