#!/usr/bin/env python3
"""FP-031 #3 — deterministic positional detector: opening <-> host-wall consistency.

Pure, consensus-ONLY (no PDF, no SKP build, no PIL/SU). Catches the exact data
class that mis-rendered planta_74's windows: an opening whose stored `wall_id`
does not geometrically host it. Three objective FAILs per opening:

  - host_mismatch       : the opening centre is far from its ASSIGNED host wall
                          segment AND a DIFFERENT wall sits clearly closer
                          (the stored wall_id points at the wrong wall).
  - off_host_segment    : centre is far from the host segment, but no clearly
                          closer wall exists (floating / detached opening).
  - width_exceeds_host  : opening width > host wall segment length * factor
                          (a 1.48 m window cannot live on a 0.53 m wall).

Distances are in pdf-points (the consensus' own unit). No fabrication, no
mutation — read-only audit.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _seg_dist(p, a, b) -> tuple[float, float]:
    """Perpendicular distance from point p to segment a->b, clamped to the
    segment, plus the unclamped projection parameter t."""
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0.0:
        return math.hypot(px - ax, py - ay), 0.0
    t = ((px - ax) * dx + (py - ay) * dy) / L2
    tc = max(0.0, min(1.0, t))
    cx, cy = ax + tc * dx, ay + tc * dy
    return math.hypot(px - cx, py - cy), t


def _seg_len(a, b) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def audit_opening_hosts(
    consensus: dict,
    *,
    off_host_tol_pt: float | None = None,
    width_factor: float = 1.15,
    mismatch_margin_pt: float = 8.0,
) -> dict:
    """Audit every opening's stored host wall. Returns a report dict with a
    per-opening verdict (PASS/FAIL) and an overall verdict.

    off_host_tol_pt: how far (perp, clamped) the centre may sit from its host
      segment before it counts as off-host. Default = wall_thickness_pts * 3.
    """
    walls = consensus.get("walls", [])
    wmap = {w["id"]: w for w in walls}
    thick = float(consensus.get("wall_thickness_pts", 5.4) or 5.4)
    tol = off_host_tol_pt if off_host_tol_pt is not None else thick * 3.0

    findings: list[dict] = []
    for o in consensus.get("openings", []):
        oid = o.get("id")
        ctr = o.get("center")
        hid = o.get("wall_id")
        host = wmap.get(hid)
        w_pt = float(o.get("opening_width_pts") or 0.0)
        reasons: list[str] = []

        if not ctr or host is None:
            findings.append({
                "opening": oid, "host_wall": hid, "verdict": "FAIL",
                "reasons": ["no_center_or_host"],
            })
            continue

        d_host, _ = _seg_dist(ctr, host["start"], host["end"])
        host_len = _seg_len(host["start"], host["end"])
        # nearest wall by clamped segment distance
        nearest = min(walls, key=lambda w: _seg_dist(ctr, w["start"], w["end"])[0])
        d_near, _ = _seg_dist(ctr, nearest["start"], nearest["end"])

        if d_host > tol:
            if nearest["id"] != hid and d_near + mismatch_margin_pt < d_host:
                reasons.append(
                    f"host_mismatch(assigned={hid}@{d_host:.0f}pt,"
                    f"nearest={nearest['id']}@{d_near:.0f}pt)"
                )
            else:
                reasons.append(f"off_host_segment(d={d_host:.0f}pt>{tol:.0f}pt)")
        if w_pt > host_len * width_factor:
            reasons.append(
                f"width_exceeds_host(w={w_pt:.0f}pt>host_len={host_len:.0f}pt)"
            )

        findings.append({
            "opening": oid,
            "kind": o.get("kind_v5") or o.get("kind") or o.get("type"),
            "host_wall": hid,
            "d_host_pt": round(d_host, 1),
            "host_len_pt": round(host_len, 1),
            "width_pt": round(w_pt, 1),
            "nearest_wall": nearest["id"],
            "d_near_pt": round(d_near, 1),
            "verdict": "FAIL" if reasons else "PASS",
            "reasons": reasons,
        })

    n_fail = sum(1 for f in findings if f["verdict"] == "FAIL")
    return {
        "detector": "opening_host_consistency",
        "tol_pt": round(tol, 1),
        "width_factor": width_factor,
        "n_openings": len(findings),
        "n_fail": n_fail,
        "overall": "FAIL" if n_fail else "PASS",
        "openings": findings,
    }


def _load_consensus(fixture: str) -> dict:
    p = (REPO_ROOT / "fixtures" / fixture
         / "consensus_with_human_walls_and_soft_barriers.json")
    if not p.exists():  # quadrado uses a different filename
        cands = sorted((REPO_ROOT / "fixtures" / fixture).glob("consensus*.json"))
        if not cands:
            raise FileNotFoundError(f"no consensus json for fixture {fixture}")
        p = cands[0]
    return json.loads(p.read_text("utf-8"))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="opening<->host-wall positional gate")
    ap.add_argument("--fixture", default="planta_74")
    a = ap.parse_args()
    rep = audit_opening_hosts(_load_consensus(a.fixture))
    print(f"[opening-host-audit] fixture={a.fixture} overall={rep['overall']} "
          f"openings={rep['n_openings']} FAIL={rep['n_fail']} tol={rep['tol_pt']}pt")
    for f in rep["openings"]:
        if f["verdict"] == "FAIL":
            print(f"  {f['opening']:8} host={f.get('host_wall')} "
                  f"-> {f['verdict']} {f['reasons']}")
    raise SystemExit(0 if rep["overall"] == "PASS" else 1)
