#!/usr/bin/env python3
"""
analise_resultados.py — Análise estatística do benchmark Hermes + Fabric 3.0
Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License

Uso:
    python3 analise_resultados.py resultados/k6_*.json

Gráficos gerados em resultados/graficos_TIMESTAMP/:
    m1_boxplot_latencia_e2e.png
    m1_boxplot_vs_thresholds.png
    m1_violin_por_cenario.png
    m1_histograma_kde_por_cenario.png
    m1_cdf_por_cenario.png
    m1_scatter_temporal.png
    m2_throughput_por_cenario.png
    nativas_http_req_duration.png
    nativas_iteration_duration.png

Dependências:
    pip install numpy pandas scipy tabulate requests matplotlib seaborn
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

PROMETHEUS_URL = "http://localhost:9090"
CENARIOS = ['C1_baseline', 'C2_leve', 'C3_moderada', 'C4_alta']
CENARIOS_LABEL = {
    'C1_baseline': 'C1 — Baseline (1 VU)',
    'C2_leve':     'C2 — Moderada (10 VUs)',
    'C3_moderada': 'C3 — Alta (100 VUs)',
    'C4_alta':     'C4 — Extrema (500 VUs)',
}
CORES = {
    'C1_baseline': '#1565C0',   # azul escuro
    'C2_leve':     '#00897B',   # verde-azulado
    'C3_moderada': '#6A1B9A',   # roxo
    'C4_alta':     '#283593',   # índigo
}
# Cores semânticas para erros — separadas das cores de cenário
COR_TIMEOUT      = '#EF6C00'   # laranja escuro
COR_ERRO         = '#B71C1C'   # vermelho escuro — erro de submit
COR_ERRO_POLLING = '#6A1B9A'   # roxo escuro    — erro HTTP no polling
LABELS_GRAF = {
    'C1_baseline': 'C1\nBaseline\n(1 VU)',
    'C2_leve':     'C2\nModerada\n(10 VUs)',
    'C3_moderada': 'C3\nAlta\n(100 VUs)',
    'C4_alta':     'C4\nExtrema\n(500 VUs)',
}
THRESHOLDS_P95 = {
    'C1_baseline': 5000,
    'C2_leve':     10000,
    'C3_moderada': 30000,
    'C4_alta':     90000,
}

# ─── Carga dos dados k6 ───────────────────────────────────────────────────────

METRICAS_INTERESSE = {
    # customizadas
    'm1_latencia_e2e_ms', 'm2_dos_ancoradas', 'm3_taxa_sucesso',
    'latencia_polling_ms', 'dos_timeout', 'dos_erro', 'dos_erro_polling',
    # nativas k6
    'http_req_duration', 'http_req_waiting', 'http_req_receiving',
    'http_req_sending', 'iteration_duration', 'http_reqs',
}

def _detectar_run(arquivo: str) -> int:
    """Extrai o número do run do path (ex: run_2/k6_... → 2). Default: 1."""
    import re
    m = re.search(r'run_(\d+)', arquivo)
    return int(m.group(1)) if m else 1


def carregar_k6(arquivos: list[str]) -> pd.DataFrame:
    """
    Carrega um ou mais arquivos JSON do k6.
    O número do run é extraído automaticamente do path (run_1/, run_2/, etc.).
    Isso permite comparação entre execuções independentes.
    """
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
        # time_s relativo dentro de cada run
        df['time_s'] = df.groupby('run')['time'].transform(
            lambda x: (x - x.min()).dt.total_seconds()
        )

    n_runs = len(runs_encontrados)
    if n_runs > 1:
        print(f"  Detectados {n_runs} runs: {sorted(runs_encontrados)}")
    return df

# ─── M1: Latência end-to-end ──────────────────────────────────────────────────

def analisar_m1(df: pd.DataFrame) -> pd.DataFrame:
    e2e = df[df['metric'] == 'm1_latencia_e2e_ms']
    resultados = []
    for cenario in CENARIOS:
        vals = e2e[e2e['cenario'] == cenario]['value'].dropna().values
        vals = vals[vals >= 0]
        if len(vals) == 0:
            continue
        amostra = vals[:5000]
        _, p_shapiro = stats.shapiro(amostra) if len(amostra) >= 3 else (0, 1)
        ic_low, ic_high = stats.t.interval(
            0.95, df=len(vals)-1,
            loc=np.mean(vals), scale=stats.sem(vals)
        )
        resultados.append({
            'Cenário':        CENARIOS_LABEL.get(cenario, cenario),
            'N':              len(vals),
            'Média (ms)':     round(np.mean(vals), 1),
            'DP (ms)':        round(np.std(vals), 1),
            'CV (%)':         round((np.std(vals) / np.mean(vals)) * 100, 1) if np.mean(vals) > 0 else 0,
            'P50 (ms)':       round(np.percentile(vals, 50), 1),
            'P95 (ms)':       round(np.percentile(vals, 95), 1),
            'P99 (ms)':       round(np.percentile(vals, 99), 1),
            'Mín (ms)':       round(np.min(vals), 1),
            'Máx (ms)':       round(np.max(vals), 1),
            'IC 95% (ms)':    f"[{round(ic_low,1)}, {round(ic_high,1)}]",
            'Normal?':        'Sim' if p_shapiro > 0.05 else 'Não',
        })
    return pd.DataFrame(resultados)

# ─── M2: Throughput ───────────────────────────────────────────────────────────

def analisar_m2(df: pd.DataFrame) -> pd.DataFrame:
    ancoradas = df[df['metric'] == 'm2_dos_ancoradas']
    duracoes  = {'C1_baseline': 300, 'C2_leve': 600, 'C3_moderada': 600, 'C4_alta': 600}
    resultados = []
    for cenario in CENARIOS:
        total  = ancoradas[ancoradas['cenario'] == cenario]['value'].sum()
        duracao = duracoes.get(cenario, 600)
        tps    = total / duracao if duracao > 0 else 0
        resultados.append({
            'Cenário':       CENARIOS_LABEL.get(cenario, cenario),
            'DOs Ancoradas': int(total),
            'Duração (s)':   duracao,
            'TPS (médio)':   round(tps, 3),
        })
    return pd.DataFrame(resultados)

# ─── M3: Taxa de sucesso ──────────────────────────────────────────────────────

def analisar_m3(df: pd.DataFrame) -> pd.DataFrame:
    """
    M3 — Taxa de sucesso por cenário.

    Quatro categorias de resultado por iteração:
      SUCESSO       — DO submetida, calculada e ancorada no Fabric (ancoradoEm presente)
      TIMEOUT       — DO submetida mas ancoragem não confirmada em POLLING_TIMEOUT segundos
      ERRO SUBMIT   — Falha HTTP no submit (status != 200 ou calcId ausente)
      ERRO POLLING  — Falha HTTP durante o polling (status != 200 ao consultar status)

    M1 (latenciaE2E) mede APENAS as iterações de SUCESSO.
    """
    sucesso     = df[df['metric'] == 'm3_taxa_sucesso']
    timeout     = df[df['metric'] == 'dos_timeout']
    erro        = df[df['metric'] == 'dos_erro']
    erro_poll   = df[df['metric'] == 'dos_erro_polling']
    resultados = []
    for cenario in CENARIOS:
        n_sucesso   = sucesso[(sucesso['cenario'] == cenario) & (sucesso['value'] == 1)].shape[0]
        n_timeout   = int(timeout[timeout['cenario'] == cenario]['value'].sum())
        n_erro      = int(erro[erro['cenario'] == cenario]['value'].sum())
        n_erro_poll = int(erro_poll[erro_poll['cenario'] == cenario]['value'].sum())
        total       = n_sucesso + n_timeout + n_erro + n_erro_poll
        taxa_suc    = (n_sucesso   / total * 100) if total > 0 else 0
        taxa_to     = (n_timeout   / total * 100) if total > 0 else 0
        taxa_err    = (n_erro      / total * 100) if total > 0 else 0
        taxa_errp   = (n_erro_poll / total * 100) if total > 0 else 0
        resultados.append({
            'Cenário':              CENARIOS_LABEL.get(cenario, cenario),
            'Total':                total,
            'Sucesso (N)':          n_sucesso,
            'Timeout (N)':          n_timeout,
            'Erro Submit (N)':      n_erro,
            'Erro Polling (N)':     n_erro_poll,
            'Sucesso (%)':          round(taxa_suc,  2),
            'Timeout (%)':          round(taxa_to,   2),
            'Erro Submit (%)':      round(taxa_err,  2),
            'Erro Polling (%)':     round(taxa_errp, 2),
        })
    return pd.DataFrame(resultados)

# ─── Métricas nativas k6 ─────────────────────────────────────────────────────

def analisar_nativas(df: pd.DataFrame) -> pd.DataFrame:
    metricas = ['http_req_duration', 'http_req_waiting', 'iteration_duration',
                'latencia_polling_ms']
    resultados = []
    for metric in metricas:
        vals = df[df['metric'] == metric]['value'].dropna().values
        vals = vals[vals >= 0]
        if len(vals) == 0:
            continue
        resultados.append({
            'Métrica':    metric,
            'N':          len(vals),
            'Média (ms)': round(np.mean(vals), 1),
            'P50 (ms)':   round(np.percentile(vals, 50), 1),
            'P95 (ms)':   round(np.percentile(vals, 95), 1),
            'P99 (ms)':   round(np.percentile(vals, 99), 1),
            'Máx (ms)':   round(np.max(vals), 1),
        })
    return pd.DataFrame(resultados)

# ─── Decomposição polling vs. submit ─────────────────────────────────────────

def analisar_polling(df: pd.DataFrame) -> pd.DataFrame:
    """
    Decompõe M1 em tempo de submit HTTP e tempo de espera de ancoragem (polling).

    latencia_polling_ms = tempo desde o primeiro poll até confirmação de ancoradoEm
    submit ≈ m1_latencia_e2e_ms − latencia_polling_ms

    Útil para isolar quanto da latência E2E é custo do Fabric vs. custo HTTP.
    """
    polling = df[df['metric'] == 'latencia_polling_ms']
    e2e     = df[df['metric'] == 'm1_latencia_e2e_ms']
    resultados = []
    for cenario in CENARIOS:
        p_vals = polling[polling['cenario'] == cenario]['value'].dropna().values
        p_vals = p_vals[p_vals >= 0]
        e_vals = e2e[e2e['cenario'] == cenario]['value'].dropna().values
        e_vals = e_vals[e_vals >= 0]
        if len(p_vals) == 0 or len(e_vals) == 0:
            continue
        p50_poll = np.percentile(p_vals, 50)
        p95_poll = np.percentile(p_vals, 95)
        p50_e2e  = np.percentile(e_vals, 50)
        p95_e2e  = np.percentile(e_vals, 95)
        p50_sub  = round(max(0, p50_e2e - p50_poll), 1)
        p95_sub  = round(max(0, p95_e2e - p95_poll), 1)
        pct_p95  = round(p95_poll / p95_e2e * 100, 1) if p95_e2e > 0 else 0
        resultados.append({
            'Cenário':             CENARIOS_LABEL.get(cenario, cenario),
            'E2E P50 (ms)':        round(p50_e2e, 1),
            'Polling P50 (ms)':    round(p50_poll, 1),
            'Submit P50 (ms)':     p50_sub,
            'E2E P95 (ms)':        round(p95_e2e, 1),
            'Polling P95 (ms)':    round(p95_poll, 1),
            'Submit P95 (ms)':     p95_sub,
            'Polling/E2E P95 (%)': pct_p95,
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
        print(f"[WARN] Prometheus indisponível: {e}")
    return None

def analisar_m4() -> dict:
    p50_e = consultar_prometheus('histogram_quantile(0.50, sum(rate(endorser_proposal_duration_bucket{success="true",chaincode="calc_do"}[10m])) by (le)) * 1000')
    p95_e = consultar_prometheus('histogram_quantile(0.95, sum(rate(endorser_proposal_duration_bucket{success="true",chaincode="calc_do"}[10m])) by (le)) * 1000')
    p50_c = consultar_prometheus('histogram_quantile(0.50, sum(rate(ledger_block_processing_time_bucket{channel="channel-all"}[10m])) by (le)) * 1000')
    p95_c = consultar_prometheus('histogram_quantile(0.95, sum(rate(ledger_block_processing_time_bucket{channel="channel-all"}[10m])) by (le)) * 1000')
    return {
        'Endosso P50 (ms)': round(p50_e, 1) if p50_e else 'N/A',
        'Endosso P95 (ms)': round(p95_e, 1) if p95_e else 'N/A',
        'Commit P50 (ms)':  round(p50_c, 1) if p50_c else 'N/A',
        'Commit P95 (ms)':  round(p95_c, 1) if p95_c else 'N/A',
    }

# ─── M5: Overhead blockchain ─────────────────────────────────────────────────

def calcular_m5(df_m1: pd.DataFrame, m4: dict) -> pd.DataFrame:
    e_p95 = m4.get('Endosso P95 (ms)')
    c_p95 = m4.get('Commit P95 (ms)')
    if e_p95 == 'N/A' or c_p95 == 'N/A':
        return pd.DataFrame()
    l_fabric_p95 = float(e_p95) + float(c_p95)
    resultados = []
    for _, row in df_m1.iterrows():
        l_e2e = row['P95 (ms)']
        overhead = (l_fabric_p95 / l_e2e * 100) if l_e2e > 0 else 0
        resultados.append({
            'Cenário':               row['Cenário'],
            'L_e2e P95 (ms)':        l_e2e,
            'L_fabric P95 (ms)':     round(l_fabric_p95, 1),
            'Overhead Fabric (%)':   round(overhead, 1),
            'Overhead Pipeline (%)': round(100 - overhead, 1),
        })
    return pd.DataFrame(resultados)

# ─── M6: Conflitos MVCC ───────────────────────────────────────────────────────

def analisar_m6_por_run(arquivos: list[str]) -> pd.DataFrame:
    """
    Lê os arquivos m6_delta.json gerados pelo run_benchmark.sh e reporta
    conflitos MVCC por run (delta = contagem ao final − contagem antes do run).
    """
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
            'Run':              run_num,
            'Tx Válidas':       valid   if valid   is not None else 'N/A',
            'Tx MVCC Conflict': mvcc    if mvcc    is not None else 'N/A',
            'Tx Inválidas':     invalid if invalid is not None else 'N/A',
            'Taxa MVCC (%)':    round(mvcc / total * 100, 2) if total and mvcc else 0,
        })
    return pd.DataFrame(sorted(resultados, key=lambda x: x['Run']))


def analisar_m6() -> dict:
    mvcc    = consultar_prometheus('sum(ledger_transaction_count{validation_code="MVCC_READ_CONFLICT"})')
    invalid = consultar_prometheus('sum(ledger_transaction_count{validation_code="INVALID"})')
    valid   = consultar_prometheus('sum(ledger_transaction_count{validation_code="VALID"})')
    return {
        'Tx MVCC Conflict': int(mvcc)    if mvcc    is not None else 'N/A',
        'Tx Inválidas':     int(invalid) if invalid is not None else 'N/A',
        'Tx Válidas':       int(valid)   if valid   is not None else 'N/A',
    }

# ─── Comparação estatística ───────────────────────────────────────────────────

def comparar_cenarios(df: pd.DataFrame) -> None:
    e2e = df[df['metric'] == 'm1_latencia_e2e_ms']
    print("\n── Testes Mann-Whitney U (comparação entre cenários) ─────────────")
    pares = [('C1_baseline','C2_leve'), ('C2_leve','C3_moderada'), ('C3_moderada','C4_alta')]
    for a, b in pares:
        va = e2e[e2e['cenario'] == a]['value'].dropna().values
        vb = e2e[e2e['cenario'] == b]['value'].dropna().values
        va, vb = va[va >= 0], vb[vb >= 0]
        if len(va) < 2 or len(vb) < 2:
            continue
        stat_, p = stats.mannwhitneyu(va, vb, alternative='two-sided')
        sig = '✓ significativo (p<0.05)' if p < 0.05 else '✗ não significativo'
        print(f"  {CENARIOS_LABEL.get(a,a)} vs {CENARIOS_LABEL.get(b,b)}")
        print(f"    U={stat_:.1f}, p={p:.4f} — {sig}")

# ─── Gráficos ─────────────────────────────────────────────────────────────────

def gerar_graficos(df: pd.DataFrame, timestamp: str):
    """
    Gera gráficos do benchmark. Visualizações incluídas:
      1. Histograma + KDE por cenário (grade 2x2)
      2. Scatter temporal com mediana móvel
      3. Violin plot por cenário
      4. Throughput (TPS) por cenário — barras
      5. Variabilidade de P95 entre runs — barras com erro
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import seaborn as sns
    except ImportError:
        print("\n[WARN] Execute: pip install matplotlib seaborn")
        return

    graf_dir = f'resultados/graficos_{timestamp}'
    os.makedirs(graf_dir, exist_ok=True)
    sns.set_theme(style="whitegrid", palette="muted")
    plt.rcParams.update({
        'font.size': 11, 'axes.titlesize': 13,
        'axes.labelsize': 12, 'figure.dpi': 150
    })

    # ── Preparar dados base ───────────────────────────────────────────────────
    e2e = df[df['metric'] == 'm1_latencia_e2e_ms']
    dados = {}
    for c in CENARIOS:
        v = e2e[e2e['cenario'] == c]['value'].dropna().values
        v = v[v >= 0]
        if len(v) > 0:
            dados[c] = v

    cenarios_ok = [c for c in CENARIOS if c in dados]
    dados_list  = [dados[c] for c in cenarios_ok]

    # Cap P95 para visualização — outliers reportados nas tabelas
    cap       = {c: np.percentile(dados[c], 95) for c in cenarios_ok}
    dados_cap = [dados[c][dados[c] <= cap[c]]    for c in cenarios_ok]
    n_out     = sum(int(np.sum(dados[c] > cap[c])) for c in cenarios_ok)
    cap_label = (
        f"Visualização cortada no P95 "
        f"({n_out} valores acima omitidos — reportados na tabela)"
    )

    if not dados:
        print("[WARN] Sem dados e2e — rode o teste completo")
    else:
        # ── 1. Histograma + KDE (2x2) ─────────────────────────────────────────
        fig, axes = plt.subplots(2, 2, figsize=(13, 9))
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
            kde = stats.gaussian_kde(v)
            xr  = np.linspace(v.min(), v.max(), 300)
            ax.plot(xr, kde(xr), color=CORES[c], linewidth=2.5, label='KDE')
            ax.axvline(p50, color='navy',    linestyle='--', lw=1.5,
                       label=f'P50={p50:.0f}ms')
            ax.axvline(p95, color='darkred', linestyle='--', lw=1.5,
                       label=f'P95={p95:.0f}ms')
            ax.set_title(LABELS_GRAF[c].replace('\n', ' '), fontweight='bold')
            ax.set_xlabel('Latência E2E (ms)')
            ax.set_ylabel('Densidade')
            ax.legend(fontsize=9)
            ax.yaxis.grid(True, linestyle='--', alpha=0.5)

        fig.suptitle('M1 — Histograma + KDE de Latência E2E por Cenário',
                     fontsize=14, fontweight='bold')
        fig.text(0.5, 0.01, cap_label, ha='center', fontsize=8,
                 color='gray', style='italic')
        plt.tight_layout(rect=[0, 0.03, 1, 1])
        p = f'{graf_dir}/m1_histograma_kde_por_cenario.png'
        plt.savefig(p, bbox_inches='tight'); plt.close()
        print(f"  [OK] {p}")

        # ── 2. Scatter temporal — timeline absoluta ──────────────────────────────
        # Eixo X = tempo absoluto desde o início do run (minutos)
        # Cenários aparecem em sequência, separados por linhas verticais
        fig, ax = plt.subplots(figsize=(14, 6))
        e2e_time = df[(df['metric'] == 'm1_latencia_e2e_ms') &
                      (df['value'] >= 0)].copy()

        if 'time_s' not in e2e_time.columns:
            e2e_time['time_s'] = 0.0

        # Tempo global relativo ao início do primeiro ponto
        t_global_min = e2e_time['time_s'].min()
        e2e_time['time_abs_min'] = (e2e_time['time_s'] - t_global_min) / 60

        # P95 global para limitar eixo Y
        vals_todos  = e2e_time['value'].values
        vals_todos  = vals_todos[vals_todos >= 0]
        p95_global  = np.percentile(vals_todos, 95)

        cenario_start = {}

        for c in cenarios_ok:
            sub = e2e_time[e2e_time['cenario'] == c].copy()
            if sub.empty:
                continue
            p95_c   = np.percentile(sub['value'].values, 95)
            sub_vis = sub[sub['value'] <= p95_c].sort_values('time_abs_min')
            t_ini   = sub_vis['time_abs_min'].min()
            cenario_start[c] = t_ini

            ax.scatter(sub_vis['time_abs_min'], sub_vis['value'],
                       color=CORES[c], alpha=0.18, s=3, zorder=2)

            rolled = sub_vis['value'].rolling(
                window=60, min_periods=5, center=True
            ).median()
            ax.plot(sub_vis['time_abs_min'], rolled,
                    color=CORES[c], linewidth=2.5, zorder=3,
                    label=CENARIOS_LABEL[c])

        # Linhas verticais de transição
        for c, t_ini in cenario_start.items():
            ax.axvline(t_ini, color=CORES[c], linestyle='--',
                       linewidth=1.2, alpha=0.7, zorder=1)
            ax.text(t_ini + 0.15, p95_global * 1.03,
                    LABELS_GRAF[c].replace('\n', ' '),
                    color=CORES[c], fontsize=8, va='bottom')

        ax.set_xlabel('Tempo desde início do run (min)')
        ax.set_ylabel('Latência E2E (ms)')
        ax.set_title(
            'M1 — Scatter Temporal de Latência E2E (timeline absoluta)\n'
            'pontos = amostras individuais (<=P95), linha = mediana móvel (60pts)',
            fontsize=12
        )
        ax.set_ylim(bottom=0, top=p95_global * 1.2)
        ax.yaxis.grid(True, linestyle='--', alpha=0.5)
        ax.legend(loc='upper left', fontsize=9, markerscale=3)
        ax.annotate(
            f"Eixo Y e pontos limitados ao P95 ({p95_global:.0f}ms) — timeouts omitidos da visualizacao",
            xy=(0.5, -0.08), xycoords='axes fraction',
            ha='center', fontsize=8, color='gray', style='italic'
        )
        plt.tight_layout()
        p = f'{graf_dir}/m1_scatter_temporal.png'
        plt.savefig(p, bbox_inches='tight'); plt.close()
        print(f"  [OK] {p}")


        # ── 3. Violin plot ────────────────────────────────────────────────────
        fig, ax = plt.subplots(figsize=(10, 6))
        # Cap por cenário: P90 para não deixar C4 achatar os demais
        # Cada cenário tem seu próprio cap independente
        cap_violin  = {c: np.percentile(dados[c], 90) for c in cenarios_ok}
        dados_v90   = [dados[c][dados[c] <= cap_violin[c]] for c in cenarios_ok]
        vp = ax.violinplot(dados_v90,
                           positions=range(1, len(cenarios_ok) + 1),
                           showmedians=True, showextrema=False)
        for body, cor in zip(vp['bodies'], [CORES[c] for c in cenarios_ok]):
            body.set_facecolor(cor)
            body.set_alpha(0.72)
        vp['cmedians'].set_color('black')
        vp['cmedians'].set_linewidth(2)

        # Marcadores de P25 e P75
        for i, v in enumerate(dados_list, 1):
            ax.scatter([i], [np.percentile(v, 25)], color='white',
                       edgecolors='black', s=45, zorder=5, marker='o')
            ax.scatter([i], [np.percentile(v, 75)], color='white',
                       edgecolors='black', s=45, zorder=5, marker='s')

        # Eixo Y: 2º maior P90 entre os cenários para não deixar C4 esmagar os demais
        caps_sorted = sorted(cap_violin[c] for c in cenarios_ok)
        p90_max = caps_sorted[-2] if len(caps_sorted) > 1 else caps_sorted[-1]
        ax.set_ylim(bottom=0, top=p90_max * 1.35)
        ax.set_xticks(range(1, len(cenarios_ok) + 1))
        ax.set_xticklabels([LABELS_GRAF[c] for c in cenarios_ok])
        ax.set_ylabel('Latência E2E (ms)')
        ax.set_title('M1 — Violin Plot de Latência E2E por Cenário')
        ax.yaxis.grid(True, linestyle='--', alpha=0.6)
        leg_items = [
            mpatches.Patch(color='white', label='● P25'),
            mpatches.Patch(color='white', label='■ P75'),
        ]
        ax.legend(handles=leg_items, loc='upper left', fontsize=9)
        ax.annotate(
            f"Dados cortados no P90 por cenário — eixo Y no 2º maior P90 (C4 pode ultrapassar a escala)",
            xy=(0.5, -0.1), xycoords='axes fraction',
            ha='center', fontsize=8, color='gray', style='italic'
        )
        plt.tight_layout()
        p = f'{graf_dir}/m1_violin_por_cenario.png'
        plt.savefig(p, bbox_inches='tight'); plt.close()
        print(f"  [OK] {p}")

    # ── 4. Throughput por cenário — barras ────────────────────────────────────
    ancoradas = df[df['metric'] == 'm2_dos_ancoradas']
    duracoes  = {'C1_baseline': 300, 'C2_leve': 600,
                 'C3_moderada': 600, 'C4_alta':  600}
    tps_data  = [
        (LABELS_GRAF[c].replace('\n', ' '),
         round(ancoradas[ancoradas['cenario'] == c]['value'].sum() / duracoes[c], 3),
         CORES[c])
        for c in CENARIOS
        if ancoradas[ancoradas['cenario'] == c]['value'].sum() > 0
    ]

    if tps_data:
        labels_t, tps_vals, cores_t = zip(*tps_data)
        fig, ax = plt.subplots(figsize=(9, 5))
        bars = ax.bar(labels_t, tps_vals, color=cores_t,
                      alpha=0.85, edgecolor='white')
        for bar, val in zip(bars, tps_vals):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(tps_vals) * 0.01,
                    f'{val:.3f} tx/s',
                    ha='center', va='bottom', fontsize=10, fontweight='bold')
        ax.set_ylabel('Throughput (tx/s)')
        ax.set_title('M2 — Throughput por Cenário (DOs ancoradas/s)',
                     fontsize=13, fontweight='bold')
        ax.yaxis.grid(True, linestyle='--', alpha=0.6)
        ax.set_axisbelow(True)
        plt.tight_layout()
        p = f'{graf_dir}/m2_throughput_por_cenario.png'
        plt.savefig(p, bbox_inches='tight'); plt.close()
        print(f"  [OK] {p}")

    # ── 5. Opção A — Barra empilhada: Sucesso vs Timeout vs Erro Submit vs Erro Polling ──
    timeout_df   = df[df['metric'] == 'dos_timeout']
    erro_df      = df[df['metric'] == 'dos_erro']
    errop_df     = df[df['metric'] == 'dos_erro_polling']
    sucesso_df   = df[(df['metric'] == 'm3_taxa_sucesso') & (df['value'] == 1)]

    stacked_data = []
    for c in CENARIOS:
        n_suc  = sucesso_df[sucesso_df['cenario'] == c].shape[0]
        n_to   = int(timeout_df[timeout_df['cenario'] == c]['value'].sum())
        n_err  = int(erro_df[erro_df['cenario'] == c]['value'].sum())
        n_errop = int(errop_df[errop_df['cenario'] == c]['value'].sum())
        total  = n_suc + n_to + n_err + n_errop
        if total > 0:
            stacked_data.append({
                'cenario': CENARIOS_LABEL[c],
                'sucesso': n_suc  / total * 100,
                'timeout': n_to   / total * 100,
                'erro':    n_err  / total * 100,
                'errop':   n_errop / total * 100,
                'n_suc':   n_suc,
                'n_to':    n_to,
                'n_err':   n_err,
                'n_errop': n_errop,
                'total':   total,
            })

    if stacked_data:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import seaborn as sns
        sns.set_theme(style='whitegrid')

        fig, ax = plt.subplots(figsize=(10, 6))
        labels_s   = [d['cenario'] for d in stacked_data]
        x          = np.arange(len(labels_s))
        w          = 0.55
        suc_vals   = [d['sucesso'] for d in stacked_data]
        to_vals    = [d['timeout'] for d in stacked_data]
        err_vals   = [d['erro']    for d in stacked_data]
        errop_vals = [d['errop']   for d in stacked_data]

        b1 = ax.bar(x, suc_vals,   w, label='Sucesso',        color='#4CAF50',      alpha=0.85)
        b2 = ax.bar(x, to_vals,    w, label='Timeout',         color=COR_TIMEOUT,    alpha=0.85,
                    bottom=suc_vals)
        b3 = ax.bar(x, err_vals,   w, label='Erro Submit',     color=COR_ERRO,       alpha=0.85,
                    bottom=[s+t for s, t in zip(suc_vals, to_vals)])
        b4 = ax.bar(x, errop_vals, w, label='Erro Polling',    color=COR_ERRO_POLLING, alpha=0.85,
                    bottom=[s+t+e for s, t, e in zip(suc_vals, to_vals, err_vals)])

        # Anotar N dentro de cada segmento
        for i, d in enumerate(stacked_data):
            if d['n_suc'] > 0:
                ax.text(i, d['sucesso'] / 2, f"{d['n_suc']:,}",
                        ha='center', va='center', fontsize=8,
                        color='white', fontweight='bold')
            if d['n_to'] > 0:
                ax.text(i, d['sucesso'] + d['timeout'] / 2,
                        f"{d['n_to']:,}",
                        ha='center', va='center', fontsize=8,
                        color='white', fontweight='bold')
            if d['n_err'] > 0:
                ax.text(i, d['sucesso'] + d['timeout'] + d['erro'] / 2,
                        f"{d['n_err']:,}",
                        ha='center', va='center', fontsize=8,
                        color='white', fontweight='bold')
            if d['n_errop'] > 0:
                ax.text(i, d['sucesso'] + d['timeout'] + d['erro'] + d['errop'] / 2,
                        f"{d['n_errop']:,}",
                        ha='center', va='center', fontsize=8,
                        color='white', fontweight='bold')

        ax.set_xticks(x)
        ax.set_xticklabels(labels_s, fontsize=10)
        ax.set_ylabel('Proporção (%)')
        ax.set_ylim(0, 105)
        ax.set_title('M3 — Distribuicao de Resultados por Cenario\n'
                     '(numeros = contagem absoluta de iteracoes)',
                     fontsize=13, fontweight='bold')
        ax.yaxis.grid(True, linestyle='--', alpha=0.5)
        ax.set_axisbelow(True)
        ax.legend(loc='lower left', fontsize=10)
        plt.tight_layout()
        p = f'{graf_dir}/m3_stacked_sucesso_timeout_erro.png'
        plt.savefig(p, bbox_inches='tight'); plt.close()
        print(f"  [OK] {p}")

    # ── 6. Opção B — Scatter com timeouts marcados no topo ────────────────────
    if dados:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import seaborn as sns
        sns.set_theme(style='whitegrid')

        fig, ax = plt.subplots(figsize=(14, 6))
        e2e_full = df[(df['metric'] == 'm1_latencia_e2e_ms') &
                      (df['value'] >= 0)].copy()
        to_full  = df[df['metric'] == 'dos_timeout'].copy()

        if 'time_s' not in e2e_full.columns:
            e2e_full['time_s'] = 0.0
        if 'time_s' not in to_full.columns:
            to_full['time_s'] = 0.0

        t_global_min = e2e_full['time_s'].min()
        e2e_full['time_abs_min'] = (e2e_full['time_s'] - t_global_min) / 60
        to_full['time_abs_min']  = (to_full['time_s']  - t_global_min) / 60

        vals_ok   = e2e_full['value'].values
        vals_ok   = vals_ok[vals_ok >= 0]
        p95_glob  = np.percentile(vals_ok, 95)
        topo_y    = p95_glob * 1.15  # linha de timeout

        cenario_start_b = {}
        for c in cenarios_ok:
            sub = e2e_full[e2e_full['cenario'] == c].copy()
            if sub.empty:
                continue
            p95_c   = np.percentile(sub['value'].values, 95)
            sub_vis = sub[sub['value'] <= p95_c].sort_values('time_abs_min')
            if sub_vis.empty:
                continue
            t_ini = sub_vis['time_abs_min'].min()
            cenario_start_b[c] = t_ini

            ax.scatter(sub_vis['time_abs_min'], sub_vis['value'],
                       color=CORES[c], alpha=0.15, s=3, zorder=2)
            rolled = sub_vis['value'].rolling(
                window=60, min_periods=5, center=True).median()
            ax.plot(sub_vis['time_abs_min'], rolled,
                    color=CORES[c], linewidth=2.5, zorder=3,
                    label=CENARIOS_LABEL[c])

            # Timeouts deste cenário como pontos X vermelhos no topo
            to_c = to_full[to_full['cenario'] == c]
            if not to_c.empty:
                ax.scatter(to_c['time_abs_min'],
                           [topo_y * 0.97] * len(to_c),
                           marker='x', color=COR_ERRO, s=30,
                           linewidths=1.5, zorder=5,
                           label='_timeout')

        # Linha de referência dos timeouts
        ax.axhline(topo_y * 0.97, color=COR_ERRO, linestyle=':',
                   linewidth=1, alpha=0.6, label='Timeout (90s)')

        # Linhas verticais de cenário
        for c, t_ini in cenario_start_b.items():
            ax.axvline(t_ini, color=CORES[c], linestyle='--',
                       linewidth=1.2, alpha=0.6, zorder=1)
            ax.text(t_ini + 0.1, p95_glob * 1.05,
                    LABELS_GRAF[c].replace('\n', ' '),
                    color=CORES[c], fontsize=8, va='bottom')

        ax.set_xlabel('Tempo desde início do run (min)')
        ax.set_ylabel('Latência E2E (ms)')
        ax.set_title(
            'pontos normais (<=P95) + X vermelho = timeout',
            fontsize=12
        )
        ax.set_ylim(bottom=0, top=topo_y * 1.05)
        ax.yaxis.grid(True, linestyle='--', alpha=0.5)
        # Montar legenda sem duplicatas
        handles, lbls = ax.get_legend_handles_labels()
        seen, h_dedup, l_dedup = set(), [], []
        for h, l in zip(handles, lbls):
            if l not in seen and not l.startswith('_'):
                seen.add(l); h_dedup.append(h); l_dedup.append(l)
        ax.legend(h_dedup, l_dedup, loc='upper left', fontsize=9, markerscale=2)
        plt.tight_layout()
        p = f'{graf_dir}/m1_scatter_com_timeouts.png'
        plt.savefig(p, bbox_inches='tight'); plt.close()
        print(f"  [OK] {p}")

    # ── 7. Opção D — Throughput dividido: ancoradas vs falhas ─────────────────
    ancoradas_d = df[df['metric'] == 'm2_dos_ancoradas']
    timeout_d   = df[df['metric'] == 'dos_timeout']
    erro_d      = df[df['metric'] == 'dos_erro']
    errop_d     = df[df['metric'] == 'dos_erro_polling']
    duracoes_d  = {'C1_baseline':300,'C2_leve':600,'C3_moderada':600,'C4_alta':600}

    tps_suc, tps_to, tps_err, tps_errop, labels_d, cores_d = [], [], [], [], [], []
    for c in CENARIOS:
        n_suc   = ancoradas_d[ancoradas_d['cenario'] == c]['value'].sum()
        n_to    = timeout_d[timeout_d['cenario'] == c]['value'].sum()
        n_err   = erro_d[erro_d['cenario'] == c]['value'].sum()
        n_errop = errop_d[errop_d['cenario'] == c]['value'].sum()
        dur     = duracoes_d.get(c, 600)
        if n_suc + n_to + n_err + n_errop > 0:
            tps_suc.append(round(n_suc   / dur, 3))
            tps_to.append(round(n_to     / dur, 3))
            tps_err.append(round(n_err   / dur, 3))
            tps_errop.append(round(n_errop / dur, 3))
            labels_d.append(LABELS_GRAF[c].replace('\n', ' '))
            cores_d.append(CORES[c])

    if tps_suc:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import seaborn as sns
        sns.set_theme(style='whitegrid')

        fig, ax = plt.subplots(figsize=(9, 5))
        x = np.arange(len(labels_d))
        w = 0.55
        b1 = ax.bar(x, tps_suc,   w, label='Ancoradas (sucesso)',
                    color=[c for c in cores_d], alpha=0.85)
        b2 = ax.bar(x, tps_to,    w, label='Timeout',
                    color=COR_TIMEOUT, alpha=0.85, bottom=tps_suc)
        b3 = ax.bar(x, tps_err,   w, label='Erro Submit',
                    color=COR_ERRO, alpha=0.85,
                    bottom=[s+t for s, t in zip(tps_suc, tps_to)])
        b4 = ax.bar(x, tps_errop, w, label='Erro Polling',
                    color=COR_ERRO_POLLING, alpha=0.85,
                    bottom=[s+t+e for s, t, e in zip(tps_suc, tps_to, tps_err)])

        # Anotar TPS de sucesso em cada barra
        for i, (s, t, e, ep) in enumerate(zip(tps_suc, tps_to, tps_err, tps_errop)):
            total_tps = s + t + e + ep
            ax.text(i, total_tps + max(tps_suc) * 0.01,
                    f'{s:.2f} tx/s',
                    ha='center', va='bottom', fontsize=9, fontweight='bold',
                    color=cores_d[i])

        ax.set_xticks(x)
        ax.set_xticklabels(labels_d, fontsize=10)
        ax.set_ylabel('Throughput (tx/s)')
        ax.set_title('M2 — Throughput dividido: sucesso vs falhas',
                     fontsize=13, fontweight='bold')
        ax.yaxis.grid(True, linestyle='--', alpha=0.6)
        ax.set_axisbelow(True)
        ax.legend(loc='upper left', fontsize=9)
        plt.tight_layout()
        p = f'{graf_dir}/m2_throughput_dividido.png'
        plt.savefig(p, bbox_inches='tight'); plt.close()
        print(f"  [OK] {p}")

    # ── 8. Variabilidade P95 entre runs ───────────────────────────────────────
    gerar_grafico_variabilidade(df, graf_dir)

    n_graficos = len(os.listdir(graf_dir))
    print(f"\n[OK] {n_graficos} gráficos salvos em {graf_dir}/")


