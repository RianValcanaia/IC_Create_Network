#!/usr/bin/env python3
"""
comparar_throughput.py — Throughput de BC (Fabric) dos dois arms de mutantes,
SEM Oracle (Hermes direto) vs COM Oracle, a partir dos CSVs do Prometheus.

A vazão NÃO vem do relógio do k6 (que é inflado pelo polling por-doc). Vem do
`tps_validas` do Prometheus — `max(rate(ledger_transaction_count{
validation_code="VALID",channel="channel-all"}[1m]))` — fatiado pela janela
[start,end] de cada arm, gravada em metadata.json pelo run_mutant_throughput.sh.

Leitura honesta dos números:
  - tps_validas = tx VÁLIDAS commitadas/s no Fabric (avg/med/p95 na janela do arm).
  - Sem Oracle ancora 5000 docs; com Oracle ancora ~4000 (1000 barrados). Logo o
    tps_validas COM Oracle tende a ser MENOR — não por lentidão, e sim porque o
    lixo nunca chegou ao Fabric (goodput, não perda). Por isso reportamos também
    duração da janela e total estimado de tx válidas.

Stdlib puro (csv/json/datetime/statistics) — igual a comparar_mutantes.py, roda
em qualquer host sem pandas.

Uso:
  # acha os run dirs padrão (tpt_hermes / tpt_oracle dentro de resultados/)
  python3 comparar_throughput.py

  # ou aponta os dois run dirs explicitamente (cada um com *_wide.csv + metadata.json)
  python3 comparar_throughput.py resultados/tpt_hermes resultados/tpt_oracle
"""
import csv
import glob
import json
import os
import sys
from datetime import datetime, timezone

RESULTS_DIR = 'resultados'
DEFAULT_HERMES_DIR = os.path.join(RESULTS_DIR, 'tpt_hermes')
DEFAULT_ORACLE_DIR = os.path.join(RESULTS_DIR, 'tpt_oracle')


def parse_ts(s):
    """Parseia timestamp ISO (com ou sem Z/offset) como datetime aware UTC."""
    if s is None or s == '':
        return None
    s = str(s).strip().replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # formatos do Prometheus às vezes vêm sem 'T' ou com espaço
        try:
            dt = datetime.fromisoformat(s.replace(' ', 'T'))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def percentil(valores, p):
    """Percentil linear (estilo numpy) sobre lista já ordenada-ou-não."""
    if not valores:
        return None
    xs = sorted(valores)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    frac = k - lo
    return xs[lo] + (xs[hi] - xs[lo]) * frac


# ── IC95 via t de Student (stdlib puro) ────────────────────────────────────────
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086, 25: 2.060, 30: 2.042}


def _t95(df):
    if df <= 0:
        return 0.0
    if df in _T95:
        return _T95[df]
    for k in sorted(_T95):
        if df < k:
            return _T95[k]
    return 1.96


def media_ic95(valores):
    """(média, meia-largura do IC95) entre réplicas. Meia-largura 0 se n < 2."""
    import statistics as st
    xs = [x for x in valores if x is not None]
    n = len(xs)
    if n == 0:
        return (None, None)
    m = sum(xs) / n
    if n < 2:
        return (m, 0.0)
    return (m, _t95(n - 1) * st.stdev(xs) / (n ** 0.5))


def achar(run_dir, nome_glob):
    arquivos = sorted(glob.glob(os.path.join(run_dir, '**', nome_glob), recursive=True))
    return arquivos[-1] if arquivos else None


def achar_todos(run_dir, nome_glob):
    return sorted(glob.glob(os.path.join(run_dir, '**', nome_glob), recursive=True))


def janela_do_metadata(meta_path):
    if not meta_path or not os.path.isfile(meta_path):
        return None, None
    with open(meta_path) as f:
        meta = json.load(f)
    return parse_ts(meta.get('start')), parse_ts(meta.get('end'))


def metadata_pareado(run_dir, wide_path):
    """Acha o metadata da MESMA execução do wide, pelo stem <arm>_<ts>.

    wide:     prometheus_<arm>_<ts>_wide.csv  → stem <arm>_<ts>
    metadata: metadata_<arm>_<ts>.json
    Fallback: metadata.json legado, ou o metadata*.json mais recente do dir.
    """
    base = os.path.basename(wide_path)
    if base.startswith('prometheus_') and base.endswith('_wide.csv'):
        stem = base[len('prometheus_'):-len('_wide.csv')]
        cand = os.path.join(os.path.dirname(wide_path), f'metadata_{stem}.json')
        if os.path.isfile(cand):
            return cand
    return achar(run_dir, 'metadata_*.json') or achar(run_dir, 'metadata.json')


def _ler_amostras(wide, run_dir):
    """Lê (tps_validas > 0, timestamps) de um wide CSV dentro da janela do metadata
    pareado da MESMA execução (evita contaminação entre réplicas)."""
    t_ini, t_fim = janela_do_metadata(metadata_pareado(run_dir, wide))
    tps, ts_list = [], []
    with open(wide, newline='') as f:
        reader = csv.DictReader(f)
        if 'tps_validas' not in (reader.fieldnames or []):
            return [], []
        for row in reader:
            ts = parse_ts(row.get('timestamp'))
            if ts is None:
                continue
            if t_ini and t_fim and not (t_ini <= ts <= t_fim):
                continue
            raw = row.get('tps_validas', '')
            if raw in ('', 'nan', 'NaN', None):
                continue
            try:
                val = float(raw)
            except ValueError:
                continue
            if val > 0:
                tps.append(val)
                ts_list.append(ts)
    return tps, ts_list


