#!/usr/bin/env python3
"""
gerar_ecdf_throughput.py — Regenera gráficos eCDF e App vs Fabric

Uso:
    # Primeira vez (demora ~minutos): agrega dados e gera gráficos
    python3 gerar_ecdf_throughput.py resultados/run_*/k6_*.json

    # Re-runs só para ajustar fontes/tamanhos (rápido, segundos):
    python3 gerar_ecdf_throughput.py --cache
"""

import sys
import os
import pickle
import numpy as np
from datetime import datetime

import analise_resultados
from analise_resultados import (
    carregar_k6,
    gerar_grafico_tps_comparativo,
    carregar_tps_fabric_por_cenario,
    CENARIOS, CENARIOS_LABEL, CORES, LABELS_GRAF, DURACOES,
)

# ─── Configurações visuais dos gráficos ──────────────────────────────────────

FIG_WIDTH           = 17
FIG_HEIGHT          = 7

FONT_TITLE          = 18
FONT_AXIS_LABEL     = 22
FONT_TICK_LABEL     = 20
FONT_LEGEND         = 18
FONT_BAR_ANNOTATION = 14

LINE_WIDTH_MAIN     = 2.8
LINE_WIDTH_MARKER   = 0.8
LINE_WIDTH_REF      = 1.0

METRICAS_USADAS = {'m1_latencia_e2e_ms', 'm2_dos_ancoradas'}

CACHE_PATH = 'resultados/cache_plot_data.pkl'

# ─── Agregação de dados (pesada — roda uma vez) ──────────────────────────────

def agregar_e_salvar_cache(arquivos):
    """
    Processa os JSONs do k6 e extrai apenas o necessário para os dois gráficos.
    Salva um pickle pequeno para reuso nos reruns.
    """
    analise_resultados.METRICAS_INTERESSE = METRICAS_USADAS

    print(f"[INFO] Carregando {len(arquivos)} arquivos k6...")
    df = carregar_k6(arquivos)
    if df.empty:
        print("[ERROR] No data found.")
        sys.exit(1)

    # ── Dados para o eCDF (e2e por cenário) ───────────────────────────────────
    e2e = df[df['metric'] == 'm1_latencia_e2e_ms']
    ecdf_data = {}
    for c in CENARIOS:
        v = e2e[e2e['cenario'] == c]['value'].dropna().values
        v = v[v > 0]
        if len(v) > 0:
            # amostra para reduzir tamanho do pickle (mantém forma da curva)
            if len(v) > 200_000:
                v = np.random.choice(v, 200_000, replace=False)
            ecdf_data[c] = np.sort(v)

    # ── Dados para App vs Fabric throughput ───────────────────────────────────
    ancoradas = df[df['metric'] == 'm2_dos_ancoradas']
    runs      = sorted(df['run'].unique())

    tps_app = {c: [] for c in CENARIOS}
    for cenario in CENARIOS:
        dur = DURACOES.get(cenario, 600)
        for run in runs:
            total = ancoradas[
                (ancoradas['cenario'] == cenario) & (ancoradas['run'] == run)
            ]['value'].sum()
            if total > 0:
                tps_app[cenario].append(total / dur)

    print("[INFO] Carregando Fabric TPS dos CSVs do Prometheus...")
    tps_fabric = carregar_tps_fabric_por_cenario("resultados")

    throughput_data = {
        'app':    tps_app,
        'fabric': tps_fabric,
        'runs':   len(runs),
    }

    cache = {
        'ecdf':       ecdf_data,
        'throughput': throughput_data,
        'timestamp':  datetime.now().isoformat(),
    }

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, 'wb') as f:
        pickle.dump(cache, f)

    size_mb = os.path.getsize(CACHE_PATH) / 1024 / 1024
    print(f"[OK] Cache salvo em {CACHE_PATH} ({size_mb:.1f} MB)")
    return cache


def carregar_cache():
    if not os.path.isfile(CACHE_PATH):
        print(f"[ERROR] Cache não encontrado em {CACHE_PATH}")
        print("        Rode sem --cache primeiro para gerá-lo.")
        sys.exit(1)
    with open(CACHE_PATH, 'rb') as f:
        cache = pickle.load(f)
    print(f"[OK] Cache carregado (gerado em {cache['timestamp'][:19]})")
    return cache


# ─── Plots (leves — rodam em segundos) ───────────────────────────────────────

