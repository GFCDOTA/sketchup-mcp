"""Tests for gate E2 (amend observed via apply_overrides — Slice 5a).

Boundary: auto-apply when ``review_overrides.json`` is present;
SKIP cleanly when it isn't (CI byte-equivalent). Opt-out via
``--no-apply-overrides``. Writes ``amended_observed.json`` into
``out_dir`` per ADR-001 §2.10.4.
"""
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from scripts.smoke.smoke_skp_export import (
    SmokeReport,
    _build_parser,
    gate_e_amend,
)
from tools.apply_overrides import AMENDED_SCHEMA_VERSION

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
            {"id": "o0", "kind_v5": "interior_door", "decision": "clean",
             "confidence": 0.95},
            {"id": "o1", "kind_v5": "window", "decision": "clean",
             "confidence": 0.55},
        ],
    }


def _override_doc(consensus_sha: str = "deadbeef" * 8,
                   block: bool = False) -> dict:
    return {
        "schema_version": "review_overrides_v1",
        "run_id": "fake_run",
        "consensus_sha256": consensus_sha,
        "consensus_path": "consensus.json",
        "created_at": "2026-05-09T00:00:00Z",
        "last_updated_at": "2026-05-09T00:00:00Z",
        "overrides": [
            {
                "id": str(uuid.uuid4()),
                "type": "opening_kind_override",
                "target": {"kind": "opening", "id": "o0"},
                "payload": {"new_kind_v5": "window"},
                "author": "human",
                "created_at": "2026-05-09T00:00:00Z",
                "reason": "test fixture",
                "signature": "sig",
            },
        ],
        "global": {
            "block_skp_export": block,
            "block_reason": ("test block" if block else None),
        },
        "audit_trail": [],
    }


def _make_report(tmp_path: Path,
                  consensus: dict | None = None,
                  overrides_in_out_dir: dict | None = None,
                  overrides_in_consensus_dir: dict | None = None,
                  consensus_sha256: str = "deadbeef" * 8) -> SmokeReport:
    out_dir = tmp_path / "smoke_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    consensus_dir = tmp_path / "consensus_dir"
    consensus_dir.mkdir(parents=True, exist_ok=True)
    consensus_path = consensus_dir / "consensus.json"
    consensus_path.write_text(
        json.dumps(consensus if consensus is not None else _toy_consensus()),
        encoding="utf-8",
    )
    if overrides_in_out_dir is not None:
        (out_dir / "review_overrides.json").write_text(
            json.dumps(overrides_in_out_dir), encoding="utf-8",
        )
    if overrides_in_consensus_dir is not None:
        (consensus_dir / "review_overrides.json").write_text(
            json.dumps(overrides_in_consensus_dir), encoding="utf-8",
        )
    return SmokeReport(
        consensus_path=str(consensus_path),
        out_dir=str(out_dir),
        started_at="2026-05-09T00:00:00Z",
        consensus_sha256=consensus_sha256,
    )


def _args(*, no_apply_overrides: bool = False) -> argparse.Namespace:
    return argparse.Namespace(no_apply_overrides=no_apply_overrides)


# ---- Default-skip semantics (CI byte-equivalent) -------------------

def test_skip_when_no_overrides_file_exists(tmp_path):
    report = _make_report(tmp_path)
    result = gate_e_amend(_args(), report)
    assert result.status == "skip"
    assert "no review_overrides.json" in result.message
    assert not (Path(report.out_dir) / "amended_observed.json").exists()


def test_skip_when_no_apply_overrides_flag(tmp_path):
    report = _make_report(
        tmp_path, overrides_in_out_dir=_override_doc(),
    )
    result = gate_e_amend(_args(no_apply_overrides=True), report)
    assert result.status == "skip"
    assert "--no-apply-overrides" in result.message
    assert not (Path(report.out_dir) / "amended_observed.json").exists()


def test_skip_byte_equivalent_on_repeated_calls(tmp_path):
    report = _make_report(tmp_path)
    r1 = gate_e_amend(_args(), report)
    r2 = gate_e_amend(_args(), report)
    assert r1.status == r2.status == "skip"
    assert r1.message == r2.message


# ---- PASS path with overrides --------------------------------------

def test_pass_writes_amended_when_overrides_in_out_dir(tmp_path):
    report = _make_report(
        tmp_path, overrides_in_out_dir=_override_doc(),
    )
    result = gate_e_amend(_args(), report)
    assert result.status == "pass", result.message
    out_path = Path(report.out_dir) / "amended_observed.json"
    assert out_path.exists()
    amended = json.loads(out_path.read_text(encoding="utf-8"))
    assert amended.get("_overrides_metadata", {}).get(
        "schema_version") == AMENDED_SCHEMA_VERSION
    # The opening_kind_override should have been applied to o0
    o0 = next(o for o in amended["openings"] if o["id"] == "o0")
    assert o0["kind_v5"] == "window"
    assert o0.get("_kind_v5_original") == "interior_door"
    # Message reports counts
    assert "applied=" in result.message
    assert "block_skp_export=no" in result.message


def test_pass_picks_up_overrides_from_consensus_dir(tmp_path):
    """When review_overrides.json sits next to the consensus (NOT in
    out_dir), the gate should still pick it up — same fallback as
    gate_f0/gate_f0_pa."""
    report = _make_report(
        tmp_path, overrides_in_consensus_dir=_override_doc(),
    )
    result = gate_e_amend(_args(), report)
    assert result.status == "pass", result.message
    out_path = Path(report.out_dir) / "amended_observed.json"
    assert out_path.exists()


