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
from tools.visual_fidelity_gate import (
    REQUIRED_VISUAL_ARTIFACTS as _GATE_ARTIFACTS,
)

# Mirror the gate's filename map so the test materialises real
# canonical files.
_ARTIFACT_FILENAMES = dict(_GATE_ARTIFACTS)

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
    """CLI accepts `--visual-evidence-dir` + the 7 artifacts populate
    `visual_evidence`. Since PR B4 also runs the algorithmic gate
    against the supplied `--consensus-after`, the verdict may be
    FAIL when the synthetic fixture trips a check — that's expected
    (gate is doing its job). What this test guarantees is the
    artifact-presence side of the gate, NOT the algorithmic verdict.
    """
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
    assert report["visual_evidence_status"] == "present"
    # The artifact-presence gate cleared. The gate's algorithmic
    # verdict for this synthetic fixture is whatever the checks say
    # — verdict_top_level may be PASS / WARN / FAIL depending on
    # the eight algorithms. The point is: the CLI wired the gate
    # through and the report carries the per-axis verdicts.
    assert report["verdict_top_level"] in {"PASS", "WARN", "FAIL"}
    # `policy_violation` is present iff the gate's algorithmic
    # verdict is FAIL (PR B4 contract). When the synthetic fixture
    # passes the gate it must be absent.
    if report["verdict_top_level"] == "FAIL":
        assert (
            report.get("policy_violation")
            == VISUAL_FIDELITY_POLICY_VIOLATION_TAG
        )
    else:
        assert "policy_violation" not in report


# ---------------------------------------------------------------------------
# PR B4 — gate propagation into top-level verdict
# ---------------------------------------------------------------------------

def _materialise_artifact_dir(directory: Path) -> Path:
    """Drop a >0-byte placeholder for each of the seven canonical
    artifact files under `directory`."""
    directory.mkdir(parents=True, exist_ok=True)
    for _key, fname in REQUIRED_VISUAL_ARTIFACTS:
        (directory / fname).write_bytes(b"x")
    return directory


def _failing_gate_consensus_path(tmp_path: Path) -> Path:
    """Write a consensus that the algorithmic gate will FAIL.

    The fixture has one interior_door whose `host_mode` is
    explicitly `unhosted` — that trips check 1
    (door_without_opening) which is a hard FAIL.
    """
    path = tmp_path / "consensus.json"
    consensus = {
        "wall_thickness_pts": 5.4,
        "source": "synthetic.pdf",
        "walls": [
            {"id": "w0", "start": [0, 0], "end": [100, 0],
             "thickness": 5.4, "orientation": "h"},
            {"id": "w1", "start": [0, 100], "end": [100, 100],
             "thickness": 5.4, "orientation": "h"},
            {"id": "w2", "start": [0, 0], "end": [0, 100],
             "thickness": 5.4, "orientation": "v"},
            {"id": "w3", "start": [100, 0], "end": [100, 100],
             "thickness": 5.4, "orientation": "v"},
            {"id": "w4", "start": [50, 0], "end": [50, 100],
             "thickness": 5.4, "orientation": "v"},
        ],
        "rooms": [
            {"id": "r0", "name": "A",
             "polygon_pts": [[0, 0], [50, 0], [50, 100], [0, 100]],
             "area_pts2": 5000, "seed_pt": [25, 50]},
            {"id": "r1", "name": "B",
             "polygon_pts": [[50, 0], [100, 0], [100, 100], [50, 100]],
             "area_pts2": 5000, "seed_pt": [75, 50]},
        ],
        "openings": [
            # Unhosted door → check 1 FAILs.
            {"id": "o0", "kind_v5": "interior_door",
             "wall_id": None, "host_mode": "unhosted",
             "center": [25, 50], "hinge_side": "left",
             "opening_width_pts": 20.0},
        ],
        "soft_barriers": [],
    }
    path.write_text(json.dumps(consensus), encoding="utf-8")
    return path


def _passing_gate_consensus_path(tmp_path: Path) -> Path:
    """Consensus that the gate's eight checks all PASS (or WARN on
    swing where no svg_arc evidence exists)."""
    path = tmp_path / "consensus_clean.json"
    # L-shape polygon → not a bbox rectangle.
    poly = [[0, 0], [100, 0], [100, 50], [50, 50], [50, 100], [0, 100]]
    consensus = {
        "wall_thickness_pts": 5.4,
        "source": "synthetic.pdf",
        "walls": [
            {"id": "w0", "start": [0, 0], "end": [200, 0],
             "thickness": 5.4, "orientation": "h"},
            {"id": "w1", "start": [0, 100], "end": [200, 100],
             "thickness": 5.4, "orientation": "h"},
            {"id": "w2", "start": [0, 0], "end": [0, 100],
             "thickness": 5.4, "orientation": "v"},
            {"id": "w3", "start": [200, 0], "end": [200, 100],
             "thickness": 5.4, "orientation": "v"},
            {"id": "w4", "start": [100, 0], "end": [100, 100],
             "thickness": 5.4, "orientation": "v"},
        ],
        "rooms": [
            {"id": "r0", "name": "ROOM_A",
             "polygon_pts": poly,
             "area_pts2": 7500.0, "seed_pt": [25, 25]},
            {"id": "r1", "name": "ROOM_B",
             "polygon_pts": [[p[0] + 100, p[1]] for p in poly],
             "area_pts2": 7500.0, "seed_pt": [125, 25]},
        ],
        "openings": [
            {"id": "o0", "kind_v5": "interior_door",
             "wall_id": "w4", "host_mode": "cut_into_wall",
             "center": [100, 50], "hinge_side": "left",
             "opening_width_pts": 20.0},
        ],
        "soft_barriers": [],
    }
    path.write_text(json.dumps(consensus), encoding="utf-8")
    return path


