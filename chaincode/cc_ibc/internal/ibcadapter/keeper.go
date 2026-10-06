/*
Monta, dentro do chaincode, os keepers reais do núcleo do ibc-go v8.2.1:
client (02), connection (03), channel (04), port (05) e capability.

Nenhuma verificação criptográfica é reimplementada aqui: o 07-tendermint e os
outros light clients rodam como num nó Cosmos. Este arquivo só faz o
encanamento:
  - os keepers gravam no fabricstore.MultiStore (o WorldState do Fabric);
  - dependências que só existem num nó Cosmos (staking, upgrade, params
    legados) viram implementações vazias (noop*);
  - o client keeper usado pela connection é embrulhado no
    selfAwareClientKeeper (self_client.go), que ensina o ibc-go a validar o
    client fabric-msp que a outra chain tem deste Fabric.

Junto com os keepers ficam o BankKeeper (saldos do ICS-20) e os stores de
pacotes enviados e recebidos, que o relayer consulta.
*/
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

// NewKeeper cria todos os keepers sobre o multistore e faz o que um genesis
// faria num nó Cosmos: grava os parâmetros (sempre) e os contadores de
// client/connection/channel (só na primeira vez; se fossem zerados a cada
// chamada, todo client novo voltaria a se chamar ...-0).
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

// initSequenceOnce grava o valor inicial de um contador só se a chave ainda
// não existe. Testa a chave direto porque o getter do ibc-go dá panic em vez
// de devolver "não encontrado".
func initSequenceOnce(store storetypes.KVStore, key string, setDefault func()) {
	if !store.Has([]byte(key)) {
		setDefault()
	}
}

// StoreKeys devolve as StoreKeys persistentes (ibc e capability). O MultiStore
// acha a store pela instância da StoreKey, então quem monta o MultiStore e o
// Keeper precisa usar as mesmas.
func StoreKeys() map[string]storetypes.StoreKey {
	return map[string]storetypes.StoreKey{
		StoreKeyIBC:        storetypes.NewKVStoreKey(StoreKeyIBC),
		StoreKeyCapability: storetypes.NewKVStoreKey(StoreKeyCapability),
	}
}

// MemStoreKeys devolve a StoreKey de memória do capability.
func MemStoreKeys() map[string]*storetypes.MemoryStoreKey {
	return storetypes.NewMemoryStoreKeys(MemStoreKeyCapability)
}

// ScopedTransferKeeper devolve o ScopedKeeper da porta transfer. Ele é criado
// no NewKeeper porque só dá para criar antes do Seal.
func (k *Keeper) ScopedTransferKeeper() capabilitykeeper.ScopedKeeper {
	return k.transferScope
}

// InitCapabilities carrega as capabilities gravadas para a store de memória;
// precisa rodar a cada chamada, já que a memória começa vazia.
func (k *Keeper) InitCapabilities(ctx sdk.Context) {
	k.CapabilityKeeper.InitMemStore(ctx)
}

// BindTransferPort liga a porta transfer ao ICS-20, se ainda não estiver
// ligada, e guarda a capability da porta.
func (k *Keeper) BindTransferPort(ctx sdk.Context) error {
	if k.PortKeeper.IsBound(ctx, ibctransfertypes.PortID) {
		return nil
	}
	capability := k.PortKeeper.BindPort(ctx, ibctransfertypes.PortID)
	return k.transferScope.ClaimCapability(ctx, capability, host.PortPath(ibctransfertypes.PortID))
}

// SetupRouter cria o router de portas com a rota transfer -> TransferApp e o
// sela, como o ibckeeper.Keeper.SetRouter do ibc-go.
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

// GetParamSet só seria chamado numa migração de versão de módulo, que não
// existe aqui.
func (noopParamSubspace) GetParamSet(_ sdk.Context, _ paramtypes.ParamSet) {
	// Nunca invocado no fluxo normal: legacySubspace.GetParamSet só é
	// chamado por migrations.go (migração de versão de módulo), que
	// este adaptador nunca executa (não há module manager/upgrade
	// handler aqui). Confirmado lendo o ibc-go v8.2.1 inteiro.
	panic("ibcadapter: legacy param subspace should never be invoked outside module migrations")
}

type noopStakingKeeper struct{}

// GetHistoricalInfo não é suportado: o Fabric não tem histórico de
// validadores.
func (noopStakingKeeper) GetHistoricalInfo(_ context.Context, _ int64) (stakingtypes.HistoricalInfo, error) {
	return stakingtypes.HistoricalInfo{}, errNotSupported
}

// UnbondingTime devolve um valor fixo (21 dias), só para nenhum cálculo
// dividir por zero.
func (noopStakingKeeper) UnbondingTime(_ context.Context) (time.Duration, error) {
	// Usado só por misbehaviour baseado em historical info - fora de
	// escopo (mesmo corte já feito no hb-qbft/fabric-msp). Um valor
	// não-zero evita divisão por zero em cálculos de trusting period
	// default, caso algum caminho indireto leia isso no futuro.
	return 21 * 24 * time.Hour, nil
}

type noopUpgradeKeeper struct{}

// ClearIBCState não tem nada a limpar.
func (noopUpgradeKeeper) ClearIBCState(_ context.Context, _ int64) error { return nil }

// GetUpgradePlan: não suportado: não há upgrade de client no Fabric.
func (noopUpgradeKeeper) GetUpgradePlan(_ context.Context) (upgradetypes.Plan, error) {
	return upgradetypes.Plan{}, errNotSupported
}

// GetUpgradedClient: não suportado: não há upgrade de client no Fabric.
func (noopUpgradeKeeper) GetUpgradedClient(_ context.Context, _ int64) ([]byte, error) {
	return nil, errNotSupported
}

// SetUpgradedClient: não suportado: não há upgrade de client no Fabric.
func (noopUpgradeKeeper) SetUpgradedClient(_ context.Context, _ int64, _ []byte) error {
	return errNotSupported
}

// GetUpgradedConsensusState: não suportado: não há upgrade de client no
// Fabric.
func (noopUpgradeKeeper) GetUpgradedConsensusState(_ context.Context, _ int64) ([]byte, error) {
	return nil, errNotSupported
}

// SetUpgradedConsensusState: não suportado: não há upgrade de client no
// Fabric.
func (noopUpgradeKeeper) SetUpgradedConsensusState(_ context.Context, _ int64, _ []byte) error {
	return errNotSupported
}

// ScheduleUpgrade: não suportado: não há upgrade de client no Fabric.
func (noopUpgradeKeeper) ScheduleUpgrade(_ context.Context, _ upgradetypes.Plan) error {
	return errNotSupported
}

var errNotSupported = clientNotSupportedErr("ibcadapter: client upgrade / misbehaviour-by-historical-info not supported")

type clientNotSupportedErr string

// Error devolve o texto do erro.
func (e clientNotSupportedErr) Error() string { return string(e) }

var _ clienttypes.StakingKeeper = noopStakingKeeper{}
var _ clienttypes.UpgradeKeeper = noopUpgradeKeeper{}
var _ connectiontypes.ParamSubspace = noopParamSubspace{}