def test_pass_reports_block_skp_export_in_message(tmp_path):
    report = _make_report(
        tmp_path,
        overrides_in_out_dir=_override_doc(block=True),
    )
    result = gate_e_amend(_args(), report)
    assert result.status == "pass"
    assert "block_skp_export=yes" in result.message
    amended = json.loads(
        (Path(report.out_dir) / "amended_observed.json").read_text(
            encoding="utf-8",
        )
    )
    assert amended["_overrides_metadata"]["block_skp_export"] is True


def test_amended_is_byte_identical_for_byte_identical_inputs(tmp_path):
    """apply_overrides is a pure function; running the gate twice
    should produce identical amended_observed.json content (modulo
    the ``applied_at`` timestamp). Verify the structural keys + the
    transformed openings are stable."""
    report = _make_report(
        tmp_path, overrides_in_out_dir=_override_doc(),
    )
    gate_e_amend(_args(), report)
    out_path = Path(report.out_dir) / "amended_observed.json"
    first = json.loads(out_path.read_text(encoding="utf-8"))

    gate_e_amend(_args(), report)
    second = json.loads(out_path.read_text(encoding="utf-8"))

    # Strip the volatile applied_at timestamp before comparing
    first.get("_overrides_metadata", {}).pop("applied_at", None)
    second.get("_overrides_metadata", {}).pop("applied_at", None)
    assert first == second


# ---- Sha-mismatch handling -----------------------------------------

def test_sha_mismatch_records_warning_in_amended_metadata(tmp_path):
    """When override's consensus_sha256 differs from the live
    consensus, apply_overrides records a warning rather than
    silently dropping. The gate still PASSes (the apply layer
    decides what to do)."""
    report = _make_report(
        tmp_path,
        overrides_in_out_dir=_override_doc(consensus_sha="OTHER_SHA"),
        consensus_sha256="LIVE_SHA",
    )
    result = gate_e_amend(_args(), report)
    assert result.status == "pass"
    amended = json.loads(
        (Path(report.out_dir) / "amended_observed.json").read_text(
            encoding="utf-8",
        )
    )
    warnings = amended.get("_overrides_metadata", {}).get("warnings") or []
    assert any("sha" in str(w).lower() or "mismatch" in str(w).lower()
                for w in warnings), warnings


# ---- Failure paths -------------------------------------------------

def test_skip_on_missing_consensus(tmp_path):
    out_dir = tmp_path / "smoke_out"
    out_dir.mkdir()
    report = SmokeReport(
        consensus_path=str(tmp_path / "missing.json"),
        out_dir=str(out_dir),
        started_at="2026-05-09T00:00:00Z",
    )
    result = gate_e_amend(_args(), report)
    assert result.status == "skip"
    assert "consensus path missing" in result.message


def test_fail_on_corrupt_overrides_json(tmp_path):
    report = _make_report(tmp_path)
    (Path(report.out_dir) / "review_overrides.json").write_text(
        "{ not json", encoding="utf-8",
    )
    result = gate_e_amend(_args(), report)
    assert result.status == "fail"
    assert "review_overrides.json" in result.message


def test_fail_on_corrupt_consensus_json(tmp_path):
    out_dir = tmp_path / "smoke_out"
    out_dir.mkdir()
    consensus_path = tmp_path / "bad_consensus.json"
    consensus_path.write_text("{ not json", encoding="utf-8")
    (out_dir / "review_overrides.json").write_text(
        json.dumps(_override_doc()), encoding="utf-8",
    )
    report = SmokeReport(
        consensus_path=str(consensus_path),
        out_dir=str(out_dir),
        started_at="2026-05-09T00:00:00Z",
        consensus_sha256="deadbeef" * 8,
    )
    result = gate_e_amend(_args(), report)
    assert result.status == "fail"
    assert "consensus" in result.message.lower()


# ---- Parser + pipeline integration --------------------------------

def test_no_apply_overrides_flag_in_parser():
    p = _build_parser()
    args = p.parse_args(["--no-apply-overrides"])
    assert args.no_apply_overrides is True
    args = p.parse_args([])
    assert args.no_apply_overrides is False


def test_pipeline_includes_gate_e_amend_between_e_and_f0():
    """Sanity: the smoke harness pipeline tuple includes gate_e_amend
    immediately after gate_e and before gate_f0."""
    import re

    import scripts.smoke.smoke_skp_export as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    m = re.search(r"pipeline\s*=\s*\((.*?)\)", src, re.DOTALL)
    assert m is not None, "pipeline tuple not found"
    body = m.group(1)
    for name in ("gate_e", "gate_e_amend", "gate_f0"):
        assert name in body, f"{name} missing from pipeline body"
    # Locate each via word-boundary so 'gate_e' doesn't match 'gate_e_amend'
    pos_e = re.search(r"\bgate_e\b(?!\w)", body).start()
    pos_e_amend = body.index("gate_e_amend")
    pos_f0 = re.search(r"\bgate_f0\b(?!\w)", body).start()
    assert pos_e < pos_e_amend < pos_f0, (
        f"order wrong: e@{pos_e}, e_amend@{pos_e_amend}, f0@{pos_f0}"
    )
