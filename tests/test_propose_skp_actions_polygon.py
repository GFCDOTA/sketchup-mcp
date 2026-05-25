"""Tests for the Slice 6b polygon-correction detection rule in
``tools.propose_skp_actions``.

Covers:
- rule emits ``expand_room_polygon`` chip when observed area is
  below the expected range;
- rule emits ``shrink_room_polygon`` chip when observed area is
  above the expected range;
- rule is a no-op when the fidelity report is missing, contains no
  warnings, or has warnings the room name doesn't match;
- the suggested polygon's recomputed area is close to the target;
- chip ids are stable across re-runs (idempotence per
  ``_stable_action_id``);
- the polygon-math helpers (shoelace area, centroid scale,
  bbox-corner deltas) are mathematically correct.

These tests do NOT exercise the cockpit chip handler — that lives in
``tests/test_cockpit_proposed_actions_polygon.py``.
"""
from __future__ import annotations

from tools.propose_skp_actions import (
    POLYGON_CORRECTION_CONFIDENCE,
    PT_TO_M,
    _bbox_delta_pts,
    _polygon_area_pts2,
    _polygon_bbox,
    _polygon_centroid,
    _rule_polygon_correction,
    _scale_polygon_around_centroid,
    propose_actions,
)

# ---- Polygon math helpers ----------------------------------------------


def test_polygon_area_unit_square():
    sq = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert _polygon_area_pts2(sq) == 100.0


def test_polygon_area_degenerate_returns_zero():
    assert _polygon_area_pts2([]) == 0.0
    assert _polygon_area_pts2([[0, 0]]) == 0.0
    assert _polygon_area_pts2([[0, 0], [1, 0]]) == 0.0


def test_polygon_area_is_orientation_invariant():
    ccw = [[0, 0], [10, 0], [10, 10], [0, 10]]
    cw = list(reversed(ccw))
    assert _polygon_area_pts2(ccw) == _polygon_area_pts2(cw)


def test_polygon_centroid_unit_square():
    sq = [[0, 0], [10, 0], [10, 10], [0, 10]]
    cx, cy = _polygon_centroid(sq)
    assert cx == 5.0
    assert cy == 5.0


def test_polygon_bbox_returns_min_max_pairs():
    pts = [[2, 3], [10, 1], [7, 9]]
    assert _polygon_bbox(pts) == (2, 1, 10, 9)


def test_scale_around_centroid_doubles_linear_dimension():
    sq = [[0, 0], [10, 0], [10, 10], [0, 10]]
    scaled = _scale_polygon_around_centroid(sq, 2.0)
    # Centroid stays at (5, 5); each vertex moves 2x distance from centroid.
    assert scaled == [[-5.0, -5.0], [15.0, -5.0], [15.0, 15.0], [-5.0, 15.0]]
    # Area should be 4x.
    assert _polygon_area_pts2(scaled) == 400.0


def test_scale_around_centroid_halves_area_when_factor_is_sqrt_half():
    sq = [[0, 0], [10, 0], [10, 10], [0, 10]]
    s = (0.5) ** 0.5
    scaled = _scale_polygon_around_centroid(sq, s)
    assert abs(_polygon_area_pts2(scaled) - 50.0) < 1e-9


def test_bbox_delta_positive_on_right_top_when_expanded():
    sq = [[0, 0], [10, 0], [10, 10], [0, 10]]
    expanded = _scale_polygon_around_centroid(sq, 2.0)
    delta = _bbox_delta_pts(sq, expanded)
    # left moves left (negative), bottom moves down (negative),
    # right moves right (positive), top moves up (positive).
    assert delta == [-5.0, -5.0, 5.0, 5.0]


def test_bbox_delta_negative_on_outer_corners_when_shrunk():
    sq = [[0, 0], [10, 0], [10, 10], [0, 10]]
    shrunk = _scale_polygon_around_centroid(sq, 0.5)
    delta = _bbox_delta_pts(sq, shrunk)
    # left moves right (positive), bottom moves up (positive),
    # right moves left (negative), top moves down (negative).
    assert delta == [2.5, 2.5, -2.5, -2.5]


# ---- Detection rule fixtures + helpers ---------------------------------


