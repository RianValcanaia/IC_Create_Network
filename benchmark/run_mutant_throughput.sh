#!/bin/bash
# run_mutant_throughput.sh — Mede THROUGHPUT de BC (Fabric) nos dois arms de
# mutantes: SEM Oracle (Hermes direto) vs COM Oracle. Comparação direta.
#
# A vazão NÃO vem do relógio do k6 (inflado pelo polling por-doc). Vem do
# `tps_validas` do Prometheus, fatiado pela janela [start,end] de cada arm.
# Reusa extrair_metricas_prometheus() de analise_resultados.py — mesma fonte/
# PromQL dos cenários C1–C5.
#
# Uso:
#   ./run_mutant_throughput.sh            # roda os dois arms
#   ./run_mutant_throughput.sh hermes     # só o arm SEM Oracle
#   ./run_mutant_throughput.sh oracle     # só o arm COM Oracle
#
# Config via env (defaults batem com run_benchmark.sh):
#   HERMES_URL      base do hermes-api-server          (default https://10.10.20.152)
#   ORACLE_URL      base do Oracle                      (default http://10.10.20.152:3000)
#   PROMETHEUS_URL  Prometheus                          (default http://10.10.20.154:9090)
#   VUS             VUs concorrentes                    (default 20)
#   ITERATIONS      docs por arm                        (default 5000)
#   PROM_STEP       step do range-query                 (default 5s)
#   DRAIN_TIMEOUT   espera máx. p/ Fabric drenar (s)    (default 600)
#
# Saída:
#   resultados/tpt_hermes/  → metadata.json + run_*/prometheus_run*_wide.csv
#   resultados/tpt_oracle/  → idem
#   depois rode:  python3 comparar_throughput.py

set -e

ARM="${1:-both}"

HERMES_URL="${HERMES_URL:-https://10.10.20.152}"
ORACLE_URL="${ORACLE_URL:-http://10.10.20.152:3000}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://10.10.20.154:9090}"
VUS="${VUS:-20}"
ITERATIONS="${ITERATIONS:-5000}"
PROM_STEP="${PROM_STEP:-5s}"
DRAIN_POLL="${DRAIN_POLL:-10}"
DRAIN_STABLE="${DRAIN_STABLE:-3}"
DRAIN_TIMEOUT="${DRAIN_TIMEOUT:-600}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/resultados"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERRO]${NC} $1"; }

command -v k6 >/dev/null 2>&1 || { error "k6 não encontrado (sudo apt install k6)"; exit 1; }

# Aguarda o Fabric drenar: tps_validas ≈ 0 por DRAIN_STABLE leituras seguidas.
# Isola a janela de um arm da cauda de transações do anterior.
wait_drain() {
    local label="$1" elapsed=0 stable=0
    info "[$label] Aguardando Fabric drenar (tps_validas≈0)..."
    while [ "$elapsed" -lt "$DRAIN_TIMEOUT" ]; do
        local tps
        tps=$(curl -sf "${PROMETHEUS_URL}/api/v1/query?query=$(python3 -c \
            "import urllib.parse;print(urllib.parse.quote('max(rate(ledger_transaction_count{validation_code=\"VALID\",channel=\"channel-all\"}[1m]))'))")" \
            2>/dev/null | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin); r=d.get('data',{}).get('result',[])
    v=float(r[0]['value'][1]) if r else 0.0
    print('na' if v!=v else f'{v:.4f}')
except: print('na')" 2>/dev/null || echo "na")
        if [ "$tps" = "na" ]; then
            stable=$((stable+1))
        else
            local idle
            idle=$(python3 -c "print('yes' if abs(float('$tps'))<0.05 else 'no')" 2>/dev/null || echo "no")
            [ "$idle" = "yes" ] && stable=$((stable+1)) || stable=0
        fi
        [ "$stable" -ge "$DRAIN_STABLE" ] && { success "[$label] Fabric drenado."; return; }
        sleep "$DRAIN_POLL"; elapsed=$((elapsed+DRAIN_POLL))
    done
    warn "[$label] Drain timeout (${DRAIN_TIMEOUT}s) — continuando assim mesmo."
}

