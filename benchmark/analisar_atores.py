#!/usr/bin/env python3
"""
analisar_atores.py — Agrega N réplicas da simulação de atores (simulate-actors.ts)
e produz a curva REPUTAÇÃO × TAXA DE ERRO com IC95, além da trajetória média de
reputação ao longo das submissões. Gráfico-pronto (CSV tidy).

Modelo (determinístico): reputação = w1·0,4 + w2·0,3 + w3·0,2 + w4·0,1, com
w1 = taxa_aceitação² × 100 dominante → maior taxa de erro ⇒ reputação cai (quadrático).
As réplicas variam pela amostragem aleatória do pool; o IC95 captura essa variância.

Entrada : diretório com resumo_<runId>.csv e timeline_<runId>.csv (1 par por réplica),
          tipicamente Automotive-Compliance-Oracle/scripts/actor-results/
Saída   : <dir>/atores_curva.csv        — 1 linha por taxa de erro (média ± IC95)
          <dir>/atores_trajetoria.csv   — reputação média ± IC95 por índice de submissão

Uso:
  python3 analisar_atores.py [dir_das_replicas] [--out <dir_saida>]
  # default dir: ../../Automotive-Compliance-Oracle/scripts/actor-results
Stdlib puro (csv/statistics), como os demais comparar_*.py.
"""
import csv
import glob
import os
import sys
from collections import defaultdict, Counter

# ── IC95 via t de Student (stdlib) ─────────────────────────────────────────────
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
    """(média, meia-largura do IC95). Meia-largura 0 se n < 2."""
    import statistics as st
    xs = [x for x in valores if x is not None]
    n = len(xs)
    if n == 0:
        return (None, None)
    m = sum(xs) / n
    if n < 2:
        return (m, 0.0)
    return (m, _t95(n - 1) * st.stdev(xs) / (n ** 0.5))


def _f(s):
    """float ou None (célula vazia)."""
    if s is None or s == '':
        return None
    try:
        return float(s)
    except ValueError:
        return None


