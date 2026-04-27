"""consume_consensus_dryrun.py
Python mirror of consume_consensus.rb#dry_run, for systems without
a Ruby interpreter on PATH (Windows dev box uses E:/Python312).

Reproduces the V6.2 plan-building logic step-for-step so we can validate
counts, host-wall lookups AND coord transform (origin normalize + Y invert
+ scale) before invoking the SketchUp Ruby side. Output bounds devem
casar com Sketchup's model.bounds quando o Ruby roda.

Usage:
    py consume_consensus_dryrun.py path/to/consensus_model.json

Env override:
    CONSUME_SCALE_OVERRIDE=0.01  py consume_consensus_dryrun.py ...
"""
from __future__ import annotations

import json
import math
import os
import sys
from typing import Any

# --- constants kept in sync with consume_consensus.rb -------------
WALL_HEIGHT_M = 2.70
ALVENARIA_THICKNESS_M = 0.14
DRYWALL_THICKNESS_M = 0.075
PT_TO_M = 0.000352778
CONF_DOOR_COMPONENT_MIN = 0.5
ARC_ORIGIN = "svg_arc"
GAP_ORIGIN = "pipeline_gap"

# Scale override empirico (debug knob). Mesmo flag que Ruby:
# CONSUME_SCALE_OVERRIDE=<float>. nil/empty = usa PT_TO_M default.
_env_override = os.environ.get("CONSUME_SCALE_OVERRIDE", "").strip()
SCALE_OVERRIDE: float | None = float(_env_override) if _env_override else None

# Origem em pt-space, populada por compute_origin antes de transform.
_ORIGIN_PT: dict[str, float] = {"min_x": 0.0, "max_y": 0.0}


def effective_scale() -> float:
    return SCALE_OVERRIDE if SCALE_OVERRIDE is not None else PT_TO_M


def compute_origin(walls: list[dict[str, Any]]) -> dict[str, float]:
    """Computa min_x, max_y das walls em pt-space + loga ranges."""
    global _ORIGIN_PT
    if not walls:
        _ORIGIN_PT = {"min_x": 0.0, "max_y": 0.0}
        print("[dryrun] empty walls — origin_pt zeroed")
        return _ORIGIN_PT
    xs = [c for w in walls for c in (w["start_pt"][0], w["end_pt"][0])]
    ys = [c for w in walls for c in (w["start_pt"][1], w["end_pt"][1])]
    _ORIGIN_PT = {"min_x": min(xs), "max_y": max(ys)}

    s = effective_scale()
    world_x_max = (max(xs) - min(xs)) * s
    world_y_max = (max(ys) - min(ys)) * s
    print(f"[dryrun] walls_pt_range:    x[{min(xs):.1f}..{max(xs):.1f}] y[{min(ys):.1f}..{max(ys):.1f}]")
    print(f"[dryrun] origin_pt:         {_ORIGIN_PT}")
    print(f"[dryrun] effective_scale:   {s}  ({'CONSUME_SCALE_OVERRIDE active' if SCALE_OVERRIDE is not None else 'PT_TO_M default'})")
    print(f"[dryrun] walls_world_range: x[0..{world_x_max:.3f}m] y[0..{world_y_max:.3f}m] (pos Y-invert)")
    return _ORIGIN_PT


def world_xy_m(x_pt: float, y_pt: float) -> tuple[float, float]:
    """Converte (x_pt, y_pt) -> (x_m, y_m) com origin shift + Y invert + scale.

    Mirror exato de consume_consensus.rb#world_xy_m.
    """
    s = effective_scale()
    nx_m = (x_pt - _ORIGIN_PT["min_x"]) * s
    ny_m = (_ORIGIN_PT["max_y"] - y_pt) * s   # INVERT Y
    return nx_m, ny_m


def classify_orientation(angle_deg: float) -> str:
    a = abs(angle_deg) % 180.0
    if a <= 15.0 or a >= 165.0:
        return "horizontal"
    if 75.0 <= a <= 105.0:
        return "vertical"
    return "oblique"


