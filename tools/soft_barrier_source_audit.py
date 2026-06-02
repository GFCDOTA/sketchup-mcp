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

    gates = {
        # so renderiza o que tem fonte; todo unsourced foi skip(no_source)
        "soft_barrier_source_audit": built == len(sourced) and len(no_source_skips) >= len(unsourced),
        # grades renderizadas == autorizadas (aqui todo sourced e grade => exato)
        "railing_exact_match_gate": built == len(grades) and len(sourced) == len(grades),
        # nenhuma grade alem das autorizadas (sem fallback peitoril->grade)
        "parapet_not_railing_fallback_gate": built <= len(grades),
    }

    print(f"sourced={sourced} grades={grades} unsourced={len(unsourced)} "
          f"| built={built} skipped={skipped} no_source_skips={len(no_source_skips)}")
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
