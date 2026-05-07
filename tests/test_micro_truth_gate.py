"""Tests for tools.micro_truth_gate — Stage 1.5 Micro Ground Truth.

Stage 1.5 boundary: gate audits ONE room against a manual GT and
emits micro_truth_report.json. NO mutation, NO Ruby/SU, NO LLM, NO
auto-correction. Default exit 0; --strict opt-in.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.micro_truth_gate import (
    GROUND_TRUTH_SCHEMA_VERSION,
    PT_TO_M_DEFAULT,
    REPORT_SCHEMA_VERSION,
    _audit_one_room,
    _detect_duplicate_walls,
    _detect_floating_openings,
    _detect_invalid_room_polygons,
    _polygon_area_pt2,
    _polygon_is_closed,
    build_micro_truth_report,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


# ---- Fixtures ----

def _square(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _consensus_with_sala_terraco() -> dict:
    """Toy consensus: SALA DE ESTAR + TERRACO SOCIAL with one
    glazed_balcony opening between them. Scaled so SALA ≈ 11 m².

    PT_TO_M = 0.19/5.4 ≈ 0.0352, so 1 m² ≈ 808 pt². A 90x100 pt
    rectangle = 9000 pt² ≈ 11.14 m² — sits comfortably in the
    [8, 25] m² range used by tests below.
    """
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "w000", "start": [0.0, 100.0],
             "end": [90.0, 100.0], "thickness": 5.4,
             "orientation": "h"},
        ],
        "rooms": [
            {"id": "r_sala", "name": "SALA DE ESTAR",
             "seed_pt": [45.0, 50.0],
             "polygon_pts": _square(0, 0, 90, 95)},
            {"id": "r_terr", "name": "TERRACO SOCIAL",
             "seed_pt": [45.0, 150.0],
             "polygon_pts": _square(0, 105, 90, 200)},
        ],
        "openings": [
            {"id": "g001", "wall_id": "w000",
             "center": [45.0, 100.0],
             "opening_width_pts": 60.0,
             "geometry_origin": "wall_gap",
             "kind_v5": "glazed_balcony",
             "decision": "clean", "confidence": 0.91,
             "evidence": {
                 "room_left": "SALA DE ESTAR",
                 "room_right": "TERRACO SOCIAL",
                 "width_m": 2.11,
                 "geometry_origin": "wall_gap",
             }},
        ],
        "soft_barriers": [],
    }


def _gt_sala_passing() -> dict:
    return {
        "schema_version": GROUND_TRUTH_SCHEMA_VERSION,
        "source_pdf": "test_fixture.pdf",
        "scope": "micro",
        "rooms": [
            {
                "label": "SALA DE ESTAR",
                "must_be_closed": True,
                "expected_area_m2_range": [8.0, 25.0],
                "expected_openings_count_range": [1, 5],
                "expected_adjacent_labels": ["TERRACO SOCIAL"],
                "allow_debug_openings": True,
            }
        ],
        "invariants": {
            "invalid_rooms": 0,
            "floating_openings": 0,
            "duplicate_walls": 0,
        },
    }


def _write(tmp_path: Path, name: str, data: dict) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---- Geometry helpers ----

def test_polygon_area_shoelace_unit_square():
    assert _polygon_area_pt2([[0, 0], [1, 0], [1, 1], [0, 1]]) == 1.0


def test_polygon_area_zero_for_two_pts():
    assert _polygon_area_pt2([[0, 0], [1, 1]]) == 0.0


def test_polygon_is_closed_min_three_distinct():
    assert _polygon_is_closed([[0, 0], [1, 0], [0, 1]]) is True
    assert _polygon_is_closed([[0, 0], [0, 0], [0, 0]]) is False
    assert _polygon_is_closed([[0, 0], [1, 1]]) is False


# ---- Schema versioning ----

def test_report_includes_schema_version_one_zero(tmp_path):
    c = _consensus_with_sala_terraco()
    cp = _write(tmp_path, "c.json", c)
    gt = _gt_sala_passing()
    gtp = _write(tmp_path, "gt.json", gt)
    r = build_micro_truth_report(c, cp, gt, gtp)
    assert r["schema_version"] == REPORT_SCHEMA_VERSION
    assert REPORT_SCHEMA_VERSION == "1.0"


def test_unsupported_gt_schema_raises(tmp_path):
    c = _consensus_with_sala_terraco()
    cp = _write(tmp_path, "c.json", c)
    gt = _gt_sala_passing()
    gt["schema_version"] = "9.9"
    gtp = _write(tmp_path, "gt.json", gt)
    with pytest.raises(ValueError, match="schema_version"):
        build_micro_truth_report(c, cp, gt, gtp)


# ---- Pass case ----

def test_pass_case_score_one(tmp_path):
    c = _consensus_with_sala_terraco()
    cp = _write(tmp_path, "c.json", c)
    gt = _gt_sala_passing()
    gtp = _write(tmp_path, "gt.json", gt)
    r = build_micro_truth_report(c, cp, gt, gtp)
    assert r["score"] == 1.0
    assert r["would_block_strict"] == []
    sala = r["rooms_audited"][0]
    assert sala["found"] is True
    assert sala["score"] == 1.0
    assert sala["matched_room_id"] == "r_sala"


# ---- Fail cases ----

def test_room_not_found_score_zero(tmp_path):
    c = _consensus_with_sala_terraco()
    c["rooms"] = [r for r in c["rooms"] if r["id"] != "r_sala"]
    cp = _write(tmp_path, "c.json", c)
    gt = _gt_sala_passing()
    gtp = _write(tmp_path, "gt.json", gt)
    r = build_micro_truth_report(c, cp, gt, gtp)
    sala = r["rooms_audited"][0]
    assert sala["found"] is False
    assert sala["score"] == 0.0
    assert any("room_not_found" in s for s in r["would_block_strict"])


def test_area_out_of_range_fails_check(tmp_path):
    c = _consensus_with_sala_terraco()
    cp = _write(tmp_path, "c.json", c)
    gt = _gt_sala_passing()
    gt["rooms"][0]["expected_area_m2_range"] = [50.0, 60.0]  # impossible
    gtp = _write(tmp_path, "gt.json", gt)
    r = build_micro_truth_report(c, cp, gt, gtp)
    sala = r["rooms_audited"][0]
    assert sala["checks"]["area_in_range"]["pass"] is False
    assert sala["score"] < 1.0


def test_openings_count_out_of_range_fails(tmp_path):
    c = _consensus_with_sala_terraco()
    cp = _write(tmp_path, "c.json", c)
    gt = _gt_sala_passing()
    gt["rooms"][0]["expected_openings_count_range"] = [5, 10]
    gtp = _write(tmp_path, "gt.json", gt)
    r = build_micro_truth_report(c, cp, gt, gtp)
    sala = r["rooms_audited"][0]
    assert sala["checks"]["openings_count_in_range"]["pass"] is False


def test_missing_required_adjacent_label_fails(tmp_path):
    c = _consensus_with_sala_terraco()
    cp = _write(tmp_path, "c.json", c)
    gt = _gt_sala_passing()
    gt["rooms"][0]["expected_adjacent_labels"] = ["COZINHA"]
    gtp = _write(tmp_path, "gt.json", gt)
    r = build_micro_truth_report(c, cp, gt, gtp)
    sala = r["rooms_audited"][0]
    assert sala["checks"]["adjacents_present"]["pass"] is False
    assert "COZINHA" in sala["checks"]["adjacents_present"]["missing"]


def test_invariant_floating_opening_fails(tmp_path):
    c = _consensus_with_sala_terraco()
    c["openings"][0]["wall_id"] = "w_does_not_exist"
    cp = _write(tmp_path, "c.json", c)
    gt = _gt_sala_passing()
    gtp = _write(tmp_path, "gt.json", gt)
    r = build_micro_truth_report(c, cp, gt, gtp)
    assert r["invariants"]["floating_openings"]["pass"] is False
    assert "floating_opening_present" in r["would_block_strict"]


def test_invariant_invalid_room_polygon_fails(tmp_path):
    c = _consensus_with_sala_terraco()
    c["rooms"][1]["polygon_pts"] = [[0, 0]]   # degenerate
    cp = _write(tmp_path, "c.json", c)
    gt = _gt_sala_passing()
    gtp = _write(tmp_path, "gt.json", gt)
    r = build_micro_truth_report(c, cp, gt, gtp)
    assert r["invariants"]["invalid_rooms"]["pass"] is False
    assert "invalid_room_present" in r["would_block_strict"]


# ---- Score reduction is monotonic ----

def test_partial_pass_score_below_one(tmp_path):
    """A room with one failing check should score < 1."""
    c = _consensus_with_sala_terraco()
    cp = _write(tmp_path, "c.json", c)
    gt = _gt_sala_passing()
    gt["rooms"][0]["expected_adjacent_labels"] = ["COZINHA", "TERRACO SOCIAL"]
    gtp = _write(tmp_path, "gt.json", gt)
    r = build_micro_truth_report(c, cp, gt, gtp)
    sala = r["rooms_audited"][0]
    # 4 of 5 checks pass (label, closed, area, count) — adjacents fails
    assert 0 < sala["score"] < 1.0


# ---- CLI exit codes ----

def test_cli_default_exits_zero_on_pass(tmp_path):
    c = _consensus_with_sala_terraco()
    cp = _write(tmp_path, "c.json", c)
    gt = _gt_sala_passing()
    gtp = _write(tmp_path, "gt.json", gt)
    r = subprocess.run(
        [PYTHON, "-m", "tools.micro_truth_gate", str(cp),
         "--ground-truth", str(gtp), "--out",
         str(tmp_path / "report.json")],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "report.json").exists()


def test_cli_default_exits_zero_on_fail(tmp_path):
    """Default mode is non-blocking: fail conditions still exit 0."""
    c = _consensus_with_sala_terraco()
    c["rooms"] = [r for r in c["rooms"] if r["id"] != "r_sala"]
    cp = _write(tmp_path, "c.json", c)
    gt = _gt_sala_passing()
    gtp = _write(tmp_path, "gt.json", gt)
    r = subprocess.run(
        [PYTHON, "-m", "tools.micro_truth_gate", str(cp),
         "--ground-truth", str(gtp), "--out",
         str(tmp_path / "report.json")],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "report.json").exists()


def test_cli_strict_exits_nonzero_when_room_missing(tmp_path):
    c = _consensus_with_sala_terraco()
    c["rooms"] = [r for r in c["rooms"] if r["id"] != "r_sala"]
    cp = _write(tmp_path, "c.json", c)
    gt = _gt_sala_passing()
    gtp = _write(tmp_path, "gt.json", gt)
    r = subprocess.run(
        [PYTHON, "-m", "tools.micro_truth_gate", str(cp),
         "--ground-truth", str(gtp), "--strict", "--out",
         str(tmp_path / "report.json")],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert r.returncode != 0, (
        f"strict should fail; stdout={r.stdout} stderr={r.stderr}"
    )


def test_cli_strict_exits_zero_on_full_pass(tmp_path):
    c = _consensus_with_sala_terraco()
    cp = _write(tmp_path, "c.json", c)
    gt = _gt_sala_passing()
    gtp = _write(tmp_path, "gt.json", gt)
    r = subprocess.run(
        [PYTHON, "-m", "tools.micro_truth_gate", str(cp),
         "--ground-truth", str(gtp), "--strict", "--out",
         str(tmp_path / "report.json")],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, r.stderr


# ---- Stage 1.5 boundary ----

def test_audit_does_not_mutate_consensus(tmp_path):
    c = _consensus_with_sala_terraco()
    cp = _write(tmp_path, "c.json", c)
    gt = _gt_sala_passing()
    gtp = _write(tmp_path, "gt.json", gt)
    snapshot_before = json.dumps(c, sort_keys=True)
    build_micro_truth_report(c, cp, gt, gtp)
    snapshot_after = json.dumps(c, sort_keys=True)
    assert snapshot_before == snapshot_after


def test_audit_does_not_invoke_subprocess_or_network(monkeypatch,
                                                       tmp_path):
    import subprocess as _sp
    import urllib.request as _ur
    def boom(*a, **kw):
        raise AssertionError("Stage 1.5 must not invoke subprocess")
    def boom_url(*a, **kw):
        raise AssertionError("Stage 1.5 must not call out to network")
    monkeypatch.setattr(_sp, "run", boom)
    monkeypatch.setattr(_sp, "Popen", boom)
    monkeypatch.setattr(_ur, "urlopen", boom_url)
    c = _consensus_with_sala_terraco()
    cp = _write(tmp_path, "c.json", c)
    gt = _gt_sala_passing()
    gtp = _write(tmp_path, "gt.json", gt)
    build_micro_truth_report(c, cp, gt, gtp)


# ---- Real planta_74 sanity ----

def test_real_planta_74_micro_passes(tmp_path):
    """Read the canonical ground_truth/planta_74_micro.json and the
    last classifier output. If the pipeline is healthy, score >= 0.8
    across the four asserted rooms. Skipped when artifacts are
    missing (CI on a stripped branch)."""
    canonical_run = (REPO_ROOT
                     / "runs/feature_room_context_2026_05_06"
                     / "consensus_with_room_context.json")
    canonical_gt = REPO_ROOT / "ground_truth" / "planta_74_micro.json"
    if not canonical_run.exists() or not canonical_gt.exists():
        pytest.skip("planta_74 artifacts missing")
    consensus = json.loads(canonical_run.read_text(encoding="utf-8"))
    gt = json.loads(canonical_gt.read_text(encoding="utf-8"))
    r = build_micro_truth_report(consensus, canonical_run, gt, canonical_gt)
    audited_labels = {room["label"] for room in r["rooms_audited"]}
    assert audited_labels == {"SALA DE ESTAR", "SUITE 02",
                              "BANHO 02", "COZINHA"}, audited_labels
    assert r["score"] >= 0.8, r
