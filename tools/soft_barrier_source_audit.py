#!/usr/bin/env python3
"""Soft-barrier provenance audit (external-review finding #4 + Hard Rule #1).

Soft barriers in the consensus become PHYSICAL low geometry (~1.10 m
SoftBarrier_Group) in the .skp. Hard Rule #1 says never invent geometry: a soft
barrier that becomes a physical parapet must trace back to the PDF (a PEITORIL /
MURETA / H=... label) or an explicit human confirmation. A bare polyline with no
barrier_type and no source is exactly the kind of thing that silently turns PDF
hachura / furniture / an internal division into a fake low wall.

This audit does NOT delete anything (the polyline may be real) and does NOT
promote it to correct either. It returns WARN listing every unsourced barrier so
a human / the PDF classifies it before it's trusted. PASS only when every soft
barrier is sourced.
"""
from __future__ import annotations

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


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser(description="soft-barrier provenance audit")
    ap.add_argument("consensus", help="consensus json path")
    a = ap.parse_args()
    con = json.loads(Path(a.consensus).read_text("utf-8"))
    res = audit_soft_barrier_sources(con)
    print(f"[soft_barrier_source] {res['verdict']} "
          f"{res['n_sourced']}/{res['n_total']} sourced, "
          f"{res['n_unsourced']} unsourced")
    for f in res["findings"]:
        print(f"  WARN {f['id']}: {f['detail']}")
    # WARN is advisory -> exit 0 (does not block); FAIL would be exit 1.
    raise SystemExit(0)