def plotar_ecdf(ecdf_data, graf_dir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import seaborn as sns
    sns.set_theme(style="whitegrid", palette="muted")

    cenarios_ok = [c for c in CENARIOS if c in ecdf_data]
    if not cenarios_ok:
        print("[WARN] Sem dados de eCDF no cache")
        return

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
    for c in cenarios_ok:
        v   = ecdf_data[c]
        cdf = np.arange(1, len(v) + 1) / len(v)
        p99 = np.percentile(v, 99)
        mask = v <= p99
        ax.plot(v[mask], cdf[mask] * 100,
                color=CORES[c], linewidth=LINE_WIDTH_MAIN, label=CENARIOS_LABEL[c])
        for pct, ls in [(50, ':'), (95, '--')]:
            ax.axvline(np.percentile(v, pct), color=CORES[c],
                       linestyle=ls, linewidth=LINE_WIDTH_MARKER, alpha=0.5)

    ax.axhline(95, color='gray', linestyle='--', linewidth=LINE_WIDTH_REF, alpha=0.6, label='P95')
    ax.axhline(50, color='gray', linestyle=':',  linewidth=LINE_WIDTH_REF, alpha=0.6, label='P50')
    ax.set_xlabel('E2E Latency (ms)', fontsize=FONT_AXIS_LABEL)
    ax.set_ylabel('Cumulative Percentile (%)', fontsize=FONT_AXIS_LABEL)
    ax.tick_params(axis='both', which='major', labelsize=FONT_TICK_LABEL)
    ax.set_ylim(0, 101)
    ax.set_title('E2E Latency eCDF by Scenario', fontsize=FONT_TITLE, fontweight='bold')
    ax.yaxis.grid(True, linestyle='--', alpha=0.5)
    ax.legend(
        loc='upper center',
        bbox_to_anchor=(0.5, -0.18),
        ncol=7,                         # C1, C2, C3, C4, C5, P95, P50 — todos em uma linha
        fontsize=FONT_LEGEND,
        frameon=True,
        facecolor='white',
        edgecolor='gray',
        framealpha=1.0,
        borderpad=0.6,
        columnspacing=1.5,
        handletextpad=0.5,
    )
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.22)    # libera ~22% da altura para a legenda

    p_png = f'{graf_dir}/m1_ecdf_por_cenario.png'
    p_pdf = f'{graf_dir}/m1_ecdf_por_cenario.pdf'
    plt.savefig(p_png, bbox_inches='tight')
    plt.savefig(p_pdf, bbox_inches='tight')
    plt.close()
    print(f"  [OK] {p_png}")
    print(f"  [OK] {p_pdf}")


def plotar_throughput(throughput_data, graf_dir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import seaborn as sns
    sns.set_theme(style="whitegrid")

    tps_app    = throughput_data['app']
    tps_fabric = throughput_data['fabric']

    cenarios_ok = [c for c in CENARIOS if tps_app.get(c) or tps_fabric.get(c)]
    if not cenarios_ok:
        print("[WARN] Sem dados de throughput no cache")
        return

    media_app, dp_app, media_fab, dp_fab = [], [], [], []
    for c in cenarios_ok:
        va = tps_app.get(c, [])
        vf = tps_fabric.get(c, [])
        media_app.append(np.mean(va) if va else 0)
        dp_app.append(np.std(va)     if len(va) > 1 else 0)
        media_fab.append(np.mean(vf) if vf else 0)
        dp_fab.append(np.std(vf)     if len(vf) > 1 else 0)

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
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
                    fontsize=FONT_BAR_ANNOTATION, color='#1565C0', fontweight='bold')

    for bar, val, dp in zip(bars_fab, media_fab, dp_fab):
        if val > 0:
            txt = f'{val:.3f}' + (f'\n±{dp:.3f}' if dp > 0 else '')
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + dp + offset_txt,
                    txt, ha='center', va='bottom',
                    fontsize=FONT_BAR_ANNOTATION, color='#00897B', fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels([LABELS_GRAF[c].replace('\n', ' ') for c in cenarios_ok],
                       fontsize=FONT_TICK_LABEL)
    ax.tick_params(axis='y', which='major', labelsize=FONT_TICK_LABEL)
    ax.set_ylabel('Throughput (Req/s)', fontsize=FONT_AXIS_LABEL)
    ax.set_title('Application vs. Fabric Throughput',
                 fontsize=FONT_TITLE, fontweight='bold')
    ax.yaxis.grid(True, linestyle='--', alpha=0.55)
    ax.set_axisbelow(True)
    ax.set_ylim(0, y_max * 1.35)
    ax.legend(loc='upper left', fontsize=FONT_LEGEND)
    plt.tight_layout()

    p_png = f'{graf_dir}/m2_tps_comparativo_app_vs_fabric.png'
    p_pdf = f'{graf_dir}/m2_tps_comparativo_app_vs_fabric.pdf'
    plt.savefig(p_png, bbox_inches='tight')
    plt.savefig(p_pdf, bbox_inches='tight')
    plt.close()
    print(f"  [OK] {p_png}")
    print(f"  [OK] {p_pdf}")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 gerar_ecdf_throughput.py resultados/run_*/k6_*.json")
        print("  python3 gerar_ecdf_throughput.py --cache")
        sys.exit(1)

    if sys.argv[1] == '--cache':
        cache = carregar_cache()
    else:
        cache = agregar_e_salvar_cache(sys.argv[1:])

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    graf_dir  = f'resultados/graficos_{timestamp}'
    os.makedirs(graf_dir, exist_ok=True)

    print(f"\n[INFO] Saída em {graf_dir}/")
    print("\n── Gerando eCDF ─────────────────────────────────────────────────")
    plotar_ecdf(cache['ecdf'], graf_dir)

    print("\n── Gerando App vs Fabric Throughput ────────────────────────────")
    plotar_throughput(cache['throughput'], graf_dir)

    print(f"\n[OK] Gráficos em {graf_dir}/")


if __name__ == '__main__':
    main()