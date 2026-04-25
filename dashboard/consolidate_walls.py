"""
consolidate_walls.py
====================

Reads consensus_model.json (288 walls = SVG faces, each masonry wall appears
as 2 faces over N segments) and produces walls_consolidated: ~50-80 LOGICAL
walls (centerlines with thickness), ready to be extruded into SKP geometry.

Algorithm
---------
1. Bucket walls by canonical orientation (mod 180, snapped to ~2 deg buckets).
2. Inside each orientation bucket, project each wall's midpoint onto the
   normal direction. Walls with very close perpendicular distance (< 6 pt)
   AND overlapping along the tangent direction belong to the same
   "alvenaria family" (the two faces of the same physical wall, possibly
   broken into segments by openings/junctions).
3. For each family:
     - len(family) == 1   -> single-face wall (drywall / isolated). Centerline
                              = the line itself, thickness = a default (drywall
                              thickness ~= 8 pt).
     - len(family) >= 2   -> pick the two extreme parallel offsets, compute
                              centerline as their midline, thickness = perp
                              distance between them, length = union extent of
                              all merged spans projected on the tangent.
4. Emit walls_consolidated[] and update diagnostics.walls_consolidated_total.
   The original 288 walls in `walls` are PRESERVED untouched.

Run
---
    py -3.12 consolidate_walls.py [path/to/consensus_model.json]

If no path is given, defaults to runs/final_planta_74/consensus_model.json
relative to this file.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import Any

# --- tunables --------------------------------------------------------------

ANGLE_TOLERANCE_DEG = 2.0      # collinear if orientation within +/- 2 deg
PERP_DISTANCE_MAX_PT = 6.0     # same family if perp distance below this
TANGENT_OVERLAP_SLACK_PT = 24.0  # how much gap along tangent still counts as
                                  # "same wall" (openings can break a face)
DRYWALL_DEFAULT_THK_PT = 8.0   # fallback thickness for orphan single faces

# --- helpers ---------------------------------------------------------------


def _canonical_angle(a_deg: float) -> float:
    """Map an angle into [0, 180) so that a line and its reverse share an
    orientation."""
    a = a_deg % 180.0
    if a < 0:
        a += 180.0
    return a


def _angles_close(a: float, b: float, tol: float = ANGLE_TOLERANCE_DEG) -> bool:
    """Compare two canonical angles in [0, 180), allowing wrap-around."""
    diff = abs(a - b)
    if diff > 90.0:
        diff = 180.0 - diff
    return diff <= tol


def _orientation_bucket(angle_canonical: float) -> int:
    """Round a canonical angle to an integer bucket so neighbours collide."""
    # snap to nearest 2 deg, in [0, 89]
    return int(round(angle_canonical / 2.0)) % 90


def _project_point_on_axis(p: tuple[float, float],
                            origin: tuple[float, float],
                            tangent: tuple[float, float],
                            normal: tuple[float, float]) -> tuple[float, float]:
    """Return (t, n) coordinates of point p in the (origin, tangent, normal)
    frame. tangent and normal must be unit vectors and perpendicular."""
    dx = p[0] - origin[0]
    dy = p[1] - origin[1]
    t = dx * tangent[0] + dy * tangent[1]
    n = dx * normal[0] + dy * normal[1]
    return t, n


def _wall_axis(w: dict[str, Any]) -> tuple[tuple[float, float], tuple[float, float]]:
    """Unit tangent and unit normal for a wall."""
    sx, sy = w["start"]
    ex, ey = w["end"]
    dx, dy = ex - sx, ey - sy
    L = math.hypot(dx, dy) or 1.0
    tx, ty = dx / L, dy / L
    # 2D normal: rotate tangent +90 deg
    nx, ny = -ty, tx
    return (tx, ty), (nx, ny)


# --- core clustering -------------------------------------------------------


def cluster_walls(walls: list[dict[str, Any]]) -> list[list[int]]:
    """
    Group wall indices into 'alvenaria families'. Two walls are in the same
    family iff:
      - their canonical orientations agree within ANGLE_TOLERANCE_DEG,
      - the perpendicular offset between their lines is <= PERP_DISTANCE_MAX_PT,
      - their projections on the tangent overlap (with TANGENT_OVERLAP_SLACK_PT
        of forgiveness for openings/junctions).

    Returns a list of clusters, each a list of wall indices into `walls`.
    """
    n = len(walls)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # Bucket by canonical orientation so we only compare candidates of
    # similar angle. A wall lives in its own bucket and the +/-1 neighbours
    # so that the +/-2 deg tolerance is respected at bucket boundaries.
    buckets: dict[int, list[int]] = {}
    canon = [_canonical_angle(w["angle_deg"]) for w in walls]
    for i, c in enumerate(canon):
        b = _orientation_bucket(c)
        buckets.setdefault(b, []).append(i)

    def neighbours(b: int) -> list[int]:
        out: list[int] = []
        for db in (-1, 0, 1):
            key = (b + db) % 90
            out.extend(buckets.get(key, []))
        return out

    visited_pair: set[tuple[int, int]] = set()

    for b, members in buckets.items():
        cands = neighbours(b)
        for i in members:
            wi = walls[i]
            tan_i, nor_i = _wall_axis(wi)
            si, ei = wi["start"], wi["end"]
            ti_s, _ = _project_point_on_axis(tuple(si), tuple(si), tan_i, nor_i)
            ti_e, _ = _project_point_on_axis(tuple(ei), tuple(si), tan_i, nor_i)
            t_lo_i, t_hi_i = sorted((ti_s, ti_e))

            for j in cands:
                if j <= i:
                    continue
                key = (i, j)
                if key in visited_pair:
                    continue
                visited_pair.add(key)

                if not _angles_close(canon[i], canon[j]):
                    continue

                wj = walls[j]
                # project j's endpoints into i's frame
                tj_s, nj_s = _project_point_on_axis(
                    tuple(wj["start"]), tuple(si), tan_i, nor_i)
                tj_e, nj_e = _project_point_on_axis(
                    tuple(wj["end"]), tuple(si), tan_i, nor_i)

                # j must lie at near-constant n in i's frame -> mean offset
                n_offset = 0.5 * (nj_s + nj_e)
                # the spread of nj_s vs nj_e tells us how well-parallel they are
                if abs(nj_s - nj_e) > PERP_DISTANCE_MAX_PT:
                    continue
                if abs(n_offset) > PERP_DISTANCE_MAX_PT:
                    continue

                # tangent overlap?
                t_lo_j, t_hi_j = sorted((tj_s, tj_e))
                overlap = min(t_hi_i, t_hi_j) - max(t_lo_i, t_lo_j)
                if overlap < -TANGENT_OVERLAP_SLACK_PT:
                    continue

                union(i, j)

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)
    return list(clusters.values())


# --- centerline + thickness ------------------------------------------------


def consolidate_cluster(cluster: list[int],
                        walls: list[dict[str, Any]],
                        cw_id: str) -> dict[str, Any]:
    """Turn one family of co-linear walls into a single logical wall."""
    members = [walls[i] for i in cluster]

    # Reference frame from the longest member (most reliable orientation).
    ref = max(members, key=lambda w: w["length_pt"])
    tan, nor = _wall_axis(ref)
    origin = tuple(ref["start"])

    # Project every endpoint into (t, n) of the reference frame.
    n_offsets: list[float] = []
    t_extents: list[float] = []
    for w in members:
        for p in (w["start"], w["end"]):
            t, n_ = _project_point_on_axis(tuple(p), origin, tan, nor)
            t_extents.append(t)
            n_offsets.append(n_)

    t_lo = min(t_extents)
    t_hi = max(t_extents)
    n_lo = min(n_offsets)
    n_hi = max(n_offsets)

    if len(members) >= 2 and (n_hi - n_lo) > 0.5:
        # Two physical faces -> centerline halfway between extreme offsets
        n_mid = 0.5 * (n_lo + n_hi)
        thickness = n_hi - n_lo
    else:
        # Single face / collapsed -> drywall default
        n_mid = n_offsets[0] if n_offsets else 0.0
        thickness = DRYWALL_DEFAULT_THK_PT

    # Convert (t_lo, n_mid) and (t_hi, n_mid) back to world coords.
    def to_world(t: float, n_: float) -> list[float]:
        x = origin[0] + t * tan[0] + n_ * nor[0]
        y = origin[1] + t * tan[1] + n_ * nor[1]
        return [round(x, 3), round(y, 3)]

    start = to_world(t_lo, n_mid)
    end = to_world(t_hi, n_mid)
    length = math.hypot(end[0] - start[0], end[1] - start[1])

    # Pool sources + confidence
    sources: set[str] = set()
    confs: list[float] = []
    for w in members:
        for s in w.get("sources", []):
            sources.add(s)
        confs.append(float(w.get("confidence", 1.0)))

    pooled_conf = sum(confs) / len(confs) if confs else 1.0
    # bonus when both pipelines agree
    if {"svg_native", "pipeline_v13"}.issubset(sources):
        pooled_conf = min(1.0, pooled_conf + 0.1)

    return {
        "wall_id": cw_id,
        "centerline_start": start,
        "centerline_end": end,
        "thickness_pt": round(thickness, 3),
        "length_pt": round(length, 3),
        "source_face_count": len(members),
        "sources_pooled": sorted(sources),
        "confidence": round(pooled_conf, 4),
        "member_wall_ids": [w["wall_id"] for w in members],
    }


# --- driver ---------------------------------------------------------------


def consolidate(consensus_path: Path) -> dict[str, Any]:
    raw = consensus_path.read_text(encoding="utf-8")
    model = json.loads(raw)
    walls = model.get("walls", [])

    t0 = time.perf_counter()
    clusters = cluster_walls(walls)
    consolidated: list[dict[str, Any]] = []
    for k, c in enumerate(sorted(clusters, key=lambda c: -sum(walls[i]["length_pt"] for i in c)), 1):
        consolidated.append(consolidate_cluster(c, walls, f"lw-{k}"))
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    model["walls_consolidated"] = consolidated
    diag = model.setdefault("diagnostics", {})
    diag["walls_consolidated_total"] = len(consolidated)
    diag["walls_consolidated_latency_ms"] = round(elapsed_ms, 2)

    consensus_path.write_text(
        json.dumps(model, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "walls_in": len(walls),
        "walls_out": len(consolidated),
        "latency_ms": elapsed_ms,
        "examples": consolidated[:3],
        "size_distribution": {
            "single_face": sum(1 for c in consolidated if c["source_face_count"] == 1),
            "two_face": sum(1 for c in consolidated if c["source_face_count"] == 2),
            "many_face": sum(1 for c in consolidated if c["source_face_count"] >= 3),
        },
    }


def _default_consensus_path() -> Path:
    here = Path(__file__).resolve().parent
    return here.parent / "runs" / "final_planta_74" / "consensus_model.json"


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else _default_consensus_path()
    if not target.exists():
        print(f"[consolidate_walls] consensus file not found: {target}",
              file=sys.stderr)
        return 1
    print(f"[consolidate_walls] reading {target}")
    report = consolidate(target)
    print(f"[consolidate_walls] in:  {report['walls_in']} face-walls")
    print(f"[consolidate_walls] out: {report['walls_out']} logical walls")
    print(f"[consolidate_walls] latency: {report['latency_ms']:.1f} ms")
    print(f"[consolidate_walls] face-count distribution: "
          f"{report['size_distribution']}")
    if not (40 <= report['walls_out'] <= 100):
        print(f"[consolidate_walls] WARNING: walls_out={report['walls_out']} "
              "is outside the expected 40-100 band. Tune tolerances.",
              file=sys.stderr)
    print("[consolidate_walls] first 2 consolidated examples:")
    for ex in report["examples"][:2]:
        print(json.dumps(ex, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
