#!/usr/bin/env python3
"""kitchen_wall_regression_gate (Felipe 2026-06-02).

Compara a geometria da regiao COZINHA/SALA do consensus ATUAL contra um
baseline KNOWN-GOOD (snapshot do consensus que gerou window_fix_20260530, antes
do regen #28). FALHA se aparecer wall full-height NOVA na regiao — i.e. um
segmento de parede atual cujo trecho NAO existe em parede nenhuma do baseline
(= parede fantasma do merge #28 bloqueando a passagem aberta cozinha/sala).

NAO reinterpreta a parede do zero: o baseline e a verdade. Determinístico.
Verde = "nenhuma parede nova na regiao vs baseline", != "modelo fiel".
"""
from __future__ import annotations

import argparse
import math
import sys

from tools.gate_util import load_json, pt_seg_dist

# Regiao COZINHA / SALA DE JANTAR / SALA DE ESTAR (open-plan), em pdf-points.
# Acima da frente do terraco (y>~458, que e a faixa do gradil — preservada),
# metade esquerda/centro (x<~555, fora das suites/banhos da direita).
KITCHEN_SALA_BBOX = (49.0, 458.0, 555.0, 695.0)  # x0, y0, x1, y1
EPS_PT = 4.0          # tolerancia p/ "coberto por parede do baseline"
MIN_NEW_PT = 18.0     # trecho novo minimo p/ contar como parede nova (~0.5m)


def _in_region(w, bbox) -> bool:
    x0, y0, x1, y1 = bbox
    mx = (w["start"][0] + w["end"][0]) / 2.0
    my = (w["start"][1] + w["end"][1]) / 2.0
    return x0 <= mx <= x1 and y0 <= my <= y1


def _max_uncovered_run(w, base_walls, eps) -> tuple:
    """Maior trecho contiguo de w NAO coberto por nenhuma parede do baseline."""
    ax, ay = w["start"]; bx, by = w["end"]
    L = math.hypot(bx - ax, by - ay)
    n = max(2, int(L))
    run = 0; best = 0; cx = cy = None
    for i in range(n + 1):
        t = i / n
        px, py = ax + t * (bx - ax), ay + t * (by - ay)
        covered = any(pt_seg_dist(px, py, ww["start"][0], ww["start"][1],
                                   ww["end"][0], ww["end"][1]) <= eps for ww in base_walls)
        if not covered:
            run += 1
            if run > best:
                best = run; cx, cy = px, py
        else:
            run = 0
    return (best / n * L if n else 0.0), cx, cy


def audit(baseline: dict, current: dict, bbox=KITCHEN_SALA_BBOX,
          eps=EPS_PT, min_new=MIN_NEW_PT) -> dict:
    base_walls = baseline.get("walls", [])
    # paredes que hospedam janela/porta/vidro sao REAIS (tem vao/abertura, nao
    # bloqueiam) e o Felipe mandou nao tocar. So parede SOLIDA (sem abertura)
    # nova e que "bloqueia a passagem" -> so essas contam como regressao.
    hosted = {o.get("wall_id") for o in current.get("openings", [])}
    findings = []
    for w in current.get("walls", []):
        if not _in_region(w, bbox):
            continue
        if w.get("id") in hosted:
            continue
        uncov, cx, cy = _max_uncovered_run(w, base_walls, eps)
        if uncov >= min_new:
            findings.append({
                "wall_id": w.get("id"), "orientation": w.get("orientation"),
                "start": w.get("start"), "end": w.get("end"),
                "new_span_pt": round(uncov, 1),
                "at": [round(cx, 1), round(cy, 1)] if cx is not None else None,
                "verdict": "FAIL",
                "reason": "wall_full_height_nova_sem_baseline (cruza passagem cozinha/sala)",
            })
    overall = "FAIL" if findings else "PASS"
    return {"overall": overall, "n_findings": len(findings),
            "region_bbox": bbox, "findings": findings}


def run(baseline_path: str, current_path: str) -> int:
    res = audit(load_json(baseline_path), load_json(current_path))
    print(f"kitchen_wall_regression_gate: {res['overall']} "
          f"({res['n_findings']} parede(s) nova(s) na regiao cozinha/sala)")
    for f in res["findings"]:
        print(f"  [FAIL] {f['wall_id']} {f['orientation']} {f['start']}->{f['end']} "
              f"| trecho_novo={f['new_span_pt']}pt @ {f['at']}")
    print("OVERALL:", "RED" if res["overall"] == "FAIL" else "GREEN (sem parede nova vs baseline)")
    return 1 if res["overall"] == "FAIL" else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True, help="consensus known-good (pre-#28)")
    ap.add_argument("--current", required=True, help="consensus atual")
    a = ap.parse_args()
    sys.exit(run(a.baseline, a.current))
