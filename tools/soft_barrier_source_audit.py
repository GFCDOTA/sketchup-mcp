#!/usr/bin/env python3
"""Soft-barrier SOURCE GATE audit (Felipe 2026-06-02).

Regra: render fisico de soft_barrier SO com FONTE EXPLICITA. Sem barrier_type +
sem human_annotation => SKIP TOTAL (nada de grade/mureta/bloco fallback). Grade
SO com render_as=grade (ou barrier_type guardrail/railing) + fonte.

Roda 3 gates contra o consensus + o geometry_report do build:
  1. soft_barrier_source_audit          — so o que tem fonte renderiza; resto skip.
  2. railing_exact_match_gate           — # de grades == # autorizadas (exato).
  3. parapet_not_railing_fallback_gate  — nenhuma grade sem autorizacao (sem fallback).

Exit 0 se todos PASS, 1 se algum FAIL (CI-able).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def has_source(b: dict) -> bool:
    # fonte explicita = tem barrier_type E foi anotado por humano
    return bool(b.get("barrier_type")) and b.get("geometry_origin") == "human_annotation"


def is_grade(b: dict) -> bool:
    return has_source(b) and (
        b.get("render_as") == "grade" or b.get("barrier_type") in ("guardrail", "railing")
    )


def railing_geometry_gates(con: dict):
    """railing_alignment_gate + railing_coverage_gate (Felipe 2026-06-02).
    Pra cada grade autorizada: o polyline deve estar COLADO numa borda do bbox
    (alignment: offset<=3cm — pega gradil recuado pro centro) e COBRIR a largura
    inteira do segmento (coverage: gap<=5cm cada ponta — pega gradil curto)."""
    pt_to_m = 0.19 / float(con.get("wall_thickness_pts", 5.4) or 5.4)
    align_tol = 0.03 / pt_to_m   # 3cm em pts
    cover_tol = 0.05 / pt_to_m   # 5cm em pts
    align_ok = cover_ok = True
    details = []
    for b in con.get("soft_barriers", []):
        if not is_grade(b):
            continue
        bb = (b.get("human_annotation") or {}).get("bbox_pts")
        pl = b.get("polyline_pts") or []
        if not bb or len(pl) < 2:
            continue
        x0, y0, x1, y1 = bb
        if b.get("orientation", "h") == "h":
            pos = sum(p[1] for p in pl) / len(pl)
            offset = min(abs(pos - y0), abs(pos - y1))   # colado numa borda, nao no centro
            lo, hi = min(p[0] for p in pl), max(p[0] for p in pl)
            miss_l, miss_r = lo - x0, x1 - hi
        else:
            pos = sum(p[0] for p in pl) / len(pl)
            offset = min(abs(pos - x0), abs(pos - x1))
            lo, hi = min(p[1] for p in pl), max(p[1] for p in pl)
            miss_l, miss_r = lo - y0, y1 - hi
        a = offset <= align_tol
        c = abs(miss_l) <= cover_tol and abs(miss_r) <= cover_tol
        align_ok &= a
        cover_ok &= c
        details.append(f"    {b.get('id')}: offset={offset:.1f}pt(tol={align_tol:.1f}) "
                       f"miss_l={miss_l:.1f} miss_r={miss_r:.1f}(tol={cover_tol:.1f}) "
                       f"-> align={'PASS' if a else 'FAIL'} coverage={'PASS' if c else 'FAIL'}")
    return align_ok, cover_ok, details


def audit(consensus_path: str, report_path: str) -> int:
    con = json.loads(Path(consensus_path).read_text("utf-8"))
    rep = json.loads(Path(report_path).read_text("utf-8"))
    sbs = con.get("soft_barriers", [])

    sourced = [b.get("id") for b in sbs if has_source(b)]
    grades = [b.get("id") for b in sbs if is_grade(b)]
    unsourced = [b.get("id") for b in sbs if not has_source(b)]

    sg = rep.get("soft_barrier_groups", {})
    built = int(sg.get("count", 0))
    skipped = int(sg.get("skipped_count", 0))
    reasons = sg.get("skip_reasons", []) or []
    no_source_skips = [r for r in reasons if "no_source" in r]

    align_ok, cover_ok, rdetails = railing_geometry_gates(con)
    gates = {
        # so renderiza o que tem fonte; todo unsourced foi skip(no_source)
        "soft_barrier_source_audit": built == len(sourced) and len(no_source_skips) >= len(unsourced),
        # grades renderizadas == autorizadas (aqui todo sourced e grade => exato)
        "railing_exact_match_gate": built == len(grades) and len(sourced) == len(grades),
        # nenhuma grade alem das autorizadas (sem fallback peitoril->grade)
        "parapet_not_railing_fallback_gate": built <= len(grades),
        # gradil colado na borda frontal do host (nao recuado pro centro)
        "railing_alignment_gate": align_ok,
        # gradil cobre a largura inteira do segmento (sem gap nas pontas)
        "railing_coverage_gate": cover_ok,
    }

    print(f"sourced={sourced} grades={grades} unsourced={len(unsourced)} "
          f"| built={built} skipped={skipped} no_source_skips={len(no_source_skips)}")
    for d in rdetails:
        print(d)
    ok = True
    for name, passed in gates.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print("OVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus", required=True)
    ap.add_argument("--report", required=True)
    a = ap.parse_args()
    sys.exit(audit(a.consensus, a.report))
