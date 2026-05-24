"""Contract-level gates for window aperture semantics (ADR-007 / FP-024).

Rule: Window openings MUST be wall-hosted partial-height apertures.
They must preserve wall mass below sill and above head. They MUST NOT
be represented as door-like full-height voids unless explicitly
classified as a door kind.

These tests run without SketchUp — they operate on the consensus
contract and the Python pre-extrude phase of build_plan_shell_skp.
The SKP geometry gates live in test_window_aperture_geometry.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.build_plan_shell_skp import (
    FULL_HEIGHT_CARVE_KINDS,
    WINDOW_APERTURE_KINDS,
    build_shell_polygon,
    is_window_aperture,
    opening_kind_v5_normalised,
)

# ---- minimal hand-built consensus fixtures --------------------------

def _base_consensus(openings: list[dict]) -> dict:
    """Quadrado-style 4m x 4m single-room consensus with given openings."""
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "dimension_mode": "inner_clear",
        "plan_id": "test_fixture",
        "walls": [
            {"id": "w_bottom", "start": [100.0, 100.0],
             "end": [213.684, 100.0], "thickness": 5.4, "orientation": "h"},
            {"id": "w_top", "start": [100.0, 213.684],
             "end": [213.684, 213.684], "thickness": 5.4, "orientation": "h"},
            {"id": "w_left", "start": [100.0, 100.0],
             "end": [100.0, 213.684], "thickness": 5.4, "orientation": "v"},
            {"id": "w_right", "start": [213.684, 100.0],
             "end": [213.684, 213.684], "thickness": 5.4, "orientation": "v"},
        ],
        "rooms": [{
            "id": "r_main", "name": "TEST",
            "polygon_pts": [[102.7, 102.7], [210.984, 102.7],
                            [210.984, 210.984], [102.7, 210.984]],
            "area_pts2": 11725.4,
        }],
        "openings": openings,
        "soft_barriers": [],
    }


def _window(wall_id: str = "w_bottom", center: tuple = (156.842, 100.0),
            width: float = 30.0, kind: str = "window",
            origin: str = "svg_segments") -> dict:
    return {
        "id": f"win_{wall_id}",
        "wall_id": wall_id,
        "kind_v5": kind,
        "geometry_origin": origin,
        "decision": "clean",
        "confidence": 0.95,
        "center": list(center),
        "opening_width_pts": width,
    }


def _door(wall_id: str = "w_bottom", center: tuple = (156.842, 100.0),
          width: float = 30.0, kind: str = "interior_door",
          origin: str = "svg_segments") -> dict:
    return {
        "id": f"door_{wall_id}",
        "wall_id": wall_id,
        "kind_v5": kind,
        "geometry_origin": origin,
        "decision": "clean",
        "confidence": 0.95,
        "center": list(center),
        "opening_width_pts": width,
    }


# ---- 1. classification: window != door =============================

def test_window_classified_as_window_aperture():
    assert is_window_aperture(_window())
    assert opening_kind_v5_normalised(_window()) == "window"


def test_interior_door_NOT_classified_as_window():
    assert not is_window_aperture(_door(kind="interior_door"))
    assert not is_window_aperture(_door(kind="door_arc"))
    assert not is_window_aperture(_door(kind="door"))


def test_passage_NOT_classified_as_window():
    assert not is_window_aperture(_door(kind="interior_passage"))
    assert not is_window_aperture(_door(kind="open_passage"))


def test_glazed_balcony_NOT_classified_as_window():
    # porta-vidro is genuinely full-height — must NOT be treated as
    # a partial-height window aperture.
    assert not is_window_aperture(_door(kind="glazed_balcony"))


def test_kind_sets_are_disjoint():
    # The two sets MUST NOT overlap. A door cannot be a window.
    overlap = FULL_HEIGHT_CARVE_KINDS & WINDOW_APERTURE_KINDS
    assert overlap == frozenset(), f"overlap: {overlap}"


# ---- 2. shell builder: windows excluded from 2D carve ==============

def test_single_window_produces_no_2d_carve_one_aperture():
    polys, stats = build_shell_polygon(_base_consensus([_window()]))
    win_aps = stats["window_apertures"]
    assert stats["openings_carved"] == 0, (
        "windows must NOT be carved in 2D pre-extrude"
    )
    assert stats["window_apertures_3d"] == 1
    assert len(win_aps) == 1
    ap = win_aps[0]
    assert ap["wall_id"] == "w_bottom"
    assert ap["kind_v5"] == "window"
    assert ap["opening_width_pts"] == 30.0


def test_single_door_produces_2d_carve_no_aperture():
    polys, stats = build_shell_polygon(_base_consensus([_door()]))
    win_aps = stats["window_apertures"]
    assert stats["openings_carved"] == 1, "doors must be 2D carved"
    assert stats["window_apertures_3d"] == 0
    assert win_aps == []


def test_glazed_balcony_produces_2d_carve_no_aperture():
    # porta-vidro IS full-height — must use 2D carve, not 3D aperture
    polys, stats = build_shell_polygon(
        _base_consensus([_door(kind="glazed_balcony")])
    )
    assert stats["openings_carved"] == 1
    assert stats["window_apertures_3d"] == 0


def test_window_AND_door_routed_correctly():
    consensus = _base_consensus([
        _window(wall_id="w_bottom", center=(156.842, 100.0)),
        _door(wall_id="w_top", center=(156.842, 213.684)),
    ])
    polys, stats = build_shell_polygon(consensus)
    win_aps = stats["window_apertures"]
    assert stats["openings_carved"] == 1
    assert stats["window_apertures_3d"] == 1
    assert win_aps[0]["wall_id"] == "w_bottom"


def test_window_keeps_shell_intact_one_piece():
    # With NO 2D carve for windows, the wall ring stays as one piece.
    # Previously: any opening (incl. windows) could split the ring.
    polys, stats = build_shell_polygon(_base_consensus([_window()]))
    assert len(polys) == 1, (
        "wall shell must remain a single connected piece when only "
        "windows are present (no full-height door/passage carve)"
    )


def test_window_missing_width_is_skipped_with_error():
    bad = _window()
    bad["opening_width_pts"] = 0
    polys, stats = build_shell_polygon(_base_consensus([bad]))
    assert stats["window_apertures_3d"] == 0
    assert len(stats["openings_skipped_by_error"]) == 1


def test_window_missing_wall_id_is_skipped_with_error():
    bad = _window()
    bad["wall_id"] = "w_nonexistent"
    polys, stats = build_shell_polygon(_base_consensus([bad]))
    assert stats["window_apertures_3d"] == 0
    assert len(stats["openings_skipped_by_error"]) == 1


# ---- 3. host wall integrity =======================================

def test_window_aperture_records_host_wall_metadata():
    polys, stats = build_shell_polygon(_base_consensus([_window()]))
    win_aps = stats["window_apertures"]
    ap = win_aps[0]
    assert "host_wall_orientation" in ap
    assert ap["host_wall_orientation"] == "h"
    assert "host_wall_thickness_pts" in ap
    assert ap["host_wall_thickness_pts"] == 5.4


# ---- 4. planta_74 regression (the real plan) =======================

PLANTA_74_CONSENSUS = (
    Path(__file__).parent.parent / "fixtures" / "planta_74"
    / "consensus_with_human_walls_and_soft_barriers.json"
)


@pytest.mark.skipif(
    not PLANTA_74_CONSENSUS.exists(),
    reason="planta_74 consensus fixture not present",
)
def test_planta_74_windows_routed_to_3d_aperture_path():
    """All planta_74 windows must be routed to window_apertures, never
    to the 2D full-height carve path. Locked baseline: 4 windows."""
    consensus = json.loads(PLANTA_74_CONSENSUS.read_text(encoding="utf-8"))
    expected_windows = [
        o for o in consensus.get("openings", [])
        if opening_kind_v5_normalised(o) == "window"
    ]
    polys, stats = build_shell_polygon(consensus)
    win_aps = stats["window_apertures"]

    assert stats["window_apertures_3d"] == len(expected_windows), (
        f"all {len(expected_windows)} planta_74 windows must be in "
        f"window_apertures_3d (got {stats['window_apertures_3d']})"
    )
    aperture_ids = {ap["id"] for ap in win_aps}
    expected_ids = {o["id"] for o in expected_windows}
    assert aperture_ids == expected_ids, (
        f"missing apertures: {expected_ids - aperture_ids}; "
        f"extras: {aperture_ids - expected_ids}"
    )


@pytest.mark.skipif(
    not PLANTA_74_CONSENSUS.exists(),
    reason="planta_74 consensus fixture not present",
)
def test_planta_74_no_window_in_carve_path():
    """No window kind may appear in the 2D-carve count. Regression
    detector for accidental re-introduction of full-height window
    carving."""
    consensus = json.loads(PLANTA_74_CONSENSUS.read_text(encoding="utf-8"))
    door_like = [
        o for o in consensus.get("openings", [])
        if opening_kind_v5_normalised(o) in FULL_HEIGHT_CARVE_KINDS
        and (o.get("geometry_origin") or "") in {
            "svg_arc", "svg_segments", "human_annotation"
        }
    ]
    polys, stats = build_shell_polygon(consensus)
    # carve count must be <= number of door-like openings (some may
    # be skipped by origin etc., but never EXCEED door-like count;
    # any excess would be a window incorrectly routed to carve).
    assert stats["openings_carved"] <= len(door_like), (
        f"openings_carved={stats['openings_carved']} exceeds door-like "
        f"count={len(door_like)}; a window may have leaked into the "
        f"full-height carve path"
    )
