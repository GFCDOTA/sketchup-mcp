"""Tests for V5 opening kind enrichment.

Validates ``tools.classify_opening_kind.classify_openings``:

* schema-additive: existing fields untouched, opening count preserved
* svg_arc → door_arc (no inventing)
* svg_segments + TERRACO room → glazed_balcony
* svg_segments elsewhere → window
* missing geometry_origin → open_passage (conservative; never door_arc)
* fixtures antigas continuam válidas (no field becomes mandatory)
* live planta_74 consensus: all 12 openings classified, all door_arc
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.classify_opening_kind import (
    ALL_KINDS_V5,
    KIND_DOOR_ARC,
    KIND_GLAZED_BALCONY,
    KIND_OPEN_PASSAGE,
    KIND_WINDOW,
    classify_one,
    classify_openings,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _square_room(name: str, x0: float, y0: float, w: float, h: float) -> dict:
    return {
        "id": name.lower().replace(" ", "_"),
        "name": name,
        "polygon_pts": [
            [x0, y0],
            [x0 + w, y0],
            [x0 + w, y0 + h],
            [x0, y0 + h],
        ],
    }


def _synthetic_consensus() -> dict:
    """Mix of opening kinds to exercise every classifier branch."""
    return {
        "schema_version": "1.0.0",
        "walls": [],
        "rooms": [
            _square_room("LIVING", 0, 0, 200, 200),
            _square_room("TERRACO SOCIAL", 200, 0, 100, 200),
            _square_room("KITCHEN", 0, 200, 200, 100),
        ],
        "openings": [
            # 1) svg_arc → door_arc
            {
                "id": "o000",
                "center": [50, 100],
                "kind": "door",
                "geometry_origin": "svg_arc",
                "arc_n_cubic": 2,
                "wall_id": "w001",
            },
            # 2) svg_segments inside TERRACO → glazed_balcony
            {
                "id": "o001",
                "center": [250, 100],
                "kind": "window",
                "geometry_origin": "svg_segments",
                "wall_id": "w002",
            },
            # 3) svg_segments inside LIVING (no TERRACO) → window
            {
                "id": "o002",
                "center": [100, 50],
                "kind": "window",
                "geometry_origin": "svg_segments",
                "wall_id": "w003",
            },
            # 4) explicit wall_gap → open_passage
            {
                "id": "o003",
                "center": [100, 250],
                "geometry_origin": "wall_gap",
                "wall_id": "w004",
            },
            # 5) missing geometry_origin → open_passage (NEVER door_arc)
            {
                "id": "o004",
                "center": [50, 50],
                "wall_id": "w005",
            },
        ],
        "soft_barriers": [],
    }


def test_classify_one_svg_arc_yields_door_arc() -> None:
    rooms = _synthetic_consensus()["rooms"]
    arc = {"geometry_origin": "svg_arc", "arc_n_cubic": 2, "center": [0, 0], "wall_id": "w001"}
    kind, reason = classify_one(arc, rooms)
    assert kind == KIND_DOOR_ARC
    assert "svg_arc" in reason
    assert "w001" in reason


def test_classify_one_svg_segments_in_terraco_yields_glazed_balcony() -> None:
    cons = _synthetic_consensus()
    seg = cons["openings"][1]   # center inside TERRACO SOCIAL
    kind, reason = classify_one(seg, cons["rooms"])
    assert kind == KIND_GLAZED_BALCONY
    assert "TERRACO" in reason or "terraço" in reason.lower()


def test_classify_one_svg_segments_outside_terraco_yields_window() -> None:
    cons = _synthetic_consensus()
    seg = cons["openings"][2]   # center inside LIVING
    kind, reason = classify_one(seg, cons["rooms"])
    assert kind == KIND_WINDOW
    assert "terraço" in reason.lower() or "varanda" in reason.lower()


def test_classify_one_wall_gap_yields_open_passage() -> None:
    cons = _synthetic_consensus()
    gap = cons["openings"][3]
    kind, _ = classify_one(gap, cons["rooms"])
    assert kind == KIND_OPEN_PASSAGE


def test_door_arc_not_invented_without_evidence() -> None:
    """An opening missing geometry_origin must NOT be classified door_arc."""
    cons = _synthetic_consensus()
    no_origin = cons["openings"][4]
    kind, reason = classify_one(no_origin, cons["rooms"])
    assert kind != KIND_DOOR_ARC
    assert kind == KIND_OPEN_PASSAGE
    assert "door_arc requires explicit" in reason


def test_classify_openings_is_schema_additive() -> None:
    """Existing opening fields are preserved verbatim; only kind_v5 +
    kind_v5_reason are added.
    """
    cons = _synthetic_consensus()
    before = json.loads(json.dumps(cons["openings"]))   # deep copy
    classify_openings(cons)
    for orig, after in zip(before, cons["openings"]):
        for k in orig:
            assert orig[k] == after[k], (
                f"existing field {k!r} mutated: {orig[k]!r} -> {after[k]!r}"
            )
        assert "kind_v5" in after
        assert "kind_v5_reason" in after
        assert after["kind_v5"] in ALL_KINDS_V5


def test_classify_openings_preserves_count_and_global_invariants() -> None:
    cons = _synthetic_consensus()
    n_walls = len(cons["walls"])
    n_rooms = len(cons["rooms"])
    n_openings = len(cons["openings"])
    n_sb = len(cons["soft_barriers"])
    classify_openings(cons)
    assert len(cons["walls"]) == n_walls
    assert len(cons["rooms"]) == n_rooms
    assert len(cons["openings"]) == n_openings
    assert len(cons["soft_barriers"]) == n_sb


def test_classify_openings_stamps_metadata_with_counts() -> None:
    cons = _synthetic_consensus()
    classify_openings(cons)
    md = cons["metadata"]["opening_kind_v5_classifier"]
    assert md["version"] == "1.0.0"
    assert md["n_openings_input"] == md["n_openings_output"] == 5
    counts = md["counts"]
    assert counts[KIND_DOOR_ARC] == 1
    assert counts[KIND_GLAZED_BALCONY] == 1
    assert counts[KIND_WINDOW] == 1
    assert counts[KIND_OPEN_PASSAGE] == 2     # wall_gap + missing origin


def test_at_least_one_open_passage_in_synthetic_fixture() -> None:
    """ChatGPT review requirement: the test corpus must include at
    least one ``open_passage`` so the label is exercised."""
    cons = _synthetic_consensus()
    classify_openings(cons)
    kinds = [o["kind_v5"] for o in cons["openings"]]
    assert KIND_OPEN_PASSAGE in kinds


def test_old_consensus_without_classifier_is_still_valid() -> None:
    """Backward-compat: a consensus produced before this PR (no kind_v5
    on openings) must still be a valid input to anything that consumed
    consensus before. Concretely: classify_openings on it does not
    raise and existing ``kind`` field stays."""
    cons = {
        "walls": [],
        "rooms": [],
        "openings": [{"id": "o0", "kind": "door", "geometry_origin": "svg_arc",
                       "arc_n_cubic": 2, "center": [0, 0]}],
        "soft_barriers": [],
    }
    classify_openings(cons)
    assert cons["openings"][0]["kind"] == "door"   # original field intact
    assert cons["openings"][0]["kind_v5"] == KIND_DOOR_ARC


def test_live_planta_74_all_door_arc() -> None:
    """On the real planta_74 consensus, every detected opening is an
    arc-door. Skipped on a fresh checkout where the run is not on disk.
    """
    candidates = sorted(REPO_ROOT.glob(
        "runs/v1_pipeline_*/consensus_with_rooms.json"
    )) + sorted(REPO_ROOT.glob(
        "runs/skp_p74_*/consensus_with_rooms.json"
    ))
    if not candidates:
        pytest.skip("no live planta_74 consensus on disk")
    cons = json.loads(candidates[-1].read_text(encoding="utf-8"))
    n = len(cons["openings"])
    classify_openings(cons)
    assert len(cons["openings"]) == n
    kinds = [o["kind_v5"] for o in cons["openings"]]
    # planta_74 has 12 arc-doors and zero windows / passages
    assert all(k == KIND_DOOR_ARC for k in kinds), (
        f"unexpected kind on planta_74: {set(kinds)}"
    )
    md = cons["metadata"]["opening_kind_v5_classifier"]
    assert md["counts"][KIND_DOOR_ARC] == n
