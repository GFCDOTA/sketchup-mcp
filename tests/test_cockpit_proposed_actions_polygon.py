"""Tests for the Slice 6b cockpit chip handler in
``cockpit.proposed_actions``.

Covers:
- ``proposed_action_to_override_payload`` promotes
  ``expand_room_polygon`` / ``shrink_room_polygon`` chips into a
  ``room_polygon_override`` payload;
- the resulting override carries ``edit_method="from_proposed_action"``
  + ``from_proposed_action_id`` linking back to the chip;
- estimated areas pre-computed by the producer are preserved; when
  missing, the chip handler recomputes (shoelace);
- malformed chip payloads (missing/empty suggested_polygon_pts, bad
  vertex shape, wrong target.kind) return ``None`` so the cockpit
  surfaces an error instead of writing a degenerate override;
- the resulting payload passes the ``tools.apply_overrides`` hard
  validator (round-trip into the Slice 6a data plane);
- pre-existing chip mappings (classify_opening, mark_low_confidence,
  request_human_review) still work — regression guard.
"""
from __future__ import annotations

from cockpit.overrides import PT_TO_M
from cockpit.proposed_actions import (
    POLYGON_PROPOSED_ACTION_TYPES,
    proposed_action_to_override_payload,
)
from tools.apply_overrides import _validate_override_payload

# ---- Fixtures ----------------------------------------------------------


def _toy_consensus() -> dict:
    return {
        "rooms": [
            {"id": "r2", "name": "TERRACO TECNICO",
             "polygon_pts": [[0, 0], [40, 0], [40, 30], [0, 30]]},
            {"id": "r4", "name": "SUITE 01",
             "polygon_pts": [[0, 0], [200, 0], [200, 150], [0, 150]]},
        ],
        "openings": [
            {"id": "o0", "kind_v5": "window"},
        ],
    }


def _expand_chip(*, suggested=None, areas: bool = True) -> dict:
    """Build a producer-shaped expand_room_polygon chip. ``areas=True``
    sets the producer's pre-computed estimated_area_*; ``areas=False``
    omits them so the chip handler must fall back to shoelace."""
    pts = suggested if suggested is not None else [
        [-1.5, -1.5], [41.5, -1.5], [41.5, 31.5], [-1.5, 31.5],
    ]
    payload: dict = {
        "current_area_m2": 1.61,
        "target_area_m2": 2.0,
        "expected_range_m2": [2.0, 8.0],
        "scale_factor": 1.1146,
        "delta_pts": [-1.5, -1.5, 1.5, 1.5],
        "suggested_polygon_pts": pts,
        "warning_text": "TERRACO TECNICO area marginal: observed 1.61 m^2",
    }
    if areas:
        # Approx: 43 * 33 = 1419 pts²; 1419 * (0.19/5.4)^2 ≈ 1.756 m²
        payload["estimated_area_pts2"] = 1419.0
        payload["estimated_area_m2"] = 1.756
    return {
        "id": "act-expand-1",
        "type": "expand_room_polygon",
        "target": {"kind": "room", "id": "r2"},
        "payload": payload,
        "confidence": 0.55,
        "rationale": "test fixture — TERRACO TECNICO expand",
        "generator": "tools/propose_skp_actions.py@v0.1",
        "created_at": "2026-05-24T00:00:00Z",
    }


def _shrink_chip() -> dict:
    return {
        "id": "act-shrink-1",
        "type": "shrink_room_polygon",
        "target": {"kind": "room", "id": "r4"},
        "payload": {
            "current_area_m2": 37.18,
            "target_area_m2": 28.0,
            "expected_range_m2": [10.0, 28.0],
            "scale_factor": 0.868,
            "delta_pts": [13.2, 9.9, -13.2, -9.9],
            "suggested_polygon_pts": [
                [13.2, 9.9], [186.8, 9.9], [186.8, 140.1], [13.2, 140.1],
            ],
            "estimated_area_pts2": 22610.0,
            "estimated_area_m2": 28.0,
            "warning_text": "SUITE 01 area out_of_range",
        },
        "confidence": 0.55,
        "rationale": "test fixture — SUITE 01 shrink",
        "generator": "tools/propose_skp_actions.py@v0.1",
        "created_at": "2026-05-24T00:00:00Z",
    }


# ---- Promotion shape ---------------------------------------------------


def test_polygon_action_types_constant_matches_expected():
    assert POLYGON_PROPOSED_ACTION_TYPES == frozenset({
        "expand_room_polygon", "shrink_room_polygon",
    })


def test_promote_expand_chip_to_room_polygon_override():
    out = proposed_action_to_override_payload(_expand_chip())
    assert out is not None
    assert out["type"] == "room_polygon_override"
    assert out["target"] == {"kind": "room", "id": "r2"}
    p = out["payload"]
    assert p["edit_method"] == "from_proposed_action"
    assert p["from_proposed_action_id"] == "act-expand-1"
    assert len(p["new_polygon_pts"]) == 4
    # All vertices are floats (not int) — apply_overrides validator
    # accepts numbers but downstream consumers may rely on float shape.
    for pt in p["new_polygon_pts"]:
        assert isinstance(pt[0], float) and isinstance(pt[1], float)
    # Producer-supplied areas are preserved verbatim.
    assert p["estimated_area_pts2"] == 1419.0
    assert p["estimated_area_m2"] == 1.756
    # Reason cites the producer's rationale prefix.
    assert "Promoted from proposed_action" in out["reason"]


