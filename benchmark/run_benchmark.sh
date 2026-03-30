#!/bin/bash
# run_benchmark.sh — Executa o benchmark k6 N vezes com cooldown entre runs
# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
#
# Uso:
#   ./run_benchmark.sh           # 3 execuções (padrão acadêmico)
#   ./run_benchmark.sh 1         # execução única (validação)
#   ./run_benchmark.sh 5         # 5 execuções
#
# Cada execução salva em:
#   resultados/run_1/k6_TIMESTAMP.json
#   resultados/run_2/k6_TIMESTAMP.json
#   ...

set -e

RUNS=${1:-3}
COOLDOWN_MIN=60        # cooldown mínimo obrigatório após cada run (segundos)
DRAIN_POLL=10          # intervalo entre polls do Prometheus (segundos)
DRAIN_STABLE=3         # quantas leituras consecutivas com TPS≈0 para considerar drenado
DRAIN_TIMEOUT=600      # desiste de esperar após este tempo (segundos) e continua assim mesmo
PROMETHEUS_URL="http://localhost:9090"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/resultados"

# ── Cores ─────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERRO]${NC} $1"; }

# ── Pré-checklist ─────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     Benchmark Hermes + Hyperledger Fabric 3.0                ║"
echo "║     $RUNS execuções × ~41 min = ~$((RUNS * 41 + (RUNS-1) * 2)) min totais estimados          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

info "Verificando pré-condições..."

# Hermes respondendo
if ! curl -sf http://localhost:3000/api/calcular-do \
    -X POST -F "input=@$SCRIPT_DIR/fixture_do.json" > /dev/null 2>&1; then
    error "Hermes não está respondendo em localhost:3000"
    error "Inicie com: cd ~/HERMESSC/projects/hermes-api-server && npm run watch"
    exit 1
fi
success "Hermes respondendo"

# Prometheus coletando
TARGETS_UP=$(curl -s 'http://localhost:9090/api/v1/targets' 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(1 for t in d['data']['activeTargets'] if t['health']=='up'))" 2>/dev/null || echo "0")
if [ "$TARGETS_UP" -lt 12 ]; then
    warn "Prometheus: apenas $TARGETS_UP/12 targets UP — métricas M4/M6 podem estar incompletas"
else
    success "Prometheus: $TARGETS_UP/12 targets UP"
fi

# k6 instalado
if ! command -v k6 &> /dev/null; then
    error "k6 não encontrado. Instale com: sudo apt install k6"
    exit 1
fi
success "k6 $(k6 version | head -1)"

echo ""
# ── Health check: aguarda Fabric drenar transações pendentes ──────────────────
#
# Consulta o Prometheus para verificar se a taxa de endorsements caiu a zero,
# indicando que o sistema processou todas as transações submetidas pelo C4.
#
# Métricas tentadas em ordem de preferência:
#   1. endorser_proposals_received  (peers — mais direta)
#   2. broadcast_processed_count    (orderers — fallback)
#
# Se nenhuma métrica retornar dados, usa cooldown fixo de DRAIN_TIMEOUT/2.