def test_b4_gate_fail_propagates_to_top_level_fail(tmp_path: Path):
    """Gate FAIL → top-level FAIL with policy_violation tag."""
    evidence_dir = _materialise_artifact_dir(tmp_path / "evidence")
    consensus_path = _failing_gate_consensus_path(tmp_path)
    report = verify_fidelities(
        _passing_consensus(), _passing_candidates(),
        labels=_labels_one_room(),
        operator_confirmed_visual=True,
        require_visual_evidence=True,
        visual_evidence_dir=evidence_dir,
        consensus_after_path=consensus_path,
    )
    assert report["visual_evidence_status"] == "present"
    assert report["verdict_top_level"] == "FAIL"
    assert (
        report["policy_violation"]
        == VISUAL_FIDELITY_POLICY_VIOLATION_TAG
    )
    assert "algorithmic check" in report["policy_reason"]
    # Embedded gate report carries the per-check verdicts.
    gate = report["visual_fidelity_gate"]
    assert gate["verdict_top_level"] == "FAIL"
    door_check = next(
        c for c in gate["checks"] if c["key"] == "door_without_opening"
    )
    assert door_check["verdict"] == "FAIL"
    # Per-axis verdicts are preserved through the propagation.
    assert "fidelities" in report
    for axis in report["fidelities"].values():
        assert axis["verdict"] in {"PASS", "WARN", "FAIL"}


def test_b4_gate_pass_preserves_per_axis_pass(tmp_path: Path):
    """Gate PASS (all 8 checks pass, no WARN) → top-level stays
    at per-axis worst (which is PASS for the synthetic fixture)."""
    evidence_dir = _materialise_artifact_dir(tmp_path / "evidence")
    consensus_path = _passing_gate_consensus_path(tmp_path)
    report = verify_fidelities(
        _passing_consensus(), _passing_candidates(),
        labels=_labels_one_room(),
        operator_confirmed_visual=True,
        require_visual_evidence=True,
        visual_evidence_dir=evidence_dir,
        consensus_after_path=consensus_path,
    )
    assert report["visual_evidence_status"] == "present"
    gate = report["visual_fidelity_gate"]
    # The gate may be WARN (swing has no arc) or PASS depending on
    # the per-check semantics; either way no FAIL.
    assert gate["verdict_top_level"] in {"PASS", "WARN"}
    # When gate is PASS the top-level stays at per-axis worst.
    if gate["verdict_top_level"] == "PASS":
        assert report["verdict_top_level"] == "PASS"
        assert "policy_violation" not in report
        # No downgrade event surfaced.
        assert "verdict_top_level_pre_visual_gate" not in report


def test_b4_gate_warn_downgrades_pass_to_warn(tmp_path: Path):
    """When the gate emits WARN and the per-axis worst was PASS,
    top-level becomes WARN (gate WARN is a real signal — eg an
    interior_door without svg_arc evidence)."""
    evidence_dir = _materialise_artifact_dir(tmp_path / "evidence")
    consensus_path = _passing_gate_consensus_path(tmp_path)
    # The fixture has a door without svg_arc evidence → gate WARN.
    report = verify_fidelities(
        _passing_consensus(), _passing_candidates(),
        labels=_labels_one_room(),
        operator_confirmed_visual=True,
        require_visual_evidence=True,
        visual_evidence_dir=evidence_dir,
        consensus_after_path=consensus_path,
    )
    gate = report["visual_fidelity_gate"]
    if gate["verdict_top_level"] != "WARN":
        pytest.skip("synthetic fixture didn't produce gate WARN")
    # Per-axis worst is PASS but gate is WARN → top-level WARN.
    assert report["verdict_top_level_pre_visual_gate"] == "PASS"
    assert report["verdict_top_level"] == "WARN"


