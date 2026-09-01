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

func NewBankKeeper(db *fabricstore.FabricDB) BankKeeper {
	return BankKeeper{db: db}
}

func balanceKey(denom, account string) []byte {
	return []byte(fmt.Sprintf("ics20/balance/%s/%s", denom, account))
}

// GetBalance devolve o saldo atual (zero se a conta nunca recebeu esse
// denom).
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

func (k BankKeeper) setBalance(denom, account string, amount sdkmath.Int) error {
	bz, err := amount.Marshal()
	if err != nil {
		return err
	}
	return k.db.Set(balanceKey(denom, account), bz)
}

// AddBalance credita amount ao saldo de account em denom (mint/unescrow).
func (k BankKeeper) AddBalance(denom, account string, amount sdkmath.Int) error {
	current, err := k.GetBalance(denom, account)
	if err != nil {
		return err
	}
	return k.setBalance(denom, account, current.Add(amount))
}

// SubBalance debita amount do saldo de account em denom (burn/escrow) -
// erro se o saldo for insuficiente, mesmo comportamento de um SendCoins
// real contra um remetente sem fundos.
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
