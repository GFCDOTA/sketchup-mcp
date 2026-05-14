"""Unit tests for `tools/visual_fidelity_gate.py` — PR B2 reader
scaffolding for the Visual Fidelity Gate Protocol (2026-05-14).

Covers:
- Schema lock: ``REQUIRED_VISUAL_ARTIFACTS`` and ``EIGHT_CHECKS``
  match the verify_fidelities + produce_visual_evidence modules.
- ``load_artifacts``: status `present` / `incomplete` / `missing`
  + correct per-artifact entries.
- ``run_gate``:
  * scaffolds the 8 checks with `not_yet_checked` status.
  * verdict FAIL when artifacts missing (with policy_violation tag).
  * verdict WARN when artifacts present + checks not yet implemented.
  * verdict FAIL when at least one check is flipped to FAIL (synthetic).
  * verdict PASS only when every check is flipped to PASS (synthetic).
- ``pending_algorithmic_checks_pr`` hint surfaces while
  ``not_yet_checked > 0``.
- CLI: returns 0 by default; returns 2 with `--strict` + FAIL; writes
  the report JSON when `--out` is supplied.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.produce_visual_evidence import (
    REQUIRED_VISUAL_ARTIFACTS as PRODUCER_ARTIFACTS,
)
from tools.verify_fidelities import (
    REQUIRED_VISUAL_ARTIFACTS as GATE_ARTIFACTS_FROM_VERIFIER,
)
from tools.visual_fidelity_gate import (
    EIGHT_CHECKS,
    GATE_REPORT_SCHEMA_VERSION,
    REQUIRED_VISUAL_ARTIFACTS,
    VISUAL_FIDELITY_POLICY_VIOLATION_TAG,
    _compute_top_level,
    _scaffold_all_checks,
    load_artifacts,
    run_gate,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Schema lock
# ---------------------------------------------------------------------------

def test_required_artifacts_match_verifier_module():
    """The gate's REQUIRED list mirrors `tools.verify_fidelities`."""
    assert REQUIRED_VISUAL_ARTIFACTS == GATE_ARTIFACTS_FROM_VERIFIER


def test_required_artifacts_match_producer_module():
    """The gate's REQUIRED list mirrors `tools.produce_visual_evidence`."""
    assert REQUIRED_VISUAL_ARTIFACTS == PRODUCER_ARTIFACTS


def test_eight_checks_count():
    assert len(EIGHT_CHECKS) == 8


def test_eight_checks_keys_lock_to_protocol():
    keys = {c["key"] for c in EIGHT_CHECKS}
    expected = {
        "door_without_opening",
        "door_crossing_or_displaced",
        "door_swing_diverges",
        "room_polygon_not_closed",
        "room_polygon_bleeds_outside",
        "invented_or_wrong_height_exterior",
        "wet_or_terrace_adjacency_wrong",
        "room_rendered_as_bbox",
    }
    assert keys == expected


def test_all_checks_have_required_fields():
    for c in EIGHT_CHECKS:
        assert set(c.keys()) >= {
            "key", "description", "severity_on_fail",
        }
        assert isinstance(c["description"], str) and c["description"]
        assert c["severity_on_fail"] in {"FAIL", "WARN"}


# ---------------------------------------------------------------------------
# load_artifacts
# ---------------------------------------------------------------------------

def _write_artifacts(directory: Path, keys: list[str]) -> None:
    """Write a >0 byte file for each key in `keys`."""
    directory.mkdir(parents=True, exist_ok=True)
    by_key = dict(REQUIRED_VISUAL_ARTIFACTS)
    for k in keys:
        fname = by_key[k]
        (directory / fname).write_bytes(b"x")


def test_load_artifacts_status_missing_when_dir_empty(tmp_path: Path):
    res = load_artifacts(tmp_path)
    assert res["overall_status"] == "missing"
    assert res["present_keys"] == []
    assert len(res["missing_keys"]) == 7
    assert len(res["per_artifact"]) == 7
    for entry in res["per_artifact"]:
        assert entry["status"] == "missing"
        assert entry["exists"] is False
        assert entry["size_bytes"] == 0


def test_load_artifacts_status_incomplete_when_some_present(tmp_path: Path):
    _write_artifacts(tmp_path, ["original_floorplan", "skp_render"])
    res = load_artifacts(tmp_path)
    assert res["overall_status"] == "incomplete"
    assert set(res["present_keys"]) == {"original_floorplan", "skp_render"}
    assert len(res["missing_keys"]) == 5


def test_load_artifacts_status_present_when_all_present(tmp_path: Path):
    _write_artifacts(tmp_path, [k for k, _ in REQUIRED_VISUAL_ARTIFACTS])
    res = load_artifacts(tmp_path)
    assert res["overall_status"] == "present"
    assert len(res["present_keys"]) == 7
    assert res["missing_keys"] == []
    assert res["empty_keys"] == []


