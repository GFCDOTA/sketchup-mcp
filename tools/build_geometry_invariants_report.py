"""Derive a per-group invariants report from a `geometry_report.json`.

Reads the report `tools/build_plan_shell_skp.rb` writes after each
run, classifies every top-level group by semantic type, runs the
type-specific invariant checks, and emits `geometry_invariants_report.json`
with one record per group plus an overall verdict.

Output schema (per group):

    {
      "name": "PlanShell_Group",
      "semantic_type": "wall_shell",
      "material": "plan_wall",
      "bbox_m": {"min": [..., ..., ...], "max": [..., ..., ...]},
      "height_m": 2.7,
      "face_count": 118,
      "edge_count": 2328,
      "lateral_face_count": 102,
      "footprint_top_face_m2": 13.644,
      "status": "PASS" | "WARN" | "FAIL",
      "reasons": ["..."]
    }

Top-level fields:

    {
      "schema_version": "1.0.0",
      "source_report": "<path>",
      "summary": {
        "PASS": N, "WARN": N, "FAIL": N,
        "verdict": "PASS" | "WARN" | "FAIL"
      },
      "rules_applied_by_type": {...},
      "groups": [<records>],
    }

This is intentionally NOT generated inside the Ruby exporter — it
runs purely on the JSON, so it can be re-derived after the fact, run
in CI without launching SU, unit-tested with synthetic reports, and
graded WARN-vs-FAIL without touching the SU-side build.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Literal

SemanticType = Literal[
    "wall_shell", "floor", "soft_barrier",
    "door_leaf", "window", "glazed_balcony", "passage_marker",
    "unknown"
]
Status = Literal["PASS", "WARN", "FAIL"]

# Expected values pinned by the exporter. Kept in sync with
# tools/build_plan_shell_skp.rb. If those move, the constants here
# AND the comment in build_plan_shell_skp.rb must move together.
WALL_HEIGHT_M = 2.70
PARAPET_HEIGHT_M = 1.10
DOOR_HEIGHT_M = 2.10
PASSAGE_MARKER_HEIGHT_M = 1.0 / 39.3700787402  # 1 in → m
HEIGHT_TOL_M = 0.01
FLOOR_HEIGHT_EPS_M = 0.001

WALL_MATERIALS = {"plan_wall", "wall_dark", "wall_ring"}
PARAPET_MATERIALS = {"plan_parapet", "parapet"}
DOOR_MATERIALS = {"plan_door", "door_leaf"}
GLASS_MATERIALS = {"plan_window_glass", "window_glass"}
WINDOW_SILL_MATERIALS = {"plan_window_sill", "window_sill"}
WINDOW_LINTEL_MATERIALS = {"plan_window_lintel", "window_lintel"}
PASSAGE_MATERIALS = {"plan_passage_marker", "passage_marker"}

# Heuristic relative ceiling for soft-barrier top-face footprint:
# WARN if a SoftBarrier's painted top area exceeds this fraction of
# the smallest floor area in the same model. See
# tests/test_plan_shell_invariants.py for rationale.
SOFT_BARRIER_FOOTPRINT_FRACTION_WARN = 0.30


def classify_semantic_type(group_record: dict) -> SemanticType:
    """Match a top-level group's name to its semantic role."""
    name = group_record.get("name") or ""
    if name == "PlanShell_Group":
        return "wall_shell"
    if name.startswith("Floor_Group_"):
        return "floor"
    if name.startswith("SoftBarrier_Group_"):
        return "soft_barrier"
    if name.startswith("DoorLeaf_Group_"):
        return "door_leaf"
    if name.startswith("Window_Group_"):
        return "window"
    if name.startswith("GlazedBalcony_Group_"):
        return "glazed_balcony"
    if name.startswith("PassageMarker_Group_"):
        return "passage_marker"
    return "unknown"