wait_system_drain() {
    local run_label="$1"
    local elapsed=0
    local stable_count=0
    local metric_available=false

    info "[$run_label] Cooldown mínimo de ${COOLDOWN_MIN}s..."
    sleep $COOLDOWN_MIN
    elapsed=$COOLDOWN_MIN

    # Detecta qual métrica está disponível
    local query=""
    local check_endorser
    check_endorser=$(curl -sf \
        "${PROMETHEUS_URL}/api/v1/query?query=sum(endorser_proposals_received)" \
        2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('ok' if d.get('data',{}).get('result') else 'empty')
" 2>/dev/null || echo "error")

    if [ "$check_endorser" = "ok" ]; then
        query='sum(rate(endorser_proposals_received[30s]))'
        metric_available=true
        info "[$run_label] Monitorando drain via endorser_proposals_received..."
    else
        local check_broadcast
        check_broadcast=$(curl -sf \
            "${PROMETHEUS_URL}/api/v1/query?query=sum(broadcast_processed_count)" \
            2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('ok' if d.get('data',{}).get('result') else 'empty')
" 2>/dev/null || echo "error")

        if [ "$check_broadcast" = "ok" ]; then
            query='sum(rate(broadcast_processed_count{status="SUCCESS"}[30s]))'
            metric_available=true
            info "[$run_label] Monitorando drain via broadcast_processed_count..."
        fi
    fi

    if [ "$metric_available" = false ]; then
        warn "[$run_label] Métricas Fabric indisponíveis no Prometheus — aguardando ${DRAIN_TIMEOUT}s fixos"
        sleep $((DRAIN_TIMEOUT - COOLDOWN_MIN))
        return
    fi

    info "[$run_label] Aguardando sistema drenar (TPS≈0 por ${DRAIN_STABLE} leituras consecutivas)..."

    while [ $elapsed -lt $DRAIN_TIMEOUT ]; do
        sleep $DRAIN_POLL
        elapsed=$((elapsed + DRAIN_POLL))

        local tps
        tps=$(curl -sf \
            "${PROMETHEUS_URL}/api/v1/query?query=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$query'))")" \
            2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    result = d.get('data', {}).get('result', [])
    if not result:
        print('0.0')
    else:
        print(result[0]['value'][1])
except:
    print('-1')
" 2>/dev/null || echo "-1")

        if [ "$tps" = "-1" ]; then
            warn "[$run_label] Falha ao consultar Prometheus (${elapsed}s decorridos)"
            stable_count=0
            continue
        fi

        # Compara como float: TPS < 0.05 é considerado "zerado"
        local is_zero
        is_zero=$(python3 -c "print('yes' if float('$tps') < 0.05 else 'no')" 2>/dev/null || echo "no")

        if [ "$is_zero" = "yes" ]; then
            stable_count=$((stable_count + 1))
            info "[$run_label] TPS≈0 (${stable_count}/${DRAIN_STABLE}) — ${elapsed}s decorridos"
            if [ $stable_count -ge $DRAIN_STABLE ]; then
                success "[$run_label] Sistema drenado após ${elapsed}s. Iniciando próxima run."
                return
            fi
        else
            if [ $stable_count -gt 0 ]; then
                info "[$run_label] TPS voltou: ${tps} tx/s — reiniciando contagem"
            else
                info "[$run_label] TPS atual: ${tps} tx/s — aguardando... (${elapsed}s/${DRAIN_TIMEOUT}s)"
            fi
            stable_count=0
        fi
    done

    warn "[$run_label] Timeout de drain atingido (${DRAIN_TIMEOUT}s). Continuando mesmo assim."
}

# ── Instrumentação por run ─────────────────────────────────────────────────────
#
# query_m6_snapshot   OUT_FILE        — snapshot de contadores MVCC/VALID/INVALID
# save_run_metadata   N DIR START END — metadata.json com timestamps por cenário
# save_m6_delta       N DIR           — delta M6 (before vs after) → m6_delta.json
# extract_prometheus  N DIR           — range queries Prometheus para janela do run
# verify_baseline_clean LABEL         — aguarda altura blockchain estabilizar

query_m6_snapshot() {
    local out_file="$1"
    python3 << PYEOF 2>/dev/null
import json, urllib.request, urllib.parse

prom_url = "$PROMETHEUS_URL"
out_file = "$out_file"

metrics = {
    "mvcc":    'sum(ledger_transaction_count{validation_code="MVCC_READ_CONFLICT"})',
    "invalid": 'sum(ledger_transaction_count{validation_code="INVALID"})',
    "valid":   'sum(ledger_transaction_count{validation_code="VALID"})',
}
result = {}
for name, query in metrics.items():
    try:
        url = prom_url + "/api/v1/query?query=" + urllib.parse.quote(query)
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        r = data.get("data", {}).get("result", [])
        result[name] = float(r[0]["value"][1]) if r else 0.0
    except Exception:
        result[name] = None

with open(out_file, "w") as f:
    json.dump(result, f)
PYEOF
}

# Salva metadata.json com timestamps precisos do run e de cada cenário.
# Offsets devem bater com os startTime definidos em test_hermes.js.
save_run_metadata() {
    local run_num="$1"
    local run_dir="$2"
    local start_ts="$3"
    local end_ts="$4"
    python3 << PYEOF 2>/dev/null
import json
from datetime import datetime, timedelta

run   = $run_num
start = "$start_ts"
end   = "$end_ts"

# (offset_s, duracao_s) — manter sincronizado com test_hermes.js
SCENARIOS = [
    ("C1_baseline", 0,    300),
    ("C2_leve",     600,  600),
    ("C3_moderada", 1500, 600),
    ("C4_alta",     2520, 600),
]

t0 = datetime.fromisoformat(start.replace("Z", "+00:00"))
cenarios = {}
for name, offset, dur in SCENARIOS:
    ts = t0 + timedelta(seconds=offset)
    te = ts + timedelta(seconds=dur)
    cenarios[name] = {
        "start": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end":   te.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

meta = {"run": run, "start": start, "end": end, "cenarios": cenarios}
with open("$run_dir/metadata.json", "w") as f:
    json.dump(meta, f, indent=2)
PYEOF
}

save_m6_delta() {
    local run_num="$1"
    local run_dir="$2"
    local before_file="$run_dir/.m6_before.json"
    local after_file="$run_dir/.m6_after.json"

    query_m6_snapshot "$after_file" || { warn "Falha ao capturar snapshot M6 final"; return 1; }

    python3 << PYEOF 2>/dev/null
import json, sys

run = $run_num
try:
    with open("$before_file") as f:
        before = json.load(f)
    with open("$after_file") as f:
        after = json.load(f)
except Exception as e:
    print(f"[WARN] Erro ao ler snapshots M6: {e}")
    sys.exit(1)

delta = {"run": run}
for k in ("mvcc", "valid", "invalid"):
    b = before.get(k)
    a = after.get(k)
    if b is not None and a is not None:
        delta[f"{k}_delta"]  = int(max(0, a - b))
        delta[f"{k}_before"] = int(b)
        delta[f"{k}_after"]  = int(a)
    else:
        delta[f"{k}_delta"] = None

with open("$run_dir/m6_delta.json", "w") as f:
    json.dump(delta, f, indent=2)
PYEOF
}

extract_prometheus_for_run() {
    local run_num="$1"
    local run_dir="$2"
    local meta_file="$run_dir/metadata.json"

    if [ ! -f "$meta_file" ]; then
        warn "[Run $run_num] metadata.json não encontrado — pulando extração Prometheus"
        return
    fi

    info "[Run $run_num] Extraindo métricas Prometheus (dados frescos)..."
    if python3 << PYEOF 2>/dev/null
import sys
sys.path.insert(0, "$SCRIPT_DIR")
import json

try:
    from analise_resultados import extrair_metricas_prometheus
    with open("$meta_file") as f:
        meta = json.load(f)
    extrair_metricas_prometheus(
        [{"run": meta["run"], "start": meta["start"], "end": meta["end"]}],
        step="15s",
        output_dir="$run_dir",
    )
except ImportError:
    sys.exit(1)
except Exception:
    sys.exit(1)
PYEOF
    then
        success "[Run $run_num] Prometheus extraído → $run_dir/"
    else
        warn "[Run $run_num] Extração Prometheus falhou (Prometheus indisponível ou analise_resultados.py ausente)"
    fi
}

# Aguarda a altura da blockchain estabilizar antes de iniciar o run.
# Usa deriv(ledger_blockchain_height) para detectar se o orderer ainda está
# commitando blocos remanescentes do run anterior.
verify_baseline_clean() {
    local run_label="$1"
    local max_wait=120
    local elapsed=0
    local poll=15
    local stable=0
    local stable_needed=2

    info "[$run_label] Verificando que blockchain está estável..."

    while [ $elapsed -lt $max_wait ]; do
        local deriv
        deriv=$(curl -sf \
            "${PROMETHEUS_URL}/api/v1/query?query=$(python3 -c \
            "import urllib.parse; print(urllib.parse.quote('sum(deriv(ledger_blockchain_height{channel=\"channel-all\"}[30s]))'))" \
            2>/dev/null)" \
            2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    r = d.get('data', {}).get('result', [])
    v = r[0]['value'][1] if r else 'na'
    print('na' if str(v) in ('NaN','Inf','+Inf','-Inf','') else v)
except: print('na')
" 2>/dev/null || echo "na")

        if [ "$deriv" = "na" ]; then
            stable=$((stable + 1))
            info "[$run_label] Blockchain sem atividade recente ($stable/$stable_needed)"
        else
            local growing
            growing=$(python3 -c \
                "print('yes' if abs(float('$deriv')) > 0.01 else 'no')" 2>/dev/null || echo "no")
            if [ "$growing" = "no" ]; then
                stable=$((stable + 1))
                info "[$run_label] Blockchain estável ($stable/$stable_needed) — deriv=${deriv} bl/s"
            else
                stable=0
                info "[$run_label] Blockchain crescendo (${deriv} bl/s) — aguardando ${poll}s..."
            fi
        fi

        if [ $stable -ge $stable_needed ]; then
            success "[$run_label] Sistema pronto."
            return
        fi

        sleep $poll
        elapsed=$((elapsed + poll))
    done

    warn "[$run_label] Verificação de baseline expirou (${max_wait}s) — continuando assim mesmo"
}

info "Iniciando $RUNS execuções. Ctrl+C para cancelar."
echo ""

# ── Loop de execuções ─────────────────────────────────────────────────────────
FAILED_RUNS=()
SUCCESSFUL_RUNS=()

for i in $(seq 1 $RUNS); do
    RUN_DIR="$RESULTS_DIR/run_$i"
    mkdir -p "$RUN_DIR"

    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    OUTPUT_FILE="$RUN_DIR/k6_run${i}_${TIMESTAMP}.json"
    SUMMARY_FILE="$RUN_DIR/summary_run${i}_${TIMESTAMP}.json"

    echo "────────────────────────────────────────────────────────────────"
    info "Execução $i/$RUNS — $(date '+%d/%m/%Y %H:%M:%S')"
    info "Output: $OUTPUT_FILE"
    echo ""

    # Verificar que blockchain está estável antes de iniciar
    verify_baseline_clean "Run $i"

    # Snapshot M6 antes do run (base para calcular delta ao final)
    query_m6_snapshot "$RUN_DIR/.m6_before.json" \
        && info "Snapshot M6 inicial capturado" \
        || warn "Falha ao capturar snapshot M6 inicial (m6_delta indisponível)"

    # Marcar início exato do run
    RUN_START_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # Executar k6
    if k6 run \
        --out "json=$OUTPUT_FILE" \
        --summary-export "$SUMMARY_FILE" \
        --env "RUN_NUMBER=$i" \
        "$SCRIPT_DIR/test_hermes.js"; then
        success "Execução $i concluída com sucesso"
        SUCCESSFUL_RUNS+=($i)
    else
        warn "Execução $i terminou com thresholds violados (dados salvos)"
        FAILED_RUNS+=($i)
        SUCCESSFUL_RUNS+=($i)  # dados ainda são válidos para análise
    fi

    # Marcar fim exato do run
    RUN_END_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # Salvar metadata.json com timestamps precisos por run e por cenário
    save_run_metadata "$i" "$RUN_DIR" "$RUN_START_TS" "$RUN_END_TS" \
        && success "metadata.json salvo → $RUN_DIR/metadata.json" \
        || warn "Falha ao salvar metadata.json"

    # Salvar m6_delta.json com conflitos MVCC ocorridos nesta run
    save_m6_delta "$i" "$RUN_DIR" \
        && success "m6_delta.json salvo → $RUN_DIR/m6_delta.json" \
        || warn "Falha ao salvar m6_delta.json"

    # Extrair range queries do Prometheus enquanto os dados estão frescos
    extract_prometheus_for_run "$i" "$RUN_DIR"

    # Cooldown adaptativo entre execuções (exceto na última)
    if [ $i -lt $RUNS ]; then
        echo ""
        wait_system_drain "Run $i → Run $((i+1))"
        echo ""
    fi
done

# ── Sumário final ─────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  BENCHMARK CONCLUÍDO                                         ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
success "Execuções com dados: ${#SUCCESSFUL_RUNS[@]}/$RUNS"
if [ ${#FAILED_RUNS[@]} -gt 0 ]; then
    warn "Execuções com thresholds violados: ${FAILED_RUNS[*]}"
fi

echo ""
info "Arquivos salvos em:"
for i in $(seq 1 $RUNS); do
    echo "  resultados/run_$i/"
    ls "$RESULTS_DIR/run_$i/" 2>/dev/null | sed 's/^/    /'
done

echo ""
info "Para analisar todas as execuções:"
echo ""
echo "  cd $SCRIPT_DIR"
echo "  python3 analise_resultados.py resultados/run_*/*.json"
echo ""