def test_load_artifacts_zero_byte_file_is_empty(tmp_path: Path):
    """A 0-byte artifact is `empty`, not `present`."""
    for _key, fname in REQUIRED_VISUAL_ARTIFACTS:
        (tmp_path / fname).write_bytes(b"")
    res = load_artifacts(tmp_path)
    assert res["overall_status"] == "incomplete"
    assert res["present_keys"] == []
    assert len(res["empty_keys"]) == 7


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------

def test_scaffold_all_checks_returns_eight_records():
    scaffolded = _scaffold_all_checks()
    assert len(scaffolded) == 8
    for entry in scaffolded:
        assert entry["status"] == "not_yet_checked"
        assert entry["verdict"] == "WARN"
        assert entry["failing_elements"] == []
        assert "Consensus not supplied" in entry["notes"]
        assert entry["severity_on_fail"] in {"FAIL", "WARN"}


# ---------------------------------------------------------------------------
# Top-level verdict
# ---------------------------------------------------------------------------

def test_top_level_fail_when_artifacts_not_present():
    counts = {
        "checks_pass": 8, "checks_warn": 0,
        "checks_fail": 0, "checks_not_yet_checked": 0,
    }
    assert _compute_top_level("missing", counts) == "FAIL"
    assert _compute_top_level("incomplete", counts) == "FAIL"


def test_top_level_fail_when_any_check_fails():
    counts = {
        "checks_pass": 7, "checks_warn": 0,
        "checks_fail": 1, "checks_not_yet_checked": 0,
    }
    assert _compute_top_level("present", counts) == "FAIL"


def test_top_level_warn_when_any_check_not_yet_checked():
    counts = {
        "checks_pass": 0, "checks_warn": 0,
        "checks_fail": 0, "checks_not_yet_checked": 8,
    }
    assert _compute_top_level("present", counts) == "WARN"


def test_top_level_warn_when_any_check_warn():
    counts = {
        "checks_pass": 7, "checks_warn": 1,
        "checks_fail": 0, "checks_not_yet_checked": 0,
    }
    assert _compute_top_level("present", counts) == "WARN"


def test_top_level_pass_only_when_all_checks_pass():
    counts = {
        "checks_pass": 8, "checks_warn": 0,
        "checks_fail": 0, "checks_not_yet_checked": 0,
    }
    assert _compute_top_level("present", counts) == "PASS"


# ---------------------------------------------------------------------------
# run_gate end-to-end
# ---------------------------------------------------------------------------

def test_run_gate_missing_directory_emits_fail(tmp_path: Path):
    """All 7 missing → FAIL + policy_violation tag."""
    report = run_gate(evidence_dir=tmp_path)
    assert report["schema_version"] == GATE_REPORT_SCHEMA_VERSION
    assert report["verdict_top_level"] == "FAIL"
    assert (
        report["policy_violation"]
        == VISUAL_FIDELITY_POLICY_VIOLATION_TAG
    )
    assert "Visual Fidelity Gate Protocol" in report["policy_reason"]
    assert len(report["checks"]) == 8
    # Every check still not_yet_checked.
    statuses = {c["status"] for c in report["checks"]}
    assert statuses == {"not_yet_checked"}
    assert report["summary"]["checks_not_yet_checked"] == 8
    assert report["summary"]["artifacts_missing"] == 7
    # PR B3 hint surfaces.
    assert report.get("pending_algorithmic_checks_pr") == "B3"


def test_run_gate_artifacts_present_yields_warn(tmp_path: Path):
    """All 7 present + 0 algorithmic checks implemented → WARN."""
    _write_artifacts(tmp_path, [k for k, _ in REQUIRED_VISUAL_ARTIFACTS])
    report = run_gate(evidence_dir=tmp_path)
    assert report["verdict_top_level"] == "WARN"
    assert "policy_violation" not in report
    assert report["artifacts"]["overall_status"] == "present"
    assert report["summary"]["artifacts_present"] == 7
    assert report["summary"]["checks_not_yet_checked"] == 8
    assert report["pending_algorithmic_checks_pr"] == "B3"