def grade_wall_shell(g: dict, _ctx: dict) -> tuple[Status, list[str]]:
    reasons: list[str] = []
    status: Status = "PASS"
    h = g.get("height_m", 0)
    if abs(h - WALL_HEIGHT_M) > HEIGHT_TOL_M:
        status = "FAIL"
        reasons.append(
            f"height {h:.4f} m != WALL_HEIGHT_M {WALL_HEIGHT_M} ± "
            f"{HEIGHT_TOL_M}"
        )
    if g.get("lateral_face_count", 0) == 0:
        status = "FAIL"
        reasons.append("wall shell has no lateral faces (it looks flat)")
    mat = g.get("primary_material") or ""
    if mat not in WALL_MATERIALS:
        status = "FAIL"
        reasons.append(
            f"primary_material {mat!r} not in wall set {sorted(WALL_MATERIALS)}"
        )
    if g.get("default_material_face_count", 0) > 0:
        status = "FAIL"
        reasons.append(
            f"{g['default_material_face_count']} faces missing material"
        )
    return status, reasons


def grade_floor(g: dict, _ctx: dict) -> tuple[Status, list[str]]:
    reasons: list[str] = []
    status: Status = "PASS"
    h = g.get("height_m", 0)
    bbox_m = g.get("bbox_m", {})
    z_min = (bbox_m.get("min") or [0, 0, 0])[2]
    z_max = (bbox_m.get("max") or [0, 0, 0])[2]
    if abs(h) > FLOOR_HEIGHT_EPS_M:
        status = "FAIL"
        reasons.append(
            f"height {h:.4f} m > FLOOR_HEIGHT_EPS_M {FLOOR_HEIGHT_EPS_M} "
            "(floor pushed-pulled into a volume)"
        )
    if abs(z_min) > FLOOR_HEIGHT_EPS_M or abs(z_max) > FLOOR_HEIGHT_EPS_M:
        status = "FAIL"
        reasons.append(
            f"bbox.z [{z_min:.4f}, {z_max:.4f}] not at z=0"
        )
    if g.get("lateral_face_count", 0) > 0:
        status = "FAIL"
        reasons.append(
            f"{g['lateral_face_count']} lateral faces (floor must be planar)"
        )
    if g.get("face_count", 0) != 1:
        status = "FAIL"
        reasons.append(
            f"face_count {g['face_count']} != 1 (expected one planar face)"
        )
    mat = g.get("primary_material") or ""
    if mat in WALL_MATERIALS or mat in PARAPET_MATERIALS:
        status = "FAIL"
        reasons.append(
            f"primary_material {mat!r} is wall/parapet, not a floor material"
        )
    if g.get("default_material_face_count", 0) > 0:
        status = "FAIL"
        reasons.append(
            f"{g['default_material_face_count']} faces missing material"
        )
    return status, reasons


def grade_soft_barrier(g: dict, ctx: dict) -> tuple[Status, list[str]]:
    reasons: list[str] = []
    status: Status = "PASS"
    h = g.get("height_m", 0)
    if abs(h - PARAPET_HEIGHT_M) > HEIGHT_TOL_M:
        # Special-case: a SoftBarrier at floor height is the visually
        # confusing failure mode — FAIL hard.
        if h < PARAPET_HEIGHT_M / 2.0:
            status = "FAIL"
            reasons.append(
                f"height {h:.4f} m is at floor level — would look like "
                f"a floor patch, not a parapet"
            )
        else:
            status = "FAIL"
            reasons.append(
                f"height {h:.4f} m != PARAPET_HEIGHT_M {PARAPET_HEIGHT_M} "
                f"± {HEIGHT_TOL_M}"
            )
    # Full wall height is the production-rendering of a parapet leaking
    # into a wall — explicit FAIL.
    if abs(h - WALL_HEIGHT_M) <= HEIGHT_TOL_M:
        status = "FAIL"
        reasons.append(
            f"height {h:.4f} m matches WALL_HEIGHT_M — soft barrier "
            f"rendered as full wall"
        )
    mat = g.get("primary_material") or ""
    if mat not in PARAPET_MATERIALS:
        status = "FAIL"
        reasons.append(
            f"primary_material {mat!r} not in parapet set "
            f"{sorted(PARAPET_MATERIALS)}"
        )
    # WARN-level: footprint relative to smallest floor
    smallest_floor = ctx.get("smallest_floor_m2")
    if smallest_floor and smallest_floor > 0:
        top = g.get("footprint_top_face_m2", 0)
        ceiling = smallest_floor * SOFT_BARRIER_FOOTPRINT_FRACTION_WARN
        if top > ceiling:
            if status != "FAIL":
                status = "WARN"
            reasons.append(
                f"top-face area {top:.3f} m² > heuristic ceiling "
                f"{ceiling:.3f} m² ({SOFT_BARRIER_FOOTPRINT_FRACTION_WARN:.0%} "
                f"of smallest floor {smallest_floor:.3f} m²) — looks like "
                f"the 2026-05-20 bbox-as-slab pattern"
            )
    return status, reasons


