#!/usr/bin/env python3
"""FP-031 #28 — regenerate a consensus with merged collinear walls + re-hosted
openings (gate :8765 verdict = approach B).

The planta_74 consensus fragments each architectural wall into short collinear
segments with gaps at the openings, so the stored opening->wall_id points at a
stub that does not host the opening (tools/opening_host_audit flags 9/12) and a
human wall duplicates an extractor wall (tools/wall_overlap_audit flags 1).

This deterministically:
  1. merges collinear walls (same orientation, same fixed coord within
     `fixed_tol`) whose spans overlap or are separated by a gap <= `bridge_gap`
     (bridges the opening gaps; absorbs the duplicate), and
  2. re-hosts every opening to the geometrically nearest merged wall.

The SKP shell polygon is rebuilt from this wall set by the Python phase, so a
rebuild IS required to judge any appearance delta — that judgement is VISUAL /
promotion and stays human (NEEDS-HUMAN). This tool only writes a CANDIDATE
consensus; it does NOT overwrite the pinned fixture.
"""
from __future__ import annotations

import json
from pathlib import Path

from tools.opening_host_audit import _seg_dist

REPO_ROOT = Path(__file__).resolve().parent.parent


def _orient(w) -> str:
    dx = abs(w["end"][0] - w["start"][0])
    dy = abs(w["end"][1] - w["start"][1])
    return "h" if dx >= dy else "v"


def regenerate(consensus: dict, *, fixed_tol: float = 2.5,
               bridge_gap: float = 100.0) -> dict:
    walls = consensus.get("walls", [])
    by_ori: dict[str, list] = {"h": [], "v": []}
    for w in walls:
        by_ori[_orient(w)].append(w)

    merged: list[dict] = []
    mid = 0
    for o, ws in by_ori.items():
        fa = 1 if o == "h" else 0   # fixed axis (h share y, v share x)
        sa = 0 if o == "h" else 1   # span axis
        ws = sorted(ws, key=lambda w: w["start"][fa])
        # cluster by fixed coordinate (within fixed_tol)
        clusters: list[dict] = []
        for w in ws:
            f = w["start"][fa]
            if clusters and abs(f - clusters[-1]["f"]) <= fixed_tol:
                clusters[-1]["ws"].append(w)
                clusters[-1]["f"] = (clusters[-1]["f"] * (len(clusters[-1]["ws"]) - 1)
                                     + f) / len(clusters[-1]["ws"])
            else:
                clusters.append({"f": f, "ws": [w]})
        for cl in clusters:
            grp = cl["ws"]
            fixed = sum(w["start"][fa] for w in grp) / len(grp)
            thick = sum(float(w.get("thickness", 5.4) or 5.4) for w in grp) / len(grp)
            ivs = sorted(sorted([w["start"][sa], w["end"][sa]]) for w in grp)
            unioned: list[list[float]] = []
            for s, e in ivs:
                if unioned and s - unioned[-1][1] <= bridge_gap:
                    unioned[-1][1] = max(unioned[-1][1], e)
                else:
                    unioned.append([s, e])
            for s, e in unioned:
                mid += 1
                if o == "h":
                    start, end = [s, fixed], [e, fixed]
                else:
                    start, end = [fixed, s], [fixed, e]
                merged.append({
                    "id": f"m{mid:03d}", "start": start, "end": end,
                    "orientation": o, "thickness": thick,
                })

    openings = [dict(op) for op in consensus.get("openings", [])]
    for op in openings:
        c = op.get("center")
        if not c or not merged:
            continue
        best = min(merged, key=lambda w: _seg_dist(c, w["start"], w["end"])[0])
        op["wall_id"] = best["id"]

    out = dict(consensus)
    out["walls"] = merged
    out["openings"] = openings
    out.setdefault("metadata", {})
    if isinstance(out["metadata"], dict):
        out["metadata"] = {**out["metadata"],
                           "fp031_regenerated": True,
                           "fp031_walls_before": len(walls),
                           "fp031_walls_after": len(merged)}
    return out


def _load(fixture: str) -> dict:
    p = (REPO_ROOT / "fixtures" / fixture
         / "consensus_with_human_walls_and_soft_barriers.json")
    return json.loads(p.read_text("utf-8"))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="regenerate consensus (merge+rehost)")
    ap.add_argument("--fixture", default="planta_74")
    ap.add_argument("--out", default=None, help="candidate output path")
    ap.add_argument("--bridge-gap", type=float, default=100.0)
    a = ap.parse_args()
    con = _load(a.fixture)
    reg = regenerate(con, bridge_gap=a.bridge_gap)
    out = a.out or str(REPO_ROOT / "runs" / a.fixture / "consensus_regenerated.json")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"[regen] {a.fixture}: walls {len(con['walls'])} -> {len(reg['walls'])}, "
          f"openings re-hosted; wrote {out}")
