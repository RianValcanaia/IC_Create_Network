/*
BankKeeper: o livro de saldos do ICS-20 dentro do chaincode.

Um chaincode não tem o módulo bank do Cosmos, então cada saldo fica numa
chave do WorldState por (denom, conta): ics20/balance/<denom>/<conta>. A
"conta" é só um texto (ex.: fabric-user-0, ou o endereço bech32 de quem
recebe), não uma identidade Fabric. O valor é um sdkmath.Int serializado.
*/
package ibcadapter

import (
	"fmt"

	sdkmath "cosmossdk.io/math"

	"github.com/rianvalcanaia/cc_ibc/internal/fabricstore"
)

// BankKeeper é um ledger mínimo de saldos por (denom, conta)
type BankKeeper struct {
	db *fabricstore.FabricDB
}

// NewBankKeeper cria o BankKeeper sobre o FabricDB.
func NewBankKeeper(db *fabricstore.FabricDB) BankKeeper {
	return BankKeeper{db: db}
}

// balanceKey monta a chave do saldo de uma conta num denom.
func balanceKey(denom, account string) []byte {
	return []byte(fmt.Sprintf("ics20/balance/%s/%s", denom, account))
}

// GetBalance devolve o saldo atual (zero se a conta nunca recebeu esse denom).
func (k BankKeeper) GetBalance(denom, account string) (sdkmath.Int, error) {
	bz, err := k.db.Get(balanceKey(denom, account))
	if err != nil {
		return sdkmath.ZeroInt(), err
	}
	if bz == nil {
		return sdkmath.ZeroInt(), nil
	}
	var amount sdkmath.Int
	if err := amount.Unmarshal(bz); err != nil {
		return sdkmath.ZeroInt(), err
	}
	return amount, nil
}

// setBalance grava o saldo.
func (k BankKeeper) setBalance(denom, account string, amount sdkmath.Int) error {
	bz, err := amount.Marshal()
	if err != nil {
		return err
	}
	return k.db.Set(balanceKey(denom, account), bz)
}

// AddBalance soma amount ao saldo (recebimento, criação de voucher ou saída do
// escrow).
func (k BankKeeper) AddBalance(denom, account string, amount sdkmath.Int) error {
	current, err := k.GetBalance(denom, account)
	if err != nil {
		return err
	}
	return k.setBalance(denom, account, current.Add(amount))
}

// SubBalance subtrai amount do saldo (envio, queima ou entrada no escrow); dá
// erro se o saldo não for suficiente.
func (k BankKeeper) SubBalance(denom, account string, amount sdkmath.Int) error {
	current, err := k.GetBalance(denom, account)
	if err != nil {
		return err
	}
	if current.LT(amount) {
		return fmt.Errorf("ibcadapter: insufficient balance: account %q has %s%s, need %s%s", account, current, denom, amount, denom)
	}
	return k.setBalance(denom, account, current.Sub(amount))
}
