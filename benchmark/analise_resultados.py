#!/usr/bin/env python3
"""
analise_resultados.py — Análise estatística do benchmark Hermes + Fabric 3.0
Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License

Uso:
    python3 analise_resultados.py resultados/run_*/k6_*.json
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from scipy import stats
from tabulate import tabulate
import requests
from datetime import datetime

# ─── Configuração ─────────────────────────────────────────────────────────────

PROMETHEUS_URL = "http://10.10.20.154:9090"
N_WORKERS      = 3   # workers por DO — normaliza TPS Fabric para comparação com TPS App

CENARIOS = ['C1_baseline', 'C2_leve', 'C3_moderada', 'C4_alta', 'C5_maxima']

CENARIOS_LABEL = {
    'C1_baseline': 'C1 (1 VU)',
    'C2_leve':     'C2 (10 VUs)',
    'C3_moderada': 'C3 (100 VUs)',
    'C4_alta':     'C4 (500 VUs)',
    'C5_maxima':   'C5 (1000 VUs)',
}

CORES = {
    'C1_baseline': '#1565C0',
    'C2_leve':     '#00897B',
    'C3_moderada': '#6A1B9A',
    'C4_alta':     '#283593',
    'C5_maxima':   '#B71C1C',
}

COR_TIMEOUT      = '#EF6C00'
COR_ERRO         = '#B71C1C'
COR_ERRO_POLLING = '#6A1B9A'

LABELS_GRAF = {
    'C1_baseline': 'C1\n(1 VU)',
    'C2_leve':     'C2\n(10 VUs)',
    'C3_moderada': 'C3\n(100 VUs)',
    'C4_alta':     'C4\n(500 VUs)',
    'C5_maxima':   'C5\n(1000 VUs)',
}

THRESHOLDS_P95 = {
    'C1_baseline': 5000,
    'C2_leve':     10000,
    'C3_moderada': 30000,
    'C4_alta':     90000,
    'C5_maxima':   120000,
}

DURACOES = {
    'C1_baseline': 300,
    'C2_leve':     600,
    'C3_moderada': 600,
    'C4_alta':     600,
    'C5_maxima':   600,
}

# ─── Carga dos dados k6 ───────────────────────────────────────────────────────

METRICAS_INTERESSE = {
    'm1_latencia_e2e_ms', 'm2_dos_ancoradas', 'm3_taxa_sucesso',
    'latencia_polling_ms', 'dos_timeout', 'dos_erro', 'dos_erro_polling',
    'http_req_duration', 'http_req_waiting', 'http_req_receiving',
    'http_req_sending', 'iteration_duration', 'http_reqs',
}

def _detectar_run(arquivo: str) -> int:
    import re
    m = re.search(r'run_(\d+)', arquivo)
    return int(m.group(1)) if m else 1


def carregar_k6(arquivos: list[str]) -> pd.DataFrame:
    registros = []
    runs_encontrados = set()
    for arquivo in arquivos:
        run_num = _detectar_run(arquivo)
        runs_encontrados.add(run_num)
        with open(arquivo) as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    obj = json.loads(linha)
                except json.JSONDecodeError:
                    continue
                if obj.get('type') != 'Point':
                    continue
                metric = obj.get('metric', '')
                if metric not in METRICAS_INTERESSE:
                    continue
                data   = obj.get('data', {})
                tags   = data.get('tags', {})
                value  = data.get('value')
                time   = data.get('time')
                registros.append({
                    'metric':  metric,
                    'value':   float(value) if value is not None else None,
                    'cenario': tags.get('cenario', 'desconhecido'),
                    'time':    time,
                    'run':     run_num,
                })

    df = pd.DataFrame(registros)
    if not df.empty and 'time' in df.columns:
        df['time'] = pd.to_datetime(df['time'], errors='coerce')
        df['time_s'] = df.groupby('run')['time'].transform(
            lambda x: (x - x.min()).dt.total_seconds()
        )

    n_runs = len(runs_encontrados)
    if n_runs > 1:
        print(f"  Detected {n_runs} runs: {sorted(runs_encontrados)}")
    return df

# ─── M1: Latência end-to-end ──────────────────────────────────────────────────

def analisar_m1(df: pd.DataFrame) -> pd.DataFrame:
    e2e = df[df['metric'] == 'm1_latencia_e2e_ms']
    resultados = []
    for cenario in CENARIOS:
        vals = e2e[e2e['cenario'] == cenario]['value'].dropna().values
        vals = vals[vals > 0]
        if len(vals) == 0:
            continue
        amostra = np.random.choice(vals, min(5000, len(vals)), replace=False)
        _, p_shapiro = stats.shapiro(amostra) if len(amostra) >= 3 else (0, 1)

        ic_low, ic_high = stats.t.interval(
            0.95, df=len(vals)-1,
            loc=np.mean(vals), scale=stats.sem(vals)
        )
        resultados.append({
            'Scenario':      CENARIOS_LABEL.get(cenario, cenario),
            'N':             len(vals),
            'Mean (ms)':     round(np.mean(vals), 1),
            'SD (ms)':       round(np.std(vals), 1),
            'CV (%)':        round((np.std(vals) / np.mean(vals)) * 100, 1) if np.mean(vals) > 0 else 0,
            'P50 (ms)':      round(np.percentile(vals, 50), 1),
            'P95 (ms)':      round(np.percentile(vals, 95), 1),
            'P99 (ms)':      round(np.percentile(vals, 99), 1),
            'Min (ms)':      round(np.min(vals), 1),
            'Max (ms)':      round(np.max(vals), 1),
            'CI 95% (ms)':   f"[{round(ic_low,1)}, {round(ic_high,1)}]",
            'Normal?':       'Yes' if p_shapiro > 0.05 else 'No',
        })
    return pd.DataFrame(resultados)

# ─── M2: Throughput ───────────────────────────────────────────────────────────

def analisar_m2(df: pd.DataFrame) -> pd.DataFrame:
    ancoradas = df[df['metric'] == 'm2_dos_ancoradas']
    runs      = sorted(df['run'].unique())
    resultados = []
    for cenario in CENARIOS:
        duracao = DURACOES.get(cenario, 600)
        tps_por_run = []
        for run in runs:
            total_run = ancoradas[
                (ancoradas['cenario'] == cenario) & (ancoradas['run'] == run)
            ]['value'].sum()
            if total_run > 0:
                tps_por_run.append(total_run / duracao)
        if not tps_por_run:
            continue
        total_geral = ancoradas[ancoradas['cenario'] == cenario]['value'].sum()
        resultados.append({
            'Scenario':        CENARIOS_LABEL.get(cenario, cenario),
            'Anchored DOs':    int(total_geral),
            'Duration (s)':    duracao,
            'Runs':            len(tps_por_run),
            'TPS (mean)':      round(np.mean(tps_por_run), 3),
            'TPS (SD)':        round(np.std(tps_por_run), 3) if len(tps_por_run) > 1 else 0,
        })
    return pd.DataFrame(resultados)

# ─── M3: Taxa de sucesso ──────────────────────────────────────────────────────

def analisar_m3(df: pd.DataFrame) -> pd.DataFrame:
    sucesso   = df[df['metric'] == 'm3_taxa_sucesso']
    timeout   = df[df['metric'] == 'dos_timeout']
    erro      = df[df['metric'] == 'dos_erro']
    erro_poll = df[df['metric'] == 'dos_erro_polling']
    resultados = []
    for cenario in CENARIOS:
        n_sucesso   = sucesso[(sucesso['cenario'] == cenario) & (sucesso['value'] == 1)].shape[0]
        n_timeout   = int(timeout[timeout['cenario'] == cenario]['value'].sum())
        n_erro      = int(erro[erro['cenario'] == cenario]['value'].sum())
        n_erro_poll = int(erro_poll[erro_poll['cenario'] == cenario]['value'].sum())
        total       = n_sucesso + n_timeout + n_erro + n_erro_poll
        resultados.append({
            'Scenario':           CENARIOS_LABEL.get(cenario, cenario),
            'Total':              total,
            'Success (N)':        n_sucesso,
            'Timeout (N)':        n_timeout,
            'Submit Error (N)':   n_erro,
            'Polling Error (N)':  n_erro_poll,
            'Success (%)':        round((n_sucesso / total * 100) if total > 0 else 0, 2),
            'Timeout (%)':        round((n_timeout / total * 100) if total > 0 else 0, 2),
            'Submit Error (%)':   round((n_erro    / total * 100) if total > 0 else 0, 2),
            'Polling Error (%)':  round((n_erro_poll / total * 100) if total > 0 else 0, 2),
        })
    return pd.DataFrame(resultados)

# ─── Métricas nativas k6 ─────────────────────────────────────────────────────

def analisar_nativas(df: pd.DataFrame) -> pd.DataFrame:
    metricas = ['http_req_duration', 'http_req_waiting', 'iteration_duration',
                'latencia_polling_ms']
    resultados = []
    for metric in metricas:
        vals = df[df['metric'] == metric]['value'].dropna().values
        vals = vals[vals > 0]
        if len(vals) == 0:
            continue
        resultados.append({
            'Metric':     metric,
            'N':          len(vals),
            'Mean (ms)':  round(np.mean(vals), 1),
            'P50 (ms)':   round(np.percentile(vals, 50), 1),
            'P95 (ms)':   round(np.percentile(vals, 95), 1),
            'P99 (ms)':   round(np.percentile(vals, 99), 1),
            'Max (ms)':   round(np.max(vals), 1),
        })
    return pd.DataFrame(resultados)

# ─── Decomposição polling vs. submit ─────────────────────────────────────────

def analisar_polling(df: pd.DataFrame) -> pd.DataFrame:
    polling = df[df['metric'] == 'latencia_polling_ms']
    e2e     = df[df['metric'] == 'm1_latencia_e2e_ms']
    resultados = []
    for cenario in CENARIOS:
        p_vals = polling[polling['cenario'] == cenario]['value'].dropna().values
        p_vals = p_vals[p_vals > 0]
        e_vals = e2e[e2e['cenario'] == cenario]['value'].dropna().values
        e_vals = e_vals[e_vals > 0]
        if len(p_vals) == 0 or len(e_vals) == 0:
            continue
        p50_poll = np.percentile(p_vals, 50)
        p95_poll = np.percentile(p_vals, 95)
        p50_e2e  = np.percentile(e_vals, 50)
        p95_e2e  = np.percentile(e_vals, 95)
        resultados.append({
            'Scenario':            CENARIOS_LABEL.get(cenario, cenario),
            'E2E P50 (ms)':        round(p50_e2e, 1),
            'Polling P50 (ms)':    round(p50_poll, 1),
            'Submit P50 (ms)':     round(max(0, p50_e2e - p50_poll), 1),
            'E2E P95 (ms)':        round(p95_e2e, 1),
            'Polling P95 (ms)':    round(p95_poll, 1),
            'Submit P95 (ms)':     round(max(0, p95_e2e - p95_poll), 1),
            'Polling/E2E P95 (%)': round(p95_poll / p95_e2e * 100, 1) if p95_e2e > 0 else 0,
        })
    return pd.DataFrame(resultados)

# ─── M4: Latência Fabric isolada ─────────────────────────────────────────────

def consultar_prometheus(query: str) -> float | None:
    try:
        r = requests.get(f"{PROMETHEUS_URL}/api/v1/query",
                         params={'query': query}, timeout=5)
        result = r.json().get('data', {}).get('result', [])
        if result:
            return float(result[0]['value'][1])
    except Exception as e:
        print(f"[WARN] Prometheus unavailable: {e}")
    return None

def _m4_valido(v) -> bool:
    import math
    return v is not None and isinstance(v, float) and not math.isnan(v)


def _analisar_m4_csv(output_dir: str = "resultados") -> dict:
    import glob
    resultado = {'Endorsement P50 (ms)': 'N/A', 'Endorsement P95 (ms)': 'N/A',
                 'Commit P50 (ms)':      'N/A', 'Commit P95 (ms)':      'N/A'}
    padrao   = os.path.join(output_dir, '**', 'prometheus_run*_wide.csv')
    arquivos = sorted(glob.glob(padrao, recursive=True))
    if not arquivos:
        padrao   = os.path.join(output_dir, 'prometheus_run*_wide.csv')
        arquivos = sorted(glob.glob(padrao))
    if not arquivos:
        return resultado
    frames = []
    for f in arquivos:
        try:
            frames.append(pd.read_csv(f))
        except Exception:
            continue
    if not frames:
        return resultado
    df_all = pd.concat(frames, ignore_index=True)
    mapa = {
        'Endorsement P50 (ms)': 'latencia_endosso_p50_ms',
        'Endorsement P95 (ms)': 'latencia_endosso_p95_ms',
        'Commit P50 (ms)':      'latencia_commit_p50_ms',
        'Commit P95 (ms)':      'latencia_commit_p95_ms',
    }
    for chave, col in mapa.items():
        if col in df_all.columns:
            vals = df_all[col].dropna().values
            vals = vals[np.isfinite(vals) & (vals > 0)]
            if len(vals) > 0:
                resultado[chave] = round(float(np.mean(vals)), 1)
    return resultado


def analisar_m4(output_dir: str = "resultados") -> dict:
    p50_e = consultar_prometheus('histogram_quantile(0.50, sum(rate(endorser_proposal_duration_bucket{success="true",chaincode="calc_do"}[10m])) by (le)) * 1000')
    p95_e = consultar_prometheus('histogram_quantile(0.95, sum(rate(endorser_proposal_duration_bucket{success="true",chaincode="calc_do"}[10m])) by (le)) * 1000')
    p50_c = consultar_prometheus('histogram_quantile(0.50, sum(rate(ledger_block_processing_time_bucket{channel="channel-all"}[10m])) by (le)) * 1000')
    p95_c = consultar_prometheus('histogram_quantile(0.95, sum(rate(ledger_block_processing_time_bucket{channel="channel-all"}[10m])) by (le)) * 1000')

    if not all(_m4_valido(v) for v in [p50_e, p95_e, p50_c, p95_c]):
        print("  [INFO] M4: Prometheus returned NaN — using CSV fallback")
        return _analisar_m4_csv(output_dir)

    return {
        'Endorsement P50 (ms)': round(p50_e, 1),
        'Endorsement P95 (ms)': round(p95_e, 1),
        'Commit P50 (ms)':      round(p50_c, 1),
        'Commit P95 (ms)':      round(p95_c, 1),
    }

# ─── M5: Overhead blockchain ─────────────────────────────────────────────────

def calcular_m5(df_m1: pd.DataFrame, m4: dict) -> pd.DataFrame:
    e_p95 = m4.get('Endorsement P95 (ms)')
    c_p95 = m4.get('Commit P95 (ms)')
    if e_p95 == 'N/A' or c_p95 == 'N/A':
        return pd.DataFrame()
    l_fabric_p95 = float(e_p95) + float(c_p95)
    resultados = []
    for _, row in df_m1.iterrows():
        l_e2e = row['P95 (ms)']
        overhead = (l_fabric_p95 / l_e2e * 100) if l_e2e > 0 else 0
        resultados.append({
            'Scenario':            row['Scenario'],
            'E2E P95 (ms)':        l_e2e,
            'Fabric P95 (ms)':     round(l_fabric_p95, 1),
            'Fabric Overhead (%)': round(overhead, 1),
            'Pipeline (%)':        round(100 - overhead, 1),
        })
    return pd.DataFrame(resultados)

# ─── M6: Conflitos MVCC ───────────────────────────────────────────────────────

def analisar_m6_por_run(arquivos: list[str]) -> pd.DataFrame:
    import re
    resultados = []
    runs_vistos: set[int] = set()
    for arquivo in arquivos:
        m_run = re.search(r'run_(\d+)', arquivo)
        if not m_run:
            continue
        run_num = int(m_run.group(1))
        if run_num in runs_vistos:
            continue
        runs_vistos.add(run_num)
        delta_path = os.path.join(os.path.dirname(os.path.abspath(arquivo)), 'm6_delta.json')
        if not os.path.isfile(delta_path):
            continue
        try:
            with open(delta_path) as f:
                d = json.load(f)
        except Exception:
            continue
        valid   = d.get('valid_delta')
        mvcc    = d.get('mvcc_delta')
        invalid = d.get('invalid_delta')
        total   = (valid or 0) + (mvcc or 0) + (invalid or 0)
        resultados.append({
            'Run':             run_num,
            'Valid Tx':        valid   if valid   is not None else 'N/A',
            'MVCC Conflict':   mvcc    if mvcc    is not None else 'N/A',
            'Invalid Tx':      invalid if invalid is not None else 'N/A',
            'MVCC Rate (%)':   round(mvcc / total * 100, 2) if total and mvcc else 0,
        })
    return pd.DataFrame(sorted(resultados, key=lambda x: x['Run']))


def analisar_m6() -> dict:
    mvcc    = consultar_prometheus('avg(ledger_transaction_count{validation_code="MVCC_READ_CONFLICT"})')
    invalid = consultar_prometheus('avg(ledger_transaction_count{validation_code="INVALID"})')
    valid   = consultar_prometheus('avg(ledger_transaction_count{validation_code="VALID"})')
    return {
        'MVCC Conflict': int(mvcc)    if mvcc    is not None else 'N/A',
        'Invalid Tx':    int(invalid) if invalid is not None else 'N/A',
        'Valid Tx':      int(valid)   if valid   is not None else 'N/A',
    }

# ─── Comparação estatística ───────────────────────────────────────────────────

def comparar_cenarios(df: pd.DataFrame) -> None:
    e2e = df[df['metric'] == 'm1_latencia_e2e_ms']
    print("\n── Mann-Whitney U Tests (scenario comparison) ────────────────────")
    pares = [
        ('C1_baseline', 'C2_leve'),
        ('C2_leve',     'C3_moderada'),
        ('C3_moderada', 'C4_alta'),
        ('C4_alta',     'C5_maxima'),
    ]
    for a, b in pares:
        va = e2e[e2e['cenario'] == a]['value'].dropna().values
        vb = e2e[e2e['cenario'] == b]['value'].dropna().values
        va, vb = va[va > 0], vb[vb > 0]
        if len(va) < 2 or len(vb) < 2:
            continue
        stat_, p = stats.mannwhitneyu(va, vb, alternative='two-sided')
        sig = '✓ significant (p<0.05)' if p < 0.05 else '✗ not significant'
        print(f"  {CENARIOS_LABEL.get(a,a)} vs {CENARIOS_LABEL.get(b,b)}")
        print(f"    U={stat_:.1f}, p={p:.4f} — {sig}")

# ─── Gráficos ─────────────────────────────────────────────────────────────────

def gerar_graficos(df: pd.DataFrame, timestamp: str):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import seaborn as sns
    except ImportError:
        print("\n[WARN] Run: pip install matplotlib seaborn")
        return

    graf_dir = f'resultados/graficos_{timestamp}'
    os.makedirs(graf_dir, exist_ok=True)
    sns.set_theme(style="whitegrid", palette="muted")
    plt.rcParams.update({
        'font.size': 11, 'axes.titlesize': 13,
        'axes.labelsize': 12, 'figure.dpi': 150
    })

    runs = sorted(df['run'].unique())

    e2e = df[df['metric'] == 'm1_latencia_e2e_ms']
    dados = {}
    for c in CENARIOS:
        v = e2e[e2e['cenario'] == c]['value'].dropna().values
        v = v[v > 0]
        if len(v) > 0:
            dados[c] = v

    cenarios_ok = [c for c in CENARIOS if c in dados]

    dados_cap = [dados[c] for c in cenarios_ok]
    n_out     = 0

    if not dados:
        print("[WARN] No e2e data — run the full test")
    else:
        # ── 1. Histogram + KDE (grade 2x3 para 5 cenários) ───────────────────
        n_cols = 3
        n_rows = 2
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(18, 10))
        axes = axes.flatten()
        for i, ax in enumerate(axes):
            if i >= len(cenarios_ok):
                ax.set_visible(False)
                continue
            c   = cenarios_ok[i]
            v   = dados_cap[i]
            p50 = np.percentile(dados[c], 50)
            p95 = np.percentile(dados[c], 95)

            ax.hist(v, bins=50, color=CORES[c], alpha=0.55,
                    edgecolor='white', linewidth=0.4, density=True)
            bw_val = max(np.std(v) * 0.3, (v.max() - v.min()) * 0.05, 1.0)
            bw_fac = bw_val / np.std(v) if np.std(v) > 0 else 0.5
            kde = stats.gaussian_kde(v, bw_method=bw_fac)
            xr  = np.linspace(v.min(), v.max(), 300)
            ax.plot(xr, kde(xr), color=CORES[c], linewidth=2.5, label='KDE')
            ax.axvline(p50, color='navy',    linestyle='--', lw=1.5,
                       label=f'P50={p50:.0f}ms')
            ax.axvline(p95, color='darkred', linestyle='--', lw=1.5,
                       label=f'P95={p95:.0f}ms')
            ax.set_title(LABELS_GRAF[c].replace('\n', ' '), fontweight='bold')
            ax.set_xlabel('E2E Latency (ms)')
            ax.set_ylabel('Density')
            ax.legend(fontsize=9)
            ax.yaxis.grid(True, linestyle='--', alpha=0.5)

        fig.suptitle('E2E Latency Distribution by Scenario',
                     fontsize=14, fontweight='bold')
        fig.text(0.5, 0.01,
                 f'Visualization clipped at P95 ({n_out} values above omitted — reported in table)',
                 ha='center', fontsize=8, color='gray', style='italic')
        plt.tight_layout(rect=[0, 0.03, 1, 1])
        p = f'{graf_dir}/m1_histograma_kde_por_cenario.png'
        plt.savefig(p, bbox_inches='tight'); plt.close()
        print(f"  [OK] {p}")

        # ── 2. Scatter temporal ───────────────────────────────────────────────
        fig, ax = plt.subplots(figsize=(16, 6))
        run_plot  = sorted(df['run'].unique())[0]
        nota_runs = (f' — Run {run_plot} (representative)' if len(runs) > 1 else '')
        e2e_time  = df[(df['metric'] == 'm1_latencia_e2e_ms') &
                       (df['value'] > 0) &
                       (df['run'] == run_plot)].copy()

        if 'time_s' not in e2e_time.columns:
            e2e_time['time_s'] = 0.0

        t_global_min = e2e_time['time_s'].min()
        e2e_time['time_abs_min'] = (e2e_time['time_s'] - t_global_min) / 60

        vals_todos = e2e_time['value'].values
        vals_todos = vals_todos[vals_todos > 0]
        p95_global = np.percentile(vals_todos, 95)

        cenario_start = {}
        MAX_SCATTER_PTS = 5000

        for c in cenarios_ok:
            sub = e2e_time[e2e_time['cenario'] == c].copy()
            if sub.empty:
                continue
            p95_c   = np.percentile(sub['value'].values, 95)
            sub_vis = sub[sub['value'] <= p95_c].sort_values('time_abs_min')
            if len(sub_vis) > MAX_SCATTER_PTS:
                sub_vis = sub_vis.sample(MAX_SCATTER_PTS, random_state=42
                                         ).sort_values('time_abs_min')
            t_ini = sub_vis['time_abs_min'].min()
            cenario_start[c] = t_ini

            ax.scatter(sub_vis['time_abs_min'], sub_vis['value'],
                       color=CORES[c], alpha=0.18, s=3, zorder=2)
            rolled = sub_vis['value'].rolling(
                window=60, min_periods=5, center=True).median()
            ax.plot(sub_vis['time_abs_min'], rolled,
                    color=CORES[c], linewidth=2.5, zorder=3,
                    label=CENARIOS_LABEL[c])

        for c, t_ini in cenario_start.items():
            ax.axvline(t_ini, color=CORES[c], linestyle='--',
                       linewidth=1.2, alpha=0.7, zorder=1)
            ax.text(t_ini + 0.15, p95_global * 1.03,
                    LABELS_GRAF[c].replace('\n', ' '),
                    color=CORES[c], fontsize=8, va='bottom')

        ax.set_xlabel('Time from Run Start (min)')
        ax.set_ylabel('E2E Latency (ms)')
        ax.set_title(f'E2E Latency Over Time{nota_runs}', fontsize=12)
        ax.set_ylim(bottom=0, top=p95_global * 1.2)
        ax.yaxis.grid(True, linestyle='--', alpha=0.5)
        ax.legend(loc='upper left', fontsize=9, markerscale=3)
        plt.tight_layout()
        p = f'{graf_dir}/m1_scatter_temporal.png'
        plt.savefig(p, bbox_inches='tight'); plt.close()
        print(f"  [OK] {p}")

        # ── 3a. Box plot ──────────────────────────────────────────────────────
        fig, ax = plt.subplots(figsize=(13, 6))
        box_data, box_labels, box_colors = [], [], []
        for c in cenarios_ok:
            box_data.append(dados[c])
            box_labels.append(LABELS_GRAF[c].replace('\n', ' '))
            box_colors.append(CORES[c])

        bp = ax.boxplot(
            box_data, patch_artist=True, notch=False,
            showfliers=False, whis=(5, 95),
            medianprops=dict(color='black', linewidth=2),
        )
        for patch, cor in zip(bp['boxes'], box_colors):
            patch.set_facecolor(cor); patch.set_alpha(0.75)
        for element in ['whiskers', 'caps']:
            for item in bp[element]:
                item.set_color('black'); item.set_linewidth(1.5)

        for i, (c, v) in enumerate(zip(cenarios_ok, box_data), 1):
            p95 = np.percentile(v, 95)
            ax.text(i, p95 * 1.002, f'P95={p95:.0f}ms',
                    ha='center', va='bottom', fontsize=8,
                    color=CORES[c], fontweight='bold')

        ax.set_xticks(range(1, len(cenarios_ok) + 1))
        ax.set_xticklabels(box_labels, fontsize=10)
        ax.set_ylabel('E2E Latency (ms)')
        ax.set_title('E2E Latency by Scenario', fontsize=13, fontweight='bold')
        ax.yaxis.grid(True, linestyle='--', alpha=0.6)
        ax.set_axisbelow(True)
        plt.tight_layout()
        p = f'{graf_dir}/m1_boxplot_por_cenario.png'
        plt.savefig(p, bbox_inches='tight'); plt.close()
        print(f"  [OK] {p}")

                # ── 3b. eCDF ──────────────────────────────────────────────────────────
        fig, ax = plt.subplots(figsize=(13, 6))
        for c in cenarios_ok:
            v   = np.sort(dados[c])
            cdf = np.arange(1, len(v) + 1) / len(v)
            p99 = np.percentile(v, 99)
            mask = v <= p99
            ax.plot(v[mask], cdf[mask] * 100,
                    color=CORES[c], linewidth=2.8, label=CENARIOS_LABEL[c])
            for pct, ls in [(50, ':'), (95, '--')]:
                ax.axvline(np.percentile(v, pct), color=CORES[c],
                           linestyle=ls, linewidth=0.8, alpha=0.5)

        ax.axhline(95, color='gray', linestyle='--', linewidth=1, alpha=0.6, label='P95')
        ax.axhline(50, color='gray', linestyle=':',  linewidth=1, alpha=0.6, label='P50')
        ax.set_xlabel('E2E Latency (ms)', fontsize=16)
        ax.set_ylabel('Cumulative Percentile (%)', fontsize=16)
        ax.tick_params(axis='both', which='major', labelsize=14)
        ax.set_ylim(0, 101)
        ax.set_title('E2E Latency by Scenario', fontsize=18, fontweight='bold')
        ax.yaxis.grid(True, linestyle='--', alpha=0.5)
        ax.legend(loc='lower right', fontsize=14)
        plt.tight_layout()
        p_png = f'{graf_dir}/m1_ecdf_por_cenario.png'
        p_pdf = f'{graf_dir}/m1_ecdf_por_cenario.pdf'
        plt.savefig(p_png, bbox_inches='tight')
        plt.savefig(p_pdf, bbox_inches='tight')
        plt.close()
        print(f"  [OK] {p_png}")
        print(f"  [OK] {p_pdf}")

    # ── 4. Throughput por cenário ─────────────────────────────────────────────
    ancoradas = df[df['metric'] == 'm2_dos_ancoradas']

    tps_data = []
    for c in CENARIOS:
        dur = DURACOES[c]
        tps_runs = [
            ancoradas[(ancoradas['cenario'] == c) & (ancoradas['run'] == r)]['value'].sum() / dur
            for r in runs
            if ancoradas[(ancoradas['cenario'] == c) & (ancoradas['run'] == r)]['value'].sum() > 0
        ]
        if tps_runs:
            tps_data.append((LABELS_GRAF[c].replace('\n', ' '),
                             round(np.mean(tps_runs), 3),
                             round(np.std(tps_runs), 3) if len(tps_runs) > 1 else 0,
                             CORES[c]))

    if tps_data:
        labels_t, tps_vals, dp_vals, cores_t = zip(*tps_data)
        tps_vals = list(tps_vals)
        dp_vals  = list(dp_vals)

        fig, ax = plt.subplots(figsize=(11, 5))
        bars = ax.bar(labels_t, tps_vals,
                      yerr=dp_vals if any(d > 0 for d in dp_vals) else None,
                      color=cores_t, alpha=0.85, edgecolor='white',
                      error_kw=dict(elinewidth=2, capsize=5, ecolor='black'))
        for bar, val, dp in zip(bars, tps_vals, dp_vals):
            txt = f'{val:.3f}' + (f'\n±{dp:.3f} tx/s' if dp > 0 else ' tx/s')
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + (dp if dp > 0 else 0) + max(tps_vals) * 0.01,
                    txt, ha='center', va='bottom', fontsize=10, fontweight='bold')
        ax.set_ylabel('Throughput (tx/s)')
        ax.set_title('Throughput by Scenario', fontsize=13, fontweight='bold')
        ax.set_yscale('log')
        ax.yaxis.grid(True, linestyle='--', alpha=0.6)
        ax.set_axisbelow(True)
        plt.tight_layout()
        p = f'{graf_dir}/m2_throughput_por_cenario.png'
        plt.savefig(p, bbox_inches='tight'); plt.close()
        print(f"  [OK] {p}")

    # ── 5. Barra empilhada M3 ─────────────────────────────────────────────────
    timeout_df = df[df['metric'] == 'dos_timeout']
    erro_df    = df[df['metric'] == 'dos_erro']
    errop_df   = df[df['metric'] == 'dos_erro_polling']
    sucesso_df = df[(df['metric'] == 'm3_taxa_sucesso') & (df['value'] == 1)]

    stacked_data = []
    for c in CENARIOS:
        n_suc   = sucesso_df[sucesso_df['cenario'] == c].shape[0]
        n_to    = int(timeout_df[timeout_df['cenario'] == c]['value'].sum())
        n_err   = int(erro_df[erro_df['cenario'] == c]['value'].sum())
        n_errop = int(errop_df[errop_df['cenario'] == c]['value'].sum())
        total   = n_suc + n_to + n_err + n_errop
        if total > 0:
            stacked_data.append({
                'cenario': CENARIOS_LABEL[c],
                'sucesso': n_suc  / total * 100,
                'timeout': n_to   / total * 100,
                'erro':    n_err  / total * 100,
                'errop':   n_errop / total * 100,
                'n_suc': n_suc, 'n_to': n_to, 'n_err': n_err, 'n_errop': n_errop,
            })

    if stacked_data:
        fig, ax = plt.subplots(figsize=(12, 6))
        x = np.arange(len(stacked_data))
        w = 0.55
        suc_v   = [d['sucesso'] for d in stacked_data]
        to_v    = [d['timeout'] for d in stacked_data]
        err_v   = [d['erro']    for d in stacked_data]
        errop_v = [d['errop']   for d in stacked_data]

        ax.bar(x, suc_v,   w, label='Success',       color='#4CAF50',        alpha=0.85)
        ax.bar(x, to_v,    w, label='Timeout',        color=COR_TIMEOUT,      alpha=0.85, bottom=suc_v)
        ax.bar(x, err_v,   w, label='Submit Error',   color=COR_ERRO,         alpha=0.85,
               bottom=[s+t for s,t in zip(suc_v, to_v)])
        ax.bar(x, errop_v, w, label='Polling Error',  color=COR_ERRO_POLLING, alpha=0.85,
               bottom=[s+t+e for s,t,e in zip(suc_v, to_v, err_v)])

        for i, d in enumerate(stacked_data):
            if d['n_suc'] > 0:
                ax.text(i, d['sucesso']/2, f"{d['n_suc']:,}",
                        ha='center', va='center', fontsize=8,
                        color='white', fontweight='bold')

        ax.set_xticks(x)
        ax.set_xticklabels([d['cenario'] for d in stacked_data], fontsize=10)
        ax.set_ylabel('Proportion (%)')
        ax.set_ylim(0, 105)
        ax.set_title('Transaction Outcomes by Scenario', fontsize=13, fontweight='bold')
        ax.yaxis.grid(True, linestyle='--', alpha=0.5)
        ax.set_axisbelow(True)
        ax.legend(loc='lower left', fontsize=10)
        plt.tight_layout()
        p = f'{graf_dir}/m3_stacked_sucesso_timeout_erro.png'
        plt.savefig(p, bbox_inches='tight'); plt.close()
        print(f"  [OK] {p}")

    # ── 6. Scatter com timeouts ───────────────────────────────────────────────
    if dados:
        fig, ax = plt.subplots(figsize=(16, 6))
        e2e_full = df[(df['metric'] == 'm1_latencia_e2e_ms') &
                      (df['value'] > 0) & (df['run'] == run_plot)].copy()
        to_full  = df[(df['metric'] == 'dos_timeout') &
                      (df['run'] == run_plot)].copy()

        for d in [e2e_full, to_full]:
            if 'time_s' not in d.columns:
                d['time_s'] = 0.0

        t_global_min = e2e_full['time_s'].min()
        e2e_full['time_abs_min'] = (e2e_full['time_s'] - t_global_min) / 60
        to_full['time_abs_min']  = (to_full['time_s']  - t_global_min) / 60

        vals_ok  = e2e_full['value'].values
        vals_ok  = vals_ok[vals_ok > 0]
        p95_glob = np.percentile(vals_ok, 95)
        topo_y   = p95_glob * 1.15

        cenario_start_b = {}
        for c in cenarios_ok:
            sub = e2e_full[e2e_full['cenario'] == c].copy()
            if sub.empty:
                continue
            p95_c   = np.percentile(sub['value'].values, 95)
            sub_vis = sub[sub['value'] <= p95_c].sort_values('time_abs_min')
            if sub_vis.empty:
                continue
            if len(sub_vis) > MAX_SCATTER_PTS:
                sub_vis = sub_vis.sample(MAX_SCATTER_PTS, random_state=42
                                         ).sort_values('time_abs_min')
            cenario_start_b[c] = sub_vis['time_abs_min'].min()

            ax.scatter(sub_vis['time_abs_min'], sub_vis['value'],
                       color=CORES[c], alpha=0.15, s=3, zorder=2)
            rolled = sub_vis['value'].rolling(
                window=60, min_periods=5, center=True).median()
            ax.plot(sub_vis['time_abs_min'], rolled,
                    color=CORES[c], linewidth=2.5, zorder=3,
                    label=CENARIOS_LABEL[c])

            to_c = to_full[to_full['cenario'] == c]
            if not to_c.empty:
                ax.scatter(to_c['time_abs_min'], [topo_y * 0.97] * len(to_c),
                           marker='x', color=COR_ERRO, s=30,
                           linewidths=1.5, zorder=5, label='_timeout')

        ax.axhline(topo_y * 0.97, color=COR_ERRO, linestyle=':',
                   linewidth=1, alpha=0.6, label='Timeout (90s)')

        for c, t_ini in cenario_start_b.items():
            ax.axvline(t_ini, color=CORES[c], linestyle='--',
                       linewidth=1.2, alpha=0.6, zorder=1)
            ax.text(t_ini + 0.1, p95_glob * 1.05,
                    LABELS_GRAF[c].replace('\n', ' '),
                    color=CORES[c], fontsize=8, va='bottom')

        ax.set_xlabel('Time from Run Start (min)')
        ax.set_ylabel('E2E Latency (ms)')
        ax.set_title(f'E2E Latency Over Time with Timeouts{nota_runs}', fontsize=12)
        ax.set_ylim(bottom=0, top=topo_y * 1.05)
        ax.yaxis.grid(True, linestyle='--', alpha=0.5)
        handles, lbls = ax.get_legend_handles_labels()
        seen, h_d, l_d = set(), [], []
        for h, l in zip(handles, lbls):
            if l not in seen and not l.startswith('_'):
                seen.add(l); h_d.append(h); l_d.append(l)
        ax.legend(h_d, l_d, loc='upper left', fontsize=9, markerscale=2)
        plt.tight_layout()
        p = f'{graf_dir}/m1_scatter_com_timeouts.png'
        plt.savefig(p, bbox_inches='tight'); plt.close()
        print(f"  [OK] {p}")

    # ── 7. Throughput dividido ────────────────────────────────────────────────
    ancoradas_d = df[df['metric'] == 'm2_dos_ancoradas']
    timeout_d   = df[df['metric'] == 'dos_timeout']
    erro_d      = df[df['metric'] == 'dos_erro']
    errop_d     = df[df['metric'] == 'dos_erro_polling']
    n_runs      = len(runs)

    tps_suc, tps_to, tps_err, tps_errop, labels_d, cores_d = [], [], [], [], [], []
    for c in CENARIOS:
        dur_total = DURACOES[c] * n_runs
        n_suc   = ancoradas_d[ancoradas_d['cenario'] == c]['value'].sum()
        n_to    = timeout_d[timeout_d['cenario'] == c]['value'].sum()
        n_err   = erro_d[erro_d['cenario'] == c]['value'].sum()
        n_errop = errop_d[errop_d['cenario'] == c]['value'].sum()
        if n_suc + n_to + n_err + n_errop > 0:
            tps_suc.append(round(n_suc    / dur_total, 3))
            tps_to.append(round(n_to      / dur_total, 3))
            tps_err.append(round(n_err    / dur_total, 3))
            tps_errop.append(round(n_errop / dur_total, 3))
            labels_d.append(LABELS_GRAF[c].replace('\n', ' '))
            cores_d.append(CORES[c])

    if tps_suc:
        fig, ax = plt.subplots(figsize=(11, 5))
        x = np.arange(len(labels_d))
        w = 0.55
        ax.bar(x, tps_suc,   w, label='Anchored (success)', color=cores_d,    alpha=0.85)
        ax.bar(x, tps_to,    w, label='Timeout',             color=COR_TIMEOUT, alpha=0.85, bottom=tps_suc)
        ax.bar(x, tps_err,   w, label='Submit Error',        color=COR_ERRO,    alpha=0.85,
               bottom=[s+t for s,t in zip(tps_suc, tps_to)])
        ax.bar(x, tps_errop, w, label='Polling Error',       color=COR_ERRO_POLLING, alpha=0.85,
               bottom=[s+t+e for s,t,e in zip(tps_suc, tps_to, tps_err)])

        for i, (s, t, e, ep) in enumerate(zip(tps_suc, tps_to, tps_err, tps_errop)):
            ax.text(i, s+t+e+ep + max(tps_suc)*0.01, f'{s:.2f} tx/s',
                    ha='center', va='bottom', fontsize=9, fontweight='bold',
                    color=cores_d[i])

        ax.set_xticks(x); ax.set_xticklabels(labels_d, fontsize=10)
        ax.set_ylabel('Throughput (tx/s)')
        ax.set_title('Throughput by Scenario', fontsize=13, fontweight='bold')
        ax.set_yscale('log')
        ax.yaxis.grid(True, linestyle='--', alpha=0.6)
        ax.set_axisbelow(True)
        ax.legend(loc='upper left', fontsize=9)
        plt.tight_layout()
        p = f'{graf_dir}/m2_throughput_dividido.png'
        plt.savefig(p, bbox_inches='tight'); plt.close()
        print(f"  [OK] {p}")

    # ── 8. Variabilidade P95 ──────────────────────────────────────────────────
    gerar_grafico_variabilidade(df, graf_dir)

    # ── 9. TPS comparativo App vs Fabric ─────────────────────────────────────
    gerar_grafico_tps_comparativo(df, graf_dir)

    gerar_boxplot_c3_c5(df, graf_dir)
    n_graficos = len(os.listdir(graf_dir))
    print(f"\n[OK] {n_graficos} graphs saved in {graf_dir}/")


# ─── Extração de dados brutos do Prometheus ───────────────────────────────────

def extrair_prometheus_range(query: str, start: str, end: str,
                              step: str = "15s") -> pd.DataFrame:
    try:
        r = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={"query": query, "start": start, "end": end, "step": step},
            timeout=30
        )
        data = r.json()
        if data.get("status") != "success":
            print(f"[WARN] Prometheus returned status: {data.get('status')}")
            return pd.DataFrame()

        registros = []
        for serie in data["data"]["result"]:
            instance = serie["metric"].get("instance", "aggregated")
            for ts, val in serie["values"]:
                registros.append({
                    "timestamp": pd.to_datetime(ts, unit="s", utc=True),
                    "value":     float(val),
                    "instance":  instance,
                })
        return pd.DataFrame(registros)
    except Exception as e:
        print(f"[WARN] Prometheus range query error: {e}")
        return pd.DataFrame()


def extrair_metricas_prometheus(runs_info: list[dict],
                                 step: str = "15s",
                                 output_dir: str = "resultados") -> None:
    os.makedirs(output_dir, exist_ok=True)

    QUERIES = {
        "tps_validas": (
    'max(rate(ledger_transaction_count{validation_code="VALID",'
    'channel="channel-all"}[1m]))'
        ),
        "tps_total": (
            'avg(rate(ledger_transaction_count{channel="channel-all"}[1m]))'
        ),
        "altura_blockchain_por_peer": (
            'ledger_blockchain_height{channel="channel-all"}'
        ),
        "latencia_endosso_p50_ms": (
            'histogram_quantile(0.50, sum(rate('
            'endorser_proposal_duration_bucket{success="true",chaincode="calc_do"}[1m]'
            ')) by (le)) * 1000'
        ),
        "latencia_endosso_p95_ms": (
            'histogram_quantile(0.95, sum(rate('
            'endorser_proposal_duration_bucket{success="true",chaincode="calc_do"}[1m]'
            ')) by (le)) * 1000'
        ),
        "latencia_commit_p50_ms": (
            'histogram_quantile(0.50, sum(rate('
            'ledger_block_processing_time_bucket{channel="channel-all"}[1m]'
            ')) by (le)) * 1000'
        ),
        "latencia_commit_p95_ms": (
            'histogram_quantile(0.95, sum(rate('
            'ledger_block_processing_time_bucket{channel="channel-all"}[1m]'
            ')) by (le)) * 1000'
        ),
    }

    for run_info in runs_info:
        run_num = run_info["run"]
        start   = run_info["start"]
        end     = run_info["end"]

        run_dir = os.path.join(output_dir, f'run_{run_num}')
        os.makedirs(run_dir, exist_ok=True)

        print(f"\n  Run {run_num} ({start} -> {end})")
        frames = []

        for nome_metrica, query in QUERIES.items():
            df_q = extrair_prometheus_range(query, start, end, step)
            if df_q.empty:
                print(f"    [WARN] {nome_metrica}: no data")
                continue
            df_q["metrica"] = nome_metrica
            df_q["run"]     = run_num
            frames.append(df_q)
            print(f"    [OK] {nome_metrica}: {len(df_q)} points")

        if not frames:
            print(f"    [WARN] Run {run_num}: no data returned from Prometheus")
            continue

        df_run = pd.concat(frames, ignore_index=True)

        csv_path = os.path.join(run_dir, f"prometheus_run{run_num}_{step}.csv")
        df_run.to_csv(csv_path, index=False)
        print(f"    [OK] Saved: {csv_path} ({len(df_run)} rows)")

        try:
            metricas_agregadas = [m for m in QUERIES if "por_peer" not in m]
            df_pivot = df_run[df_run["metrica"].isin(metricas_agregadas)].copy()
            df_pivot = df_pivot.groupby(["timestamp", "metrica", "run"])["value"].mean().reset_index()
            df_wide  = df_pivot.pivot_table(
                index=["timestamp", "run"], columns="metrica", values="value"
            ).reset_index()
            wide_path = os.path.join(run_dir, f"prometheus_run{run_num}_wide.csv")
            df_wide.to_csv(wide_path, index=False)
            print(f"    [OK] Wide: {wide_path}")
        except Exception as e:
            print(f"    [WARN] Pivot failed: {e}")


def detectar_intervalos_runs(arquivos: list[str]) -> list[dict]:
    import re
    from datetime import timedelta

    runs_info = {}
    for arquivo in arquivos:
        m_run = re.search(r'run_(\d+)', arquivo)
        if not m_run:
            continue
        run_num = int(m_run.group(1))
        if run_num in runs_info:
            continue

        run_dir   = os.path.dirname(os.path.abspath(arquivo))
        meta_path = os.path.join(run_dir, 'metadata.json')
        if os.path.isfile(meta_path):
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                runs_info[run_num] = {
                    'run': meta['run'], 'start': meta['start'], 'end': meta['end'],
                }
                continue
            except Exception:
                pass

        m_ts = re.search(r'(\d{8})_(\d{6})', arquivo)
        if not m_ts:
            continue
        try:
            dt_inicio  = datetime.strptime(f"{m_ts.group(1)}_{m_ts.group(2)}", "%Y%m%d_%H%M%S")
            utc_offset = datetime.now().astimezone().utcoffset()
            dt_utc     = dt_inicio - utc_offset
            dt_fim     = dt_utc + timedelta(minutes=90)
            runs_info[run_num] = {
                'run':   run_num,
                'start': dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'end':   dt_fim.strftime('%Y-%m-%dT%H:%M:%SZ'),
            }
        except ValueError:
            continue

    return sorted(runs_info.values(), key=lambda x: x['run'])

# ─── Variabilidade entre runs ─────────────────────────────────────────────────

def analisar_variabilidade_runs(df: pd.DataFrame) -> pd.DataFrame:
    runs = sorted(df['run'].unique())
    if len(runs) <= 1:
        return pd.DataFrame()

    e2e = df[df['metric'] == 'm1_latencia_e2e_ms']
    resultados = []
    for cenario in CENARIOS:
        p50_por_run, p95_por_run, tps_por_run = [], [], []
        ancoradas = df[df['metric'] == 'm2_dos_ancoradas']
        dur = DURACOES.get(cenario, 600)

        for run in runs:
            vals = e2e[(e2e['cenario'] == cenario) & (e2e['run'] == run)]['value'].dropna().values
            vals = vals[vals > 0]
            if len(vals) > 0:
                p50_por_run.append(np.percentile(vals, 50))
                p95_por_run.append(np.percentile(vals, 95))
            total = ancoradas[(ancoradas['cenario'] == cenario) & (ancoradas['run'] == run)]['value'].sum()
            if total > 0:
                tps_por_run.append(total / dur)

        if not p50_por_run:
            continue

        resultados.append({
            'Scenario':       CENARIOS_LABEL.get(cenario, cenario),
            'Runs':           len(p50_por_run),
            'P50 mean (ms)':  round(np.mean(p50_por_run), 1),
            'P50 SD (ms)':    round(np.std(p50_por_run), 1),
            'P95 mean (ms)':  round(np.mean(p95_por_run), 1),
            'P95 SD (ms)':    round(np.std(p95_por_run), 1),
            'TPS mean':       round(np.mean(tps_por_run), 3) if tps_por_run else 0,
            'TPS SD':         round(np.std(tps_por_run), 3)  if tps_por_run else 0,
        })
    return pd.DataFrame(resultados)


def gerar_grafico_variabilidade(df: pd.DataFrame, graf_dir: str):
    runs = sorted(df['run'].unique())
    if len(runs) <= 1:
        return

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import seaborn as sns
        sns.set_theme(style="whitegrid")
    except ImportError:
        return

    e2e = df[df['metric'] == 'm1_latencia_e2e_ms']
    cenarios_ok, medias, desvios, cores_bar = [], [], [], []

    for cenario in CENARIOS:
        p95_por_run = []
        for run in runs:
            vals = e2e[(e2e['cenario'] == cenario) & (e2e['run'] == run)]['value'].dropna().values
            vals = vals[vals > 0]
            if len(vals) > 0:
                p95_por_run.append(np.percentile(vals, 95))
        if p95_por_run:
            cenarios_ok.append(CENARIOS_LABEL[cenario])
            medias.append(np.mean(p95_por_run))
            desvios.append(np.std(p95_por_run))
            cores_bar.append(CORES[cenario])

    if not cenarios_ok:
        return

    fig, ax = plt.subplots(figsize=(11, 5))
    x = np.arange(len(cenarios_ok))
    bars = ax.bar(x, medias, yerr=desvios, capsize=6,
                  color=cores_bar, alpha=0.8, edgecolor='white',
                  error_kw=dict(elinewidth=2, ecolor='black', capthick=2))

    for bar, m, d in zip(bars, medias, desvios):
        ax.text(bar.get_x() + bar.get_width()/2,
                bar.get_height() + d + max(medias)*0.01,
                f'{m:.0f}±{d:.0f}ms',
                ha='center', va='bottom', fontsize=9, fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(cenarios_ok, fontsize=10)
    ax.set_ylabel('P95 E2E Latency (ms)')
    ax.set_title(f'P95 Latency Reproducibility ({len(runs)} runs)',
                 fontsize=13, fontweight='bold')
    ax.yaxis.grid(True, linestyle='--', alpha=0.6)
    ax.set_axisbelow(True)
    plt.tight_layout()
    p = f'{graf_dir}/variabilidade_p95_entre_runs.png'
    plt.savefig(p, bbox_inches='tight')
    plt.close()
    print(f"  [OK] {p}")


# ─── Comparativo TPS: Aplicação vs Blockchain ────────────────────────────────

def carregar_tps_fabric_por_cenario(output_dir: str = "resultados") -> dict:
    import re
    import glob

    OFFSETS = {
        'C1_baseline': (0,    300),
        'C2_leve':     (600,  600),
        'C3_moderada': (1500, 600),
        'C4_alta':     (2520, 600),
        'C5_maxima':   (3720, 600),
    }

    resultado = {c: [] for c in CENARIOS}
    padrao    = os.path.join(output_dir, 'run_*', 'prometheus_run*_wide.csv')
    arquivos  = sorted(glob.glob(padrao))
    if not arquivos:
        padrao   = os.path.join(output_dir, 'prometheus_run*_wide.csv')
        arquivos = sorted(glob.glob(padrao))
    if not arquivos:
        print("  [WARN] No prometheus_run*_wide.csv found — Fabric TPS unavailable")
        return resultado

    for csv_path in arquivos:
        m = re.search(r'run_(\d+)', csv_path)
        run_num = int(m.group(1)) if m else 1

        try:
            df_prom = pd.read_csv(csv_path, parse_dates=['timestamp'])
        except Exception as e:
            print(f"  [WARN] Error reading {csv_path}: {e}")
            continue

        if 'tps_validas' not in df_prom.columns or df_prom.empty:
            print(f"  [WARN] tps_validas missing in {csv_path}")
            continue

        mediana_tps = df_prom['tps_validas'].dropna().median()
        if mediana_tps > 5000:
            print(f"  [WARN] Run {run_num}: tps_validas median={mediana_tps:.0f} — possibly sum() instead of avg()")
            continue

        run_dir   = os.path.dirname(csv_path)
        meta_path = os.path.join(run_dir, 'metadata.json')
        janelas   = {}

        if os.path.isfile(meta_path):
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                for c, info in meta.get('cenarios', {}).items():
                    janelas[c] = (
                        pd.to_datetime(info['start'], utc=True),
                        pd.to_datetime(info['end'],   utc=True),
                    )
            except Exception:
                pass

        if not janelas:
            t0 = df_prom['timestamp'].min()
            if pd.isna(t0):
                continue
            for c, (offset, dur) in OFFSETS.items():
                janelas[c] = (
                    t0 + pd.Timedelta(seconds=offset),
                    t0 + pd.Timedelta(seconds=offset + dur),
                )

        for cenario, (t_ini, t_fim) in janelas.items():
            if cenario not in CENARIOS:
                continue
            mask   = (df_prom['timestamp'] >= t_ini) & (df_prom['timestamp'] <= t_fim)
            subset = df_prom.loc[mask, 'tps_validas'].dropna()
            subset = subset[subset > 0]
            if subset.empty:
                continue
            tps_normalizado = float(subset.mean())
            resultado[cenario].append(tps_normalizado)
            print(f"    Run {run_num} | {cenario}: "
                  f"{subset.mean():.3f} tx/s Fabric → "
                  f"{tps_normalizado:.3f} DOs/s"
                  f"{len(subset)} samples)")

    return resultado


def gerar_grafico_tps_comparativo(df: pd.DataFrame, graf_dir: str,
                                   output_dir: str = "resultados"):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import seaborn as sns
        sns.set_theme(style="whitegrid")
    except ImportError:
        print("  [WARN] matplotlib/seaborn not installed — skipping comparative TPS graph")
        return

    ancoradas = df[df['metric'] == 'm2_dos_ancoradas']
    runs      = sorted(df['run'].unique())

    tps_app: dict = {c: [] for c in CENARIOS}
    for cenario in CENARIOS:
        dur = DURACOES.get(cenario, 600)
        for run in runs:
            total = ancoradas[
                (ancoradas['cenario'] == cenario) & (ancoradas['run'] == run)
            ]['value'].sum()
            if total > 0:
                tps_app[cenario].append(total / dur)

    print("\n  Loading Fabric TPS from Prometheus CSVs...")
    tps_fabric = carregar_tps_fabric_por_cenario(output_dir)

    cenarios_ok = [c for c in CENARIOS if tps_app.get(c) or tps_fabric.get(c)]
    if not cenarios_ok:
        print("  [WARN] Insufficient data for TPS comparative graph")
        return

    media_app, dp_app, media_fab, dp_fab = [], [], [], []
    for c in cenarios_ok:
        va = tps_app.get(c, [])
        vf = tps_fabric.get(c, [])
        media_app.append(np.mean(va) if va else 0)
        dp_app.append(np.std(va)     if len(va) > 1 else 0)
        media_fab.append(np.mean(vf) if vf else 0)
        dp_fab.append(np.std(vf)     if len(vf) > 1 else 0)

    fig, ax = plt.subplots(figsize=(13, 6))
    x      = np.arange(len(cenarios_ok))
    w      = 0.35
    err_kw = dict(elinewidth=1.8, capsize=5, capthick=1.8, ecolor='black')

    bars_app = ax.bar(x - w/2, media_app, w,
                      yerr=dp_app if any(d > 0 for d in dp_app) else None,
                      label='App TPS',
                      color='#1565C0', alpha=0.85, edgecolor='white', error_kw=err_kw)
    bars_fab = ax.bar(x + w/2, media_fab, w,
                      yerr=dp_fab if any(d > 0 for d in dp_fab) else None,
                      label='Fabric TPS',
                      color='#00897B', alpha=0.85, edgecolor='white', error_kw=err_kw)

    y_max      = max(max(media_app, default=0), max(media_fab, default=0))
    offset_txt = y_max * 0.015 if y_max > 0 else 0.01

    for bar, val, dp in zip(bars_app, media_app, dp_app):
        if val > 0:
            txt = f'{val:.3f}' + (f'\n±{dp:.3f}' if dp > 0 else '')
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + dp + offset_txt,
                    txt, ha='center', va='bottom',
                    fontsize=12, color='#1565C0', fontweight='bold')

    for bar, val, dp in zip(bars_fab, media_fab, dp_fab):
        if val > 0:
            txt = f'{val:.3f}' + (f'\n±{dp:.3f}' if dp > 0 else '')
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + dp + offset_txt,
                    txt, ha='center', va='bottom',
                    fontsize=12, color='#00897B', fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels([LABELS_GRAF[c].replace('\n', ' ') for c in cenarios_ok], fontsize=14)
    ax.tick_params(axis='y', which='major', labelsize=13)
    ax.set_ylabel('Throughput (Req/s)', fontsize=16)
    ax.set_title('Application vs. Fabric Throughput',
                 fontsize=18, fontweight='bold')
    ax.yaxis.grid(True, linestyle='--', alpha=0.55)
    ax.set_axisbelow(True)
    ax.set_ylim(0, y_max * 1.35)
    ax.legend(loc='upper left', fontsize=14)
    plt.tight_layout()
    p_png = f'{graf_dir}/m2_tps_comparativo_app_vs_fabric.png'
    p_pdf = f'{graf_dir}/m2_tps_comparativo_app_vs_fabric.pdf'
    plt.savefig(p_png, bbox_inches='tight')
    plt.savefig(p_pdf, bbox_inches='tight')
    plt.close()
    print(f"  [OK] {p_png}")
    print(f"  [OK] {p_pdf}")


def gerar_boxplot_c3_c5(df: pd.DataFrame, graf_dir: str):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import seaborn as sns
    import numpy as np
    sns.set_theme(style="whitegrid")

    e2e = df[df['metric'] == 'm1_latencia_e2e_ms']
    cenarios_sel = ['C3_moderada', 'C4_alta', 'C5_maxima']

    dados, labels, cores_box = [], [], []
    for c in cenarios_sel:
        v = e2e[e2e['cenario'] == c]['value'].dropna().values
        v = v[v > 0]
        if len(v) > 0:
            dados.append(v)
            labels.append(LABELS_GRAF[c].replace('\n', ' '))
            cores_box.append(CORES[c])

    if not dados:
        return

    fig, ax = plt.subplots(figsize=(9, 6))
    bp = ax.boxplot(
        dados, patch_artist=True, notch=False,
        showfliers=False, whis=(5, 95),
        medianprops=dict(color='black', linewidth=2),
    )
    for patch, cor in zip(bp['boxes'], cores_box):
        patch.set_facecolor(cor); patch.set_alpha(0.75)
    for element in ['whiskers', 'caps']:
        for item in bp[element]:
            item.set_color('black'); item.set_linewidth(1.5)

    for i, (c, v) in enumerate(zip(cenarios_sel, dados), 1):
        p50 = np.percentile(v, 50)
        p95 = np.percentile(v, 95)
        ax.text(i, p95 * 1.01, f'P95={p95:.0f}ms',
                ha='center', va='bottom', fontsize=9,
                color=CORES[c], fontweight='bold')
        ax.text(i, p50 + (p95 - p50) * 0.05, f'P50={p50:.0f}ms',
                ha='center', va='bottom', fontsize=8,
                color='white', fontweight='bold')

    ax.set_xticks(range(1, len(cenarios_sel) + 1))
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylabel('E2E Latency (ms)')
    ax.set_title('E2E Latency by Scenario (C3–C5)', fontsize=13, fontweight='bold')
    ax.yaxis.grid(True, linestyle='--', alpha=0.6)
    ax.set_axisbelow(True)
    plt.tight_layout()
    p = f'{graf_dir}/m1_boxplot_c3_c5.png'
    plt.savefig(p, bbox_inches='tight'); plt.close()
    print(f"  [OK] {p}")
    
    



# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analise_resultados.py resultados/run_*/k6_*.json")
        sys.exit(1)

    arquivos = sys.argv[1:]
    print(f"\n{'='*70}")
    print(f"  Hermes + Hyperledger Fabric 3.0 Benchmark Analysis")
    print(f"  Date: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"  Files: {', '.join(arquivos)}")
    print(f"{'='*70}\n")

    df = carregar_k6(arquivos)
    if df.empty:
        print("[ERROR] No data found.")
        sys.exit(1)

    print("── M1: E2E Latency — successful anchorings only ─────────────────")
    df_m1 = analisar_m1(df)
    if not df_m1.empty:
        print(tabulate(df_m1, headers='keys', tablefmt='rounded_outline', showindex=False))
    else:
        print("  (no data — run the full test)")

    print("\n── M2: Throughput (TPS) ──────────────────────────────────────────")
    df_m2 = analisar_m2(df)
    print(tabulate(df_m2, headers='keys', tablefmt='rounded_outline', showindex=False))

    print("\n── M3: Success Rate ──────────────────────────────────────────────")
    df_m3 = analisar_m3(df)
    print(tabulate(df_m3, headers='keys', tablefmt='rounded_outline', showindex=False))

    print("\n── Native k6 Metrics ─────────────────────────────────────────────")
    df_nat = analisar_nativas(df)
    if not df_nat.empty:
        print(tabulate(df_nat, headers='keys', tablefmt='rounded_outline', showindex=False))

    print("\n── Submit vs. Polling Decomposition ─────────────────────────────")
    df_poll = analisar_polling(df)
    if not df_poll.empty:
        print(tabulate(df_poll, headers='keys', tablefmt='rounded_outline', showindex=False))
    else:
        print("  (latencia_polling_ms not found in data)")

    print("\n── M4: Isolated Fabric Latency (Prometheus) ─────────────────────")
    m4 = analisar_m4(output_dir="resultados")
    for k, v in m4.items():
        print(f"  {k}: {v}")

    print("\n── M5: Blockchain Overhead ───────────────────────────────────────")
    df_m5 = calcular_m5(df_m1, m4)
    if not df_m5.empty:
        print(tabulate(df_m5, headers='keys', tablefmt='rounded_outline', showindex=False))
    else:
        print("  (M4 unavailable — run with Prometheus active)")

    print("\n── M6: MVCC Conflicts (Prometheus — global snapshot) ────────────")
    m6 = analisar_m6()
    for k, v in m6.items():
        print(f"  {k}: {v}")

    print("\n── M6: MVCC Conflicts per Run (delta via m6_delta.json) ─────────")
    df_m6_runs = analisar_m6_por_run(arquivos)
    if not df_m6_runs.empty:
        print(tabulate(df_m6_runs, headers='keys', tablefmt='rounded_outline', showindex=False))
    else:
        print("  (m6_delta.json not found)")

    comparar_cenarios(df)

    runs = sorted(df['run'].unique())
    if len(runs) > 1:
        print(f"\n── Variability across {len(runs)} runs ──────────────────────────────")
        df_var = analisar_variabilidade_runs(df)
        if not df_var.empty:
            print(tabulate(df_var, headers='keys', tablefmt='rounded_outline', showindex=False))
        else:
            print("  (insufficient data)")

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs('resultados', exist_ok=True)
    df_m1.to_csv(f'resultados/m1_latencia_{timestamp}.csv', index=False)
    df_m2.to_csv(f'resultados/m2_throughput_{timestamp}.csv', index=False)
    df_m3.to_csv(f'resultados/m3_sucesso_{timestamp}.csv', index=False)
    if not df_nat.empty:
        df_nat.to_csv(f'resultados/nativas_{timestamp}.csv', index=False)
    print(f"\n[OK] CSVs exported to resultados/m*_{timestamp}.csv")

    print("\n── Extracting Prometheus raw data ────────────────────────────────")
    runs_info = detectar_intervalos_runs(arquivos)
    if runs_info:
        for r in runs_info:
            print(f"  Run {r['run']}: {r['start']} → {r['end']}")
        extrair_metricas_prometheus(runs_info, step="15s", output_dir="resultados")
    else:
        print("  [WARN] Could not detect run intervals automatically.")

    print("\n── Generating graphs ─────────────────────────────────────────────")
    gerar_graficos(df, timestamp)
    


if __name__ == '__main__':
    main()