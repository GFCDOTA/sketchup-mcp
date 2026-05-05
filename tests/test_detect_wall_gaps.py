"""Tests for the wall-gap detector (``tools.detect_wall_gaps``).

Coverage:

* schema-additive: walls / rooms / soft_barriers untouched, existing
  openings preserved, only new openings appended
* a real collinear gap is emitted with ``geometry_origin == "wall_gap"``
* gaps too narrow / too wide are rejected (no fabrication)
* a perpendicular wall crossing the gap blocks the emission (T-junction
  case)
* an existing arc opening at the gap centroid blocks the emission
* V5 classifier labels every wall_gap origin as ``open_passage``
* live planta_74 consensus: counts preserved when not invoked; when
  invoked, all new openings have ``geometry_origin == "wall_gap"``
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.classify_opening_kind import (
    KIND_OPEN_PASSAGE,
    classify_openings,
)
from tools.detect_wall_gaps import (
    DEFAULT_GAP_MAX_PTS,
    DEFAULT_GAP_MIN_PTS,
    detect_wall_gaps,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _h_wall(wid: str, x0: float, x1: float, y: float,
            thickness: float = 4.0) -> dict:
    return {
        "id": wid,
        "start": [x0, y],
        "end": [x1, y],
        "thickness": thickness,
        "orientation": "h",
    }


def _v_wall(wid: str, x: float, y0: float, y1: float,
            thickness: float = 4.0) -> dict:
    return {
        "id": wid,
        "start": [x, y0],
        "end": [x, y1],
        "thickness": thickness,
        "orientation": "v",
    }


def _empty_consensus(walls: list[dict],
                      existing_openings: list[dict] | None = None,
                      thickness: float = 4.0) -> dict:
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": thickness,
        "walls": walls,
        "openings": list(existing_openings or []),
        "rooms": [],
        "soft_barriers": [],
    }


# ---------- happy path --------------------------------------------------

def test_emits_wall_gap_for_collinear_pair_with_door_sized_gap():
    """Two H walls collinear at y=100, separated by a 75 pt gap (~door).
    Detector should emit exactly one wall_gap opening."""
    walls = [
        _h_wall("w000", 0, 100, 100),
        _h_wall("w001", 175, 300, 100),
    ]
    consensus = _empty_consensus(walls)
    detect_wall_gaps(consensus)

    openings = consensus["openings"]
    assert len(openings) == 1
    op = openings[0]
    assert op["geometry_origin"] == "wall_gap"
    assert op["kind"] == "door"
    assert op["wall_id"] == "w000"
    assert op["gap_neighbor_wall_id"] == "w001"
    assert op["opening_width_pts"] == pytest.approx(75.0, abs=0.01)
    assert op["center"] == [pytest.approx(137.5, abs=0.01),
                            pytest.approx(100.0, abs=0.01)]
    assert op["id"].startswith("g")
    assert 0.0 <= op["confidence"] <= 1.0


def test_metadata_stamp_records_detector_run():
    walls = [
        _h_wall("w000", 0, 100, 100),
        _h_wall("w001", 175, 300, 100),
    ]
    consensus = _empty_consensus(walls)
    detect_wall_gaps(consensus)

    md = consensus["metadata"]["wall_gap_detector"]
    assert md["version"] == "1.0.0"
    assert md["n_gaps_detected"] == 1
    assert md["n_openings_input"] == 0
    assert md["n_openings_output"] == 1
    assert md["gap_min_pts"] == DEFAULT_GAP_MIN_PTS
    assert md["gap_max_pts"] == DEFAULT_GAP_MAX_PTS


def test_works_for_vertical_walls_too():
    walls = [
        _v_wall("w000", 50, 0, 100),
        _v_wall("w001", 50, 175, 300),
    ]
    consensus = _empty_consensus(walls)
    detect_wall_gaps(consensus)

    openings = consensus["openings"]
    assert len(openings) == 1
    op = openings[0]
    assert op["geometry_origin"] == "wall_gap"
    assert op["wall_id"] == "w000"
    assert op["gap_neighbor_wall_id"] == "w001"
    assert op["center"] == [pytest.approx(50.0, abs=0.01),
                            pytest.approx(137.5, abs=0.01)]


# ---------- rejection: not fabricating ---------------------------------

def test_rejects_gap_below_min_threshold():
    """A 10 pt gap (~12 cm at 1:50) is wall imprecision, not a passage."""
    walls = [
        _h_wall("w000", 0, 100, 100),
        _h_wall("w001", 110, 300, 100),
    ]
    consensus = _empty_consensus(walls)
    detect_wall_gaps(consensus)
    assert consensus["openings"] == []
    assert consensus["metadata"]["wall_gap_detector"]["n_gaps_detected"] == 0


def test_rejects_gap_above_max_threshold():
    """A 400 pt gap (~5 m) is "no wall here", not a passage."""
    walls = [
        _h_wall("w000", 0, 100, 100),
        _h_wall("w001", 500, 700, 100),
    ]
    consensus = _empty_consensus(walls)
    detect_wall_gaps(consensus)
    assert consensus["openings"] == []


def test_rejects_when_perpendicular_wall_crosses_gap():
    """T-junction: a V wall crosses through what would otherwise be a
    valid H gap. The "gap" is actually a corner; no passage there."""
    walls = [
        _h_wall("w000", 0, 100, 100),
        _h_wall("w001", 175, 300, 100),
        # Perpendicular wall sitting in the middle of the would-be gap
        _v_wall("w002", 137, 80, 100),
    ]
    consensus = _empty_consensus(walls)
    detect_wall_gaps(consensus)
    assert consensus["openings"] == [], (
        "T-junction must not register as a passage gap"
    )


def test_does_not_pair_walls_on_different_centerlines():
    """Two H walls at clearly distinct y levels are not collinear and
    must not pair into a gap."""
    walls = [
        _h_wall("w000", 0, 100, 100),
        _h_wall("w001", 175, 300, 200),  # different y
    ]
    consensus = _empty_consensus(walls)
    detect_wall_gaps(consensus)
    assert consensus["openings"] == []


def test_emits_gap_with_thickness_scale_collinearity():
    """Two H walls drifted by less than half a wall thickness still
    count as collinear (drawing imprecision tolerance)."""
    walls = [
        _h_wall("w000", 0, 100, 100, thickness=4.0),
        _h_wall("w001", 175, 300, 101.5, thickness=4.0),  # 1.5 pt off
    ]
    consensus = _empty_consensus(walls, thickness=4.0)
    detect_wall_gaps(consensus)
    assert len(consensus["openings"]) == 1
    op = consensus["openings"][0]
    assert op["gap_collinearity_offset_pts"] == pytest.approx(1.5, abs=0.01)


# ---------- existing-opening dedupe -------------------------------------

def test_skips_gap_already_covered_by_arc_opening():
    """If an svg_arc door is already at the gap centroid, the wall-gap
    detector must not emit a second opening at the same place."""
    walls = [
        _h_wall("w000", 0, 100, 100),
        _h_wall("w001", 175, 300, 100),
    ]
    existing = [{
        "id": "o000",
        "center": [137.5, 100.0],
        "kind": "door",
        "geometry_origin": "svg_arc",
        "wall_id": "w000",
    }]
    consensus = _empty_consensus(walls, existing_openings=existing)
    detect_wall_gaps(consensus)
    # Existing arc preserved, no new wall_gap added
    assert len(consensus["openings"]) == 1
    assert consensus["openings"][0]["geometry_origin"] == "svg_arc"


def test_preserves_unrelated_existing_openings():
    """Existing openings far from any gap are preserved unchanged."""
    walls = [
        _h_wall("w000", 0, 100, 100),
        _h_wall("w001", 175, 300, 100),
    ]
    existing = [{
        "id": "o000",
        "center": [500.0, 500.0],   # nowhere near the gap
        "kind": "window",
        "geometry_origin": "svg_segments",
        "wall_id": "w999",
    }]
    consensus = _empty_consensus(walls, existing_openings=existing)
    detect_wall_gaps(consensus)
    assert len(consensus["openings"]) == 2
    origins = {o["geometry_origin"] for o in consensus["openings"]}
    assert origins == {"svg_segments", "wall_gap"}


# ---------- ID collisions ------------------------------------------------

def test_new_ids_use_g_prefix_to_avoid_arc_id_collisions():
    walls = [
        _h_wall("w000", 0, 100, 100),
        _h_wall("w001", 175, 300, 100),
    ]
    existing = [{
        "id": "o000",
        "center": [-999, -999],
        "kind": "door",
        "geometry_origin": "svg_arc",
    }]
    consensus = _empty_consensus(walls, existing_openings=existing)
    detect_wall_gaps(consensus)
    new_ids = [o["id"] for o in consensus["openings"]
               if o["geometry_origin"] == "wall_gap"]
    assert all(nid.startswith("g") for nid in new_ids)
    # No collisions with arc ids
    arc_ids = {o["id"] for o in consensus["openings"]
               if o["geometry_origin"] == "svg_arc"}
    assert set(new_ids).isdisjoint(arc_ids)


# ---------- V5 integration ----------------------------------------------

def test_v5_classifier_labels_every_wall_gap_as_open_passage():
    walls = [
        _h_wall("w000", 0, 100, 100),
        _h_wall("w001", 175, 300, 100),
        _v_wall("w002", 50, 200, 350),
        _v_wall("w003", 50, 425, 600),
    ]
    consensus = _empty_consensus(walls)
    detect_wall_gaps(consensus)
    assert len(consensus["openings"]) == 2

    classify_openings(consensus)
    for op in consensus["openings"]:
        assert op["kind_v5"] == KIND_OPEN_PASSAGE


# ---------- live planta_74 ----------------------------------------------

def _planta_74_consensus() -> dict | None:
    """Returns the live planta_74 consensus if available, else None.
    Mirrors the pattern used in tests/test_classify_opening_kind.py."""
    candidates = [
        REPO_ROOT / "runs" / "vector" / "consensus_model.json",
        REPO_ROOT / "runs" / "post_merge_e2e_2026_05_05" /
        "consensus_with_openings.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                continue
    return None


@pytest.mark.skipif(_planta_74_consensus() is None,
                    reason="planta_74 consensus snapshot unavailable")
def test_live_planta_74_walls_and_rooms_unchanged():
    consensus = _planta_74_consensus()
    n_walls_before = len(consensus["walls"])
    n_rooms_before = len(consensus.get("rooms") or [])
    n_sb_before = len(consensus.get("soft_barriers") or [])
    n_openings_before = len(consensus.get("openings") or [])

    detect_wall_gaps(consensus)

    assert len(consensus["walls"]) == n_walls_before
    assert len(consensus.get("rooms") or []) == n_rooms_before
    assert len(consensus.get("soft_barriers") or []) == n_sb_before
    # New openings can only ADD, never remove
    assert len(consensus["openings"]) >= n_openings_before
    md = consensus["metadata"]["wall_gap_detector"]
    n_added = md["n_gaps_detected"]
    assert (len(consensus["openings"]) - n_openings_before) == n_added


@pytest.mark.skipif(_planta_74_consensus() is None,
                    reason="planta_74 consensus snapshot unavailable")
def test_live_planta_74_new_openings_all_have_wall_gap_origin():
    consensus = _planta_74_consensus()
    n_before = len(consensus.get("openings") or [])
    detect_wall_gaps(consensus)
    new_openings = consensus["openings"][n_before:]
    for op in new_openings:
        assert op["geometry_origin"] == "wall_gap"
        assert op["wall_id"] != op.get("gap_neighbor_wall_id")
