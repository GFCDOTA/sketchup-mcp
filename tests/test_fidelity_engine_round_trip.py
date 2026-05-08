"""Round-trip guard for the fidelity engine.

If a manual ``expected_model.json`` round-trips through
``tools.fidelity.synth_from_expected.synthesize_observed`` and back
through ``compare(...)``, the resulting ``global_fidelity`` MUST be
1.0. Anything less means the engine itself has a bug — wrong area
formula, wrong unit conversion, swapped axes, broken adjacency
matcher, etc.

This is a different shape of test from `test_fidelity_engine.py`:
- That file tests the engine against curated synthetic fixtures
  designed to exercise specific code paths.
- This file uses the engine on REAL ground-truth files
  (`ground_truth/planta_74/expected_model.json` shipped in v1) and
  asserts the round-trip property holds for them.

The point: if a future maintainer edits the engine and breaks a
metric in a subtle way, the curated tests might still pass; the
round-trip catches it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.fidelity.compare_generated_to_expected import (
    PT_TO_M_DEFAULT,
    compare,
)
from tools.fidelity.synth_from_expected import synthesize_observed

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_round_trip_planta_74_scores_one():
    expected_path = (REPO_ROOT / "ground_truth" / "planta_74"
                     / "expected_model.json")
    if not expected_path.exists():
        pytest.skip("planta_74 expected_model.json missing")
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    observed = synthesize_observed(expected, pt_to_m=PT_TO_M_DEFAULT)
    report = compare(expected=expected, observed=observed,
                     pt_to_m=PT_TO_M_DEFAULT)
    assert report["hard_fails"] == [], (
        f"round-trip should not produce hard_fails, got: "
        f"{report['hard_fails']}"
    )
    # global == 1.0 exact (synth picks mid-range areas, edges all
    # present, counts exact, bbox exact)
    assert report["global_fidelity"] == 1.0, (
        f"round-trip global_fidelity should be 1.0 exactly, got "
        f"{report['global_fidelity']}; sub_scores={report['sub_scores']}"
    )


def test_round_trip_preserves_room_label_match():
    expected_path = (REPO_ROOT / "ground_truth" / "planta_74"
                     / "expected_model.json")
    if not expected_path.exists():
        pytest.skip("planta_74 expected_model.json missing")
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    observed = synthesize_observed(expected, pt_to_m=PT_TO_M_DEFAULT)
    report = compare(expected=expected, observed=observed,
                     pt_to_m=PT_TO_M_DEFAULT)
    assert report["metrics"]["rooms"]["label_match_ratio"] == 1.0
    assert (report["metrics"]["rooms"]["matched_rooms"]
            == report["metrics"]["rooms"]["expected_rooms"])


def test_round_trip_preserves_adjacency_f1():
    expected_path = (REPO_ROOT / "ground_truth" / "planta_74"
                     / "expected_model.json")
    if not expected_path.exists():
        pytest.skip("planta_74 expected_model.json missing")
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    if not expected.get("adjacency"):
        pytest.skip("expected_model has no adjacency edges to round-trip")
    observed = synthesize_observed(expected, pt_to_m=PT_TO_M_DEFAULT)
    report = compare(expected=expected, observed=observed,
                     pt_to_m=PT_TO_M_DEFAULT)
    assert report["metrics"]["adjacency"]["f1"] == 1.0


def test_round_trip_synthetic_minimal_fixture():
    """Pure-fixture round trip — does NOT depend on planta_74 files
    being present. CI on a stripped branch should still run this."""
    expected = {
        "schema_version": "1.0",
        "plan_id": "synth_min",
        "unit": "m",
        "global_bbox": {"width": 10.0, "height": 5.0, "tolerance_pct": 5},
        "expected_counts": {"rooms": 2, "openings": 1, "walls": 10,
                             "tolerance": {"rooms_delta": 0,
                                           "openings_delta": 0,
                                           "walls_delta": 6}},
        "rooms": [
            {"id": "a", "label": "ROOM A",
             "expected_area_m2_range": [8.0, 12.0],
             "manual_confidence": "high"},
            {"id": "b", "label": "ROOM B",
             "expected_area_m2_range": [4.0, 6.0],
             "manual_confidence": "high"},
        ],
        "openings": [
            {"id": "d", "kind": "interior_door",
             "connects": ["a", "b"], "manual_confidence": "high"},
        ],
        "adjacency": [
            {"a": "a", "b": "b", "via": "d",
             "kind": "interior_door", "manual_confidence": "high"},
        ],
    }
    observed = synthesize_observed(expected, pt_to_m=PT_TO_M_DEFAULT)
    report = compare(expected=expected, observed=observed,
                     pt_to_m=PT_TO_M_DEFAULT)
    assert report["hard_fails"] == [], report["hard_fails"]
    assert report["global_fidelity"] == 1.0
