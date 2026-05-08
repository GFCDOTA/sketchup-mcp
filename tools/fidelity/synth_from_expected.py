"""synth_from_expected.py — generate a synthetic observed consensus
that perfectly matches a manual ``expected_model.json``.

Why this exists:

The fidelity engine in ``compare_generated_to_expected`` is the
authority on "did the pipeline match the truth". If the engine has a
bug — wrong formula, wrong unit conversion, swapped axes — the gate
gives wrong answers. This module catches that case via a round-trip:

    expected_model.json
            |
            v
    synthesize_observed(expected) -> fake observed dict
            |
            v
    compare(observed, expected) should return global_fidelity == 1.0

If the round trip ever returns < 1.0, the engine is broken (not the
pipeline). Used by ``tests/test_fidelity_engine_round_trip.py`` to
guard the engine itself.

Boundary (v0):
- Only generates the FIELDS that the engine reads:
  rooms[].name + .area_pts2 + .polygon_pts (closed),
  openings[].evidence.{room_left,room_right,room_left_id,room_right_id},
  openings[].kind_v5,
  walls (just enough to satisfy the global_bbox metric).
- Does NOT generate door arcs, opening positions, soft_barriers,
  page_size_pts, source metadata. Those are downstream concerns the
  engine v1 doesn't read.
- Picks an arbitrary mid-range area_m2 from each room's expected
  range; converts to pt^2 via PT_TO_M.
"""
from __future__ import annotations

from typing import Any

PT_TO_M_DEFAULT = 0.19 / 5.4


def _mid_area_m2(rng: list[float] | None) -> float:
    if not rng or len(rng) != 2:
        return 10.0  # arbitrary plausible
    lo, hi = float(rng[0]), float(rng[1])
    return (lo + hi) / 2.0


def _square_polygon_for_area_m2(area_m2: float, x0: float, y0: float,
                                  pt_to_m: float) -> tuple[list[list[float]], float]:
    """Returns (polygon_pts in PDF coords, area_pts2). The polygon is a
    square with the requested m^2 area, anchored at (x0, y0) in pt
    space. Returned polygon is CLOSED-style (3+ distinct verts) without
    repeating the first vertex (matches the consensus convention)."""
    side_m = max(area_m2, 0.01) ** 0.5
    side_pt = side_m / pt_to_m
    poly = [
        [x0, y0],
        [x0 + side_pt, y0],
        [x0 + side_pt, y0 + side_pt],
        [x0, y0 + side_pt],
    ]
    area_pt2 = side_pt * side_pt
    return poly, area_pt2


