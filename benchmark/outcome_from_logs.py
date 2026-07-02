#!/usr/bin/env python3
"""
outcome_from_logs.py — Recupera o outcome EXATO de cada decisão (pass / light_review /
heavy_review / reject) direto do Mongo do Oráculo e cruza com a classe do documento,
produzindo o split light/heavy que o k6 (runs antigas) agregava em "review".
NÃO requer re-rodar experimento — lê a auditoria já persistida.

Fonte : coleção `auditablelogs`, evento `decision_made`, campo `details.outcome`.
Cruzamento: submissionId "...-MUT-<idx>" -> mutant_payloads.json[idx].categoria.
            (submissões de atores "SIM-..." caem no balde 'ator'.)

Uso (rode no NÓ onde está o container do Mongo do Oráculo):
  python3 outcome_from_logs.py
  python3 outcome_from_logs.py --container automotive-compliance-oracle-mongo-1 \
                               --db compliance_oracle --payloads mutant_payloads.json

Requer: docker + mongosh no container mongo (a imagem mongo:7 já traz).
Saída : tabela classe × outcome no terminal + resultados/outcome_detalhado.csv
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
from collections import Counter


def carregar_docs(args):
    if args.from_json:  # modo debug: lê docs de um arquivo em vez do Mongo
        return json.load(open(args.from_json))
    query = ("db.auditablelogs.find({event:'decision_made'},"
             "{_id:0,submissionId:1,'details.outcome':1}).toArray()")
    cmd = ['docker', 'exec', args.container, 'mongosh', args.db, '--quiet',
           '--eval', f'print(JSON.stringify({query}))']
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print('[ERRO] mongosh falhou:', r.stderr.strip()[:400])
        sys.exit(1)
    raw = r.stdout.strip()
    try:
        return json.loads(raw or '[]')
    except json.JSONDecodeError:
        print('[ERRO] saída do mongosh não é JSON — confira --container / coleção.')
        print(raw[:300])
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--container', default='automotive-compliance-oracle-mongo-1')
    ap.add_argument('--db', default='compliance_oracle')
    ap.add_argument('--payloads', default='mutant_payloads.json')
    ap.add_argument('--from-json', help='(debug) docs decision_made de um JSON local')
    args = ap.parse_args()

    label = {}
    if os.path.isfile(args.payloads):
        for p in json.load(open(args.payloads)):
            label[p['id']] = p.get('categoria', '?')
    else:
        print(f'[AVISO] {args.payloads} não encontrado — classe dos mutantes ficará "?"')

    docs = carregar_docs(args)
    if not docs:
        print('[AVISO] nenhum decision_made encontrado. A coleção é `auditablelogs`? '
              'O Oráculo já processou submissões?')
        return

    rx = re.compile(r'-MUT-(\d+)(?:-|$)')
    tab = Counter()
    for d in docs:
        sid = d.get('submissionId', '')
        oc = (d.get('details') or {}).get('outcome', '?')
        m = rx.search(sid)
        if m:
            cat = label.get(int(m.group(1)), '?')
        elif sid.startswith('SIM-'):
            cat = 'ator'
        else:
            cat = 'outro'
        tab[(cat, oc)] += 1

    cats = [c for c in ['limpo', 'quase_limite', 'sub_limiar', 'erro', 'ator', 'outro', '?']
            if any((c, o) in tab for o in
                   ['pass', 'light_review', 'heavy_review', 'reject', '?'])]
    ocs = [o for o in ['pass', 'light_review', 'heavy_review', 'reject', '?']
           if any((c, o) in tab for c in cats)]

    print(f'\n{"classe":14}' + ''.join(f'{o:>15}' for o in ocs) + f'{"total":>9}')
    rows = [['classe'] + ocs + ['total']]
    for c in cats:
        vals = [tab.get((c, o), 0) for o in ocs]
        print(f'{c:14}' + ''.join(f'{x:>15}' for x in vals) + f'{sum(vals):>9}')
        rows.append([c] + vals + [sum(vals)])

    os.makedirs('resultados', exist_ok=True)
    out = 'resultados/outcome_detalhado.csv'
    with open(out, 'w', newline='') as f:
        csv.writer(f).writerows(rows)
    print(f'\n[OK] {out}')


if __name__ == '__main__':
    main()