def stats_arm(run_dir, rotulo):
    """Agrega TODAS as réplicas (cada prometheus_*_wide.csv = 1 réplica) do arm:
    média de tps por réplica → média ± IC95 entre réplicas; percentis/pico do pool."""
    wides = achar_todos(run_dir, 'prometheus_*_wide.csv')
    if not wides:
        print(f'  [AVISO] {rotulo}: nenhum prometheus_*_wide.csv em {run_dir}')
        return None

    rep_means = []   # média de tps_validas por réplica (a unidade de análise do IC)
    pooled    = []   # todas as amostras juntas (p/ mediana, p95, pico)
    dur_total = 0.0
    for wide in wides:
        tps, ts_list = _ler_amostras(wide, run_dir)
        if not tps:
            continue
        rep_means.append(sum(tps) / len(tps))
        pooled.extend(tps)
        if len(ts_list) > 1:
            dur_total += (max(ts_list) - min(ts_list)).total_seconds()

    if not rep_means:
        print(f'  [AVISO] {rotulo}: tps_validas sem amostras > 0 na(s) janela(s)')
        return None

    avg, ci = media_ic95(rep_means)
    dur_med = dur_total / len(rep_means)
    return {
        'rotulo':         rotulo,
        'n_reps':         len(rep_means),
        'avg':            avg,
        'avg_ci95':       ci,
        'med':            percentil(pooled, 50),
        'p95':            percentil(pooled, 95),
        'pico':           max(pooled),
        'amostras':       len(pooled),
        'duracao_s':      round(dur_med, 1),
        # integral aproximada: TPS médio × duração média da janela ≈ tx válidas/réplica
        'tx_validas_est': round(avg * dur_med) if dur_med else None,
    }


def main():
    if len(sys.argv) >= 3:
        dir_hermes, dir_oracle = sys.argv[1], sys.argv[2]
    else:
        dir_hermes, dir_oracle = DEFAULT_HERMES_DIR, DEFAULT_ORACLE_DIR

    sem = stats_arm(dir_hermes, 'SEM Oracle')
    com = stats_arm(dir_oracle, 'COM Oracle')

    if not sem and not com:
        print('[ERRO] Nenhum dado de throughput encontrado. Rode run_mutant_throughput.sh primeiro.')
        sys.exit(1)

    print('\n' + '=' * 70)
    print('  THROUGHPUT Fabric (tps_validas — tx VÁLIDAS commitadas/s)')
    print('=' * 70)
    print(f'  {"":26} {"SEM Oracle":>18} {"COM Oracle":>18}')

    def cel(d, k, fmt='{:.3f}'):
        if not d or d.get(k) is None:
            return f'{"—":>18}'
        return f'{fmt.format(d[k]):>18}'

    def cel_ci(d):
        if not d or d.get('avg') is None:
            return f'{"—":>18}'
        return f'{d["avg"]:.3f} ± {d.get("avg_ci95") or 0:.3f}'.rjust(18)

    print(f'  {"Réplicas":26} {cel(sem, "n_reps", "{:.0f}")} {cel(com, "n_reps", "{:.0f}")}')
    print(f'  {"TPS médio ± IC95":26} {cel_ci(sem)} {cel_ci(com)}')
    print(f'  {"TPS mediano (pool)":26} {cel(sem, "med")} {cel(com, "med")}')
    print(f'  {"TPS p95 (pool)":26} {cel(sem, "p95")} {cel(com, "p95")}')
    print(f'  {"TPS pico (pool)":26} {cel(sem, "pico")} {cel(com, "pico")}')
    print(f'  {"Duração média janela (s)":26} {cel(sem, "duracao_s", "{:.1f}")} {cel(com, "duracao_s", "{:.1f}")}')
    print(f'  {"Tx válidas/réplica (est.)":26} {cel(sem, "tx_validas_est", "{:.0f}")} {cel(com, "tx_validas_est", "{:.0f}")}')

    if sem and com and com['avg']:
        delta = (com['avg'] - sem['avg']) / sem['avg'] * 100
        print(f'\n  Δ TPS médio (com vs sem): {delta:+.1f}%')
        print('  NOTA: TPS menor com Oracle reflete os docs-lixo filtrados ANTES')
        print('        do Fabric (capacidade não desperdiçada = goodput), não')
        print('        lentidão da BC. Cruze com comparacao_filtragem.csv (FP/TN).')

    # ── CSV ────────────────────────────────────────────────────────────────────
    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = os.path.join(RESULTS_DIR, 'comparacao_throughput.csv')
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['metrica', 'sem_oracle', 'com_oracle'])
        for k, label in [
            ('n_reps', 'n_replicas'),
            ('avg', 'tps_validas_avg'),
            ('avg_ci95', 'tps_validas_ic95'),
            ('med', 'tps_validas_med'),
            ('p95', 'tps_validas_p95'),
            ('pico', 'tps_validas_pico'),
            ('duracao_s', 'duracao_janela_s'),
            ('tx_validas_est', 'tx_validas_estim'),
            ('amostras', 'amostras_prometheus'),
        ]:
            sv = '' if not sem or sem.get(k) is None else round(sem[k], 4)
            cv = '' if not com or com.get(k) is None else round(com[k], 4)
            w.writerow([label, sv, cv])

    print(f'\n[OK] CSV salvo: {out}')


if __name__ == '__main__':
    main()
