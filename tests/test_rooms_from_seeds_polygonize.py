"""Tests for the FP-014 P0 fix — polygonize-based room detection.

The legacy ``voronoi`` method (raster watershed + contour trace) emits room
polygons with up to 738 vertices because it traces raster pixel boundaries.
The polygonize method delegated to ``polygonize_rooms.polygonize_rooms``
emits clean wall-aligned cells (4–20 vts) via
``shapely.unary_union(wall_boxes) → env.difference()``.

These tests use small synthetic wall layouts to verify the seed→cell
mapping, two-seeds-same-cell handling, and dropped-seed accounting that
``detect_rooms_polygonize`` adds on top of ``polygonize_rooms``. No
``planta_74`` coupling per CLAUDE.md §2.4.
"""
from __future__ import annotations

from tools.rooms_from_seeds import detect_rooms_polygonize


def _rect_walls(x0: float = 0.0, y0: float = 0.0,
                x1: float = 100.0, y1: float = 100.0) -> list[dict]:
    return [
        {"id": "w000", "start": [x0, y1], "end": [x1, y1],
         "orientation": "h", "thickness": 5.0},
        {"id": "w001", "start": [x0, y0], "end": [x1, y0],
         "orientation": "h", "thickness": 5.0},
        {"id": "w002", "start": [x0, y0], "end": [x0, y1],
         "orientation": "v", "thickness": 5.0},
        {"id": "w003", "start": [x1, y0], "end": [x1, y1],
         "orientation": "v", "thickness": 5.0},
    ]


def _consensus(walls: list[dict], region: list[float] | None = None) -> dict:
    if region is None:
        xs = [pt[0] for w in walls for pt in (w["start"], w["end"])]
        ys = [pt[1] for w in walls for pt in (w["start"], w["end"])]
        region = [min(xs), min(ys), max(xs), max(ys)]
    return {
        "walls": walls,
        "wall_thickness_pts": 5.0,
        "planta_region": region,
    }


def _label(name: str, x: float, y: float, label_id: str | None = None) -> dict:
    return {
        "id": label_id or f"L_{name}",
        "name": name,
        "seed_pt": [x, y],
    }


def test_one_rect_room():
    """4 walls + 1 seed → 1 named room with ≤ 6 vts (clean rectangle)."""
    walls = _rect_walls()
    consensus = _consensus(walls)
    labels = [_label("KITCHEN", 50, 50)]
    rooms = detect_rooms_polygonize(consensus, labels)
    assert len(rooms) == 1
    r = rooms[0]
    assert r["name"] == "KITCHEN"
    assert r["method"] == "polygonize"
    # Wall-aligned rectangle: shapely's exterior.coords closes the ring,
    # so 4 corners → 5 entries. Tolerance 4-6 covers axis-aligned cases
    # where shapely may emit colinear midpoints from end_extend overlaps.
    assert 4 <= len(r["polygon_pts"]) <= 6, (
        f"expected 4-6 vts for a rectangle, got {len(r['polygon_pts'])}: "
        f"{r['polygon_pts']}"
    )
    assert r["area_pts2"] > 50.0


def test_two_adjacent_rooms():
    """H-shape (4 outer + 1 inner divider wall) + 2 seeds → 2 rooms."""
    walls = _rect_walls()
    walls.append({"id": "w004", "start": [50, 0], "end": [50, 100],
                  "orientation": "v", "thickness": 5.0})
    consensus = _consensus(walls)
    labels = [
        _label("ROOM_LEFT", 25, 50),
        _label("ROOM_RIGHT", 75, 50),
    ]
    rooms = detect_rooms_polygonize(consensus, labels)
    names = {r["name"] for r in rooms}
    assert len(rooms) == 2, (
        f"expected 2 rooms split by inner wall, got {len(rooms)}: {names}"
    )
    assert names == {"ROOM_LEFT", "ROOM_RIGHT"}
    for r in rooms:
        warnings = r.get("metadata", {}).get("warnings", [])
        assert "seeds_share_cell" not in warnings, (
            f"unexpected merge warning for {r['name']}: {warnings}"
        )


def test_room_with_door_gap():
    """2 colinear walls with a door-range gap → bridge closes the cell."""
    walls = [
        {"id": "w000", "start": [0, 100], "end": [100, 100],
         "orientation": "h", "thickness": 5.0},
        {"id": "w001a", "start": [0, 0], "end": [40, 0],
         "orientation": "h", "thickness": 5.0},
        {"id": "w001b", "start": [60, 0], "end": [100, 0],
         "orientation": "h", "thickness": 5.0},
        {"id": "w002", "start": [0, 0], "end": [0, 100],
         "orientation": "v", "thickness": 5.0},
        {"id": "w003", "start": [100, 0], "end": [100, 100],
         "orientation": "v", "thickness": 5.0},
    ]
    consensus = _consensus(walls)
    labels = [_label("ROOM", 50, 50)]
    # Gap = 60 - 40 = 20pt; default door_min=15 / door_max=50 → bridge fires.
    rooms = detect_rooms_polygonize(consensus, labels)
    assert len(rooms) == 1, (
        f"door bridge should close the gap → 1 room, got {len(rooms)}"
    )
    assert rooms[0]["name"] == "ROOM"
    assert len(rooms[0]["polygon_pts"]) <= 20