# ─── Extração de dados brutos do Prometheus ───────────────────────────────────

def extrair_prometheus_range(query: str, start: str, end: str,
                              step: str = "15s") -> pd.DataFrame:
    """
    Consulta o Prometheus por range e retorna DataFrame com colunas:
        timestamp (datetime), value (float), instance (str)

    Parâmetros:
        query  — PromQL (ex: 'sum(rate(...))')
        start  — ISO8601 ou Unix timestamp (ex: '2026-03-19T16:19:00Z')
        end    — ISO8601 ou Unix timestamp
        step   — resolução (ex: '15s', '1m')
    """
    try:
        r = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={"query": query, "start": start, "end": end, "step": step},
            timeout=30
        )
        data = r.json()
        if data.get("status") != "success":
            print(f"[WARN] Prometheus retornou status: {data.get('status')}")
            return pd.DataFrame()

        registros = []
        for serie in data["data"]["result"]:
            instance = serie["metric"].get("instance", "agregado")
            for ts, val in serie["values"]:
                registros.append({
                    "timestamp": pd.to_datetime(ts, unit="s", utc=True),
                    "value":     float(val),
                    "instance":  instance,
                })
        return pd.DataFrame(registros)
    except Exception as e:
        print(f"[WARN] Erro ao consultar Prometheus range: {e}")
        return pd.DataFrame()


