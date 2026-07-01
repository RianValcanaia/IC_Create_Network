#!/bin/bash
# run_mutant_throughput_reps.sh — Executa run_mutant_throughput.sh N vezes por braço,
# acumulando réplicas timestamped em resultados/tpt_hermes/ e resultados/tpt_oracle/.
# Cada réplica vira um prometheus_<arm>_<ts>_wide.csv independente (nada é sobrescrito;
# a granularidade de segundo do timestamp separa réplicas, pois cada arm leva minutos).
#
# Depois agregue com média ± IC95 entre réplicas:
#   python3 comparar_throughput.py
#
# E, para a latência de compliance inserida com IC entre réplicas:
#   python3 comparar_mutantes.py --reps-glob 'resultados/summary_oracle_mutants_*.json'
#
# Uso:
#   REPS=5 ./run_mutant_throughput_reps.sh            # 5 réplicas de ambos os braços
#   REPS=3 ./run_mutant_throughput_reps.sh oracle     # só o braço COM Oracle
#
# Herda toda a configuração de run_mutant_throughput.sh (HERMES_URL, ORACLE_URL,
# PROMETHEUS_URL, VUS, ITERATIONS, DRAIN_*). O wait_drain entre braços/réplicas já
# isola as janelas de cada execução.
set -e

ARM="${1:-both}"
REPS="${REPS:-5}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Throughput de mutantes — $REPS réplica(s) por braço ($ARM)"
echo "╚══════════════════════════════════════════════════════════════╝"

for r in $(seq 1 "$REPS"); do
    echo ""
    echo -e "${BLUE}########## RÉPLICA $r / $REPS ##########${NC}"
    RUN_REP="$r" bash "$SCRIPT_DIR/run_mutant_throughput.sh" "$ARM"
done

echo ""
echo -e "${GREEN}[OK]${NC} $REPS réplica(s) concluída(s). Agora agregue com IC95:"
echo "     python3 comparar_throughput.py"
echo "     python3 comparar_mutantes.py --reps-glob 'resultados/summary_oracle_mutants_*.json'"