def grade_door_leaf(g: dict, _ctx: dict) -> tuple[Status, list[str]]:
    reasons: list[str] = []
    status: Status = "PASS"
    h = g.get("height_m", 0)
    # The leaf is rotated 30° on its hinge, so the rendered bbox
    # height is slightly less than DOOR_HEIGHT_M (cos(30°) ≈ 0.87).
    # Accept the rotated height: [DOOR_HEIGHT_M * 0.85, DOOR_HEIGHT_M + tol].
    min_h = DOOR_HEIGHT_M * 0.85
    max_h = DOOR_HEIGHT_M + HEIGHT_TOL_M
    if h < min_h or h > max_h:
        # FAIL hard if at wall height — a door leaf rendered as a
        # full wall is the visually-confusing failure.
        if abs(h - WALL_HEIGHT_M) <= HEIGHT_TOL_M:
            status = "FAIL"
            reasons.append(
                f"door leaf height {h:.3f} m matches WALL_HEIGHT_M — "
                f"rendered as full wall instead of leaf"
            )
        elif h < FLOOR_HEIGHT_EPS_M:
            status = "FAIL"
            reasons.append(
                "door leaf flat at z=0; would look like a floor patch"
            )
        else:
            status = "FAIL"
            reasons.append(
                f"door leaf height {h:.3f} m outside expected band "
                f"[{min_h:.3f}, {max_h:.3f}]"
            )
    mat = g.get("primary_material") or ""
    if mat not in DOOR_MATERIALS:
        status = "FAIL"
        reasons.append(
            f"primary_material {mat!r} not in door set {sorted(DOOR_MATERIALS)}"
        )
    if g.get("default_material_face_count", 0) > 0:
        status = "FAIL"
        reasons.append(
            f"{g['default_material_face_count']} faces missing material"
        )
    return status, reasons


def grade_window(g: dict, _ctx: dict) -> tuple[Status, list[str]]:
    reasons: list[str] = []
    status: Status = "PASS"
    h = g.get("height_m", 0)
    # The wrapper Window_Group bbox spans from 0 to WALL_HEIGHT_M
    # because it contains all 3 bands (sill + glass + lintel).
    if abs(h - WALL_HEIGHT_M) > HEIGHT_TOL_M:
        status = "FAIL"
        reasons.append(
            f"window 3-band wrapper height {h:.3f} m != WALL_HEIGHT_M "
            f"{WALL_HEIGHT_M} ± {HEIGHT_TOL_M}; expect bbox 0 → WALL_HEIGHT_M"
        )
    # We don't enforce primary_material at the wrapper level — the
    # 3 bands inside have different materials. The wrapper records
    # the modal material, which depends on which band has more faces.
    if g.get("default_material_face_count", 0) > 0:
        status = "FAIL"
        reasons.append(
            f"{g['default_material_face_count']} faces missing material"
        )
    return status, reasons


