"""Unit tests for tools.build_plan_shell_skp pure-Python phase.

Tests the geometric primitives that produce the 2D shell polygon
before SketchUp gets involved, plus the sidecar-metadata cache layer
added in phase 3 (ADR-003). SU is not exercised here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import MultiPolygon, Polygon

from tools.build_plan_shell_skp import (
    MIN_SLIVER_AREA_PTS2,
    SNAP_EPS_PTS,
    _file_sha256,
    build_shell_polygon,
    metadata_path,
    opening_carve_rect,
    read_metadata,
    serialize_polygons,
    should_skip,
    wall_footprint,
    write_metadata,
)

# ---- wall_footprint --------------------------------------------------


def test_wall_footprint_horizontal() -> None:
    w = {"id": "w0", "start": [10.0, 20.0], "end": [30.0, 20.0],
         "thickness": 4.0, "orientation": "h"}
    box = wall_footprint(w)
    assert box.bounds == (10.0, 18.0, 30.0, 22.0)
    assert pytest.approx(box.area) == 20.0 * 4.0


def test_wall_footprint_vertical() -> None:
    w = {"id": "w1", "start": [50.0, 10.0], "end": [50.0, 60.0],
         "thickness": 6.0, "orientation": "v"}
    box = wall_footprint(w)
    assert box.bounds == (47.0, 10.0, 53.0, 60.0)
    assert pytest.approx(box.area) == 50.0 * 6.0


def test_wall_footprint_handles_reversed_endpoints() -> None:
    # start > end on the principal axis still produces correct bounds.
    w = {"id": "w2", "start": [100.0, 50.0], "end": [20.0, 50.0],
         "thickness": 5.0, "orientation": "h"}
    box = wall_footprint(w)
    assert box.bounds == (20.0, 47.5, 100.0, 52.5)


def test_wall_footprint_rejects_unknown_orientation() -> None:
    w = {"id": "w_bad", "start": [0, 0], "end": [10, 10],
         "thickness": 5.0, "orientation": "diag"}
    with pytest.raises(ValueError, match="orientation"):
        wall_footprint(w)


def test_wall_footprint_missing_thickness() -> None:
    w = {"id": "w_no_t", "start": [0, 0], "end": [10, 0],
         "orientation": "h"}
    with pytest.raises(ValueError, match="thickness"):
        wall_footprint(w)


# ---- opening_carve_rect ---------------------------------------------


def test_opening_carve_rect_horizontal_wall() -> None:
    wall = {"id": "w0", "start": [10.0, 20.0], "end": [30.0, 20.0],
            "thickness": 4.0, "orientation": "h"}
    op = {"id": "o0", "wall_id": "w0", "center": [20.0, 20.0],
          "opening_width_pts": 6.0}
    rect = opening_carve_rect(op, wall, default_thickness=5.0)
    assert rect.bounds == (17.0, 18.0, 23.0, 22.0)
    assert pytest.approx(rect.area) == 6.0 * 4.0


def test_opening_carve_rect_vertical_wall() -> None:
    wall = {"id": "w1", "start": [50.0, 10.0], "end": [50.0, 60.0],
            "thickness": 6.0, "orientation": "v"}
    op = {"id": "o1", "wall_id": "w1", "center": [50.0, 35.0],
          "opening_width_pts": 10.0}
    rect = opening_carve_rect(op, wall, default_thickness=5.0)
    assert rect.bounds == (47.0, 30.0, 53.0, 40.0)


def test_opening_carve_rect_invalid_width() -> None:
    wall = {"id": "w0", "start": [10.0, 20.0], "end": [30.0, 20.0],
            "thickness": 4.0, "orientation": "h"}
    op = {"id": "o_bad", "wall_id": "w0", "center": [20.0, 20.0],
          "opening_width_pts": 0}
    with pytest.raises(ValueError, match="opening_width_pts"):
        opening_carve_rect(op, wall, default_thickness=5.0)


# ---- build_shell_polygon: a closed 4-wall ring ----------------------


def _square_consensus() -> dict:
    """4 walls forming a 100×100 ring centred at (0, 0), thickness 4."""
    return {
        "wall_thickness_pts": 4.0,
        "walls": [
            {"id": "wb", "start": [-50, -50], "end": [50, -50],
             "thickness": 4.0, "orientation": "h"},
            {"id": "wt", "start": [-50, 50], "end": [50, 50],
             "thickness": 4.0, "orientation": "h"},
            {"id": "wl", "start": [-50, -50], "end": [-50, 50],
             "thickness": 4.0, "orientation": "v"},
            {"id": "wr", "start": [50, -50], "end": [50, 50],
             "thickness": 4.0, "orientation": "v"},
        ],
        "openings": [],
        "rooms": [],
    }


def test_build_shell_polygon_square_no_openings_single_piece() -> None:
    polys, stats = build_shell_polygon(_square_consensus())
    assert stats["input_walls"] == 4
    assert stats["openings_carved"] == 0
    assert stats["shell_pieces_after_sliver_filter"] == 1
    poly = polys[0]
    assert isinstance(poly, Polygon)
    # Outer perimeter sits in the expected bbox (±2 thickness from centre).
    assert poly.exterior.bounds == (-52.0, -52.0, 52.0, 52.0)
    # Topology: exactly one inner hole (the room interior).
    assert len(list(poly.interiors)) == 1
    # Theoretical donut area = 104² - 96² = 1600. Shapely's actual
    # union deducts the 4 corner overlap cells (4×4 each, 4×4=16
    # double-counted) → 1584. The buffer-close-gap pass shaves a
    # further few square units at concave inner corners. A 5% band
    # comfortably covers both.
    expected_area = 104 ** 2 - 96 ** 2
    assert poly.area == pytest.approx(expected_area, rel=0.06)


def test_build_shell_polygon_square_with_door_breaks_outer() -> None:
    cons = _square_consensus()
    cons["openings"] = [{
        "id": "door", "wall_id": "wb", "center": [0.0, -50.0],
        "opening_width_pts": 20.0,
    }]
    polys, stats = build_shell_polygon(cons)
    assert stats["openings_carved"] == 1
    # Single piece still — the door punches the outer ring but the
    # shell remains connected via the other three walls.
    assert stats["shell_pieces_after_sliver_filter"] == 1
    # Door cut removes ~20 × 4 = 80 pt² from the donut. Combined with
    # the same buffer/overlap accounting as the no-door case, a 5%
    # band still passes cleanly.
    expected_area = (104 ** 2 - 96 ** 2) - 80.0
    assert polys[0].area == pytest.approx(expected_area, rel=0.06)


# ---- build_shell_polygon: disconnected walls -----------------------


def test_build_shell_polygon_disconnected_walls_yield_multiple_pieces() -> None:
    cons = {
        "wall_thickness_pts": 4.0,
        "walls": [
            # First isolated H wall
            {"id": "w0", "start": [0, 0], "end": [100, 0],
             "thickness": 4.0, "orientation": "h"},
            # Second isolated H wall, far away — no overlap
            {"id": "w1", "start": [0, 500], "end": [100, 500],
             "thickness": 4.0, "orientation": "h"},
        ],
        "openings": [],
        "rooms": [],
    }
    polys, stats = build_shell_polygon(cons)
    assert stats["shell_pieces_after_sliver_filter"] == 2
    assert all(isinstance(p, Polygon) for p in polys)


# ---- build_shell_polygon: error paths ------------------------------


def test_build_shell_polygon_empty_walls_raises() -> None:
    with pytest.raises(ValueError, match="no walls"):
        build_shell_polygon({"walls": [], "openings": []})


def test_build_shell_polygon_opening_with_missing_wall_id_is_skipped() -> None:
    cons = _square_consensus()
    cons["openings"] = [
        {"id": "ghost", "wall_id": "DOES_NOT_EXIST", "center": [0, 0],
         "opening_width_pts": 5.0},
    ]
    polys, stats = build_shell_polygon(cons)
    # Still produces shell; the ghost opening is logged in skipped.
    assert len(polys) == 1
    assert any("DOES_NOT_EXIST" in s for s in stats["openings_skipped"])
    assert stats["openings_carved"] == 0


# ---- serialization round-trip ---------------------------------------


def test_serialize_polygons_strips_closing_duplicate() -> None:
    polys, stats = build_shell_polygon(_square_consensus())
    payload = serialize_polygons(polys, {"source": "test",
                                          "wall_thickness_pts": 4.0,
                                          "page_size_pts": [200, 200]},
                                  stats)
    assert payload["schema_version"] == "1.0.0"
    assert len(payload["polygons"]) == 1
    p = payload["polygons"][0]
    # The buffer-close-gap idiom can add micro "stair" verts at each
    # corner (one extra per concave inner-corner). We require the
    # closing duplicate to be STRIPPED — that's what the serializer
    # is responsible for — but allow the buffer-introduced verts.
    outer = p["outer"]
    assert outer[0] != outer[-1], \
        "serializer must strip the closing duplicate vertex"
    # The clean theoretical count is 4 (square corners). buffer can
    # add up to ~12 extra verts; if we see >32 something else is wrong.
    assert 4 <= len(outer) <= 32, f"unexpected outer vert count: {len(outer)}"
    # The square donut has exactly one hole, also a simple polygon.
    assert len(p["holes"]) == 1
    hole = p["holes"][0]
    assert hole[0] != hole[-1], \
        "serializer must strip the closing duplicate vertex for holes"
    assert 4 <= len(hole) <= 32


def test_sliver_threshold_keeps_real_pieces_drops_micro() -> None:
    # Two walls: one real-sized, one micro that survives in the union.
    cons = {
        "wall_thickness_pts": 4.0,
        "walls": [
            {"id": "real", "start": [0, 0], "end": [100, 0],
             "thickness": 4.0, "orientation": "h"},
            # A tiny disconnected wall, area = 0.4 * 0.4 = 0.16 pts^2
            # — below MIN_SLIVER_AREA_PTS2.
            {"id": "micro", "start": [1000, 1000], "end": [1000.4, 1000],
             "thickness": 0.4, "orientation": "h"},
        ],
        "openings": [],
        "rooms": [],
    }
    polys, stats = build_shell_polygon(cons)
    # Only the real wall survives.
    assert stats["shell_pieces_after_sliver_filter"] == 1
    assert stats["slivers_removed"] == 1
    assert MIN_SLIVER_AREA_PTS2 > 0.16


# ---- constants pinned to documented values --------------------------


def test_snap_eps_within_expected_range() -> None:
    # Stays well below typical wall thickness (5 pt for planta_74)
    # so the buffer-close-gap idiom cannot accidentally merge real
    # parallel walls.
    assert 0 < SNAP_EPS_PTS < 0.5


def test_min_sliver_area_below_typical_wall_unit() -> None:
    # A 1×1 pt² sliver is real noise; the threshold must be lower
    # than meaningful geometry.
    assert 0 < MIN_SLIVER_AREA_PTS2 < 1.0


# ---- sidecar metadata cache (phase 3) -------------------------------


def test_should_skip_returns_false_when_no_metadata(tmp_path: Path) -> None:
    skp = tmp_path / "m.skp"
    skp.write_bytes(b"fake")
    assert should_skip(skp, consensus_sha256="abc" * 8) is False


def test_should_skip_true_when_sha_and_exporter_match(tmp_path: Path) -> None:
    consensus = tmp_path / "c.json"
    consensus.write_text('{"foo": "bar"}', encoding="utf-8")
    sha = _file_sha256(consensus)
    skp = tmp_path / "m.skp"
    skp.write_bytes(b"fake-skp")
    write_metadata(
        skp, consensus_sha256=sha,
        sketchup_exe=Path("su.exe"), command=["python", "-m", "x"],
    )
    assert should_skip(skp, sha) is True


def test_should_skip_false_when_sha_mismatches(tmp_path: Path) -> None:
    skp = tmp_path / "m.skp"
    skp.write_bytes(b"fake-skp")
    write_metadata(
        skp, consensus_sha256="aaa" * 8,
        sketchup_exe=Path("su.exe"), command=[],
    )
    assert should_skip(skp, consensus_sha256="bbb" * 8) is False


def test_should_skip_false_when_exporter_differs(tmp_path: Path) -> None:
    """A .skp produced by consume_consensus.rb must NOT be reused by
    a plan_shell request (and vice-versa). The exporter tag in
    metadata distinguishes them."""
    skp = tmp_path / "m.skp"
    skp.write_bytes(b"fake-skp")
    sha = "abc" * 8
    write_metadata(
        skp, consensus_sha256=sha,
        sketchup_exe=Path("su.exe"), command=[],
    )
    # Now overwrite the exporter tag to something else.
    meta = read_metadata(skp)
    assert meta is not None
    meta["exporter"] = "consume_consensus"  # not us
    metadata_path(skp).write_text(json.dumps(meta), encoding="utf-8")
    assert should_skip(skp, sha) is False


def test_metadata_path_is_sidecar(tmp_path: Path) -> None:
    skp = tmp_path / "model.skp"
    p = metadata_path(skp)
    assert p.parent == skp.parent
    assert p.name == "model.skp.metadata.json"


def test_read_metadata_returns_none_on_missing_or_corrupt(
    tmp_path: Path,
) -> None:
    skp = tmp_path / "m.skp"
    skp.write_bytes(b"x")
    # missing
    assert read_metadata(skp) is None
    # corrupt
    metadata_path(skp).write_text("{not json", encoding="utf-8")
    assert read_metadata(skp) is None


def test_write_metadata_includes_exporter_tag(tmp_path: Path) -> None:
    skp = tmp_path / "m.skp"
    skp.write_bytes(b"x")
    write_metadata(
        skp, consensus_sha256="abc" * 8,
        sketchup_exe=Path("su.exe"),
        command=["python", "-m", "tools.build_plan_shell_skp"],
    )
    meta = read_metadata(skp)
    assert meta is not None
    # The exporter name is the cache namespace — must be present so a
    # consume-produced sidecar doesn't satisfy a plan-shell skip query.
    assert meta["exporter"] == "build_plan_shell_skp"
    assert meta["consensus_sha256"] == "abc" * 8
    assert meta["schema_version"] == "1.0.0"
