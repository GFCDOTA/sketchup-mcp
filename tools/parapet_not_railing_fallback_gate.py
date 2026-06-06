#!/usr/bin/env python3
"""parapet_not_railing_fallback_gate — removing a railing can't mint a block.

The other half of the seesaw: when the builder stops drawing a railing it must
NOT silently substitute a solid low wall / parapet block in its place, and an
unsourced soft barrier must NOT become physical geometry at all (Hard Rule #1:
never invent). This gate fails when the report shows a rendered barrier whose
consensus entry has no provenance.

Reads consensus + geometry_report (same contract as railing_exact_match_gate).
A barrier is "sourced" iff soft_barrier_source_audit considers it sourced
(barrier_type / confirmation / PDF-text). Any rendered-but-unsourced barrier ->
FAIL, regardless of whether it rendered as a low_wall, block, or railing.
"""
from __future__ import annotations

from tools.soft_barrier_source_audit import _source_of


def _report_barriers(report: dict) -> list[dict]:
    return (report.get("soft_barrier_groups") or {}).get("barriers") or []


def audit_parapet_not_railing_fallback(consensus: dict, report: dict) -> dict:
    sourced = {sb.get("id") for sb in consensus.get("soft_barriers", [])
               if _source_of(sb)}
    findings: list[dict] = []
    for b in _report_barriers(report):
        if b.get("rendered") and b.get("id") not in sourced:
            findings.append({
                "id": b.get("id"),
                "render_as": b.get("render_as"),
                "reason": "unsourced_barrier_rendered_physical",
                "detail": "an unsourced soft barrier became physical geometry "
                          "(invented low wall / block / railing) — Hard Rule #1",
            })
    return {
        "verdict": "PASS" if not findings else "FAIL",
        "n_unsourced_rendered": len(findings),
        "findings": findings,
    }


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path
    ap = argparse.ArgumentParser(description="parapet-not-railing fallback gate")
    ap.add_argument("consensus")
    ap.add_argument("report", help="geometry_report.json")
    a = ap.parse_args()
    con = json.loads(Path(a.consensus).read_text("utf-8"))
    rep = json.loads(Path(a.report).read_text("utf-8"))
    res = audit_parapet_not_railing_fallback(con, rep)
    print(f"[parapet_not_railing_fallback] {res['verdict']} "
          f"unsourced_rendered={res['n_unsourced_rendered']} "
          f"findings={res['findings']}")
    raise SystemExit(0 if res["verdict"] == "PASS" else 1)
