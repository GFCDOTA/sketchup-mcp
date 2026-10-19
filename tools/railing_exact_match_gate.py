#!/usr/bin/env python3
"""railing_exact_match_gate — railings in the SKP must match the consensus.

The soft-barrier "seesaw" (all->railing, then none->block) happens because the
builder has no per-segment semantics. This gate makes the rendered railings an
EXACT match of what the consensus authorizes, so neither over- nor under-
rendering can pass.

Contract — reads two dicts:
  consensus: {... "soft_barriers": [{"id","barrier_type","host_wall_id"?,
              "polyline_pts"? ...}]}
  report (geometry_report.json): {... "soft_barrier_groups": {"barriers":
              [{"id","barrier_type","sourced","rendered","render_as"
               ("low_wall"|"railing"|null),"host_wall_id"?,"length_m"? ...}]}}

A railing is EXPECTED when its consensus barrier_type is a railing type. It is
ACTUAL when the report rendered it as render_as=="railing".

FAIL on: missing_expected_railing, extra_unexpected_railing,
railing_on_wrong_host, railing_length_delta>tol.
"""
from __future__ import annotations

RAILING_TYPES = {"guardrail", "railing", "guarda_corpo", "guarda-corpo",
                 "guarda_corpo_com_grade", "peitoril_com_grade"}
LENGTH_TOL_M = 0.10
# Mesma precedência do builder (`barrier_render_as` em build_plan_shell_skp.rb): o `render_as` EXPLÍCITO do consensus
# (curadoria humana) vence o mapeamento por `barrier_type`, nos dois sentidos.
EXPLICIT_RAILING = {"grade", "railing", "guardrail"}
EXPLICIT_LOW_WALL = {"low_wall", "mureta", "peitoril", "parapet"}


def _report_barriers(report: dict) -> list[dict]:
    return (report.get("soft_barrier_groups") or {}).get("barriers") or []


def _is_railing_type(bt) -> bool:
    return str(bt or "").strip().lower() in RAILING_TYPES


def _expects_railing(sb: dict) -> bool:
    explicit = str(sb.get("render_as") or "").strip().lower()
    if explicit in EXPLICIT_RAILING:
        return True
    if explicit in EXPLICIT_LOW_WALL:
        return False
    return _is_railing_type(sb.get("barrier_type"))


def audit_railing_exact_match(consensus: dict, report: dict,
                              *, length_tol_m: float = LENGTH_TOL_M) -> dict:
    con_by_id = {sb.get("id"): sb for sb in consensus.get("soft_barriers", [])}
    expected = {sid for sid, sb in con_by_id.items() if _expects_railing(sb)}
    barriers = _report_barriers(report)
    actual = {b.get("id") for b in barriers if b.get("render_as") == "railing"}

    findings: list[dict] = []
    for sid in sorted(expected - actual):
        findings.append({"id": sid, "reason": "missing_expected_railing"})
    for sid in sorted(actual - expected):
        findings.append({"id": sid, "reason": "extra_unexpected_railing"})

    # wrong host / length only for railings that are in BOTH (rendered + expected)
    for b in barriers:
        if b.get("render_as") != "railing":
            continue
        sid = b.get("id")
        csb = con_by_id.get(sid)
        if not csb:
            continue
        ch, bh = csb.get("host_wall_id"), b.get("host_wall_id")
        if ch and bh and ch != bh:
            findings.append({"id": sid, "reason": "railing_on_wrong_host",
                             "detail": f"consensus={ch} skp={bh}"})
        cl, bl = csb.get("expected_length_m"), b.get("length_m")
        if cl is not None and bl is not None and abs(cl - bl) > length_tol_m:
            findings.append({"id": sid, "reason": "railing_length_delta",
                             "detail": f"|{cl}-{bl}|>{length_tol_m}"})

    return {
        "verdict": "PASS" if not findings else "FAIL",
        "n_expected": len(expected),
        "n_actual": len(actual),
        "findings": findings,
    }


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path
    ap = argparse.ArgumentParser(description="railing exact-match gate")
    ap.add_argument("consensus")
    ap.add_argument("report", help="geometry_report.json")
    a = ap.parse_args()
    con = json.loads(Path(a.consensus).read_text("utf-8"))
    rep = json.loads(Path(a.report).read_text("utf-8"))
    res = audit_railing_exact_match(con, rep)
    print(f"[railing_exact_match] {res['verdict']} "
          f"expected={res['n_expected']} actual={res['n_actual']} "
          f"findings={res['findings']}")
    raise SystemExit(0 if res["verdict"] == "PASS" else 1)
