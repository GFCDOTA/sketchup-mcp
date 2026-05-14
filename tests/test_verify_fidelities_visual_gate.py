"""Unit tests for the Visual Fidelity Gate (2026-05-14) added to
`tools/verify_fidelities.py`.

Covers:
- Backward compatibility — without `--require-visual-evidence` the
  function is byte-equivalent to the prior contract.
- Gate behavior — with the flag, missing/incomplete artifacts FORCE
  top-level FAIL while preserving the per-axis verdicts.
- Report fields — `policy_violation`, `policy_reason`,
  `visual_evidence_required`, `visual_evidence_status`,
  `missing_visual_artifacts`, `visual_evidence.per_artifact`,
  `verdict_top_level_pre_visual_gate`.
- CLI integration — the flag wires through; --visual-evidence-dir
  defaults to the parent of --consensus-after when not specified.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.verify_fidelities import (
    REQUIRED_VISUAL_ARTIFACTS,
    VISUAL_FIDELITY_POLICY_VIOLATION_TAG,
    _check_visual_evidence,
    verify_fidelities,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _passing_consensus() -> dict:
    """Minimal consensus where every per-axis verdict naturally passes.

    `wall_fidelity` has a planta_74-specific check that hardcodes
    `h_o005` as a required `human_annotation` opening with
    `cut_into_wall` host mode (see `tools/verify_fidelities.py`
    `_wall_fidelity`). Replicate that opening here so the fixture
    yields PASS across all four axes; the visual gate's behavior
    can then be observed independently of any axis FAIL.
    """
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "walls": [
            # Horizontal wall at y=50, x range 0..100. Its filled
            # bbox is [0, 47.3, 100, 52.7] given thickness=5.4 →
            # the h_o005 center below lies inside it ⇒ cut_into_wall.
            {"id": "w0", "start": [0, 50], "end": [100, 50],
             "thickness": 5.4, "orientation": "h"},
        ],
        "rooms": [
            {"id": "r0", "name": "SALA",
             "polygon_pts": [[0, 0], [50, 0], [50, 50], [0, 50]],
             "area_pts2": 2500.0, "seed_pt": [25, 25]},
        ],
        "openings": [
            {"id": "h_o005",
             "geometry_origin": "human_annotation",
             "kind_v5": "interior_door",
             "center": [50.0, 50.0],
             "opening_width_pts": 10.0,
             "orientation": "h",
             "human_annotation": {
                 "bbox_pts": [45.0, 47.0, 55.0, 53.0],
             }},
        ],
        "soft_barriers": [],
    }


def _passing_candidates() -> dict:
    """Minimal candidates report — no pairs need painting."""
    return {
        "schema_version": "1.0",
        "n_merged_cells": 0,
        "n_pairs": 0,
        "by_candidate_type": {},
        "n_should_user_paint": 0,
        "n_should_not_paint": 0,
        "n_downgraded_by_existing_human_wall": 0,
        "candidates": [],
    }


def _labels_one_room() -> list[dict]:
    return [{"name": "SALA", "seed_pt": [25, 25]}]


def _write_artifact(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _write_all_artifacts(directory: Path) -> None:
    for _key, fname in REQUIRED_VISUAL_ARTIFACTS:
        _write_artifact(directory / fname)


# ---------------------------------------------------------------------------
# Backward compatibility (no flag set)
# ---------------------------------------------------------------------------

def test_backward_compatible_when_flag_not_set():
    """Without the flag the report has no `visual_evidence_*` fields."""
    report = verify_fidelities(
        _passing_consensus(), _passing_candidates(),
        labels=_labels_one_room(),
        operator_confirmed_visual=True,
    )
    assert "visual_evidence_required" not in report
    assert "visual_evidence_status" not in report
    assert "policy_violation" not in report
    assert "missing_visual_artifacts" not in report
    assert "verdict_top_level_pre_visual_gate" not in report


def test_backward_compatible_top_level_unchanged_when_flag_off():
    """Worst-axis verdict (PASS here) survives without the flag."""
    report = verify_fidelities(
        _passing_consensus(), _passing_candidates(),
        labels=_labels_one_room(),
        operator_confirmed_visual=True,
    )
    assert report["verdict_top_level"] == "PASS"


# ---------------------------------------------------------------------------
# Gate behavior with --require-visual-evidence
# ---------------------------------------------------------------------------

def test_gate_forces_fail_when_no_evidence_dir_supplied():
    """All 7 artifacts missing → top-level FAIL."""
    report = verify_fidelities(
        _passing_consensus(), _passing_candidates(),
        labels=_labels_one_room(),
        operator_confirmed_visual=True,
        require_visual_evidence=True,
        visual_evidence_dir=None,
    )
    assert report["verdict_top_level"] == "FAIL"
    assert report["policy_violation"] == VISUAL_FIDELITY_POLICY_VIOLATION_TAG
    assert report["visual_evidence_required"] is True
    assert report["visual_evidence_status"] == "missing"
    assert set(report["missing_visual_artifacts"]) == {
        k for k, _ in REQUIRED_VISUAL_ARTIFACTS
    }


def test_gate_preserves_per_axis_verdicts(tmp_path: Path):
    """Top-level is downgraded; the 4 axes keep their natural verdicts."""
    report = verify_fidelities(
        _passing_consensus(), _passing_candidates(),
        labels=_labels_one_room(),
        operator_confirmed_visual=True,
        require_visual_evidence=True,
        visual_evidence_dir=tmp_path,
    )
    assert report["verdict_top_level"] == "FAIL"
    # Per-axis verdicts must survive the downgrade.
    for axis in ("wall_fidelity", "soft_barrier_fidelity",
                 "semantic_room_fidelity", "global_visual_fidelity"):
        assert report["fidelities"][axis]["verdict"] == "PASS"
    # The pre-gate worst-axis value is captured for inspection.
    assert report["verdict_top_level_pre_visual_gate"] == "PASS"


def test_gate_status_incomplete_when_some_artifacts_present(tmp_path: Path):
    """Some artifacts present → status incomplete, still FAIL."""
    # Drop 3 of the 7 artifacts in place.
    _write_artifact(tmp_path / "original_floorplan.png")
    _write_artifact(tmp_path / "skp_render.png")
    _write_artifact(tmp_path / "overlay_pdf_skp.png")
    report = verify_fidelities(
        _passing_consensus(), _passing_candidates(),
        labels=_labels_one_room(),
        operator_confirmed_visual=True,
        require_visual_evidence=True,
        visual_evidence_dir=tmp_path,
    )
    assert report["visual_evidence_status"] == "incomplete"
    assert report["verdict_top_level"] == "FAIL"
    # The 4 still-missing artifacts are listed by key.
    assert set(report["missing_visual_artifacts"]) == {
        "diff_walls", "diff_doors", "diff_rooms", "mismatches_list",
    }


def test_gate_passes_when_all_seven_artifacts_present(tmp_path: Path):
    """Top-level clears the gate when all 7 artifacts exist + non-empty."""
    _write_all_artifacts(tmp_path)
    report = verify_fidelities(
        _passing_consensus(), _passing_candidates(),
        labels=_labels_one_room(),
        operator_confirmed_visual=True,
        require_visual_evidence=True,
        visual_evidence_dir=tmp_path,
    )
    assert report["visual_evidence_required"] is True
    assert report["visual_evidence_status"] == "present"
    # Top-level reverts to the per-axis worst (PASS in this fixture).
    assert report["verdict_top_level"] == "PASS"
    assert "policy_violation" not in report
    # `verdict_top_level_pre_visual_gate` is only set when gate triggers.
    assert "verdict_top_level_pre_visual_gate" not in report


def test_gate_zero_byte_artifact_counts_as_missing(tmp_path: Path):
    """A 0-byte file at the expected path is treated as missing."""
    for _key, fname in REQUIRED_VISUAL_ARTIFACTS:
        (tmp_path / fname).write_bytes(b"")
    report = verify_fidelities(
        _passing_consensus(), _passing_candidates(),
        labels=_labels_one_room(),
        operator_confirmed_visual=True,
        require_visual_evidence=True,
        visual_evidence_dir=tmp_path,
    )
    assert report["visual_evidence_status"] == "missing"
    assert report["verdict_top_level"] == "FAIL"


def test_gate_uses_canonical_filenames_in_per_artifact(tmp_path: Path):
    """Per-artifact list resolves the canonical filename relative to dir."""
    _write_artifact(tmp_path / "original_floorplan.png")
    report = verify_fidelities(
        _passing_consensus(), _passing_candidates(),
        labels=_labels_one_room(),
        require_visual_evidence=True,
        visual_evidence_dir=tmp_path,
    )
    per_artifact = report["visual_evidence"]["per_artifact"]
    present = [a for a in per_artifact if a["status"] == "present"]
    assert len(present) == 1
    assert present[0]["key"] == "original_floorplan"
    assert present[0]["expected_path"].endswith("original_floorplan.png")


def test_required_artifacts_count_is_seven():
    """Schema lock — the protocol defines exactly seven artifacts."""
    assert len(REQUIRED_VISUAL_ARTIFACTS) == 7


def test_required_artifacts_keys_match_protocol_doc():
    """Keys must match the names referenced in CLAUDE.md §10 and
    docs/protocols/visual_fidelity_gate_protocol.md."""
    actual = {k for k, _ in REQUIRED_VISUAL_ARTIFACTS}
    expected = {
        "original_floorplan",
        "skp_render",
        "overlay_pdf_skp",
        "diff_walls",
        "diff_doors",
        "diff_rooms",
        "mismatches_list",
    }
    assert actual == expected


def test_check_visual_evidence_directory_field_resolves(tmp_path: Path):
    """The `directory` field on the evidence report is the supplied dir."""
    res = _check_visual_evidence(tmp_path)
    assert res["directory"] == str(tmp_path)


def test_check_visual_evidence_directory_none_when_dir_missing():
    """When no dir is supplied, evidence.directory is null."""
    res = _check_visual_evidence(None)
    assert res["directory"] is None
    assert res["status"] == "missing"
    assert len(res["missing"]) == 7


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

def _materialise_cli_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    consensus_path = tmp_path / "consensus.json"
    consensus_path.write_text(json.dumps(_passing_consensus()),
                              encoding="utf-8")
    candidates_path = tmp_path / "candidates.json"
    candidates_path.write_text(json.dumps(_passing_candidates()),
                                encoding="utf-8")
    labels_path = tmp_path / "labels.json"
    labels_path.write_text(json.dumps(_labels_one_room()),
                            encoding="utf-8")
    return consensus_path, candidates_path, labels_path


def test_cli_without_flag_omits_visual_evidence_fields(tmp_path: Path):
    consensus_path, candidates_path, labels_path = _materialise_cli_inputs(
        tmp_path)
    out_path = tmp_path / "report.json"
    res = subprocess.run(
        [sys.executable, "-m", "tools.verify_fidelities",
         "--consensus-after", str(consensus_path),
         "--candidates", str(candidates_path),
         "--labels", str(labels_path),
         "--operator-confirmed-visual",
         "--out", str(out_path)],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["verdict_top_level"] == "PASS"
    assert "policy_violation" not in report
    assert "visual_evidence_required" not in report


def test_cli_require_flag_defaults_dir_to_consensus_parent(tmp_path: Path):
    consensus_path, candidates_path, labels_path = _materialise_cli_inputs(
        tmp_path)
    out_path = tmp_path / "report.json"
    res = subprocess.run(
        [sys.executable, "-m", "tools.verify_fidelities",
         "--consensus-after", str(consensus_path),
         "--candidates", str(candidates_path),
         "--labels", str(labels_path),
         "--operator-confirmed-visual",
         "--require-visual-evidence",
         "--out", str(out_path)],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    )
    # Top-level FAIL because tmp_path doesn't have the 7 artifacts;
    # strict not set, so exit 0.
    assert res.returncode == 0, res.stderr
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["verdict_top_level"] == "FAIL"
    assert report["policy_violation"] == VISUAL_FIDELITY_POLICY_VIOLATION_TAG
    assert (
        report["visual_evidence"]["directory"]
        == str(consensus_path.parent)
    )


def test_cli_require_flag_with_explicit_visual_evidence_dir(tmp_path: Path):
    consensus_path, candidates_path, labels_path = _materialise_cli_inputs(
        tmp_path)
    artifact_dir = tmp_path / "artifacts"
    _write_all_artifacts(artifact_dir)
    out_path = tmp_path / "report.json"
    res = subprocess.run(
        [sys.executable, "-m", "tools.verify_fidelities",
         "--consensus-after", str(consensus_path),
         "--candidates", str(candidates_path),
         "--labels", str(labels_path),
         "--operator-confirmed-visual",
         "--require-visual-evidence",
         "--visual-evidence-dir", str(artifact_dir),
         "--out", str(out_path)],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["verdict_top_level"] == "PASS"
    assert report["visual_evidence_status"] == "present"
    assert "policy_violation" not in report


def test_cli_strict_exits_2_on_visual_gate_fail(tmp_path: Path):
    consensus_path, candidates_path, labels_path = _materialise_cli_inputs(
        tmp_path)
    out_path = tmp_path / "report.json"
    res = subprocess.run(
        [sys.executable, "-m", "tools.verify_fidelities",
         "--consensus-after", str(consensus_path),
         "--candidates", str(candidates_path),
         "--labels", str(labels_path),
         "--operator-confirmed-visual",
         "--require-visual-evidence",
         "--strict",
         "--out", str(out_path)],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    )
    # Strict → FAIL → exit 2.
    assert res.returncode == 2, res.stderr
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["verdict_top_level"] == "FAIL"