# Extrai tps_validas (e demais métricas) do Prometheus na janela [start,end].
# Reusa extrair_metricas_prometheus() (escreve em run_1/ com nome fixo) e depois
# RENOMEIA os artefatos para incluir arm+timestamp — nada é sobrescrito entre runs.
# Saída final no nível do arm:
#   prometheus_<arm>_<ts>_wide.csv   (usado por comparar_throughput.py)
#   prometheus_<arm>_<ts>_<step>.csv (formato longo, p/ referência)
#   metadata_<arm>_<ts>.json         (janela [start,end] pareada por timestamp)
extract_prom() {
    local out_dir="$1" arm="$2" ts="$3" start="$4" end="$5"
    mkdir -p "$out_dir"
    # metadata etiquetado com arm+ts (janela total do arm)
    python3 - "$out_dir/metadata_${arm}_${ts}.json" "$start" "$end" << 'PYEOF'
import json, sys
path, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, "w") as f:
    json.dump({"run": 1, "start": start, "end": end, "cenarios": {}}, f, indent=2)
PYEOF
    # extrai para um tmp e depois renomeia
    local tmp="$out_dir/.tmp_${arm}_${ts}"
    PROMETHEUS_URL="$PROMETHEUS_URL" _DIR="$SCRIPT_DIR" _OUT="$tmp" \
    _START="$start" _END="$end" _STEP="$PROM_STEP" python3 - << 'PYEOF'
import os, sys
sys.path.insert(0, os.environ['_DIR'])
# garante que analise_resultados use a mesma URL do driver
import analise_resultados as ar
ar.PROMETHEUS_URL = os.environ['PROMETHEUS_URL']
ar.extrair_metricas_prometheus(
    [{"run": 1, "start": os.environ['_START'], "end": os.environ['_END']}],
    step=os.environ['_STEP'],
    output_dir=os.environ['_OUT'],
)
PYEOF
    # renomeia para nomes etiquetados; só conta sucesso se o wide existir
    local wide_src="$tmp/run_1/prometheus_run1_wide.csv"
    [ -f "$wide_src" ] || { rm -rf "$tmp"; return 1; }
    mv -f "$wide_src" "$out_dir/prometheus_${arm}_${ts}_wide.csv"
    local long_src="$tmp/run_1/prometheus_run1_${PROM_STEP}.csv"
    [ -f "$long_src" ] && mv -f "$long_src" "$out_dir/prometheus_${arm}_${ts}_${PROM_STEP}.csv"
    rm -rf "$tmp"
    return 0
}

# Roda um arm: k6 (submit + polling p/ classificar vazamento) cercado por
# timestamps UTC; o throughput sai depois do Prometheus, não do k6.
run_arm() {
    local arm="$1"          # hermes | oracle
    local script out_dir base_env
    if [ "$arm" = "hermes" ]; then
        script="test_hermes_mutants.js"; out_dir="$RESULTS_DIR/tpt_hermes"
        base_env="--env BASE_URL=$HERMES_URL"
    else
        script="test_oracle_mutants.js"; out_dir="$RESULTS_DIR/tpt_oracle"
        base_env="--env ORACLE_URL=$ORACLE_URL"
    fi

    wait_drain "$arm"

    mkdir -p "$out_dir"
    local ts; ts=$(date +%Y%m%d_%H%M%S)
    local start; start=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    info "[$arm] k6 → $script (VUS=$VUS, ITER=$ITERATIONS) | início $start"
    ( cd "$SCRIPT_DIR" && k6 run $base_env --env VUS="$VUS" --env ITERATIONS="$ITERATIONS" \
        --out json="$out_dir/k6_${arm}_mutants_${ts}.json" "$script" ) \
        || warn "[$arm] k6 retornou código != 0 (thresholds?) — seguindo p/ extração"

    local end; end=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    success "[$arm] k6 concluído | fim $end"

    info "[$arm] Extraindo throughput do Prometheus na janela [$start, $end]..."
    extract_prom "$out_dir" "$arm" "$ts" "$start" "$end" \
        && success "[$arm] tps_validas → $out_dir/prometheus_${arm}_${ts}_wide.csv" \
        || warn "[$arm] Extração Prometheus falhou (Prometheus indisponível?)"
}

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Throughput de mutantes — SEM vs COM Oracle (tps_validas)   ║"
echo "╚══════════════════════════════════════════════════════════════╝"

case "$ARM" in
    hermes) run_arm hermes ;;
    oracle) run_arm oracle ;;
    both)   run_arm hermes; run_arm oracle ;;
    *) error "ARM inválido: '$ARM' (use: hermes | oracle | both)"; exit 1 ;;
esac

echo ""
success "Pronto. Compare com:  python3 comparar_throughput.py"
