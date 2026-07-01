#!/usr/bin/env python3
"""
prepare_mutant_payloads.py — Converte o dataset de mutantes (JSON concatenado,
pretty-printed) num array JSON único que o K6 consegue carregar via SharedArray.

Entrada : dataset5000.json (com campo `auditoria` = gabarito)
Saída   : mutant_payloads.json — array de
            { id, esperado, tipos, severidade, categoria, eixo, doc }

O campo `auditoria` é REMOVIDO do `doc` enviado (simula entrada cega), mas seu
conteúdo vira os rótulos para medir vazamento/filtragem no pós-teste:
  esperado   : "pass" | "reject"                 (tem_erro)
  tipos      : [ERRO_...]                          (tipos de erro injetados)
  severidade : "flagrante" | "limitrofe" | "na"   (dos erros; "na" p/ docs pass)
  categoria  : "limpo"|"quase_limite"|"sub_limiar"|"erro"
  eixo       : eixo da perturbação limítrofe/sub-limiar (soma/divergencia/...) ou "na"

Uso:
    python3 prepare_mutant_payloads.py \
        /home/sohn/Automotive-Compliance-Oracle/scripts/dataset5000.json \
        mutant_payloads.json
"""
import json
import sys


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else \
        '/home/sohn/Automotive-Compliance-Oracle/scripts/dataset5000.json'
    dst = sys.argv[2] if len(sys.argv) > 2 else 'mutant_payloads.json'

    txt = open(src, encoding='utf-8').read().strip()
    dec = json.JSONDecoder()

    payloads = []
    idx = 0
    while idx < len(txt):
        while idx < len(txt) and txt[idx] in ' \t\r\n':
            idx += 1
        if idx >= len(txt):
            break
        obj, idx = dec.raw_decode(txt, idx)

        aud = obj.pop('auditoria', {}) or {}      # remove e captura o gabarito
        tem_erro = bool(aud.get('tem_erro'))
        tipos = sorted({e.get('tipo', '?') for e in aud.get('erros', [])})
        categoria = aud.get('categoria', 'erro' if tem_erro else 'limpo')
        # severidade: presente nos erros; para docs pass é 'na'
        severidade = aud.get('severidade') or ('na' if not tem_erro else 'flagrante')
        # eixo: dos erros limítrofes (localizacao) ou das notas (quase_limite/sub_limiar)
        notas = aud.get('notas', []) or []
        eixo = (notas[0].get('eixo') if notas else None) or 'na'

        payloads.append({
            'id': len(payloads),
            'esperado': 'reject' if tem_erro else 'pass',
            'tipos': tipos,
            'severidade': severidade,
            'categoria': categoria,
            'eixo': eixo,
            'doc': obj,
        })

    with open(dst, 'w', encoding='utf-8') as f:
        json.dump(payloads, f, ensure_ascii=False)

    n_rej = sum(1 for p in payloads if p['esperado'] == 'reject')
    from collections import Counter
    cats = Counter(p['categoria'] for p in payloads)
    sevs = Counter(p['severidade'] for p in payloads if p['esperado'] == 'reject')
    print(f'[OK] {len(payloads)} docs -> {dst}')
    print(f'     esperado=pass:   {len(payloads) - n_rej}')
    print(f'     esperado=reject: {n_rej}')
    print(f'     categorias:      {dict(cats)}')
    print(f'     severidade(rej): {dict(sevs)}')


if __name__ == '__main__':
    main()