def grade_glazed_balcony(g: dict, _ctx: dict) -> tuple[Status, list[str]]:
    reasons: list[str] = []
    status: Status = "PASS"
    h = g.get("height_m", 0)
    if abs(h - WALL_HEIGHT_M) > HEIGHT_TOL_M:
        status = "FAIL"
        reasons.append(
            f"glazed balcony height {h:.3f} m != WALL_HEIGHT_M "
            f"{WALL_HEIGHT_M} ± {HEIGHT_TOL_M}; porta-vidro should "
            f"sweep full height"
        )
    mat = g.get("primary_material") or ""
    if mat not in GLASS_MATERIALS:
        status = "FAIL"
        reasons.append(
            f"primary_material {mat!r} not in glass set {sorted(GLASS_MATERIALS)}"
        )
    if g.get("default_material_face_count", 0) > 0:
        status = "FAIL"
        reasons.append(
            f"{g['default_material_face_count']} faces missing material"
        )
    return status, reasons


def grade_passage_marker(g: dict, _ctx: dict) -> tuple[Status, list[str]]:
    reasons: list[str] = []
    status: Status = "PASS"
    h = g.get("height_m", 0)
    # Marker is intentionally tiny (~2.5 cm). FAIL if at wall or
    # door height — those would be confused with structural elements.
    if h > 0.10:  # 10 cm is the upper bound for a "marker"
        status = "FAIL"
        reasons.append(
            f"passage marker height {h:.3f} m > 0.10 m; markers must "
            f"be floor-level (~{PASSAGE_MARKER_HEIGHT_M:.3f} m)"
        )
    if h <= 0:
        status = "FAIL"
        reasons.append(
            f"passage marker height {h:.3f} m <= 0; would not render"
        )
    mat = g.get("primary_material") or ""
    if mat not in PASSAGE_MATERIALS:
        status = "FAIL"
        reasons.append(
            f"primary_material {mat!r} not in passage set "
            f"{sorted(PASSAGE_MATERIALS)}"
        )
    return status, reasons


def grade_unknown(g: dict, _ctx: dict) -> tuple[Status, list[str]]:
    return "FAIL", [
        f"group name {g.get('name')!r} does not match any known "
        "semantic prefix; cannot grade — fix exporter or extend "
        "classification."
    ]


GRADERS: dict[SemanticType, Any] = {
    "wall_shell": grade_wall_shell,
    "floor": grade_floor,
    "soft_barrier": grade_soft_barrier,
    "door_leaf": grade_door_leaf,
    "window": grade_window,
    "glazed_balcony": grade_glazed_balcony,
    "passage_marker": grade_passage_marker,
    "unknown": grade_unknown,
}


