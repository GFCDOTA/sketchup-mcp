"""Defense-in-depth tests pinning opening routing invariants.

These tests do NOT prove a bug exists — they pin invariants that are
currently satisfied (verified 2026-05-27 on planta_74 build) so any
future regression fails loudly. Companion to
test_window_aperture_contract.py:

- test_window_aperture_contract.py — pins the *contract logic*
  (kind classification, single-opening shell behaviour).
- THIS file — pins *structural invariants on the stats output*
  (count match, unique IDs, soft-barrier isolation, stub-cleanup
  preserving routing).

Background: the visual fidelity-review of planta_74 raised a
hypothesis ("maybe stub cleanup leaked extra window apertures"). The
data dismissed it (4/4 windows, no soft_barrier bleed-through, zero
duplicates). These tests crystallise that finding so the next
canonicalisation tweak doesn't silently regress routing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.build_plan_shell_skp import (
    build_shell_polygon,
    opening_kind_v5_normalised,
)

PLANTA_74_CONSENSUS = (
    Path(__file__).parent.parent / "fixtures" / "planta_74"
    / "consensus_with_human_walls_and_soft_barriers.json"
)


# ---- minimal hand-built consensus helpers ---------------------------

def _base_consensus(
    openings: list[dict], soft_barriers: list[dict] | None = None,
) -> dict:
    """Quadrado-style 4m x 4m single-room consensus."""
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "dimension_mode": "inner_clear",
        "plan_id": "test_routing_invariants",
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
        "soft_barriers": soft_barriers or [],
    }


def _window(
    wall_id: str = "w_bottom",
    center: tuple = (156.842, 100.0),
    width: float = 30.0,
    id_: str | None = None,
) -> dict:
    return {
        "id": id_ or f"win_{wall_id}",
        "wall_id": wall_id, "kind_v5": "window",
        "geometry_origin": "svg_segments", "decision": "clean",
        "confidence": 0.95, "center": list(center),
        "opening_width_pts": width,
    }


def _door(
    wall_id: str = "w_bottom",
    center: tuple = (156.842, 100.0),
    width: float = 30.0,
    id_: str | None = None,
) -> dict:
    return {
        "id": id_ or f"door_{wall_id}",
        "wall_id": wall_id, "kind_v5": "interior_door",
        "geometry_origin": "svg_segments", "decision": "clean",
        "confidence": 0.95, "center": list(center),
        "opening_width_pts": width,
    }


def _soft_barrier(id_: str, polyline_pts: list[list[float]]) -> dict:
    return {"id": id_, "polyline_pts": polyline_pts}


# ---- invariant 1: count match (generic) =============================

def test_window_aperture_count_equals_kind_window_count_generic():
    """len(window_apertures) == count of openings with kind_v5 == 'window',
    regardless of how many doors/passages share the consensus."""
    consensus = _base_consensus(openings=[
        _window(wall_id="w_bottom", id_="win_a"),
        _window(wall_id="w_top", id_="win_b", center=(156.842, 213.684)),
        _door(wall_id="w_left", id_="door_a", center=(100.0, 156.842)),
    ])
    expected = sum(
        1 for o in consensus["openings"]
        if opening_kind_v5_normalised(o) == "window"
    )
    _, stats = build_shell_polygon(consensus)
    assert stats["window_apertures_3d"] == expected
    assert len(stats["window_apertures"]) == expected


# ---- invariant 2: soft_barriers never produce window apertures ======

def test_soft_barriers_alone_produce_no_window_apertures():
    """A consensus with ONLY soft_barriers (no openings) must produce
    zero window apertures. soft_barriers (peitoril, grade) live in
    their own Ruby groups (SoftBarrier_Group_*); they are NOT
    openings and must never appear in window_apertures."""
    consensus = _base_consensus(
        openings=[],
        soft_barriers=[
            _soft_barrier("sb_0", [[110.0, 100.0], [200.0, 100.0]]),
            _soft_barrier("sb_1", [[110.0, 213.684], [200.0, 213.684]]),
        ],
    )
    _, stats = build_shell_polygon(consensus)
    assert stats["window_apertures_3d"] == 0
    assert stats["window_apertures"] == []


def test_soft_barriers_alongside_windows_do_not_inflate_aperture_count():
    """Adding soft_barriers to a consensus must NOT increase
    window_apertures_3d. Only openings with kind_v5='window' count."""
    no_sb = _base_consensus(openings=[_window()])
    _, stats_no_sb = build_shell_polygon(no_sb)

    with_sb = _base_consensus(
        openings=[_window()],
        soft_barriers=[
            _soft_barrier("sb_0", [[110.0, 100.0], [200.0, 100.0]]),
            _soft_barrier("sb_1", [[110.0, 213.684], [200.0, 213.684]]),
            _soft_barrier("sb_2", [[100.0, 110.0], [100.0, 200.0]]),
        ],
    )
    _, stats_with_sb = build_shell_polygon(with_sb)

    assert stats_no_sb["window_apertures_3d"] == 1
    assert stats_with_sb["window_apertures_3d"] == 1, (
        "soft_barriers must not affect window_apertures_3d count"
    )


# ---- invariant 4: each opening_id appears at most once =============

def test_window_apertures_have_unique_ids():
    """Each window must appear exactly once in window_apertures.
    Duplication can sneak in if the shell is split into multiple
    pieces and the aperture loop re-applies the same opening per
    piece."""
    consensus = _base_consensus(openings=[
        _window(wall_id="w_bottom", id_="win_a"),
        _window(wall_id="w_top", id_="win_b", center=(156.842, 213.684)),
        _window(wall_id="w_left", id_="win_c", center=(100.0, 156.842)),
    ])
    _, stats = build_shell_polygon(consensus)
    ids = [ap["id"] for ap in stats["window_apertures"]]
    assert len(ids) == len(set(ids)), (
        f"duplicate window aperture ids: {ids}"
    )


def test_openings_carved_does_not_double_count_doors():
    """Each door must be carved exactly once. Duplicate carving was a
    historical fail-mode when shell was fragmented mid-flow."""
    consensus = _base_consensus(openings=[
        _door(wall_id="w_bottom", id_="door_a"),
        _door(wall_id="w_top", id_="door_b", center=(156.842, 213.684)),
    ])
    _, stats = build_shell_polygon(consensus)
    assert stats["openings_carved"] == 2, (
        f"expected 2 carves, got {stats['openings_carved']}"
    )


# ---- invariant 5: planta_74 routing baseline pinned ================

@pytest.mark.skipif(
    not PLANTA_74_CONSENSUS.exists(),
    reason="planta_74 consensus fixture not present",
)
def test_planta_74_routing_counts_baseline_2026_05_27():
    """Snapshot baseline for planta_74 (verified 2026-05-27 after
    FP-026 + PR #194 organisation): 4 windows in window_apertures_3d
    and 8 openings_carved (7 interior_door + 1 glazed_balcony).

    If stub cleanup or canonicalisation alters these counts, the
    test fails loudly so the change is reviewed against routing
    semantics, not just visual gates."""
    consensus = json.loads(PLANTA_74_CONSENSUS.read_text(encoding="utf-8"))
    _, stats = build_shell_polygon(consensus)

    assert stats["window_apertures_3d"] == 4, (
        f"planta_74 window count drifted from baseline=4 "
        f"to {stats['window_apertures_3d']} — investigate routing"
    )
    assert stats["openings_carved"] == 8, (
        f"planta_74 carve count drifted from baseline=8 "
        f"to {stats['openings_carved']} — investigate routing"
    )

    # Every aperture id must correspond to a kind_v5='window' opening.
    win_ids = {
        o["id"] for o in consensus["openings"]
        if opening_kind_v5_normalised(o) == "window"
    }
    aperture_ids = {ap["id"] for ap in stats["window_apertures"]}
    assert aperture_ids == win_ids, (
        f"aperture IDs diverged from kind=window IDs; "
        f"missing: {win_ids - aperture_ids}; "
        f"extras: {aperture_ids - win_ids}"
    )


@pytest.mark.skipif(
    not PLANTA_74_CONSENSUS.exists(),
    reason="planta_74 consensus fixture not present",
)
def test_planta_74_soft_barrier_ids_never_appear_as_window_apertures():
    """planta_74 has 9 soft_barriers. None of their IDs may appear
    in window_apertures — bleed-through detection."""
    consensus = json.loads(PLANTA_74_CONSENSUS.read_text(encoding="utf-8"))
    _, stats = build_shell_polygon(consensus)
    aperture_ids = {ap["id"] for ap in stats["window_apertures"]}
    sb_ids = {sb["id"] for sb in consensus.get("soft_barriers", [])}
    bleed = aperture_ids & sb_ids
    assert bleed == set(), (
        f"soft_barrier ids leaked into window apertures: {bleed}"
    )