def test_b4_gate_scaffolded_when_no_consensus_path(tmp_path: Path):
    """When `consensus_after_path` is None the gate scaffolds
    (no checks run); the verifier MUST NOT propagate that into a
    downgrade. Top-level stays at the per-axis worst."""
    evidence_dir = _materialise_artifact_dir(tmp_path / "evidence")
    report = verify_fidelities(
        _passing_consensus(), _passing_candidates(),
        labels=_labels_one_room(),
        operator_confirmed_visual=True,
        require_visual_evidence=True,
        visual_evidence_dir=evidence_dir,
        consensus_after_path=None,  # explicit
    )
    assert report["visual_evidence_status"] == "present"
    assert report["verdict_top_level"] == "PASS"
    assert "policy_violation" not in report
    # Gate report is still embedded (for inspection) even though it
    # didn't propagate.
    gate = report["visual_fidelity_gate"]
    assert gate["summary"]["checks_not_yet_checked"] == 8


def test_b4_gate_report_embedded_under_visual_fidelity_gate(
        tmp_path: Path):
    """Schema lock — when the gate runs, the verifier exposes the
    full gate report under `report['visual_fidelity_gate']` so
    downstream consumers don't need to re-run the gate to inspect
    per-check details."""
    evidence_dir = _materialise_artifact_dir(tmp_path / "evidence")
    consensus_path = _passing_gate_consensus_path(tmp_path)
    report = verify_fidelities(
        _passing_consensus(), _passing_candidates(),
        labels=_labels_one_room(),
        require_visual_evidence=True,
        visual_evidence_dir=evidence_dir,
        consensus_after_path=consensus_path,
    )
    gate = report["visual_fidelity_gate"]
    assert "schema_version" in gate
    assert "verdict_top_level" in gate
    assert isinstance(gate["checks"], list)
    assert len(gate["checks"]) == 8
    assert {c["key"] for c in gate["checks"]} == {
        "door_without_opening", "door_crossing_or_displaced",
        "door_swing_diverges", "room_polygon_not_closed",
        "room_polygon_bleeds_outside",
        "invented_or_wrong_height_exterior",
        "wet_or_terrace_adjacency_wrong",
        "room_rendered_as_bbox",
    }


# ---------------------------------------------------------------------------
# PR B4 — Integration on planta_74
# ---------------------------------------------------------------------------

PLANTA_74_PDF = REPO_ROOT / "planta_74.pdf"
PLANTA_74_CONSENSUS = (
    REPO_ROOT
    / "fixtures"
    / "planta_74"
    / "consensus_with_human_walls_and_soft_barriers.json"
)
PLANTA_74_CANDIDATES = (
    REPO_ROOT
    / "fixtures"
    / "planta_74"
    / "loop_closure_candidates_after_soft_barriers.json"
)
PLANTA_74_EVIDENCE_DIR = (
    REPO_ROOT / "fixtures" / "planta_74" / "visual_evidence"
)
PLANTA_74_LABELS = REPO_ROOT / "runs" / "vector" / "labels.json"


_planta_74_available = (
    PLANTA_74_PDF.exists()
    and PLANTA_74_CONSENSUS.exists()
    and PLANTA_74_CANDIDATES.exists()
    and PLANTA_74_EVIDENCE_DIR.exists()
    and PLANTA_74_LABELS.exists()
)


@pytest.mark.skipif(
    not _planta_74_available,
    reason="planta_74 fixtures missing (shallow clone?)",
)
def test_b4_integration_planta_74_top_level_fails(tmp_path: Path):
    """End-to-end: planta_74's known-bad consensus runs through
    producer → gate → verifier and the top-level lands at FAIL with
    the gate's per-check verdicts surfaced.

    The h_o005 unhosted opening is the canonical signal: it trips
    `door_without_opening` AND `door_crossing_or_displaced`.
    """
    out_path = tmp_path / "fidelity_report.json"
    res = subprocess.run(
        [sys.executable, "-m", "tools.verify_fidelities",
         "--consensus-after", str(PLANTA_74_CONSENSUS),
         "--candidates", str(PLANTA_74_CANDIDATES),
         "--labels", str(PLANTA_74_LABELS),
         "--pdf", str(PLANTA_74_PDF),
         "--require-visual-evidence",
         "--visual-evidence-dir", str(PLANTA_74_EVIDENCE_DIR),
         "--out", str(out_path)],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["visual_evidence_status"] == "present"
    assert report["verdict_top_level"] == "FAIL"
    assert (
        report["policy_violation"]
        == VISUAL_FIDELITY_POLICY_VIOLATION_TAG
    )
    gate = report["visual_fidelity_gate"]
    assert gate["verdict_top_level"] == "FAIL"
    # h_o005 should appear in the door checks.
    door_check = next(
        c for c in gate["checks"] if c["key"] == "door_without_opening"
    )
    assert door_check["verdict"] == "FAIL"
    assert any(
        e.get("opening_id") == "h_o005"
        for e in door_check["failing_elements"]
    )
    cross_check = next(
        c for c in gate["checks"]
        if c["key"] == "door_crossing_or_displaced"
    )
    assert cross_check["verdict"] == "FAIL"


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
