#!/usr/bin/env python3
"""
comparar_mutantes.py — Compara os dois runs de cobertura de mutantes
(SEM Oracle vs COM Oracle) a partir dos summary JSONs do k6 (handleSummary).

Produz:
  - tabela de FILTRAGEM  (vazamento sem Oracle vs matriz de confusão com Oracle)
  - tabela de LATÊNCIA   (HERMES real, decomposição, latência inserida pelo Oracle)
  - CSVs em resultados/  para gráficos/tabelas do artigo

Uso:
  python3 comparar_mutantes.py \
      resultados/summary_mutants_<ts>.json \
      resultados/summary_oracle_mutants_<ts>.json

  # ou deixa ele achar os mais recentes:
  python3 comparar_mutantes.py
"""
import csv
import glob
import json
import os
import sys

N_REJECT = 1500   # mutantes (esperado=reject) no dataset5000
N_PASS   = 3500   # limpos   (esperado=pass)


def carregar(path):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    return data.get('metrics', {})


def v(metrics, nome, campo, default=0.0):
    """Lê metrics[nome].values[campo] com fallback."""
    m = metrics.get(nome, {})
    vals = m.get('values', {})
    return vals.get(campo, default)


def trend(metrics, nome):
    """Retorna (avg, med, p95) de uma métrica Trend."""
    return (
        v(metrics, nome, 'avg'),
        v(metrics, nome, 'med'),
        v(metrics, nome, 'p(95)'),
    )


def achar_mais_recente(padrao):
    arquivos = sorted(glob.glob(os.path.join('resultados', padrao)))
    return arquivos[-1] if arquivos else None


# ── Estatística: IC95 via t de Student (stdlib puro, sem scipy) ────────────────
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
    return 1.96  # df grande → aproxima da normal


def media_ic95(valores):
    """(média, meia-largura do IC95). Meia-largura = 0 se n < 2."""
    import statistics as st
    xs = [x for x in valores if x is not None]
    n = len(xs)
    if n == 0:
        return (None, None)
    m = sum(xs) / n
    if n < 2:
        return (m, 0.0)
    return (m, _t95(n - 1) * st.stdev(xs) / (n ** 0.5))


# ── Taxonomia (espelha generate-mutants.ts / test_oracle_mutants.js) ───────────
TIPOS_DET = ['ERRO_NCM_INELEGIVEL', 'ERRO_FOB_INVERTIDO', 'ERRO_FOB_NAO_POSITIVO',
             'ERRO_PARTICIPACAO_EXCEDE_100', 'ERRO_PAIS_NAO_MEMBRO_ACE55',
             'ERRO_CIF_ZERO_COM_PARTICIPACAO', 'ERRO_PARTICIPACAO_DIVERGENTE',
             'ERRO_CIF_TERCEIROS_EXCEDE_FOB']
TIPOS_NDET = ['ERRO_CLASSIF_NCM', 'ERRO_VALOR_CIF_SUBFATURADO', 'ERRO_ORIGEM_INCORRETA',
              'ERRO_FORNECEDOR_SEM_CERTIFICADO']
SEVS = ['flagrante', 'limitrofe']
CLASSES_PASS = ['limpo', 'quase_limite', 'sub_limiar']


def categorizacao(mo):
    """Lê as submétricas por tipo×severidade do summary COM Oracle e imprime a matriz
    de filtragem por célula. Retorna as linhas para CSV."""
    print('\n' + '=' * 70)
    print('  CATEGORIZAÇÃO por TIPO × SEVERIDADE (COM Oracle)')
    print('=' * 70)
    print(f'  {"tipo":32} {"sev":10} {"barrado":>8} {"vazou":>6} {"total":>6}')
    linhas = []
    vazam_lim = []
    for grupo, tipos in (('detectáveis', TIPOS_DET),
                         ('não-detectáveis — FN esperado', TIPOS_NDET)):
        print(f'  [{grupo}]')
        for t in tipos:
            for s in SEVS:
                tp = int(v(mo, f'oracle_tp_bloqueou{{tipo:{t},severidade:{s}}}', 'count'))
                fn = int(v(mo, f'vazamento_mutantes{{tipo:{t},severidade:{s}}}', 'count'))
                tot = tp + fn
                if tot == 0:
                    continue
                flag = ''
                if s == 'limitrofe' and fn > 0 and t in TIPOS_DET:
                    flag = '  <-- LIMITROFE VAZOU (FN real)'
                    vazam_lim.append((t, fn, tot))
                print(f'  {t:32} {s:10} {tp:>8} {fn:>6} {tot:>6}{flag}')
                linhas.append((t, s, tp, fn, tot))

    print('  [limpos por classe — FP se barrado]')
    for c in CLASSES_PASS:
        tn = int(v(mo, f'oracle_tn_aprovou{{classe:{c}}}', 'count'))
        fp = int(v(mo, f'oracle_fp_falso_pos{{classe:{c}}}', 'count'))
        tot = tn + fp
        if tot == 0:
            continue
        flag = '  <-- FP real' if fp > 0 and c in ('quase_limite', 'sub_limiar') else ''
        print(f'  {c:32} {"pass":10} {tn:>8} {fp:>6} {tot:>6}{flag}')
        linhas.append((c, 'pass', tn, fp, tot))

    if vazam_lim:
        print(f'\n  [!] {len(vazam_lim)} tipo(s) detectável(is) VAZARAM na variante limítrofe '
              '— tolerância folgada demais, investigar.')
    else:
        print('\n  [OK] Nenhum erro limítrofe detectável vazou (regras firmes no limiar).')
    return linhas


