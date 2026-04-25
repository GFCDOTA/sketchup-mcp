"""Map each opening in consensus_model.json to its flanking consolidated walls.

For every opening, finds wall_a / wall_b — the two consolidated walls it sits on
(typical for a door cutting one wall) or only wall_a (end-of-corridor / window
with a single wall match).

Distance metric: point-to-segment distance from opening center to each wall
centerline.  A wall is a candidate iff distance < (thickness/2 + 8 pt).

Updates the JSON in-place adding `wall_a`, `wall_b`, `offset_m` to each opening
and writes diagnostics counts under `diagnostics`.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Optional

CONSENSUS_PATH = Path(
    r"E:\Claude\sketchup-mcp-exp-dedup\runs\final_planta_74\consensus_model.json"
)

# 1 pt at the SVG scale used by this pipeline ~= 0.01 m  (the consolidator
# already stores lengths in points; 1 pt ≈ 1/72 inch but the pipeline uses
# the planta-baixa SVG scale where 1 pt has been calibrated to 0.01 m).
PT_TO_M = 0.01
SLACK_PT = 8.0  # strict tolerance beyond half-thickness (preferred match)
FALLBACK_PT = 25.0  # if no strict match, accept nearest wall within this absolute distance
                    # (covers openings whose detected center drifted slightly off
                    # the consolidated centerline — arc-seed / YOLO offsets)


def point_to_segment(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> tuple[float, float]:
    """Return (distance, t) where t in [0,1] is parametric position on AB.

    distance is the perpendicular (or endpoint) distance from P to segment AB.
    """
    dx = bx - ax
    dy = by - ay
    seg_len2 = dx * dx + dy * dy
    if seg_len2 == 0.0:
        # degenerate: a==b
        return math.hypot(px - ax, py - ay), 0.0
    t = ((px - ax) * dx + (py - ay) * dy) / seg_len2
    t_clamped = max(0.0, min(1.0, t))
    cx = ax + t_clamped * dx
    cy = ay + t_clamped * dy
    return math.hypot(px - cx, py - cy), t_clamped


def map_openings(model: dict) -> dict:
    walls = model.get("walls_consolidated", [])
    openings = model.get("openings", [])

    counts = {"both": 0, "single": 0, "fallback": 0, "none": 0}

    for op in openings:
        cx, cy = op["center"]
        # score every wall once — keep both strict and absolute-fallback shortlists
        all_scored: list[tuple[float, dict, float]] = []  # (dist, wall, t)
        for w in walls:
            ax, ay = w["centerline_start"]
            bx, by = w["centerline_end"]
            d, t = point_to_segment(cx, cy, ax, ay, bx, by)
            all_scored.append((d, w, t))
        all_scored.sort(key=lambda r: r[0])

        # strict pass: require dist < half_thickness + SLACK_PT
        scored = [
            r for r in all_scored
            if r[0] < float(r[1].get("thickness_pt", 0.0)) * 0.5 + SLACK_PT
        ]
        op["match_mode"] = "strict"

        # fallback: nearest wall(s) within FALLBACK_PT — handles centers that
        # drifted slightly off the consolidated centerline.
        if not scored:
            scored = [r for r in all_scored if r[0] < FALLBACK_PT]
            if scored:
                op["match_mode"] = "fallback"

        if not scored:
            op["wall_a"] = None
            op["wall_b"] = None
            op["offset_m"] = None
            op["match_mode"] = "none"
            counts["none"] += 1
            continue
        if op["match_mode"] == "fallback":
            counts["fallback"] += 1

        wa = scored[0][1]
        ta = scored[0][2]
        op["wall_a"] = wa["wall_id"]

        # offset along wall_a from its centerline_start, in metres
        seg_len_pt = math.hypot(
            wa["centerline_end"][0] - wa["centerline_start"][0],
            wa["centerline_end"][1] - wa["centerline_start"][1],
        )
        op["offset_m"] = round(ta * seg_len_pt * PT_TO_M, 4)

        if len(scored) >= 2:
            op["wall_b"] = scored[1][1]["wall_id"]
            counts["both"] += 1
        else:
            op["wall_b"] = None
            counts["single"] += 1

    diag = model.setdefault("diagnostics", {})
    diag["openings_mapped_both_walls"] = counts["both"]
    diag["openings_mapped_single_wall"] = counts["single"]
    diag["openings_mapped_fallback"] = counts["fallback"]
    diag["openings_unmapped"] = counts["none"]

    return counts


def main() -> int:
    if not CONSENSUS_PATH.exists():
        print(f"[ERR] not found: {CONSENSUS_PATH}", file=sys.stderr)
        return 2

    with CONSENSUS_PATH.open("r", encoding="utf-8") as f:
        model = json.load(f)

    counts = map_openings(model)

    with CONSENSUS_PATH.open("w", encoding="utf-8") as f:
        json.dump(model, f, indent=2, ensure_ascii=False)

    print(f"openings total       : {len(model.get('openings', []))}")
    print(f"  with wall_a+wall_b : {counts['both']}")
    print(f"  with wall_a only   : {counts['single']}")
    print(f"  fallback (loose)   : {counts['fallback']}  (within {FALLBACK_PT}pt of nearest centerline)")
    print(f"  no match           : {counts['none']}")
    print()
    print("examples (first 3 mapped):")
    shown = 0
    for op in model["openings"]:
        if op.get("wall_a") is None:
            continue
        print(
            f"  {op['opening_id']:>6}  wall_a={op['wall_a']!s:<6} "
            f"wall_b={op.get('wall_b')!s:<8} offset_m={op.get('offset_m')}"
        )
        shown += 1
        if shown >= 3:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