def test_envelope_terraco():
    """3 walls + 1 free edge along envelope → cell bounded by envelope side."""
    walls = [
        {"id": "w000", "start": [0, 100], "end": [100, 100],
         "orientation": "h", "thickness": 5.0},
        {"id": "w002", "start": [0, 0], "end": [0, 100],
         "orientation": "v", "thickness": 5.0},
        {"id": "w003", "start": [100, 0], "end": [100, 100],
         "orientation": "v", "thickness": 5.0},
    ]
    consensus = _consensus(walls, region=[0, 0, 100, 100])
    labels = [_label("TERRACO", 50, 50)]
    rooms = detect_rooms_polygonize(consensus, labels)
    assert len(rooms) == 1, (
        f"terraço with envelope-bound bottom → 1 cell, got {len(rooms)}"
    )
    r = rooms[0]
    assert r["name"] == "TERRACO"
    # Envelope bottom replaces the missing wall → substantial area.
    assert r["area_pts2"] > 100.0, (
        f"expected area > 100 pts² for terraço, got {r['area_pts2']}"
    )


def test_two_seeds_same_cell():
    """4 walls + 2 seeds inside same cell → 1 merged room + warning."""
    walls = _rect_walls()
    consensus = _consensus(walls)
    labels = [
        _label("LIVING", 30, 50, label_id="L1"),
        _label("DINING", 70, 50, label_id="L2"),
    ]
    rooms = detect_rooms_polygonize(consensus, labels)
    assert len(rooms) == 1
    r = rooms[0]
    assert r["name"] == "LIVING | DINING"
    assert r["label_ids"] == ["L1", "L2"]
    assert "seeds_share_cell" in r["metadata"]["warnings"]
    assert len(r["merged_seeds"]) == 2


def test_soft_barrier_closes_open_cell():
    """3 walls (U-shape) + soft_barrier sealing the open side → 1 closed room.

    Without the soft_barrier the cell only closes via the envelope bottom
    (see ``test_envelope_terraco``). With a soft_barrier well inside the
    envelope, the room's polygon should be bounded by the barrier line —
    materially smaller area than the envelope-bounded variant. This proves
    polygonize_rooms picks up ``consensus.soft_barriers`` as part of the
    wall_union (FP-014 §"Opção A" — peitoris/grades are the bridge between
    wall fragments that vector PDF plantas leave open).
    """
    walls = [
        {"id": "w000", "start": [0, 100], "end": [100, 100],
         "orientation": "h", "thickness": 5.0},
        {"id": "w002", "start": [0, 50], "end": [0, 100],
         "orientation": "v", "thickness": 5.0},
        {"id": "w003", "start": [100, 50], "end": [100, 100],
         "orientation": "v", "thickness": 5.0},
    ]
    consensus = _consensus(walls, region=[0, 0, 100, 100])
    consensus["soft_barriers"] = [{
        "id": "sb000",
        "polyline_pts": [[0, 50], [100, 50]],
    }]
    labels = [_label("ROOM_WITH_PEITORIL", 50, 75)]
    rooms = detect_rooms_polygonize(consensus, labels)
    assert len(rooms) == 1
    r = rooms[0]
    assert r["name"] == "ROOM_WITH_PEITORIL"
    # The soft_barrier at y=50 caps the cell from below — area should be
    # roughly 100 (x) * 50 (y) = 5000 minus the wall+barrier buffer strip
    # contribution. Significantly less than the envelope-only terraço
    # (~9500 in test_envelope_terraco), so a tight upper bound catches a
    # regression where the barrier is silently ignored.
    assert 3000 < r["area_pts2"] < 6000, (
        f"expected ~5000 pts² bounded by soft_barrier, got {r['area_pts2']}"
    )


def test_seed_outside_all_cells():
    """Seed far outside any cell is dropped + recorded in metadata."""
    walls = _rect_walls()
    consensus = _consensus(walls)
    labels = [
        _label("INSIDE", 50, 50, label_id="L_in"),
        _label("OUTSIDE_FAR", 500, 500, label_id="L_far"),
    ]
    rooms = detect_rooms_polygonize(consensus, labels)
    assert len(rooms) == 1
    assert rooms[0]["name"] == "INSIDE"
    dropped = consensus["metadata"]["rooms_from_seeds"]["dropped_seeds"]
    assert any(d["label_id"] == "L_far" for d in dropped), (
        f"expected L_far in dropped_seeds, got: {dropped}"
    )
    assert all(d["label_id"] != "L_in" for d in dropped), (
        "L_in should not be dropped (sits at cell center)"
    )