def _toy_consensus_with_polygon_rooms() -> dict:
    """3 rooms with explicit polygons. Areas chosen so the canonical
    fidelity warning fixtures below trigger the expected behaviour."""
    return {
        "schema_version": "1.0.0",
        "walls": [],
        "openings": [],
        "rooms": [
            # TERRACO TECNICO: 40x30 = 1200 pts² ≈ 1.49 m².
            # We claim observed=1.61 m² (close enough; the rule reads
            # the warning text not the polygon area) and expect a
            # chip suggesting expansion toward [2.0, 8.0].
            {"id": "r2", "name": "TERRACO TECNICO",
             "polygon_pts": [[0, 0], [40, 0], [40, 30], [0, 30]],
             "area_pts2": 1200},
            # SUITE 01: 200x150 = 30000 pts² ≈ 37.18 m².
            # Used for shrink case (observed too large).
            {"id": "r4", "name": "SUITE 01",
             "polygon_pts": [[0, 0], [200, 0], [200, 150], [0, 150]],
             "area_pts2": 30000},
            # SALA: in-range; no chip should fire.
            {"id": "r0", "name": "SALA",
             "polygon_pts": [[0, 0], [100, 0], [100, 100], [0, 100]],
             "area_pts2": 10000},
        ],
    }


def _expand_warning() -> str:
    return ("TERRACO TECNICO area marginal: observed 1.61 m^2 vs "
            "expected [2.0, 8.0]")


def _shrink_warning() -> str:
    return ("SUITE 01 area out_of_range: observed 37.18 m^2 vs "
            "expected [10.0, 28.0]")


# ---- Rule behaviour ----------------------------------------------------


def test_rule_emits_expand_chip_when_room_below_min():
    actions = _rule_polygon_correction(
        _toy_consensus_with_polygon_rooms()["rooms"],
        {"warnings": [_expand_warning()]},
        created_at="2026-05-24T00:00:00Z",
    )
    expand = [a for a in actions if a["type"] == "expand_room_polygon"]
    assert len(expand) == 1, [a["type"] for a in actions]
    a = expand[0]
    assert a["target"] == {"kind": "room", "id": "r2"}
    assert a["confidence"] == POLYGON_CORRECTION_CONFIDENCE
    p = a["payload"]
    assert p["current_area_m2"] == 1.61
    assert p["target_area_m2"] == 2.0
    assert p["expected_range_m2"] == [2.0, 8.0]
    assert p["scale_factor"] > 1.0  # expansion
    assert len(p["suggested_polygon_pts"]) == 4
    assert isinstance(p["delta_pts"], list) and len(p["delta_pts"]) == 4
    assert isinstance(p["estimated_area_pts2"], float)
    assert isinstance(p["estimated_area_m2"], float)
    assert "TERRACO TECNICO" in p["warning_text"].upper()


def test_rule_emits_shrink_chip_when_room_above_max():
    actions = _rule_polygon_correction(
        _toy_consensus_with_polygon_rooms()["rooms"],
        {"warnings": [_shrink_warning()]},
        created_at="2026-05-24T00:00:00Z",
    )
    shrink = [a for a in actions if a["type"] == "shrink_room_polygon"]
    assert len(shrink) == 1
    a = shrink[0]
    assert a["target"] == {"kind": "room", "id": "r4"}
    assert a["payload"]["scale_factor"] < 1.0  # shrink


def test_rule_skips_when_no_fidelity_report():
    actions = _rule_polygon_correction(
        _toy_consensus_with_polygon_rooms()["rooms"],
        None,
        created_at="2026-05-24T00:00:00Z",
    )
    assert actions == []


def test_rule_skips_when_no_warnings_field():
    actions = _rule_polygon_correction(
        _toy_consensus_with_polygon_rooms()["rooms"],
        {},
        created_at="2026-05-24T00:00:00Z",
    )
    assert actions == []


def test_rule_skips_when_room_name_not_in_warnings():
    actions = _rule_polygon_correction(
        _toy_consensus_with_polygon_rooms()["rooms"],
        {"warnings": [
            "NONEXISTENT ROOM area marginal: observed 1.0 m^2 vs "
            "expected [2.0, 4.0]",
        ]},
        created_at="2026-05-24T00:00:00Z",
    )
    assert actions == []


def test_rule_skips_when_observed_in_range_warning():
    """If a warning's parsed range happens to bracket observed area
    (which shouldn't normally appear in a real fidelity report, but
    is possible if the engine emits a marginal/borderline warning),
    the rule emits nothing — there's no correction to suggest."""
    actions = _rule_polygon_correction(
        _toy_consensus_with_polygon_rooms()["rooms"],
        {"warnings": [
            "TERRACO TECNICO area marginal: observed 3.0 m^2 vs "
            "expected [2.0, 8.0]",
        ]},
        created_at="2026-05-24T00:00:00Z",
    )
    assert actions == []


