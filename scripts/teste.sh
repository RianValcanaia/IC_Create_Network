#!/bin/bash

echo "--- 🧪 Teste de Ambiente e Binários ---"

# 1. Verificar se o PATH inclui nossa pasta bin local
# O Python deve ter injetado algo como .../seu-projeto/bin no inicio
echo "📂 PATH atual: $PATH"

# 2. Verificar onde está o executável 'peer'
echo "🔍 Localização do binário 'peer':"
which peer

if [ $? -ne 0 ]; then
    echo "❌ Erro: O comando 'peer' não foi encontrado no PATH."
    exit 1
fi

# 3. Rodar o comando de versão
echo -e "\n📊 Versão do Peer:"
peer version

# 4. Testar outro binário crítico (configtxgen)
echo -e "\n📊 Versão do Configtxgen:"
configtxgen -version

echo "--- ✅ Teste concluído com sucesso ---"