def build_invariants_report(report: dict) -> dict:
    """Produce the geometry_invariants_report dict from a raw
    geometry_report dict. Pure function — no I/O."""
    diagnostic = report.get("groups_diagnostic") or []
    # First pass: classify, derive context (smallest floor area).
    classified: list[tuple[dict, SemanticType]] = []
    for g in diagnostic:
        classified.append((g, classify_semantic_type(g)))

    floor_areas = [
        g.get("footprint_top_face_m2", 0)
        for g, t in classified
        if t == "floor" and g.get("footprint_top_face_m2", 0) > 0
    ]
    ctx = {
        "smallest_floor_m2": min(floor_areas) if floor_areas else None,
    }

    # Second pass: grade.
    out_groups: list[dict] = []
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for g, semantic in classified:
        grader = GRADERS[semantic]
        status, reasons = grader(g, ctx)
        counts[status] += 1
        out_groups.append({
            "name": g.get("name"),
            "semantic_type": semantic,
            "material": g.get("primary_material"),
            "bbox_m": g.get("bbox_m"),
            "height_m": g.get("height_m"),
            "face_count": g.get("face_count"),
            "edge_count": g.get("edge_count"),
            "lateral_face_count": g.get("lateral_face_count"),
            "footprint_top_face_m2": g.get("footprint_top_face_m2"),
            "footprint_bbox_m2": g.get("footprint_bbox_m2"),
            "status": status,
            "reasons": reasons,
        })

    # Overall verdict: worst-status across all groups.
    if counts["FAIL"] > 0:
        verdict: Status = "FAIL"
    elif counts["WARN"] > 0:
        verdict = "WARN"
    else:
        verdict = "PASS"

    return {
        "schema_version": "1.0.0",
        "source_report": report.get("skp_path", "(unknown)"),
        "summary": {
            "PASS": counts["PASS"],
            "WARN": counts["WARN"],
            "FAIL": counts["FAIL"],
            "verdict": verdict,
        },
        "context": ctx,
        "rules_applied_by_type": {
            "wall_shell": [
                f"height ≈ WALL_HEIGHT_M ({WALL_HEIGHT_M} ± {HEIGHT_TOL_M})",
                "lateral_face_count > 0",
                f"primary_material in {sorted(WALL_MATERIALS)}",
                "default_material_face_count == 0",
            ],
            "floor": [
                f"height ≤ FLOOR_HEIGHT_EPS_M ({FLOOR_HEIGHT_EPS_M})",
                "bbox.z[min] and bbox.z[max] at 0",
                "lateral_face_count == 0",
                "face_count == 1",
                "primary_material is a floor_* material (not wall/parapet)",
                "default_material_face_count == 0",
            ],
            "soft_barrier": [
                f"height ≈ PARAPET_HEIGHT_M ({PARAPET_HEIGHT_M} ± {HEIGHT_TOL_M})",
                "height NOT equal to WALL_HEIGHT_M",
                "height NOT at floor level (< PARAPET/2)",
                f"primary_material in {sorted(PARAPET_MATERIALS)}",
                "WARN: footprint_top_face_m2 ≤ "
                f"{SOFT_BARRIER_FOOTPRINT_FRACTION_WARN:.0%} × smallest_floor",
            ],
            "door_leaf": [
                f"rotated bbox height in [DOOR_HEIGHT_M×0.85, DOOR_HEIGHT_M+tol] "
                f"= [{DOOR_HEIGHT_M * 0.85:.3f}, {DOOR_HEIGHT_M + HEIGHT_TOL_M:.3f}] m",
                "height NOT equal to WALL_HEIGHT_M (no full-wall door)",
                "height NOT at floor level (no flat door patch)",
                f"primary_material in {sorted(DOOR_MATERIALS)}",
            ],
            "window": [
                f"wrapper height ≈ WALL_HEIGHT_M ({WALL_HEIGHT_M} ± {HEIGHT_TOL_M}) "
                "— bbox spans sill+glass+lintel = 0 → 2.70 m",
                "no default-material faces",
            ],
            "glazed_balcony": [
                f"height ≈ WALL_HEIGHT_M ({WALL_HEIGHT_M} ± {HEIGHT_TOL_M}) "
                "— porta-vidro full height",
                f"primary_material in {sorted(GLASS_MATERIALS)}",
            ],
            "passage_marker": [
                "height ≤ 0.10 m (floor-level marker, not structural)",
                "height > 0 (must render)",
                f"primary_material in {sorted(PASSAGE_MATERIALS)}",
            ],
            "unknown": ["FAIL — every group must classify into a known type"],
        },
        "groups": out_groups,
    }


def main(report_path: Path, out_path: Path) -> int:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    invariants = build_invariants_report(report)
    out_path.write_text(
        json.dumps(invariants, indent=2), encoding="utf-8"
    )
    s = invariants["summary"]
    print(
        f"[invariants] {out_path}  verdict={s['verdict']}  "
        f"PASS={s['PASS']} WARN={s['WARN']} FAIL={s['FAIL']}"
    )
    # Exit code reflects verdict: FAIL → 1, WARN → 0, PASS → 0.
    # Caller may grep stdout for verdict or read the JSON directly.
    return 1 if s["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("report", type=Path,
                    help="path to geometry_report.json")
    ap.add_argument(
        "--out", type=Path, default=None,
        help="output path (default: geometry_invariants_report.json "
             "alongside the input)",
    )
    args = ap.parse_args()
    out = args.out or args.report.parent / "geometry_invariants_report.json"
    raise SystemExit(main(args.report.resolve(), out.resolve()))