def test_promote_shrink_chip_to_room_polygon_override():
    out = proposed_action_to_override_payload(_shrink_chip())
    assert out is not None
    assert out["type"] == "room_polygon_override"
    assert out["target"]["id"] == "r4"
    assert out["payload"]["from_proposed_action_id"] == "act-shrink-1"


def test_promote_recomputes_area_when_producer_omits():
    """When the producer chip is missing estimated_area_*, the chip
    handler falls back to a shoelace computation so the override
    always carries consistent area fields."""
    chip = _expand_chip(areas=False)
    out = proposed_action_to_override_payload(chip)
    assert out is not None
    p = out["payload"]
    pts = p["new_polygon_pts"]
    expected_area_pts2 = abs(
        sum(pts[i][0] * pts[(i + 1) % len(pts)][1]
             - pts[(i + 1) % len(pts)][0] * pts[i][1]
             for i in range(len(pts)))
    ) / 2.0
    assert abs(p["estimated_area_pts2"] - expected_area_pts2) < 1e-6
    assert abs(p["estimated_area_m2"]
                - expected_area_pts2 * (PT_TO_M ** 2)) < 1e-6


# ---- Defensive — malformed chips ---------------------------------------


def test_promote_returns_none_for_non_room_target():
    chip = _expand_chip()
    chip["target"] = {"kind": "opening", "id": "o0"}
    assert proposed_action_to_override_payload(chip) is None


def test_promote_returns_none_when_suggested_polygon_missing():
    chip = _expand_chip()
    chip["payload"].pop("suggested_polygon_pts")
    assert proposed_action_to_override_payload(chip) is None


def test_promote_returns_none_when_suggested_polygon_too_short():
    chip = _expand_chip(suggested=[[0, 0], [1, 0]])
    assert proposed_action_to_override_payload(chip) is None


def test_promote_returns_none_when_vertex_is_not_xy_pair():
    chip = _expand_chip(suggested=[[0, 0], [1, 0], "garbage"])
    assert proposed_action_to_override_payload(chip) is None


def test_promote_returns_none_when_vertex_is_not_numeric():
    chip = _expand_chip(suggested=[[0, 0], [1, 0], ["x", "y"]])
    assert proposed_action_to_override_payload(chip) is None


def test_promote_returns_none_when_polygon_has_zero_area():
    # Three colinear points → shoelace = 0.
    chip = _expand_chip(
        suggested=[[0, 0], [1, 0], [2, 0]],
    )
    # Strip producer-supplied area so the handler must recompute.
    chip["payload"].pop("estimated_area_pts2", None)
    chip["payload"].pop("estimated_area_m2", None)
    assert proposed_action_to_override_payload(chip) is None


# ---- Round-trip into Slice 6a apply layer ------------------------------


def test_promoted_payload_passes_apply_overrides_hard_validation():
    """End-to-end contract: a chip-derived payload must satisfy the
    Slice 6a apply-layer validator. If this regresses, the cockpit
    would write overrides that apply_overrides silently drops."""
    chip = _expand_chip()
    promoted = proposed_action_to_override_payload(chip)
    assert promoted is not None
    # Build the wire-shaped override (apply_overrides expects id +
    # author + created_at; save_override would fill them. For the
    # hard validator only target + type + payload matter).
    wire = {
        "id": "fake-uuid",
        "type": promoted["type"],
        "target": promoted["target"],
        "payload": promoted["payload"],
    }
    assert _validate_override_payload(wire, _toy_consensus()) is None


def test_promoted_shrink_payload_passes_apply_overrides_hard_validation():
    promoted = proposed_action_to_override_payload(_shrink_chip())
    assert promoted is not None
    wire = {
        "id": "fake-uuid",
        "type": promoted["type"],
        "target": promoted["target"],
        "payload": promoted["payload"],
    }
    assert _validate_override_payload(wire, _toy_consensus()) is None


# ---- Regression — pre-existing mappings stay intact --------------------


def test_classify_opening_mapping_unchanged():
    """Slice 4 contract — classify_opening still maps to
    opening_kind_override. Slice 6b must not regress it."""
    action = {
        "id": "act-classify",
        "type": "classify_opening",
        "target": {"kind": "opening", "id": "o0"},
        "payload": {"suggested_kind": "interior_passage"},
        "rationale": "kind_unknown_default",
    }
    out = proposed_action_to_override_payload(action)
    assert out is not None
    assert out["type"] == "opening_kind_override"
    assert out["payload"]["new_kind_v5"] == "interior_passage"


def test_mark_low_confidence_mapping_unchanged():
    action = {
        "id": "act-low",
        "type": "mark_low_confidence",
        "target": {"kind": "opening", "id": "o0"},
        "payload": {"current_confidence": 0.55},
        "rationale": "below threshold",
    }
    out = proposed_action_to_override_payload(action)
    assert out is not None
    assert out["type"] == "mark_suspect"
    assert out["payload"]["severity"] == "low"


def test_unknown_type_returns_none_unchanged():
    action = {
        "id": "act-future",
        "type": "future_unknown_type",
        "target": {"kind": "opening", "id": "o0"},
        "payload": {},
    }
    assert proposed_action_to_override_payload(action) is None