def latencia_compliance_reps(glob_pat):
    """Agrega latencia_oracle_compliance_ms (avg e p95) de N summaries COM Oracle
    (réplicas) → média ± IC95 entre réplicas. Retorna dict ou None."""
    paths = sorted(glob.glob(glob_pat))
    if len(paths) < 1:
        return None
    avgs, p95s = [], []
    for p in paths:
        m = carregar(p)
        a = v(m, 'latencia_oracle_compliance_ms', 'avg', None)
        p95 = v(m, 'latencia_oracle_compliance_ms', 'p(95)', None)
        if a:
            avgs.append(a)
        if p95:
            p95s.append(p95)
    return {
        'n': len(paths),
        'avg_mean': media_ic95(avgs),
        'p95_mean': media_ic95(p95s),
    }


def main():
    # --reps-glob <padrão> : agrega latência de compliance de N réplicas (IC95)
    args = sys.argv[1:]
    reps_glob = None
    if '--reps-glob' in args:
        i = args.index('--reps-glob')
        reps_glob = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]

    positionals = [a for a in args if not a.startswith('--')]
    if len(positionals) >= 2:
        path_hermes, path_oracle = positionals[0], positionals[1]
    else:
        path_hermes = achar_mais_recente('summary_mutants_*.json')
        path_oracle = achar_mais_recente('summary_oracle_mutants_*.json')

    if not path_hermes or not os.path.isfile(path_hermes):
        print('[ERRO] summary do run SEM Oracle não encontrado. Passe o caminho como 1º arg.')
        sys.exit(1)
    if not path_oracle or not os.path.isfile(path_oracle):
        print('[AVISO] summary do run COM Oracle não encontrado — mostrando só o baseline.')
        path_oracle = None

    mh = carregar(path_hermes)
    mo = carregar(path_oracle) if path_oracle else {}

    # ── FILTRAGEM ─────────────────────────────────────────────────────────────
    # Sem Oracle: vazamento_mutantes = mutantes ancorados; barrados = hermes_rejeitou
    h_vazou  = int(v(mh, 'vazamento_mutantes', 'count'))
    h_barrou = int(v(mh, 'hermes_rejeitou', 'count'))
    h_leak   = h_vazou / N_REJECT * 100 if N_REJECT else 0

    print('\n' + '=' * 70)
    print('  FILTRAGEM — conformidade (motor de regras ACE-55/ALADI) e custo')
    print('=' * 70)
    print('  Verificação de motor determinístico: Precisão = robustez a FP/soundness;')
    print('  Recall = cobertura de regras (limitado ao escopo pré-RVC). Não é classificador.')
    print(f'  {"":24} {"SEM Oracle":>14} {"COM Oracle":>14}')

    if mo:
        tp = int(v(mo, 'oracle_tp_bloqueou', 'count'))
        fn = int(v(mo, 'vazamento_mutantes', 'count'))
        tn = int(v(mo, 'oracle_tn_aprovou', 'count'))
        fp = int(v(mo, 'oracle_fp_falso_pos', 'count'))
        precision = tp / (tp + fp) if (tp + fp) else 0
        recall    = tp / (tp + fn) if (tp + fn) else 0
        f1        = 2 * precision * recall / (precision + recall) if (precision + recall) else 0
        o_leak    = fn / N_REJECT * 100 if N_REJECT else 0

        print(f'  {"Mutantes barrados (TP)":24} {h_barrou:>14} {tp:>14}')
        print(f'  {"Mutantes VAZADOS (FN)":24} {h_vazou:>14} {fn:>14}')
        print(f'  {"Taxa de vazamento":24} {h_leak:>13.1f}% {o_leak:>13.1f}%')
        print(f'  {"Limpos aprovados (TN)":24} {"—":>14} {tn:>14}')
        print(f'  {"Limpos barrados (FP)":24} {"—":>14} {fp:>14}')
        print(f'  {"Precisão (robustez FP)":24} {"—":>14} {precision:>14.3f}')
        print(f'  {"Recall (cobertura)":24} {"—":>14} {recall:>14.3f}')
        print(f'  {"F1 (derivado, referência)":24} {"—":>14} {f1:>14.3f}')
    else:
        print(f'  {"Mutantes VAZADOS":24} {h_vazou:>14}')
        print(f'  {"Taxa de vazamento":24} {h_leak:>13.1f}%')

    # ── CATEGORIZAÇÃO por tipo × severidade ────────────────────────────────────
    cat_linhas = categorizacao(mo) if mo else []

    # ── LATÊNCIA ──────────────────────────────────────────────────────────────
    print('\n' + '=' * 70)
    print('  LATÊNCIA (ms) — avg / med / p95')
    print('=' * 70)

    def linha(rotulo, metrics, nome):
        if nome not in metrics:
            return f'  {rotulo:32} {"(ausente)":>26}'
        a, md, p95 = trend(metrics, nome)
        return f'  {rotulo:32} {a:7.0f} / {md:7.0f} / {p95:7.0f}'

    print('  SEM Oracle:')
    print(linha('HERMES real (e2e)',       mh, 'm1_latencia_e2e_ms'))
    print(linha('  ├─ cálculo ICR',        mh, 'latencia_calc_ms'))
    print(linha('  └─ ancoragem Fabric',   mh, 'latencia_fabric_ms'))
    print(linha('cliente (com polling)',   mh, 'latencia_cliente_ms'))

    if mo:
        print('  COM Oracle:')
        print(linha('HERMES real (e2e)',          mo, 'm1_latencia_e2e_ms'))
        print(linha('  ├─ cálculo ICR',           mo, 'latencia_calc_ms'))
        print(linha('  └─ ancoragem Fabric',      mo, 'latencia_fabric_ms'))
        print(linha('Oracle compliance (INSERIDA)', mo, 'latencia_oracle_compliance_ms'))
        print(linha('cliente (com polling Oracle)', mo, 'latencia_cliente_ms'))
        print(linha('residual (forward+polling)',   mo, 'latencia_overhead_resid_ms'))

    # ── Latência de compliance INSERIDA — IC95 entre réplicas ──────────────────
    reps = latencia_compliance_reps(reps_glob) if reps_glob else None
    if reps:
        am, ah = reps['avg_mean']
        pm, ph = reps['p95_mean']
        print('\n' + '=' * 70)
        print(f'  LATÊNCIA INSERIDA pelo Oracle — {reps["n"]} réplica(s), média ± IC95')
        print('=' * 70)
        if am is not None:
            print(f'  compliance avg : {am:7.1f} ± {ah:.1f} ms')
        if pm is not None:
            print(f'  compliance p95 : {pm:7.1f} ± {ph:.1f} ms')

    # ── CSVs ──────────────────────────────────────────────────────────────────
    os.makedirs('resultados', exist_ok=True)

    with open('resultados/comparacao_filtragem.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['metrica', 'sem_oracle', 'com_oracle'])
        w.writerow(['mutantes_vazados', h_vazou, (fn if mo else '')])
        w.writerow(['mutantes_barrados', h_barrou, (tp if mo else '')])
        w.writerow(['taxa_vazamento_pct', round(h_leak, 2), (round(o_leak, 2) if mo else '')])
        if mo:
            w.writerow(['limpos_aprovados_TN', '', tn])
            w.writerow(['limpos_barrados_FP', '', fp])
            w.writerow(['precision', '', round(precision, 4)])
            w.writerow(['recall', '', round(recall, 4)])
            w.writerow(['f1', '', round(f1, 4)])

    metr_lat = ['m1_latencia_e2e_ms', 'latencia_calc_ms', 'latencia_fabric_ms',
                'latencia_oracle_compliance_ms', 'latencia_cliente_ms',
                'latencia_overhead_resid_ms']
    with open('resultados/comparacao_latencia.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['metrica', 'run', 'avg_ms', 'med_ms', 'p95_ms'])
        for nome in metr_lat:
            if nome in mh:
                a, md, p95 = trend(mh, nome)
                w.writerow([nome, 'sem_oracle', round(a, 1), round(md, 1), round(p95, 1)])
            if mo and nome in mo:
                a, md, p95 = trend(mo, nome)
                w.writerow([nome, 'com_oracle', round(a, 1), round(md, 1), round(p95, 1)])

    salvos = ['resultados/comparacao_filtragem.csv', 'resultados/comparacao_latencia.csv']
    if cat_linhas:
        with open('resultados/comparacao_categorizacao.csv', 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['tipo_ou_classe', 'severidade_ou_esperado', 'barrado_ou_TN', 'vazou_ou_FP', 'total'])
            for row in cat_linhas:
                w.writerow(row)
        salvos.append('resultados/comparacao_categorizacao.csv')

    print('\n[OK] CSVs salvos:')
    for s in salvos:
        print(f'     {s}')


if __name__ == '__main__':
    main()
