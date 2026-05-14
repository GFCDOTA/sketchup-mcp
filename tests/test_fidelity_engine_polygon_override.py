"""End-to-end fidelity-engine tests for `room_polygon_override`
(ADR-002 Slice 6a).

The override layer should:
  1. Surface `polygon_overrides_applied_count` on the post-override
     fidelity report metadata.
  2. Cause a measurable shift in sub-scores between pre/post when the
     reviewer's polygon corrects a room that was previously failing
     `room_area_in_range`.
  3. Leave pre-override metrics unchanged so a regression in the
     detector still surfaces in `global_fidelity_pre_override`.
"""
from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path

import pytest

from tools.apply_overrides import OVERRIDES_SCHEMA_VERSION, _consensus_sha256
from tools.fidelity.compare_generated_to_expected import (
    EXPECTED_SCHEMA_VERSION,
    compare,
)

PT_TO_M = 0.19 / 5.4


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _square(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _observed_with_bad_room() -> dict:
    """Two rooms; SALA's detected polygon is way out of range
    (50x50 -> 2500 pt² ~= 3.10 m², expected band 8..14 m²).
    """
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "plan_id": "test_polygon_fixture",
        "walls": [
            {"id": "w0", "start": [0, 0], "end": [175, 0],
             "thickness": 5.4, "orientation": "h"},
            {"id": "w1", "start": [0, 0], "end": [0, 90],
             "thickness": 5.4, "orientation": "v"},
            {"id": "w2", "start": [0, 90], "end": [175, 90],
             "thickness": 5.4, "orientation": "h"},
            {"id": "w3", "start": [175, 0], "end": [175, 90],
             "thickness": 5.4, "orientation": "v"},
            {"id": "w4", "start": [90, 0], "end": [90, 90],
             "thickness": 5.4, "orientation": "v"},
        ],
        "rooms": [
            {"id": "r0", "name": "SALA DE ESTAR",
             "polygon_pts": _square(0, 0, 50, 50),  # 2500 pt²
             "area_pts2": 2500.0, "seed_pt": [25, 25]},
            {"id": "r1", "name": "COZINHA",
             "polygon_pts": _square(95, 0, 175, 80),
             "area_pts2": 6400.0, "seed_pt": [135, 40]},
        ],
        "openings": [
            {"id": "o0", "wall_id": "w4", "kind_v5": "interior_door",
             "decision": "clean",
             "evidence": {"room_left": "SALA DE ESTAR",
                          "room_right": "COZINHA"}},
        ],
        "soft_barriers": [],
    }


def _expected_two_rooms() -> dict:
    return {
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "plan_id": "test_polygon_fixture",
        "unit": "m",
        "global_bbox": {"width": 6.2, "height": 3.2, "tolerance_pct": 25},
        "expected_counts": {
            "rooms": 2, "openings": 1, "walls": 5,
            "tolerance": {"rooms_delta": 0, "openings_delta": 0,
                          "walls_delta": 0},
        },
        "rooms": [
            {"id": "sala", "label": "SALA DE ESTAR",
             "expected_area_m2_range": [8.0, 14.0],
             "manual_confidence": "high"},
            {"id": "coz", "label": "COZINHA",
             "expected_area_m2_range": [5.0, 10.0],
             "manual_confidence": "high"},
        ],
        "openings": [
            {"id": "od", "kind": "interior_door",
             "connects": ["sala", "coz"], "manual_confidence": "high"},
        ],
        "adjacency": [
            {"a": "sala", "b": "coz", "via": "od",
             "kind": "interior_door", "manual_confidence": "high"},
        ],
    }


def _polygon_override(target_id: str, new_pts: list[list[float]],
                      area_pts2: float,
                      area_m2: float,
                      edit_method: str = "manual_draw") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "type": "room_polygon_override",
        "target": {"kind": "room", "id": target_id},
        "payload": {
            "new_polygon_pts": new_pts,
            "edit_method": edit_method,
            "estimated_area_pts2": area_pts2,
            "estimated_area_m2": area_m2,
        },
        "author": "human:tester",
        "created_at": "2026-05-13T20:00:00Z",
        "reason": "fixture",
        "signature": "deadbeef" * 8,
    }


def _overrides_doc(overrides: list[dict],
                   consensus: dict) -> dict:
    return {
        "schema_version": OVERRIDES_SCHEMA_VERSION,
        "run_id": "test_run_id",
        "consensus_sha256": _consensus_sha256(consensus),
        "consensus_path": "runs/test/consensus.json",
        "created_at": "2026-05-13T20:00:00Z",
        "last_updated_at": "2026-05-13T20:00:00Z",
        "overrides": overrides,
        "global": {"block_skp_export": False, "block_reason": None},
        "audit_trail": [],
    }


# ---------------------------------------------------------------------------
# Metadata surface
# ---------------------------------------------------------------------------