def normalise_wall(w: dict[str, Any]) -> dict[str, Any]:
    sx, sy = (float(c) for c in w["start"])
    ex, ey = (float(c) for c in w["end"])
    dx, dy = ex - sx, ey - sy
    length_pt = math.hypot(dx, dy)
    angle_deg = float(w.get("angle_deg") or math.degrees(math.atan2(dy, dx)))
    return {
        "wall_id": w["wall_id"],
        "start_pt": (sx, sy),
        "end_pt": (ex, ey),
        "length_pt": length_pt,
        "length_m": length_pt * effective_scale(),  # consistente com pt->world
        "angle_deg": angle_deg,
        "orientation": classify_orientation(angle_deg),
        "thickness_m": ALVENARIA_THICKNESS_M,
        "confidence": float(w.get("confidence") or 1.0),
        "sources": w.get("sources") or [],
    }


def normalise_opening(o: dict[str, Any]) -> dict[str, Any]:
    cx_pt, cy_pt = (float(c) for c in o["center"])
    chord_pt = float(o.get("chord_pt") or 0.0)
    return {
        "opening_id": o["opening_id"],
        "center_pt": (cx_pt, cy_pt),
        # center_m calculado em dry_run via world_xy_m (precisa origin)
        "chord_pt": chord_pt,
        "chord_m": chord_pt * effective_scale(),  # delta sem origin shift; mesmo scale
        "kind": o.get("kind") or "door",
        "hinge_side": o.get("hinge_side"),
        "swing_deg": o.get("swing_deg"),
        "room_a": o.get("room_a"),
        "room_b": o.get("room_b"),
        "confidence": float(o.get("confidence") or 0.0),
        "geometry_origin": o.get("geometry_origin"),
        "wall_thickness_m": ALVENARIA_THICKNESS_M,
    }


def normalise_room(r: dict[str, Any]) -> dict[str, Any]:
    poly_pt = r.get("polygon") or []
    area_pt2 = float(r.get("area") or 0.0)
    s = effective_scale()
    return {
        "room_id": r["room_id"],
        "label": r.get("label_qwen") or r["room_id"],
        # polygon RAW pt — convertido on-demand via world_xy_m
        "polygon_pt": [(float(x), float(y)) for x, y in poly_pt],
        "area_m2": area_pt2 * s * s,  # consistente; pt^2 -> m^2
        "sources": r.get("sources") or [],
    }


def dist_point_to_segment(p, a, b) -> float:
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    seg_len2 = dx * dx + dy * dy
    if seg_len2 < 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def nearest_wall_for(point_pt, walls):
    if not walls:
        return None
    return min(walls, key=lambda w: dist_point_to_segment(point_pt, w["start_pt"], w["end_pt"]))


def build_plan(data: dict[str, Any]) -> dict[str, list]:
    walls = [normalise_wall(w) for w in (data.get("walls") or [])]
    doors: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    skipped: list[tuple[str, str, float]] = []
    for o in data.get("openings") or []:
        rec = normalise_opening(o)
        origin = rec["geometry_origin"]
        conf = rec["confidence"]
        if origin == ARC_ORIGIN and conf >= CONF_DOOR_COMPONENT_MIN:
            doors.append(rec)
        elif origin == GAP_ORIGIN:
            gaps.append(rec)
        else:
            skipped.append((rec["opening_id"], str(origin), conf))
    rooms = [normalise_room(r) for r in (data.get("rooms") or [])]
    return {"walls": walls, "doors": doors, "gaps": gaps, "rooms": rooms, "skipped": skipped}