def test_run_gate_propagates_consensus_and_pdf_paths(tmp_path: Path):
    """B2 doesn't consume these paths but must reflect them in the
    report so PR B3 can drop in algorithms without a CLI change."""
    _write_artifacts(tmp_path, [k for k, _ in REQUIRED_VISUAL_ARTIFACTS])
    consensus = tmp_path / "consensus.json"
    pdf = tmp_path / "p.pdf"
    consensus.write_bytes(b"{}")
    pdf.write_bytes(b"%PDF-1.4")
    report = run_gate(
        evidence_dir=tmp_path,
        consensus_path=consensus,
        pdf_path=pdf,
    )
    assert report["consensus_path"] == str(consensus)
    assert report["pdf_path"] == str(pdf)
    assert report["evidence_dir"] == str(tmp_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_default_exits_zero_and_writes_report(tmp_path: Path):
    _write_artifacts(tmp_path, [k for k, _ in REQUIRED_VISUAL_ARTIFACTS])
    out = tmp_path / "gate_report.json"
    res = subprocess.run(
        [sys.executable, "-m", "tools.visual_fidelity_gate",
         "--evidence-dir", str(tmp_path),
         "--out", str(out)],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict_top_level"] == "WARN"
    assert report["schema_version"] == GATE_REPORT_SCHEMA_VERSION


def test_cli_strict_exits_2_on_fail(tmp_path: Path):
    """Empty evidence dir + --strict → exit code 2."""
    out = tmp_path / "gate_report.json"
    res = subprocess.run(
        [sys.executable, "-m", "tools.visual_fidelity_gate",
         "--evidence-dir", str(tmp_path),
         "--out", str(out),
         "--strict"],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    )
    assert res.returncode == 2
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict_top_level"] == "FAIL"
    assert (
        report["policy_violation"]
        == VISUAL_FIDELITY_POLICY_VIOLATION_TAG
    )


def test_cli_nonexistent_evidence_dir_exits_2(tmp_path: Path):
    """Pointing at a non-existent directory short-circuits to exit 2."""
    nonexistent = tmp_path / "no_such_dir"
    res = subprocess.run(
        [sys.executable, "-m", "tools.visual_fidelity_gate",
         "--evidence-dir", str(nonexistent)],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    )
    assert res.returncode == 2
    assert "does not exist" in res.stderr


def test_cli_propagates_consensus_and_pdf_paths(tmp_path: Path):
    """CLI maps --consensus / --pdf into the report (B2 reserves
    them for B3)."""
    _write_artifacts(tmp_path, [k for k, _ in REQUIRED_VISUAL_ARTIFACTS])
    consensus = tmp_path / "consensus.json"
    pdf = tmp_path / "plan.pdf"
    consensus.write_bytes(b"{}")
    pdf.write_bytes(b"%PDF-1.4")
    out = tmp_path / "gate_report.json"
    res = subprocess.run(
        [sys.executable, "-m", "tools.visual_fidelity_gate",
         "--evidence-dir", str(tmp_path),
         "--consensus", str(consensus),
         "--pdf", str(pdf),
         "--out", str(out)],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["consensus_path"] == str(consensus)
    assert report["pdf_path"] == str(pdf)


# ---------------------------------------------------------------------------
# planta_74 end-to-end smoke (skipped when fixtures absent)
# ---------------------------------------------------------------------------

PLANTA_74_EVIDENCE_DIR = (
    REPO_ROOT / "fixtures" / "planta_74" / "visual_evidence"
)
PLANTA_74_CONSENSUS = (
    REPO_ROOT / "fixtures" / "planta_74"
    / "consensus_with_human_walls_and_soft_barriers.json"
)


@pytest.mark.skipif(
    not (PLANTA_74_EVIDENCE_DIR.exists() and PLANTA_74_CONSENSUS.exists()),
    reason="planta_74 fixtures missing",
)
def test_planta_74_end_to_end_smoke(tmp_path: Path):
    """Real planta_74 evidence dir + consensus → top-level FAIL.

    After PR B3 the gate runs the 8 algorithmic checks. The known
    planta_74 baseline trips two FAIL checks (the unhosted
    ``h_o005`` interior_door fails both ``door_without_opening`` and
    ``door_crossing_or_displaced``) and one WARN
    (``door_swing_diverges`` lacks svg_arc evidence in consensus).
    """
    out = tmp_path / "gate_report.json"
    report = run_gate(
        evidence_dir=PLANTA_74_EVIDENCE_DIR,
        consensus_path=PLANTA_74_CONSENSUS,
    )
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert report["artifacts"]["overall_status"] == "present"
    assert report["summary"]["artifacts_present"] == 7
    # B3 ran the checks → 0 scaffolded.
    assert report["summary"]["checks_not_yet_checked"] == 0
    assert report["verdict_top_level"] == "FAIL"
    assert report["summary"]["checks_fail"] >= 1
    assert "policy_violation" not in report
    # Spot-check: door_without_opening FAILed on h_o005.
    door_check = next(
        c for c in report["checks"]
        if c["key"] == "door_without_opening"
    )
    assert door_check["verdict"] == "FAIL"
    assert any(
        e.get("opening_id") == "h_o005"
        for e in door_check["failing_elements"]
    )