def synthesize_observed(expected: dict,
                          pt_to_m: float = PT_TO_M_DEFAULT) -> dict:
    """Build a synthetic consensus dict whose fidelity score against
    ``expected`` should be 1.0.

    Layout strategy:
    - Compute target global bbox from ``expected.global_bbox`` (or
      from rooms' areas if missing).
    - Lay out room polygons (squares of mid-range area) packed inside
      the bbox, each anchored at an arbitrary corner — the engine
      only inspects per-room polygon area + closure, not where the
      polygon sits.
    - Emit exactly ``expected_counts.walls`` walls (when present),
      all of which lie ON the bbox rectangle so global_bbox metric
      passes exactly. The first 4 are the corner segments; remaining
      are inserted as zero-displacement dupes (the engine only reads
      walls[].start/end for bbox; counts what's there).
    """
    rooms_synth: list[dict] = []
    label_to_id_observed: dict[str, str] = {}

    gb = expected.get("global_bbox") or {}
    if gb and "width" in gb and "height" in gb:
        target_w_pt = float(gb["width"]) / pt_to_m
        target_h_pt = float(gb["height"]) / pt_to_m
    else:
        # Fallback: pick a square that fits all rooms loosely.
        n = max(1, len(expected.get("rooms") or []))
        target_w_pt = max(1.0, n * 50.0)
        target_h_pt = 50.0

    # Lay out rooms along the bottom edge inside the bbox; coords
    # are decorative for the engine.
    cursor_x = 0.0
    for i, gt_room in enumerate(expected.get("rooms") or []):
        label = gt_room["label"]
        target_area = _mid_area_m2(gt_room.get("expected_area_m2_range"))
        poly, area_pt2 = _square_polygon_for_area_m2(
            target_area, cursor_x, 0.0, pt_to_m,
        )
        side_pt = poly[1][0] - poly[0][0]
        rid = f"r{i:03d}"
        rooms_synth.append({
            "id": rid,
            "name": label,
            "label_id": f"l{i:03d}",
            "seed_pt": [cursor_x + side_pt / 2, side_pt / 2],
            "polygon_pts": poly,
            "area_pts2": round(area_pt2, 2),
            "centroid": [cursor_x + side_pt / 2, side_pt / 2],
            "method": "synthesized",
        })
        label_to_id_observed[gt_room["id"]] = rid
        cursor_x += side_pt + 1.0

    # Emit walls anchored on the bbox rectangle so global_bbox metric
    # is satisfied exactly. Wall count = expected_counts.walls when
    # present (otherwise just the 4 corners).
    expected_wall_count = (
        (expected.get("expected_counts") or {}).get("walls")
    )
    walls_synth: list[dict] = [
        {"id": "w_b", "start": [0.0, 0.0],
         "end": [target_w_pt, 0.0],
         "thickness": 5.4, "orientation": "h"},
        {"id": "w_t", "start": [0.0, target_h_pt],
         "end": [target_w_pt, target_h_pt],
         "thickness": 5.4, "orientation": "h"},
        {"id": "w_l", "start": [0.0, 0.0],
         "end": [0.0, target_h_pt],
         "thickness": 5.4, "orientation": "v"},
        {"id": "w_r", "start": [target_w_pt, 0.0],
         "end": [target_w_pt, target_h_pt],
         "thickness": 5.4, "orientation": "v"},
    ]
    if expected_wall_count is not None:
        target_n = int(expected_wall_count)
        # Pad with degenerate-but-distinct wall stubs anchored on the
        # bbox edge, all within the bbox so they don't grow it.
        # Engine reads walls[].start/end only for the global bbox
        # corners; padding inside doesn't move them.
        i = 0
        while len(walls_synth) < target_n:
            x = (i + 1) * (target_w_pt / (target_n + 1))
            walls_synth.append({
                "id": f"w_pad_{i}",
                "start": [x, 0.0],
                "end": [x, 1.0],  # 1pt segment, inside bbox
                "thickness": 5.4,
                "orientation": "v",
            })
            i += 1
        # If we already had MORE than target_n (possible for very small
        # target_n < 4), trim. Never goes below the 4 corners.
        if target_n >= 4:
            walls_synth = walls_synth[:target_n]

    openings_synth: list[dict] = []
    for j, gt_op in enumerate(expected.get("openings") or []):
        connects = gt_op.get("connects") or []
        if len(connects) < 2:
            continue
        a_id = label_to_id_observed.get(connects[0])
        b_id = label_to_id_observed.get(connects[1])
        if not a_id or not b_id:
            continue
        a_label = next(
            (r["label"] for r in expected["rooms"] if r["id"] == connects[0]),
            None,
        )
        b_label = next(
            (r["label"] for r in expected["rooms"] if r["id"] == connects[1]),
            None,
        )
        if not a_label or not b_label:
            continue
        kind = gt_op.get("kind", "interior_door")
        openings_synth.append({
            "id": f"o{j:03d}",
            "kind_v5": kind,
            "decision": "clean",
            "evidence": {
                "room_left": a_label,
                "room_right": b_label,
                "room_left_id": a_id,
                "room_right_id": b_id,
            },
        })

    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "synth_provenance": "tools.fidelity.synth_from_expected",
        "walls": walls_synth,
        "rooms": rooms_synth,
        "openings": openings_synth,
        "soft_barriers": [],
    }