def test_polygon_overrides_applied_count_surfaces_on_post_report():
    observed = _observed_with_bad_room()
    expected = _expected_two_rooms()
    # Corrected polygon: 90x90 ≈ 8100 pt² ≈ 10.03 m² — inside [8, 14].
    corrected_pts = _square(0, 0, 90, 90)
    ov = _polygon_override(
        "r0", corrected_pts,
        area_pts2=8100.0, area_m2=8100.0 * (PT_TO_M ** 2),
    )
    doc = _overrides_doc([ov], observed)

    report = compare(observed, expected, pt_to_m=PT_TO_M,
                      apply_overrides=True, overrides_doc=doc)
    assert report["polygon_overrides_applied_count"] == 1
    # The legacy total counter still ticks too.
    assert report["overrides_applied_count"] == 1


def test_polygon_overrides_applied_count_zero_without_polygon_overrides():
    observed = _observed_with_bad_room()
    expected = _expected_two_rooms()
    # A label override only — no polygon mutation.
    label_ov = {
        "id": str(uuid.uuid4()),
        "type": "room_label_override",
        "target": {"kind": "room", "id": "r0"},
        "payload": {"new_name": "ESCRITORIO"},
        "author": "human:tester",
        "created_at": "2026-05-13T20:00:00Z",
        "reason": "fixture",
        "signature": "deadbeef" * 8,
    }
    doc = _overrides_doc([label_ov], observed)
    report = compare(observed, expected, pt_to_m=PT_TO_M,
                      apply_overrides=True, overrides_doc=doc)
    assert report["polygon_overrides_applied_count"] == 0
    assert report["overrides_applied_count"] == 1


def test_polygon_overrides_applied_count_absent_in_pre_override_only_mode():
    """With apply_overrides=False, the new field is NOT present."""
    observed = _observed_with_bad_room()
    expected = _expected_two_rooms()
    report = compare(observed, expected, pt_to_m=PT_TO_M)
    assert "polygon_overrides_applied_count" not in report


# ---------------------------------------------------------------------------
# Sub-score shift
# ---------------------------------------------------------------------------

def test_polygon_override_moves_room_area_score():
    """A corrected polygon flips SALA from FAIL to PASS on
    `room_area_in_range`, raising the post-override room sub-score."""
    observed = _observed_with_bad_room()
    expected = _expected_two_rooms()

    corrected_pts = _square(0, 0, 90, 90)
    ov = _polygon_override(
        "r0", corrected_pts,
        area_pts2=8100.0, area_m2=8100.0 * (PT_TO_M ** 2),
    )
    doc = _overrides_doc([ov], observed)

    report = compare(observed, expected, pt_to_m=PT_TO_M,
                      apply_overrides=True, overrides_doc=doc)

    pre = report["sub_scores_pre_override"]
    post = report["sub_scores"]
    # pre is starved (SALA out of range), post is closer to 1.0.
    assert report["global_fidelity"] >= report["global_fidelity_pre_override"]
    # `room_score` is the engine's per-room aggregated sub-score
    # (mirrors `_metric_rooms`). It must rise after the polygon fix
    # to prove the override reached the scorer.
    assert post.get("room_score", 0) > pre.get("room_score", 0)


# ---------------------------------------------------------------------------
# Honest reporting — detector regression still visible
# ---------------------------------------------------------------------------

def test_pre_override_score_reflects_detector_output_unchanged():
    """An override-rich post-report should not erase the pre-override
    score — that's the canonical detector regression signal
    (ADR-002 §3, Risk A mitigation)."""
    observed = _observed_with_bad_room()
    expected = _expected_two_rooms()

    raw_report = compare(observed, expected, pt_to_m=PT_TO_M)

    corrected_pts = _square(0, 0, 90, 90)
    ov = _polygon_override(
        "r0", corrected_pts,
        area_pts2=8100.0, area_m2=8100.0 * (PT_TO_M ** 2),
    )
    doc = _overrides_doc([ov], observed)
    amended_report = compare(observed, expected, pt_to_m=PT_TO_M,
                              apply_overrides=True, overrides_doc=doc)

    # The pre_override field on the amended report must equal the raw
    # observed score — proving the override does not contaminate the
    # detector-only baseline.
    assert (amended_report["global_fidelity_pre_override"]
            == raw_report["global_fidelity"])
    assert (amended_report["sub_scores_pre_override"]
            == raw_report["sub_scores"])


def test_apply_overrides_does_not_mutate_inputs():
    """Compare() must not mutate the input observed/overrides docs."""
    observed = _observed_with_bad_room()
    expected = _expected_two_rooms()
    corrected_pts = _square(0, 0, 90, 90)
    ov = _polygon_override(
        "r0", corrected_pts,
        area_pts2=8100.0, area_m2=8100.0 * (PT_TO_M ** 2),
    )
    doc = _overrides_doc([ov], observed)
    observed_clone = copy.deepcopy(observed)
    doc_clone = copy.deepcopy(doc)
    _ = compare(observed, expected, pt_to_m=PT_TO_M,
                  apply_overrides=True, overrides_doc=doc)
    assert observed == observed_clone
    assert doc == doc_clone