def extrair_metricas_prometheus(runs_info: list[dict],
                                 step: str = "15s",
                                 output_dir: str = "resultados") -> None:
    """
    Extrai métricas de vazão e latência do Prometheus para cada run
    e salva como CSVs separados.

    Parâmetro runs_info: lista de dicts com:
        {"run": 1, "start": "2026-03-19T16:19:28Z", "end": "2026-03-19T17:00:00Z"}

    Os timestamps são detectados automaticamente dos arquivos k6 se não fornecidos.

    Métricas extraídas:
        - tps_validas        — tx válidas/s (ledger_transaction_count VALID)
        - tps_total          — tx totais/s
        - altura_blockchain  — blocos por peer
        - latencia_endosso   — P50/P95 de endorser_proposal_duration
        - latencia_commit    — P50/P95 de ledger_block_processing_time
    """
    os.makedirs(output_dir, exist_ok=True)

    QUERIES = {
        "tps_validas": (
            'sum(rate(ledger_transaction_count{validation_code="VALID",'
            'channel="channel-all"}[1m]))'
        ),
        "tps_total": (
            'sum(rate(ledger_transaction_count{channel="channel-all"}[1m]))'
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

        print(f"\n  Run {run_num} ({start} -> {end})")
        frames = []

        for nome_metrica, query in QUERIES.items():
            df_q = extrair_prometheus_range(query, start, end, step)
            if df_q.empty:
                print(f"    [WARN] {nome_metrica}: sem dados")
                continue
            df_q["metrica"] = nome_metrica
            df_q["run"]     = run_num
            frames.append(df_q)
            print(f"    [OK] {nome_metrica}: {len(df_q)} pontos")

        if not frames:
            print(f"    [WARN] Run {run_num}: nenhum dado retornado do Prometheus")
            continue

        df_run = pd.concat(frames, ignore_index=True)

        # Salvar CSV bruto — uma linha por (timestamp, metrica, instance, run)
        csv_path = f"{output_dir}/prometheus_run{run_num}_{step.replace('s','s').replace('m','m')}.csv"
        df_run.to_csv(csv_path, index=False)
        print(f"    [OK] Salvo: {csv_path} ({len(df_run)} linhas)")

        # Salvar também em formato wide (pivot) — mais fácil para plotar
        try:
            # Para métricas agregadas (sem instance específica)
            metricas_agregadas = [m for m in QUERIES if "por_peer" not in m]
            df_pivot = df_run[df_run["metrica"].isin(metricas_agregadas)].copy()
            df_pivot = df_pivot.groupby(["timestamp", "metrica", "run"])["value"].mean().reset_index()
            df_wide = df_pivot.pivot_table(
                index=["timestamp", "run"],
                columns="metrica",
                values="value"
            ).reset_index()
            wide_path = f"{output_dir}/prometheus_run{run_num}_wide.csv"
            df_wide.to_csv(wide_path, index=False)
            print(f"    [OK] Wide: {wide_path}")
        except Exception as e:
            print(f"    [WARN] Pivot falhou: {e}")


def detectar_intervalos_runs(arquivos: list[str]) -> list[dict]:
    """
    Detecta automaticamente os intervalos de tempo de cada run.

    Ordem de preferência:
      1. run_N/metadata.json gerado pelo run_benchmark.sh (timestamps precisos)
      2. Timestamp no nome do arquivo k6 + estimativa de 75 min (fallback)
    """
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

        # Preferência: metadata.json com timestamps reais do run_benchmark.sh
        run_dir   = os.path.dirname(os.path.abspath(arquivo))
        meta_path = os.path.join(run_dir, 'metadata.json')
        if os.path.isfile(meta_path):
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                runs_info[run_num] = {
                    'run':   meta['run'],
                    'start': meta['start'],
                    'end':   meta['end'],
                }
                continue
            except Exception:
                pass  # fallback para detecção pelo nome do arquivo

        # Fallback: estima a partir do timestamp no nome do arquivo
        m_ts = re.search(r'(\d{8})_(\d{6})', arquivo)
        if not m_ts:
            continue

        data_str = m_ts.group(1)
        hora_str = m_ts.group(2)

        try:
            dt_inicio = datetime.strptime(f"{data_str}_{hora_str}", "%Y%m%d_%H%M%S")
            import time as time_mod
            offset_h = -time_mod.timezone // 3600
            dt_utc = dt_inicio - pd.Timedelta(hours=offset_h)
            # C4 encerra em ~52min + gracefulStop 12min = ~64min; 75min para margem
            dt_fim = dt_utc + timedelta(minutes=75)
            runs_info[run_num] = {
                'run':   run_num,
                'start': dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'end':   dt_fim.strftime('%Y-%m-%dT%H:%M:%SZ'),
            }
        except ValueError:
            continue

    result = sorted(runs_info.values(), key=lambda x: x['run'])
    return result

# ─── Variabilidade entre runs ─────────────────────────────────────────────────

def analisar_variabilidade_runs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compara P50/P95 de latência E2E entre runs independentes.
    Relevante quando há múltiplos arquivos de runs diferentes.
    Reporta média e desvio padrão entre runs — padrão acadêmico.
    """
    runs = sorted(df['run'].unique())
    if len(runs) <= 1:
        return pd.DataFrame()

    e2e = df[df['metric'] == 'm1_latencia_e2e_ms']
    resultados = []
    for cenario in CENARIOS:
        p50_por_run, p95_por_run, tps_por_run = [], [], []
        ancoradas = df[df['metric'] == 'm2_dos_ancoradas']
        duracoes  = {'C1_baseline':300,'C2_leve':600,'C3_moderada':600,'C4_alta':600}

        for run in runs:
            vals = e2e[(e2e['cenario'] == cenario) & (e2e['run'] == run)]['value'].dropna().values
            vals = vals[vals >= 0]
            if len(vals) > 0:
                p50_por_run.append(np.percentile(vals, 50))
                p95_por_run.append(np.percentile(vals, 95))
            total = ancoradas[(ancoradas['cenario'] == cenario) & (ancoradas['run'] == run)]['value'].sum()
            dur = duracoes.get(cenario, 600)
            if total > 0:
                tps_por_run.append(total / dur)

        if not p50_por_run:
            continue

        resultados.append({
            'Cenário':          CENARIOS_LABEL.get(cenario, cenario),
            'Runs':             len(runs),
            'P50 média (ms)':   round(np.mean(p50_por_run), 1),
            'P50 DP (ms)':      round(np.std(p50_por_run), 1),
            'P95 média (ms)':   round(np.mean(p95_por_run), 1),
            'P95 DP (ms)':      round(np.std(p95_por_run), 1),
            'TPS média':        round(np.mean(tps_por_run), 3) if tps_por_run else 0,
            'TPS DP':           round(np.std(tps_por_run), 3)  if tps_por_run else 0,
        })
    return pd.DataFrame(resultados)


def gerar_grafico_variabilidade(df: pd.DataFrame, graf_dir: str):
    """
    Gera gráfico de barras com erro (mean ± std) para P95 de latência E2E
    entre runs — visualiza reprodutibilidade do benchmark.
    """
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
    cenarios_ok = []
    medias, desvios, cores_bar = [], [], []

    for cenario in CENARIOS:
        p95_por_run = []
        for run in runs:
            vals = e2e[(e2e['cenario'] == cenario) & (e2e['run'] == run)]['value'].dropna().values
            vals = vals[vals >= 0]
            if len(vals) > 0:
                p95_por_run.append(np.percentile(vals, 95))
        if p95_por_run:
            cenarios_ok.append(CENARIOS_LABEL[cenario])
            medias.append(np.mean(p95_por_run))
            desvios.append(np.std(p95_por_run))
            cores_bar.append(CORES[cenario])

    if not cenarios_ok:
        return

    fig, ax = plt.subplots(figsize=(9, 5))
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
    ax.set_ylabel('P95 Latência E2E (ms)')
    ax.set_title(f'Reprodutibilidade — P95 Latência E2E (média ± DP, {len(runs)} runs)',
                 fontsize=13, fontweight='bold')
    ax.yaxis.grid(True, linestyle='--', alpha=0.6)
    ax.set_axisbelow(True)
    plt.tight_layout()
    p = f'{graf_dir}/variabilidade_p95_entre_runs.png'
    plt.savefig(p, bbox_inches='tight')
    plt.close()
    print(f"  [OK] {p}")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Uso: python3 analise_resultados.py resultados/k6_*.json")
        sys.exit(1)

    arquivos = sys.argv[1:]
    print(f"\n{'='*70}")
    print(f"  Benchmark Hermes + Hyperledger Fabric 3.0")
    print(f"  Análise: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"  Arquivos: {', '.join(arquivos)}")
    print(f"{'='*70}\n")

    df = carregar_k6(arquivos)
    if df.empty:
        print("[ERRO] Nenhum dado encontrado.")
        sys.exit(1)

    print("── M1: Latência E2E — apenas ancoragens bem-sucedidas ───────────")
    df_m1 = analisar_m1(df)
    if not df_m1.empty:
        print(tabulate(df_m1, headers='keys', tablefmt='rounded_outline', showindex=False))
    else:
        print("  (sem dados — rode o teste completo sem --vus/--duration)")

    print("\n── M2: Throughput (TPS) ──────────────────────────────────────────")
    df_m2 = analisar_m2(df)
    print(tabulate(df_m2, headers='keys', tablefmt='rounded_outline', showindex=False))

    print("\n── M3: Taxa de Sucesso ───────────────────────────────────────────")
    df_m3 = analisar_m3(df)
    print(tabulate(df_m3, headers='keys', tablefmt='rounded_outline', showindex=False))

    print("\n── Métricas Nativas k6 ───────────────────────────────────────────")
    df_nat = analisar_nativas(df)
    if not df_nat.empty:
        print(tabulate(df_nat, headers='keys', tablefmt='rounded_outline', showindex=False))

    print("\n── Decomposição Submit vs. Polling (Fabric wait) ─────────────────")
    df_poll = analisar_polling(df)
    if not df_poll.empty:
        print(tabulate(df_poll, headers='keys', tablefmt='rounded_outline', showindex=False))
    else:
        print("  (latencia_polling_ms não encontrada nos dados)")

    print("\n── M4: L_fabric Isolado (Prometheus) ────────────────────────────")
    m4 = analisar_m4()
    for k, v in m4.items():
        print(f"  {k}: {v}")

    print("\n── M5: Overhead Blockchain ───────────────────────────────────────")
    df_m5 = calcular_m5(df_m1, m4)
    if not df_m5.empty:
        print(tabulate(df_m5, headers='keys', tablefmt='rounded_outline', showindex=False))
    else:
        print("  (M4 indisponível — execute com Prometheus ativo)")

    print("\n── M6: Conflitos MVCC (Prometheus — snapshot global) ────────────")
    m6 = analisar_m6()
    for k, v in m6.items():
        print(f"  {k}: {v}")

    print("\n── M6: Conflitos MVCC por Run (delta via m6_delta.json) ─────────")
    df_m6_runs = analisar_m6_por_run(arquivos)
    if not df_m6_runs.empty:
        print(tabulate(df_m6_runs, headers='keys', tablefmt='rounded_outline', showindex=False))
    else:
        print("  (m6_delta.json não encontrado — disponível a partir da próxima run com run_benchmark.sh)")

    comparar_cenarios(df)

    runs = sorted(df['run'].unique())
    if len(runs) > 1:
        print(f"\n── Variabilidade entre {len(runs)} runs ─────────────────────────────────")
        df_var = analisar_variabilidade_runs(df)
        if not df_var.empty:
            print(tabulate(df_var, headers='keys', tablefmt='rounded_outline', showindex=False))
        else:
            print("  (dados insuficientes)")

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs('resultados', exist_ok=True)
    df_m1.to_csv(f'resultados/m1_latencia_{timestamp}.csv', index=False)
    df_m2.to_csv(f'resultados/m2_throughput_{timestamp}.csv', index=False)
    df_m3.to_csv(f'resultados/m3_sucesso_{timestamp}.csv', index=False)
    if not df_nat.empty:
        df_nat.to_csv(f'resultados/nativas_{timestamp}.csv', index=False)
    print(f"\n[OK] CSVs exportados em resultados/m*_{timestamp}.csv")

    # ── Extração de dados brutos do Prometheus ───────────────────────────────
    print("\n── Extraindo dados brutos do Prometheus ──────────────────────────")
    runs_info = detectar_intervalos_runs(arquivos)
    if runs_info:
        for r in runs_info:
            print(f"  Run {r['run']}: {r['start']} → {r['end']}")
        extrair_metricas_prometheus(
            runs_info,
            step="15s",
            output_dir="resultados"
        )
    else:
        print("  [WARN] Não foi possível detectar intervalos dos runs automaticamente.")
        print("  Forneça manualmente: extrair_metricas_prometheus([")
        print('    {"run": 1, "start": "2026-03-19T16:19:28Z", "end": "2026-03-19T17:00:00Z"},')
        print("  ])")

    print("\n── Gerando gráficos ──────────────────────────────────────────────")
    gerar_graficos(df, timestamp)


if __name__ == '__main__':
    main()