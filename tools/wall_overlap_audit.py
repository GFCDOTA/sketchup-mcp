#!/usr/bin/env python3
"""FP-031 #3b — deterministic structural detector: duplicate/overlapping walls.

Pure, consensus-ONLY (no PDF/SKP/SU/PIL). Flags pairs of walls that are
collinear (same orientation, fixed axis within ~wall thickness) AND overlap
along their span. That is redundant geometry — a wall annotated twice (e.g. a
human wall duplicating an extractor wall) — which inflates the wall set and can
produce z-fighting / double-thick walls in the shell.

Found in planta_74: h_w001 duplicates w020 (vertical, x 127.6 vs 129.2, span
overlap ~97pt). Read-only audit; the fix (drop the duplicate) mutates the
fixture => NEEDS-HUMAN.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _orient(w) -> str:
    dx = abs(w["end"][0] - w["start"][0])
    dy = abs(w["end"][1] - w["start"][1])
    return "h" if dx >= dy else "v"


def _span(w, axis: int) -> tuple[float, float]:
    a, b = w["start"][axis], w["end"][axis]
    return (a, b) if a <= b else (b, a)


def audit_wall_overlaps(
    consensus: dict,
    *,
    collinear_tol_pt: float | None = None,
    min_overlap_pt: float | None = None,
) -> dict:
    """Flag collinear, span-overlapping wall pairs (duplicate geometry)."""
    walls = consensus.get("walls", [])
    thick = float(consensus.get("wall_thickness_pts", 5.4) or 5.4)
    ctol = collinear_tol_pt if collinear_tol_pt is not None else thick * 1.2
    movl = min_overlap_pt if min_overlap_pt is not None else thick * 2.0

    findings: list[dict] = []
    for i in range(len(walls)):
        for j in range(i + 1, len(walls)):
            a, b = walls[i], walls[j]
            oa = _orient(a)
            if oa != _orient(b):
                continue
            fixed_axis = 1 if oa == "h" else 0   # h walls share y; v walls share x
            span_axis = 0 if oa == "h" else 1
            if abs(a["start"][fixed_axis] - b["start"][fixed_axis]) > ctol:
                continue  # not collinear
            a0, a1 = _span(a, span_axis)
            b0, b1 = _span(b, span_axis)
            overlap = min(a1, b1) - max(a0, b0)
            if overlap > movl:
                findings.append({
                    "wall_a": a.get("id"),
                    "wall_b": b.get("id"),
                    "orientation": oa,
                    "overlap_pt": round(overlap, 1),
                    "fixed_axis_gap_pt": round(
                        abs(a["start"][fixed_axis] - b["start"][fixed_axis]), 2),
                    "reason": "duplicate_or_overlapping_wall",
                })
    return {
        "detector": "wall_overlap",
        "collinear_tol_pt": round(ctol, 1),
        "min_overlap_pt": round(movl, 1),
        "n_walls": len(walls),
        "n_overlaps": len(findings),
        "overall": "FAIL" if findings else "PASS",
        "overlaps": findings,
    }


def _load_consensus(fixture: str) -> dict:
    p = (REPO_ROOT / "fixtures" / fixture
         / "consensus_with_human_walls_and_soft_barriers.json")
    if not p.exists():
        cands = sorted((REPO_ROOT / "fixtures" / fixture).glob("consensus*.json"))
        if not cands:
            raise FileNotFoundError(f"no consensus json for fixture {fixture}")
        p = cands[0]
    return json.loads(p.read_text("utf-8"))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="duplicate/overlapping wall gate")
    ap.add_argument("--fixture", default="planta_74")
    a = ap.parse_args()
    rep = audit_wall_overlaps(_load_consensus(a.fixture))
    print(f"[wall-overlap-audit] fixture={a.fixture} overall={rep['overall']} "
          f"walls={rep['n_walls']} overlaps={rep['n_overlaps']}")
    for f in rep["overlaps"]:
        print(f"  {f['wall_a']} ~ {f['wall_b']} ({f['orientation']}) "
              f"overlap={f['overlap_pt']}pt gap={f['fixed_axis_gap_pt']}pt")
    raise SystemExit(0 if rep["overall"] == "PASS" else 1)
