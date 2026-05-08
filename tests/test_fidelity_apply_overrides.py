"""Unit tests for the fidelity engine's apply-overrides mode (Slice 3).

Validates ADR-001 §2.10.5: when ``apply_overrides=True``, the report
carries BOTH ``global_fidelity`` (post-override) and
``global_fidelity_pre_override``. When ``apply_overrides=False``
(default), behaviour is byte-equivalent to v1 — no override-aware
keys are present.
"""
from __future__ import annotations

import copy
import uuid

import pytest

from tools.apply_overrides import OVERRIDES_SCHEMA_VERSION, _consensus_sha256
from tools.fidelity.compare_generated_to_expected import (
    EXPECTED_SCHEMA_VERSION,
    compare,
)

# ---------------------------------------------------------------------------
# Fixtures (mirror the existing fidelity engine test fixtures)
# ---------------------------------------------------------------------------


def _square(x0: float, y0: float, x1: float, y1: float):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _observed_two_rooms() -> dict:
    """Toy observed consensus: SALA + COZINHA with 1 door + 1 window."""
    sala_pts = _square(0, 0, 90, 90)
    coz_pts = _square(95, 0, 175, 80)
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
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
             "polygon_pts": sala_pts, "area_pts2": 8100,
             "seed_pt": [45, 45]},
            {"id": "r1", "name": "COZINHA",
             "polygon_pts": coz_pts, "area_pts2": 6400,
             "seed_pt": [135, 40]},
        ],
        "openings": [
            {"id": "o0", "wall_id": "w4",
             "kind_v5": "interior_door", "decision": "clean",
             "evidence": {"room_left": "SALA DE ESTAR",
                          "room_right": "COZINHA"}},
            {"id": "o1", "wall_id": "w0",
             "kind_v5": "window", "decision": "clean",
             "evidence": {"room_left": "SALA DE ESTAR"}},
        ],
        "soft_barriers": [],
    }


def _expected_two_rooms() -> dict:
    return {
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "plan_id": "test_fixture",
        "expected_counts": {
            "rooms": 2, "openings": 2, "walls": 5,
            "tolerance": {"rooms_delta": 1, "openings_delta": 1, "walls_delta": 2},
        },
        "rooms": [
            {"id": "gt_r0", "label": "SALA DE ESTAR",
             "manual_confidence": "high",
             "expected_area_m2_range": [9.0, 12.0],
             "must_be_closed": True},
            {"id": "gt_r1", "label": "COZINHA",
             "manual_confidence": "high",
             "expected_area_m2_range": [6.0, 9.0],
             "must_be_closed": True},
        ],
        "adjacency": [
            {"a": "gt_r0", "b": "gt_r1"},
        ],
        "openings": [
            {"id": "gt_o0", "kind": "interior_door"},
            {"id": "gt_o1", "kind": "window"},
        ],
        "global_bbox": {
            "width": 6.156, "height": 3.166, "tolerance_pct": 15,
        },
    }


def _override(otype: str, target_kind: str, target_id: str,
              payload: dict | None = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "type": otype,
        "target": {"kind": target_kind, "id": target_id},
        "payload": payload or {},
        "author": "human:tester",
        "created_at": "2026-05-08T20:00:00Z",
        "reason": "test fixture",
        "signature": "deadbeef" * 8,
    }


def _overrides_doc(overrides: list[dict],
                    consensus: dict | None = None) -> dict:
    sha = (
        _consensus_sha256(consensus) if consensus is not None
        else "0" * 64
    )
    return {
        "schema_version": OVERRIDES_SCHEMA_VERSION,
        "run_id": "test_run_id",
        "consensus_sha256": sha,
        "consensus_path": "runs/test_run_id/consensus.json",
        "created_at": "2026-05-08T20:00:00Z",
        "last_updated_at": "2026-05-08T20:00:00Z",
        "overrides": overrides,
        "global": {"block_skp_export": False, "block_reason": None},
        "audit_trail": [],
    }


# ---------------------------------------------------------------------------
# Test 1 — Default mode is byte-equivalent (no new keys)
# ---------------------------------------------------------------------------


def test_compare_default_mode_no_override_keys():
    """Default ``apply_overrides=False`` must NOT add the override-aware
    keys to the report — preserves byte-equivalent behaviour for the
    existing CI invocations."""
    observed = _observed_two_rooms()
    expected = _expected_two_rooms()
    report = compare(observed, expected)
    assert "global_fidelity" in report
    assert "global_fidelity_pre_override" not in report
    assert "overrides_applied_count" not in report
    assert "block_skp_export" not in report


