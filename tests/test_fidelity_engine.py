"""Unit tests for tools.fidelity.compare_generated_to_expected.

Stage 1 / Ground Truth v1 boundary: no shapely IoU, no SU, no LLM.
Tests use synthetic observed + expected dicts so they execute fast
and don't depend on planta_74.pdf or any external artifact.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.fidelity.compare_generated_to_expected import (
    EXPECTED_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
    compare,
    render_scorecard,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

# PT_TO_M used by the engine. Sized to roughly match planta_74.
PT_TO_M = 0.03518518518518518


# ---- Fixtures ---------------------------------------------------------

def _square(x0: float, y0: float, x1: float, y1: float):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _observed_two_rooms() -> dict:
    """Toy observed consensus with SALA + COZINHA + 1 door between them.

    Areas calibrated so SALA = ~10 m^2, COZINHA = ~7 m^2.
    """
    # 10 m^2 ≈ 8082 pt^2; pick a 90 x 90 pt rectangle ≈ 8100 pt^2
    sala_pts = _square(0, 0, 90, 90)
    coz_pts = _square(95, 0, 175, 80)  # ~7 m^2
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
        ],
        "soft_barriers": [],
    }


def _expected_two_rooms_passing() -> dict:
    return {
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "plan_id": "test_fixture",
        "unit": "m",
        "global_bbox": {"width": 6.2, "height": 3.2, "tolerance_pct": 10},
        "expected_counts": {
            "rooms": 2, "openings": 1, "walls": 5,
            "tolerance": {"rooms_delta": 0, "openings_delta": 0, "walls_delta": 0},
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


def _write(tmp: Path, name: str, data: dict) -> Path:
    p = tmp / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---- Schema versioning ------------------------------------------------

def test_report_schema_version_is_1_0():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    r = compare(obs, exp, pt_to_m=PT_TO_M)
    assert r["schema_version"] == REPORT_SCHEMA_VERSION
    assert REPORT_SCHEMA_VERSION == "1.0"


def test_unsupported_expected_schema_raises():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    exp["schema_version"] = "9.9"
    with pytest.raises(ValueError, match="schema_version"):
        compare(obs, exp, pt_to_m=PT_TO_M)


# ---- Pass case --------------------------------------------------------

def test_pass_case_global_score_one():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    r = compare(obs, exp, pt_to_m=PT_TO_M)
    assert r["hard_fails"] == [], r["hard_fails"]
    assert r["global_fidelity"] == 1.0
    assert r["sub_scores"]["count_score"] == 1.0
    assert r["sub_scores"]["adjacency_score"] == 1.0
    assert r["metrics"]["rooms"]["label_match_ratio"] == 1.0


# ---- Counts -----------------------------------------------------------

def test_count_delta_room_count_drift_is_hard_fail():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    obs["rooms"] = obs["rooms"][:1]  # drop COZINHA
    r = compare(obs, exp, pt_to_m=PT_TO_M)
    assert any("rooms_count_delta" in hf for hf in r["hard_fails"])
    assert r["global_fidelity"] <= 0.69


def test_count_delta_opening_count_drift_is_warning_not_hard():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    exp["expected_counts"]["openings"] = 5
    exp["expected_counts"]["tolerance"]["openings_delta"] = 0
    r = compare(obs, exp, pt_to_m=PT_TO_M)
    assert any("openings_count_delta" in w for w in r["warnings"])
    # not in hard_fails
    assert not any("openings_count_delta" in hf for hf in r["hard_fails"])


# ---- Rooms ------------------------------------------------------------

def test_room_missing_high_conf_is_hard_fail():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    obs["rooms"] = [r for r in obs["rooms"] if r["name"] != "SALA DE ESTAR"]
    r = compare(obs, exp, pt_to_m=PT_TO_M)
    assert any("room_missing_high_conf" in hf for hf in r["hard_fails"])


def test_area_out_of_range_high_conf_is_hard_fail():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    obs["rooms"][0]["area_pts2"] = 80_000  # ~99 m^2
    r = compare(obs, exp, pt_to_m=PT_TO_M)
    assert any("area_in_range:SALA DE ESTAR" in hf
               for hf in r["hard_fails"])


def test_area_out_of_range_low_conf_is_warning_not_hard():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    exp["rooms"][0]["manual_confidence"] = "low"
    obs["rooms"][0]["area_pts2"] = 80_000
    r = compare(obs, exp, pt_to_m=PT_TO_M)
    assert any("area_in_range:SALA DE ESTAR" in w
               for w in r["warnings"])
    assert not any("area_in_range:SALA DE ESTAR" in hf
                   for hf in r["hard_fails"])


def test_label_match_ratio_below_70pct_is_hard_fail():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    # Add 2 more expected rooms so 2/4 found = 0.5 < 0.7
    exp["rooms"] += [
        {"id": "x", "label": "BANHEIRO",
         "expected_area_m2_range": [1.0, 5.0],
         "manual_confidence": "low"},
        {"id": "y", "label": "QUARTO",
         "expected_area_m2_range": [5.0, 20.0],
         "manual_confidence": "low"},
    ]
    r = compare(obs, exp, pt_to_m=PT_TO_M)
    assert any("label_match_ratio" in hf for hf in r["hard_fails"])


# ---- Adjacency --------------------------------------------------------

def test_adjacency_f1_perfect():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    r = compare(obs, exp, pt_to_m=PT_TO_M)
    assert r["metrics"]["adjacency"]["f1"] == 1.0
    assert r["metrics"]["adjacency"]["precision"] == 1.0
    assert r["metrics"]["adjacency"]["recall"] == 1.0


def test_adjacency_f1_below_60pct_is_hard_fail():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    # Add a phantom expected edge that has no opening in observed
    exp["rooms"].append({
        "id": "extra", "label": "QUARTO",
        "expected_area_m2_range": [5.0, 15.0],
        "manual_confidence": "low",
    })
    exp["adjacency"].append({"a": "sala", "b": "extra"})
    exp["adjacency"].append({"a": "coz", "b": "extra"})
    # 1 of 3 expected edges present → precision=1, recall=0.33,
    # f1 = 0.5 < 0.6
    r = compare(obs, exp, pt_to_m=PT_TO_M)
    assert any("adjacency_f1" in hf for hf in r["hard_fails"])


def test_adjacency_skipped_when_no_expected_edges():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    exp["adjacency"] = []
    r = compare(obs, exp, pt_to_m=PT_TO_M)
    assert "skipped" in r["metrics"]["adjacency"]


# ---- Hard-fail cap ----------------------------------------------------

def test_global_fidelity_capped_at_0_69_when_hard_fail():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    obs["rooms"][0]["area_pts2"] = 80_000
    r = compare(obs, exp, pt_to_m=PT_TO_M)
    assert r["hard_fails"], "test setup wrong: should have hard_fail"
    assert r["global_fidelity"] <= 0.69


def test_global_fidelity_not_capped_when_only_warnings():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    # Convert all rooms to low-confidence, then break one area
    for r_ in exp["rooms"]:
        r_["manual_confidence"] = "low"
    obs["rooms"][0]["area_pts2"] = 80_000
    r = compare(obs, exp, pt_to_m=PT_TO_M)
    assert r["hard_fails"] == [], r["hard_fails"]
    assert r["global_fidelity"] > 0.69


# ---- Bbox -------------------------------------------------------------

def test_bbox_drift_within_tolerance_passes():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    r = compare(obs, exp, pt_to_m=PT_TO_M)
    assert r["metrics"]["global_bbox"]["pass"] is True


def test_bbox_drift_outside_tolerance_warns():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    exp["global_bbox"]["width"] = 100.0  # absurd
    exp["global_bbox"]["tolerance_pct"] = 5
    r = compare(obs, exp, pt_to_m=PT_TO_M)
    assert r["metrics"]["global_bbox"]["pass"] is False


# ---- Scorecard --------------------------------------------------------

def test_scorecard_renders_markdown():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    r = compare(obs, exp, pt_to_m=PT_TO_M)
    md = render_scorecard(r)
    assert "Fidelity Scorecard" in md
    assert "global_fidelity" in md
    assert str(r["global_fidelity"]) in md


# ---- CLI --------------------------------------------------------------

def test_cli_default_exits_zero_on_pass(tmp_path):
    obs_p = _write(tmp_path, "obs.json", _observed_two_rooms())
    exp_p = _write(tmp_path, "exp.json", _expected_two_rooms_passing())
    out_p = tmp_path / "report.json"
    proc = subprocess.run(
        [PYTHON, "-m", "tools.fidelity.compare_generated_to_expected",
         str(obs_p), "--expected", str(exp_p), "--out", str(out_p)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_p.exists()


def test_cli_strict_exits_nonzero_on_hard_fail(tmp_path):
    obs = _observed_two_rooms()
    obs["rooms"][0]["area_pts2"] = 80_000
    obs_p = _write(tmp_path, "obs.json", obs)
    exp_p = _write(tmp_path, "exp.json", _expected_two_rooms_passing())
    out_p = tmp_path / "report.json"
    proc = subprocess.run(
        [PYTHON, "-m", "tools.fidelity.compare_generated_to_expected",
         str(obs_p), "--expected", str(exp_p), "--out", str(out_p),
         "--strict"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode != 0, proc.stdout


def test_cli_writes_scorecard_when_requested(tmp_path):
    obs_p = _write(tmp_path, "obs.json", _observed_two_rooms())
    exp_p = _write(tmp_path, "exp.json", _expected_two_rooms_passing())
    out_p = tmp_path / "report.json"
    sc_p = tmp_path / "scorecard.md"
    proc = subprocess.run(
        [PYTHON, "-m", "tools.fidelity.compare_generated_to_expected",
         str(obs_p), "--expected", str(exp_p), "--out", str(out_p),
         "--scorecard", str(sc_p)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert sc_p.exists()
    assert "Fidelity Scorecard" in sc_p.read_text(encoding="utf-8")


# ---- No-side-effect contract ------------------------------------------

def test_compare_does_not_mutate_inputs():
    obs = _observed_two_rooms()
    exp = _expected_two_rooms_passing()
    obs_before = json.dumps(obs, sort_keys=True)
    exp_before = json.dumps(exp, sort_keys=True)
    compare(obs, exp, pt_to_m=PT_TO_M)
    assert json.dumps(obs, sort_keys=True) == obs_before
    assert json.dumps(exp, sort_keys=True) == exp_before
