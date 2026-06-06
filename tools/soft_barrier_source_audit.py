#!/usr/bin/env python3
"""Soft-barrier provenance + SOURCE GATE (merge develop + feat/planta74-peitoril, 2026-06-03).

Duas camadas que convivem:

A) PROVENANCE audit (external-review finding #4 + Hard Rule #1): toda soft_barrier que
   vira geometria fisica (~1.10m SoftBarrier_Group) deve rastrear a uma fonte
   (barrier_type / label PDF / confirmacao humana). `audit_soft_barrier_sources` retorna
   PASS/WARN (advisory, nao deleta nem promove). `_source_of` e reusado pelo
   parapet_not_railing_fallback_gate.

B) SOURCE GATE (Felipe 2026-06-02): render fisico SO com FONTE EXPLICITA (barrier_type +
   geometry_origin=human_annotation). Sem fonte => SKIP TOTAL (nada de grade/mureta/bloco
   fallback). Grade SO com render_as=grade (ou barrier_type guardrail/railing). `audit`
   roda 5 gates CI-able contra o consensus + o geometry_report do build.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---- (A) provenance audit — consensus-only, advisory (WARN, nunca FAIL) ----
# a barrier is "sourced" if it declares what it is...
TYPE_KEYS = ("barrier_type", "kind", "class", "barrier_class")
# ...or carries an explicit confirmation / PDF-text provenance.
CONFIRM_KEYS = ("human_confirmed", "confirmed", "pdf_text", "source_label",
                "label_text", "pdf_label")


def _source_of(sb: dict) -> str | None:
    for k in TYPE_KEYS:
        if sb.get(k):
            return f"{k}={sb[k]}"
    for k in CONFIRM_KEYS:
        if sb.get(k):
            return f"{k}={sb[k]}"
    return None


def audit_soft_barrier_sources(consensus: dict) -> dict:
    """{verdict PASS/WARN, n_total, n_sourced, n_unsourced, findings}. WARN (not
    FAIL): an unsourced barrier is a governance flag for human/PDF review, not a
    proven defect."""
    sbs = consensus.get("soft_barriers", []) or []
    findings: list[dict] = []
    n_sourced = 0
    for sb in sbs:
        src = _source_of(sb)
        if src:
            n_sourced += 1
        else:
            findings.append({
                "id": sb.get("id"),
                "reason": "unsourced_soft_barrier",
                "detail": "no barrier_type / confirmation / PDF-text source — "
                          "becomes a physical ~1.10m barrier without provenance",
            })
    return {
        "verdict": "PASS" if not findings else "WARN",
        "n_total": len(sbs),
        "n_sourced": n_sourced,
        "n_unsourced": len(findings),
        "findings": findings,
    }


# ---- (B) SOURCE GATE (Felipe 2026-06-02) — CI-able render gate ----
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
    align_tol = 0.03 / pt_to_m   # 3cm em pts (offset do host, spec Felipe)
    cover_tol = 0.10 / pt_to_m   # 10cm em pts (comprimento/cobertura, spec Felipe;
    #                              permite o grade passar um tico do bbox p/ encostar na parede)
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
        # FRONT-RUN = segmento mais longo (corrida frontal); resto = retorno de
        # fechamento. alignment/coverage so no front-run (suporta L de fechamento).
        fa, fb = max(((pl[i], pl[i + 1]) for i in range(len(pl) - 1)),
                     key=lambda ab: (ab[1][0] - ab[0][0]) ** 2 + (ab[1][1] - ab[0][1]) ** 2)
        if b.get("orientation", "h") == "h":
            pos = (fa[1] + fb[1]) / 2.0
            offset = min(abs(pos - y0), abs(pos - y1))   # colado numa borda, nao no centro
            lo, hi = min(fa[0], fb[0]), max(fa[0], fb[0])
            miss_l, miss_r = lo - x0, x1 - hi
        else:
            pos = (fa[0] + fb[0]) / 2.0
            offset = min(abs(pos - x0), abs(pos - x1))
            lo, hi = min(fa[1], fb[1]), max(fa[1], fb[1])
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
    ap = argparse.ArgumentParser(description="soft-barrier source gate (+ provenance)")
    ap.add_argument("--consensus", required=True)
    ap.add_argument("--report", required=True)
    a = ap.parse_args()
    sys.exit(audit(a.consensus, a.report))