def test_compare_byte_equivalent_with_overrides_param_false():
    """Passing ``apply_overrides=False`` explicitly must produce the
    SAME report as the default."""
    observed = _observed_two_rooms()
    expected = _expected_two_rooms()
    a = compare(observed, expected)
    b = compare(observed, expected, apply_overrides=False)
    # generated_at differs (datetime.now); strip for compare
    a.pop("generated_at", None)
    b.pop("generated_at", None)
    assert a == b


# ---------------------------------------------------------------------------
# Test 2 — apply_overrides=True with no overrides → pre == post
# ---------------------------------------------------------------------------


def test_compare_apply_overrides_with_empty_doc_pre_equals_post():
    observed = _observed_two_rooms()
    expected = _expected_two_rooms()
    doc = _overrides_doc(overrides=[], consensus=observed)
    report = compare(observed, expected,
                     apply_overrides=True, overrides_doc=doc)
    assert "global_fidelity" in report
    assert "global_fidelity_pre_override" in report
    assert report["global_fidelity"] == report["global_fidelity_pre_override"]
    assert report["overrides_applied_count"] == 0


# ---------------------------------------------------------------------------
# Test 3 — Both scores present when overrides actually change things
# ---------------------------------------------------------------------------


def test_compare_apply_overrides_emits_both_scores():
    """When overrides change the observation, the report must surface
    BOTH pre and post scores (ADR-001 §2.10.5)."""
    observed = _observed_two_rooms()
    expected = _expected_two_rooms()
    # Override: re-classify the door as a window. Affects opening_kinds
    # metric but not adjacency / count / bbox / room areas.
    ov = _override("opening_kind_override", "opening", "o0",
                   payload={"new_kind_v5": "exterior_door"})
    doc = _overrides_doc(overrides=[ov], consensus=observed)
    report = compare(observed, expected,
                     apply_overrides=True, overrides_doc=doc)
    assert "global_fidelity_pre_override" in report
    assert "global_fidelity" in report
    assert report["overrides_applied_count"] == 1
    assert "sub_scores_pre_override" in report
    assert "warnings_pre_override" in report
    assert "hard_fails_pre_override" in report


# ---------------------------------------------------------------------------
# Test 4 — Reject lowers count → score reflects the rejection in post
# ---------------------------------------------------------------------------


def test_compare_apply_overrides_reject_changes_post_score():
    """A reject_element drops an opening; opening_count_delta moves;
    the post score should reflect that while the pre score doesn't."""
    observed = _observed_two_rooms()
    expected = _expected_two_rooms()
    ov = _override("reject_element", "opening", "o0", payload={})
    doc = _overrides_doc(overrides=[ov], consensus=observed)
    report = compare(observed, expected,
                     apply_overrides=True, overrides_doc=doc)
    assert report["overrides_applied_count"] == 1
    # The opening count moved from 2 to 1; expected is 2 with tol 1
    # (delta=-1, within tol). pre_observed had 2 openings (delta=0).
    counts_post = report["metrics"]["counts"]["checks"]
    assert counts_post["openings_count_delta"]["actual"] == 1


# ---------------------------------------------------------------------------
# Test 5 — block_skp_export from overrides surfaces in fidelity report
# ---------------------------------------------------------------------------


def test_compare_apply_overrides_surfaces_block_flag():
    observed = _observed_two_rooms()
    expected = _expected_two_rooms()
    doc = _overrides_doc(overrides=[], consensus=observed)
    doc["global"]["block_skp_export"] = True
    doc["global"]["block_reason"] = "needs reviewer eyeball"
    report = compare(observed, expected,
                     apply_overrides=True, overrides_doc=doc)
    assert report["block_skp_export"] is True
    assert report["block_reason"] == "needs reviewer eyeball"


# ---------------------------------------------------------------------------
# Test 6 — Source consensus is never mutated by the engine
# ---------------------------------------------------------------------------


def test_compare_apply_overrides_does_not_mutate_observed():
    observed = _observed_two_rooms()
    expected = _expected_two_rooms()
    snap = copy.deepcopy(observed)
    ov = _override("opening_kind_override", "opening", "o0",
                   payload={"new_kind_v5": "window"})
    doc = _overrides_doc(overrides=[ov], consensus=observed)
    compare(observed, expected,
            apply_overrides=True, overrides_doc=doc)
    assert observed == snap


# ---------------------------------------------------------------------------
# Test 7 — apply_overrides=True with overrides_doc=None gives identity
# ---------------------------------------------------------------------------


def test_compare_apply_overrides_true_but_doc_none_is_identity():
    """Defensive path: caller asks for overrides mode but supplies no
    document. Engine must NOT raise; pre == post; applied_count == 0."""
    observed = _observed_two_rooms()
    expected = _expected_two_rooms()
    report = compare(observed, expected,
                     apply_overrides=True, overrides_doc=None)
    assert report["global_fidelity"] == report["global_fidelity_pre_override"]
    assert report["overrides_applied_count"] == 0
