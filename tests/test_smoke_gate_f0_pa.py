"""Tests for gate F0pa (proposed_actions producer integration in
the smoke harness — Cycle 13b).

Boundary: opt-in via ``--emit-proposed-actions``. Default off
preserves byte-equivalent CI behaviour. When on, the gate runs
``tools.propose_skp_actions`` and writes
``runs/<smoke_out_dir>/proposed_actions.json`` for the cockpit
Slice 4 Review tab to consume.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from scripts.smoke.smoke_skp_export import (
    GateResult,
    SmokeReport,
    _build_parser,
    gate_f0_pa,
)

# ---- Helpers --------------------------------------------------------

def _toy_consensus() -> dict:
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "w0", "start": [0, 0], "end": [100, 0],
             "thickness": 5.4, "orientation": "h"},
        ],
        "rooms": [
            {"id": "r0", "name": "SALA", "polygon_pts": [
                [0, 0], [50, 0], [50, 100], [0, 100],
            ], "area_pts2": 5000},
        ],
        "openings": [
            # Low confidence → producer emits mark_low_confidence
            {"id": "o0", "kind_v5": "window", "decision": "clean",
             "confidence": 0.55},
            # Unknown kind → producer emits classify_opening
            {"id": "o1", "kind_v5": "unknown", "decision": "clean",
             "confidence": 0.9},
        ],
    }


def _toy_fidelity_report() -> dict:
    return {
        "schema_version": "fidelity_v1",
        "global_fidelity": 0.92,
        "warnings": ["SALA area marginal"],
        "hard_fails": [],
        "sub_scores": {},
    }


def _make_report_with_consensus(tmp_path: Path,
                                  consensus: dict | None = None,
                                  fidelity: dict | None = None) -> SmokeReport:
    """Lay out an out_dir + consensus on disk and return a SmokeReport
    pointing at them, mirroring how the real pipeline wires it up."""
    out_dir = tmp_path / "smoke_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    consensus_path = tmp_path / "consensus.json"
    consensus_path.write_text(
        json.dumps(consensus if consensus is not None else _toy_consensus()),
        encoding="utf-8",
    )
    if fidelity is not None:
        (out_dir / "fidelity_report.json").write_text(
            json.dumps(fidelity), encoding="utf-8",
        )
    return SmokeReport(
        consensus_path=str(consensus_path),
        out_dir=str(out_dir),
        started_at="2026-05-09T00:00:00Z",
        consensus_sha256="deadbeef" * 8,
    )


def _args(*, emit_proposed_actions: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        emit_proposed_actions=emit_proposed_actions,
    )


# ---- Default-off contract -------------------------------------------

def test_gate_f0_pa_skips_when_flag_not_set(tmp_path):
    report = _make_report_with_consensus(tmp_path)
    result = gate_f0_pa(_args(), report)
    assert result.status == "skip"
    assert "default off" in result.message
    # No file should be written
    assert not (Path(report.out_dir) / "proposed_actions.json").exists()


def test_gate_f0_pa_byte_equivalent_when_flag_off(tmp_path):
    """Repeated calls without the flag produce identical SKIP results
    — guards against accidental side effects."""
    report = _make_report_with_consensus(tmp_path)
    r1 = gate_f0_pa(_args(), report)
    r2 = gate_f0_pa(_args(), report)
    assert r1.status == r2.status == "skip"
    assert r1.message == r2.message
    assert not (Path(report.out_dir) / "proposed_actions.json").exists()


# ---- Opt-in PASS path ----------------------------------------------

def test_gate_f0_pa_passes_and_writes_file_when_flag_on(tmp_path):
    report = _make_report_with_consensus(tmp_path)
    result = gate_f0_pa(_args(emit_proposed_actions=True), report)
    assert result.status == "pass", result.message
    out_path = Path(report.out_dir) / "proposed_actions.json"
    assert out_path.exists()
    doc = json.loads(out_path.read_text(encoding="utf-8"))
    assert doc["schema_version"] == "proposed_actions_v1"
    # Producer should have emitted at least 2 actions on the toy
    # consensus (low-confidence + unknown-kind).
    assert len(doc["actions"]) >= 2
    # The gate's message reports the count
    assert "emitted" in result.message
    # The artifact pointer is set
    assert any("proposed_actions.json" in a for a in result.artifacts)


def test_gate_f0_pa_consumes_fidelity_report_when_present(tmp_path):
    report = _make_report_with_consensus(
        tmp_path, fidelity=_toy_fidelity_report(),
    )
    result = gate_f0_pa(_args(emit_proposed_actions=True), report)
    assert result.status == "pass"
    assert "fidelity_report consumed" in result.message
    doc = json.loads(
        (Path(report.out_dir) / "proposed_actions.json").read_text(
            encoding="utf-8",
        )
    )
    # Rule 4 (room-in-fidelity-warning) should have fired on SALA
    assert any(
        a["type"] == "request_human_review"
        and a["target"]["kind"] == "room"
        for a in doc["actions"]
    )


def test_gate_f0_pa_passes_without_fidelity_report(tmp_path):
    """No fidelity_report.json on disk should not crash the gate —
    rules 1-3 (opening-only) still fire."""
    report = _make_report_with_consensus(tmp_path)
    result = gate_f0_pa(_args(emit_proposed_actions=True), report)
    assert result.status == "pass"
    assert "fidelity_report consumed" not in result.message
    doc = json.loads(
        (Path(report.out_dir) / "proposed_actions.json").read_text(
            encoding="utf-8",
        )
    )
    # Should have at least the low-confidence + unknown-kind actions
    # but no room-fidelity-warning rows
    assert all(a["target"]["kind"] == "opening" for a in doc["actions"])


def test_gate_f0_pa_finds_sibling_fidelity_report(tmp_path):
    """When fidelity_report.json sits next to the consensus (NOT in
    out_dir), the gate should still pick it up — same fallback as
    gate_f0."""
    report = _make_report_with_consensus(tmp_path)
    sibling = Path(report.consensus_path).parent / "fidelity_report.json"
    sibling.write_text(json.dumps(_toy_fidelity_report()), encoding="utf-8")
    result = gate_f0_pa(_args(emit_proposed_actions=True), report)
    assert result.status == "pass"
    assert "fidelity_report consumed" in result.message


# ---- Failure paths --------------------------------------------------

def test_gate_f0_pa_skips_on_missing_consensus(tmp_path):
    """When consensus_path doesn't exist (gate_b should have caught
    this earlier), F0pa skips defensively rather than crashing."""
    out_dir = tmp_path / "smoke_out"
    out_dir.mkdir()
    report = SmokeReport(
        consensus_path=str(tmp_path / "does_not_exist.json"),
        out_dir=str(out_dir),
        started_at="2026-05-09T00:00:00Z",
    )
    result = gate_f0_pa(_args(emit_proposed_actions=True), report)
    assert result.status == "skip"
    assert "consensus path missing" in result.message


def test_gate_f0_pa_fails_on_corrupt_consensus_json(tmp_path):
    out_dir = tmp_path / "smoke_out"
    out_dir.mkdir()
    consensus_path = tmp_path / "consensus.json"
    consensus_path.write_text("{ not json", encoding="utf-8")
    report = SmokeReport(
        consensus_path=str(consensus_path),
        out_dir=str(out_dir),
        started_at="2026-05-09T00:00:00Z",
    )
    result = gate_f0_pa(_args(emit_proposed_actions=True), report)
    assert result.status == "fail"
    assert "failed to load consensus" in result.message


# ---- Parser + pipeline integration ---------------------------------

def test_emit_proposed_actions_flag_in_parser():
    p = _build_parser()
    args = p.parse_args(["--emit-proposed-actions"])
    assert args.emit_proposed_actions is True
    args = p.parse_args([])
    assert args.emit_proposed_actions is False


def test_pipeline_includes_gate_f0_pa_after_gate_f0():
    """Sanity: the smoke harness pipeline tuple includes gate_f0_pa
    immediately after gate_f0 and before gate_f."""
    import re

    import scripts.smoke.smoke_skp_export as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    m = re.search(r"pipeline\s*=\s*\((.*?)\)", src, re.DOTALL)
    assert m is not None, "pipeline tuple not found"
    body = m.group(1)
    # All three gates present in the body
    for name in ("gate_f0", "gate_f0_pa", "gate_f"):
        assert name in body, f"{name} missing from pipeline body"
    # Order: gate_f0 then gate_f0_pa then gate_f (allowing whitespace
    # / newlines / commas between)
    pos_f0 = body.index("gate_f0")
    pos_f0_pa = body.index("gate_f0_pa")
    # gate_f is the bare token — match after the comma to avoid
    # matching gate_f0 / gate_f0_pa
    pos_bare_f = re.search(r"\bgate_f\b(?!\w)", body)
    assert pos_bare_f is not None, "bare gate_f not found"
    pos_f = pos_bare_f.start()
    assert pos_f0 < pos_f0_pa < pos_f, (
        f"order wrong: gate_f0 @ {pos_f0}, gate_f0_pa @ {pos_f0_pa}, "
        f"gate_f @ {pos_f}"
    )
