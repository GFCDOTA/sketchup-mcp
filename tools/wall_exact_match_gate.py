#!/usr/bin/env python3
"""wall_exact_match_gate + wall_endpoint_connectivity_gate (Felipe 2026-06-02).

A classe de bug que os gates atuais NAO viam: "teco de parede" faltando /
retorno curto / junction que nao fecha. O oracle visual e cego pra isso e os
detectores so pegavam bugs ja codificados. Este compara EXPECTED (baseline
known-good) x OBSERVED (consensus atual), determinístico:

  wall_exact_match_gate:
    - missing_wall_segment   : parede do baseline sem cobertura no atual (sumiu)
    - wall_segment_short      : parede do baseline so parcialmente coberta (encurtou)
  wall_endpoint_connectivity_gate:
    - expected_junction_missing / terminal_wall_gap : endpoint que no baseline
      encostava em outra parede e no atual ficou solto (retorno nao fecha)

Se o EXPECTED nao tiver o teco, o gate herda a cegueira — por isso o expected e
o baseline KNOWN-GOOD (que tinha as paredes completas), nao o consensus atual.
"""
from __future__ import annotations

import argparse
import math
import sys

from tools.gate_util import load_json, pt_seg_dist

MISSING_PT = 8.0      # trecho contiguo sem cobertura p/ contar como faltante (~0.2m)
JUNCTION_GAP_PT = 6.0  # endpoint solto vs parede mais proxima (~0.15m em pdf-pt)


def _max_uncovered(w, walls, eps) -> tuple:
    ax, ay = w["start"]; bx, by = w["end"]
    L = math.hypot(bx - ax, by - ay)
    n = max(2, int(L))
    run = 0; best = 0; cx = cy = None
    for i in range(n + 1):
        t = i / n
        px, py = ax + t * (bx - ax), ay + t * (by - ay)
        if not any(pt_seg_dist(px, py, ww["start"][0], ww["start"][1],
                             ww["end"][0], ww["end"][1]) <= eps for ww in walls):
            run += 1
            if run > best:
                best = run; cx, cy = px, py
        else:
            run = 0
    return (best / n * L if n else 0.0), cx, cy


def _endpoints(walls):
    pts = []
    for w in walls:
        pts.append(tuple(w["start"])); pts.append(tuple(w["end"]))
    return pts


def audit(expected: dict, observed: dict, eps=4.0,
          missing_pt=MISSING_PT, junction_gap=JUNCTION_GAP_PT) -> dict:
    exp_w = expected.get("walls", [])
    obs_w = observed.get("walls", [])
    findings = []

    # --- wall_exact_match: cada parede esperada coberta pelo observado? ---
    for w in exp_w:
        uncov, cx, cy = _max_uncovered(w, obs_w, eps)
        L = math.hypot(w["end"][0] - w["start"][0], w["end"][1] - w["start"][1])
        if uncov >= missing_pt:
            kind = "missing_wall_segment" if uncov > 0.8 * L else "wall_segment_short"
            findings.append({"gate": "wall_exact_match", "reason": kind,
                             "expected_wall": w.get("id"),
                             "start": [round(v, 1) for v in w["start"]],
                             "end": [round(v, 1) for v in w["end"]],
                             "uncovered_pt": round(uncov, 1),
                             "at": [round(cx, 1), round(cy, 1)] if cx is not None else None,
                             "verdict": "FAIL"})

    # --- wall_endpoint_connectivity: junctions do baseline presentes? ---
    # endpoint do baseline que tocava OUTRA parede do baseline (junction) deve,
    # no observado, ter parede encostando tambem. Se ficou solto -> retorno sumiu.
    obs_pts = _endpoints(obs_w)
    for w in exp_w:
        for ep in (w["start"], w["end"]):
            # era junction no baseline? (toca outra parede do baseline, nao a si mesma)
            touches_exp = sum(1 for ww in exp_w if ww is not w and
                              pt_seg_dist(ep[0], ep[1], ww["start"][0], ww["start"][1],
                                        ww["end"][0], ww["end"][1]) <= eps)
            if touches_exp == 0:
                continue
            # no observado, ha parede encostando nesse ponto?
            d_obs = min((pt_seg_dist(ep[0], ep[1], ww["start"][0], ww["start"][1],
                                   ww["end"][0], ww["end"][1]) for ww in obs_w), default=99)
            if d_obs > junction_gap:
                findings.append({"gate": "wall_endpoint_connectivity",
                                 "reason": "expected_junction_missing",
                                 "expected_wall": w.get("id"),
                                 "at": [round(ep[0], 1), round(ep[1], 1)],
                                 "gap_pt": round(d_obs, 1), "verdict": "FAIL"})

    # dedup junction findings por ponto
    seen = set(); dedup = []
    for f in findings:
        k = (f["reason"], tuple(f.get("at") or []))
        if k in seen:
            continue
        seen.add(k); dedup.append(f)
    return {"overall": "FAIL" if dedup else "PASS", "n_findings": len(dedup), "findings": dedup}


def run(expected_path: str, observed_path: str) -> int:
    res = audit(load_json(expected_path), load_json(observed_path))
    print(f"wall_exact_match/connectivity: {res['overall']} ({res['n_findings']} achados)")
    for f in res["findings"]:
        extra = (f"uncov={f.get('uncovered_pt')}pt" if "uncovered_pt" in f
                 else f"gap={f.get('gap_pt')}pt")
        print(f"  [{f['verdict']}] {f['gate']}/{f['reason']} exp_wall={f['expected_wall']} "
              f"@ {f.get('at')} {extra}")
    print("OVERALL:", "RED" if res["overall"] == "FAIL" else "GREEN (paredes completas vs baseline)")
    return 1 if res["overall"] == "FAIL" else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--expected", required=True, help="baseline known-good consensus")
    ap.add_argument("--observed", required=True, help="consensus atual")
    a = ap.parse_args()
    sys.exit(run(a.expected, a.observed))