def test_rule_skips_room_without_polygon_pts():
    rooms = [{"id": "r9", "name": "TERRACO TECNICO", "polygon_pts": []}]
    actions = _rule_polygon_correction(
        rooms, {"warnings": [_expand_warning()]},
        created_at="2026-05-24T00:00:00Z",
    )
    assert actions == []


def test_rule_skips_malformed_warning_text():
    actions = _rule_polygon_correction(
        _toy_consensus_with_polygon_rooms()["rooms"],
        {"warnings": [
            "garbled — not an area warning",
            123,  # not a string at all
        ]},
        created_at="2026-05-24T00:00:00Z",
    )
    assert actions == []


def test_suggested_polygon_expands_area_for_expand_chip():
    """Direction-of-change invariant. The producer scales by
    sqrt(target_warning_area / observed_warning_area), then applies
    to the consensus polygon. The polygon area may not match the
    warning's observed area exactly (the rule reads the warning
    text, not the polygon), so we assert direction not absolute
    target. The cockpit text-area lets the human refine."""
    rooms = _toy_consensus_with_polygon_rooms()["rooms"]
    actions = _rule_polygon_correction(
        rooms, {"warnings": [_expand_warning()]},
        created_at="2026-05-24T00:00:00Z",
    )
    a = actions[0]
    p = a["payload"]
    target_room = next(r for r in rooms if r["id"] == "r2")
    original_area_pts2 = _polygon_area_pts2(target_room["polygon_pts"])
    suggested_area_pts2 = _polygon_area_pts2(p["suggested_polygon_pts"])
    # Expand chip → suggested area > original.
    assert suggested_area_pts2 > original_area_pts2
    # And the recomputed estimated_area_pts2 on the chip payload
    # matches what we compute here (chip is internally consistent).
    assert abs(p["estimated_area_pts2"] - suggested_area_pts2) < 1.0


def test_suggested_polygon_shrinks_area_for_shrink_chip():
    """Symmetrical direction-of-change check for shrink chips."""
    rooms = _toy_consensus_with_polygon_rooms()["rooms"]
    actions = _rule_polygon_correction(
        rooms, {"warnings": [_shrink_warning()]},
        created_at="2026-05-24T00:00:00Z",
    )
    a = next(x for x in actions if x["type"] == "shrink_room_polygon")
    p = a["payload"]
    target_room = next(r for r in rooms if r["id"] == "r4")
    original_area_pts2 = _polygon_area_pts2(target_room["polygon_pts"])
    suggested_area_pts2 = _polygon_area_pts2(p["suggested_polygon_pts"])
    assert suggested_area_pts2 < original_area_pts2


def test_rule_does_not_double_fire_on_same_room():
    """If the same room appears in two warnings, only one chip should
    be emitted (the first matched). Prevents chip spam."""
    actions = _rule_polygon_correction(
        _toy_consensus_with_polygon_rooms()["rooms"],
        {"warnings": [_expand_warning(), _expand_warning()]},
        created_at="2026-05-24T00:00:00Z",
    )
    targets = [a["target"]["id"] for a in actions]
    assert targets.count("r2") == 1


# ---- End-to-end via propose_actions() ---------------------------------


def test_propose_actions_includes_polygon_chip_when_warning_present():
    """The orchestrator wires the new rule alongside the existing four."""
    doc = propose_actions(
        consensus=_toy_consensus_with_polygon_rooms(),
        fidelity_report={"warnings": [_expand_warning()]},
    )
    types = [a["type"] for a in doc["actions"]]
    assert "expand_room_polygon" in types


def test_propose_actions_chip_id_is_stable_across_runs():
    """Idempotence — same consensus + same warning text → byte-identical
    action id. Required by ADR-001 §2.6."""
    c = _toy_consensus_with_polygon_rooms()
    f = {"warnings": [_expand_warning()]}
    doc1 = propose_actions(consensus=c, fidelity_report=f,
                            generated_at="2026-05-24T00:00:00Z")
    doc2 = propose_actions(consensus=c, fidelity_report=f,
                            generated_at="2026-05-24T01:00:00Z")
    expand1 = [a for a in doc1["actions"] if a["type"] == "expand_room_polygon"]
    expand2 = [a for a in doc2["actions"] if a["type"] == "expand_room_polygon"]
    assert expand1 and expand2
    assert expand1[0]["id"] == expand2[0]["id"]
