#!/usr/bin/env python
"""generalization_gate.py — gate ANTI-OVERFIT (verificavel, sem SketchUp).

Le os validation.json de renders/sofa_eval/<case>/ e assegura que a CLASSE gera
sofas COERENTES e variados (nao quebrou, nao virou exemplar). Roda DEPOIS da suite.

Checa por caso: status OK; componentizado (n_parts >= 4, nao bloco unico); bbox
dentro de faixas sas (sem geometria explodida/colapsada). Erros = FAIL; warnings de
clamp/proporcao = degradacao elegante (nao reprovam). Exige DIVERSIDADE no conjunto
(varios seat_count/arm/bbox) pra provar que nao e 1 exemplar repetido.

Saida: por-caso PASS/FAIL + veredito do conjunto. Exit 0 = gate verde.
"""
import json
import os
import sys

# faixas sas (m) — pegam explosao/colapso, nao julgam estetica
RANGES = {'w': (0.8, 3.6), 'd': (0.6, 2.2), 'h': (0.45, 1.15)}
MIN_PARTS = 4


def check_case(vj):
    errs = []
    if vj.get('status') != 'OK':
        errs.append(f"status={vj.get('status')}")
    n = vj.get('n_parts', 0)
    if n < MIN_PARTS:
        errs.append(f"n_parts={n}<{MIN_PARTS} (bloco unico?)")
    bb = vj.get('bbox_m') or []
    if len(bb) == 3:
        for v, key in zip(bb, ('w', 'd', 'h')):
            lo, hi = RANGES[key]
            if not (lo <= v <= hi):
                errs.append(f"bbox.{key}={v} fora de [{lo},{hi}]")
    else:
        errs.append(f"bbox_m invalido: {bb}")
    return errs


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'renders', 'sofa_eval')
    cases = []
    for name in sorted(os.listdir(base)):
        vp = os.path.join(base, name, 'validation.json')
        if os.path.isfile(vp):
            try:
                cases.append((name, json.load(open(vp, encoding='utf-8'))))
            except Exception as e:
                cases.append((name, {'status': f'PARSE_ERR:{e}'}))
    if not cases:
        print('FAIL: nenhum validation.json encontrado em', base)
        return 1

    failed = 0
    bboxes, seats, arms = [], set(), set()
    for name, vj in cases:
        errs = check_case(vj)
        warns = len(vj.get('warnings') or [])
        if errs:
            failed += 1
            print(f'  FAIL {name}: {"; ".join(errs)}')
        else:
            print(f'  PASS {name}: parts={vj.get("n_parts")} bbox={vj.get("bbox_m")} warns={warns}')
        bb = tuple(vj.get('bbox_m') or [])
        if bb:
            bboxes.append(bb)

    # diversidade: bboxes distintos (proxy de "muitos sofas diferentes", nao 1 exemplar)
    distinct = len({tuple(round(x, 2) for x in b) for b in bboxes})
    diverse = distinct >= max(3, len(cases) - 1)
    print(f'\nCasos: {len(cases)} | FAIL: {failed} | bboxes distintos: {distinct}'
          f' | diverso: {"sim" if diverse else "NAO"}')
    ok = failed == 0 and diverse
    print('GATE GENERALIZACAO:', 'VERDE' if ok else 'VERMELHO')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