def ler_csvs(diretorio, prefixo):
    linhas = []
    for path in sorted(glob.glob(os.path.join(diretorio, f'{prefixo}_*.csv'))):
        with open(path, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                linhas.append(row)
    return linhas


def main():
    args = sys.argv[1:]
    out_dir = None
    if '--out' in args:
        i = args.index('--out')
        out_dir = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]

    positionals = [a for a in args if not a.startswith('--')]
    if positionals:
        in_dir = positionals[0]
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        in_dir = os.path.normpath(os.path.join(here, '..', '..',
                                               'Automotive-Compliance-Oracle', 'scripts', 'actor-results'))
    out_dir = out_dir or in_dir

    resumo = ler_csvs(in_dir, 'resumo')
    tl     = ler_csvs(in_dir, 'timeline')
    if not resumo:
        print(f'[ERRO] nenhum resumo_*.csv em {in_dir}. Rode simulate-actors.ts (N réplicas) antes.')
        sys.exit(1)

    n_runs = len({r['run_id'] for r in resumo})

    # ── CURVA reputação × taxa de erro (agrega réplicas por taxa) ──────────────
    por_taxa = defaultdict(lambda: {'rep_final': [], 'rep_mean': [], 'grade': [], 'flagged_rate': []})
    for r in resumo:
        taxa = _f(r['error_rate_pct'])
        subs = _f(r['submissions']) or 1
        d = por_taxa[taxa]
        d['rep_final'].append(_f(r['rep_final']))
        d['rep_mean'].append(_f(r['rep_mean']))
        d['grade'].append(_f(r['grade_mean']))
        fl = _f(r['flagged'])
        d['flagged_rate'].append((fl / subs * 100) if fl is not None else None)

    print('\n' + '=' * 78)
    print(f'  REPUTAÇÃO × TAXA DE ERRO — {n_runs} réplica(s), média ± IC95')
    print('=' * 78)
    print(f'  {"taxa_erro%":>10} {"n":>3} {"rep_final (média±IC95)":>26} {"grade":>8} {"flagged%":>9}')

    curva_rows = [['error_rate_pct', 'n_reps', 'rep_final_mean', 'rep_final_ic95',
                   'rep_mean_mean', 'rep_mean_ic95', 'grade_mean', 'grade_ic95', 'flagged_rate_mean']]
    for taxa in sorted(por_taxa):
        d = por_taxa[taxa]
        rfm, rfc = media_ic95(d['rep_final'])
        rmm, rmc = media_ic95(d['rep_mean'])
        gm, gc   = media_ic95(d['grade'])
        flm, _   = media_ic95(d['flagged_rate'])
        n = len([x for x in d['rep_final'] if x is not None])
        rep_str = f'{rfm:.2f} ± {rfc:.2f}' if rfm is not None else '—'
        print(f'  {taxa:>10.2f} {n:>3} {rep_str:>26} {("%.1f" % gm) if gm is not None else "—":>8} '
              f'{("%.1f" % flm) if flm is not None else "—":>9}')
        curva_rows.append([
            f'{taxa:.2f}', n,
            '' if rfm is None else round(rfm, 3), '' if rfc is None else round(rfc, 3),
            '' if rmm is None else round(rmm, 3), '' if rmc is None else round(rmc, 3),
            '' if gm is None else round(gm, 3),  '' if gc is None else round(gc, 3),
            '' if flm is None else round(flm, 3),
        ])

    os.makedirs(out_dir, exist_ok=True)
    curva_path = os.path.join(out_dir, 'atores_curva.csv')
    with open(curva_path, 'w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerows(curva_rows)

    # ── TRAJETÓRIA: reputação média ± IC95 por índice de submissão ─────────────
    traj_path = None
    if tl:
        por_idx = defaultdict(lambda: defaultdict(list))  # taxa -> i -> [rep]
        for row in tl:
            taxa = _f(row['error_rate_pct'])
            i    = _f(row['i'])
            rep  = _f(row['reputation_score'])
            if taxa is None or i is None or rep is None:
                continue
            por_idx[taxa][int(i)].append(rep)

        traj_rows = [['error_rate_pct', 'i', 'rep_mean', 'rep_ic95', 'n']]
        for taxa in sorted(por_idx):
            for i in sorted(por_idx[taxa]):
                m, hw = media_ic95(por_idx[taxa][i])
                traj_rows.append([f'{taxa:.2f}', i,
                                  '' if m is None else round(m, 3),
                                  '' if hw is None else round(hw, 3),
                                  len(por_idx[taxa][i])])
        traj_path = os.path.join(out_dir, 'atores_trajetoria.csv')
        with open(traj_path, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows(traj_rows)

    # ── REJEIÇÃO por severidade (agrega todos os erros submetidos) ─────────────
    sev_path = None
    if tl:
        def flagged(outcome):
            o = (outcome or '').strip()
            return o not in ('', 'pass') and not o.startswith('HTTP') and o != 'NETWORK_ERROR'

        por_sev = defaultdict(lambda: {'sub': 0, 'rej': 0})
        for row in tl:
            if _f(row.get('had_error')) != 1:
                continue
            s = row.get('severidade', 'na') or 'na'
            por_sev[s]['sub'] += 1
            if flagged(row.get('outcome')):
                por_sev[s]['rej'] += 1

        if por_sev:
            print('\n' + '=' * 78)
            print('  REJEIÇÃO por SEVERIDADE do erro (todos os atores/réplicas)')
            print('=' * 78)
            print(f'  {"severidade":12} {"submetidos":>11} {"rejeitados":>11} {"taxa rejeição":>15}')
            sev_rows = [['severidade', 'submetidos', 'rejeitados', 'taxa_rejeicao_pct']]
            for s in sorted(por_sev):
                d = por_sev[s]
                taxa = d['rej'] / d['sub'] * 100 if d['sub'] else 0.0
                print(f'  {s:12} {d["sub"]:>11} {d["rej"]:>11} {taxa:>14.1f}%')
                sev_rows.append([s, d['sub'], d['rej'], round(taxa, 2)])
            sev_path = os.path.join(out_dir, 'atores_severidade.csv')
            with open(sev_path, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerows(sev_rows)

    # ── DISTRIBUIÇÃO de OUTCOME por taxa de erro (= por ator) ──────────────────
    # É aqui que light/heavy_review fazem sentido: grade = 0.6·compliance + 0.4·reputação,
    # e a reputação cai com a taxa de erro do ator → mesmo doc recebe mais escrutínio.
    outcome_path = None
    if tl:
        OCS = ['pass', 'light_review', 'heavy_review', 'reject']
        por_taxa_oc = defaultdict(Counter)   # taxa de erro -> Counter(outcome)
        for row in tl:
            taxa = _f(row['error_rate_pct'])
            oc = (row.get('outcome') or '').strip()
            if oc not in OCS:
                oc = 'erro_transporte'
            por_taxa_oc[taxa][oc] += 1

        print('\n' + '=' * 78)
        print('  OUTCOME por taxa de erro do ator (10 réplicas) — escrutínio × reputação')
        print('=' * 78)
        print(f'  {"taxa%":>6} {"pass":>8} {"light_rev":>10} {"heavy_rev":>10} {"reject":>8} {"total":>8}')
        oc_rows = [['error_rate_pct'] + OCS + ['erro_transporte', 'total']]
        for taxa in sorted(por_taxa_oc):
            c = por_taxa_oc[taxa]
            tot = sum(c.values())
            print(f'  {taxa:>6.2f} {c.get("pass",0):>8} {c.get("light_review",0):>10} '
                  f'{c.get("heavy_review",0):>10} {c.get("reject",0):>8} {tot:>8}')
            oc_rows.append([f'{taxa:.2f}'] + [c.get(o, 0) for o in OCS]
                           + [c.get('erro_transporte', 0), tot])
        outcome_path = os.path.join(out_dir, 'atores_outcome.csv')
        with open(outcome_path, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows(oc_rows)

    print('\n[OK] CSVs salvos:')
    print(f'     {curva_path}')
    if traj_path:
        print(f'     {traj_path}')
    if sev_path:
        print(f'     {sev_path}')
    if outcome_path:
        print(f'     {outcome_path}')


if __name__ == '__main__':
    main()