def dry_run(json_path: str) -> dict[str, int]:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    plan = build_plan(data)
    compute_origin(plan["walls"])

    print("=== consume_consensus DRY-RUN (python mirror) ===")
    print(f"input: {json_path}")
    md = data.get("metadata", {})
    print(f"schema_version: {md.get('schema_version')}")
    print(f"coordinate_space: {md.get('coordinate_space')}")
    print(f"page_bounds: {md.get('page_bounds')}")
    print()

    print(f"WALLS - would create {len(plan['walls'])} wall groups (height {WALL_HEIGHT_M} m)")
    for w in plan["walls"][:3]:
        sx, sy = w["start_pt"]
        ex, ey = w["end_pt"]
        wsx, wsy = world_xy_m(sx, sy)
        wex, wey = world_xy_m(ex, ey)
        print(
            f"  ex: {w['wall_id']} {w['orientation']} "
            f"length={w['length_m']:.3f}m thick={w['thickness_m']}m  "
            f"world_start=({wsx:.3f},{wsy:.3f}) world_end=({wex:.3f},{wey:.3f})"
        )
    if len(plan["walls"]) > 3:
        print(f"  ...({len(plan['walls']) - 3} more)")
    print()

    # Sanity check: world bounds calculated from ALL walls (not just first 3)
    all_world_xs = []
    all_world_ys = []
    for w in plan["walls"]:
        for px, py in (w["start_pt"], w["end_pt"]):
            wx, wy = world_xy_m(px, py)
            all_world_xs.append(wx)
            all_world_ys.append(wy)
    if all_world_xs:
        print(
            f"  walls bbox SU world (m): "
            f"x[{min(all_world_xs):.3f}..{max(all_world_xs):.3f}]  "
            f"y[{min(all_world_ys):.3f}..{max(all_world_ys):.3f}]  "
            f"diag={math.hypot(max(all_world_xs)-min(all_world_xs), max(all_world_ys)-min(all_world_ys)):.3f}m"
        )
    print()

    print(
        f"DOORS - would place {len(plan['doors'])} real components "
        f"(geometry_origin={ARC_ORIGIN}, confidence>={CONF_DOOR_COMPONENT_MIN})"
    )
    for d in plan["doors"]:
        host = nearest_wall_for(d["center_pt"], plan["walls"])
        host_id = host["wall_id"] if host else "<none>"
        host_axis = host["orientation"] if host else "?"
        cx_m, cy_m = world_xy_m(*d["center_pt"])
        print(
            f"  {d['opening_id']:6s} chord={d['chord_m']:.3f}m "
            f"center_m=({cx_m:.3f}, {cy_m:.3f}) host={host_id} axis={host_axis}"
        )
    print()

    print(
        f"GAPS  - would carve {len(plan['gaps'])} simple voids "
        f"(geometry_origin={GAP_ORIGIN}, no door component)"
    )
    for g in plan["gaps"][:5]:
        host = nearest_wall_for(g["center_pt"], plan["walls"])
        host_id = host["wall_id"] if host else "<none>"
        cx_m, cy_m = world_xy_m(*g["center_pt"])
        print(f"  {g['opening_id']:6s} chord={g['chord_m']:.3f}m center_m=({cx_m:.3f},{cy_m:.3f}) host={host_id}")
    if len(plan["gaps"]) > 5:
        print(f"  ...({len(plan['gaps']) - 5} more)")
    print()

    print(f"ROOMS - would create {len(plan['rooms'])} named groups (label_qwen)")
    for r in plan["rooms"]:
        if r["polygon_pt"]:
            world_pts = [world_xy_m(x, y) for x, y in r["polygon_pt"]]
            xs = [p[0] for p in world_pts]
            ys = [p[1] for p in world_pts]
            bbox = f"world_bbox=x[{min(xs):.2f}..{max(xs):.2f}] y[{min(ys):.2f}..{max(ys):.2f}]"
        else:
            bbox = "world_bbox=<empty>"
        print(
            f"  {r['room_id']:6s} '{r['label']}' poly_pts={len(r['polygon_pt'])} "
            f"area_m2={r['area_m2']:.4f} {bbox}"
        )
    print()

    if plan["skipped"]:
        print(f"SKIPPED - {len(plan['skipped'])} openings filtered out")
        for oid, origin, conf in plan["skipped"]:
            print(f"  {oid:6s} origin={origin} conf={conf:.2f}")
        print()

    summary = {
        "walls": len(plan["walls"]),
        "doors": len(plan["doors"]),
        "gaps": len(plan["gaps"]),
        "rooms": len(plan["rooms"]),
    }
    print(
        f"would create {summary['walls']} walls / {summary['doors']} doors / "
        f"{summary['gaps']} gaps / {summary['rooms']} rooms"
    )
    return summary


if __name__ == "__main__":
    default_path = (
        r"E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/consensus_model.json"
    )
    path = sys.argv[1] if len(sys.argv) > 1 else default_path
    dry_run(path)
