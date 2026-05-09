"""Tests for gate E3 (amended-fidelity computation — Slice 5b).

Boundary: auto-skip when expected_model OR review_overrides is
missing (CI byte-equivalent). When both are present, runs the
fidelity engine in ``apply_overrides=True`` mode and writes
``fidelity_report_amended.json`` to ``out_dir``. Emits both
``global_fidelity`` and ``global_fidelity_pre_override`` per
ADR-001 §2.10.5.
"""
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from scripts.smoke.smoke_skp_export import (
    SmokeReport,
    _build_parser,
    gate_e_fidelity_amended,
)

# ---- Fixtures -------------------------------------------------------

def _toy_consensus() -> dict:
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "w0", "start": [0, 0], "end": [600, 0],
             "thickness": 5.4, "orientation": "h"},
            {"id": "w1", "start": [0, 240], "end": [600, 240],
             "thickness": 5.4, "orientation": "h"},
            {"id": "w2", "start": [0, 0], "end": [0, 240],
             "thickness": 5.4, "orientation": "v"},
            {"id": "w3", "start": [600, 0], "end": [600, 240],
             "thickness": 5.4, "orientation": "v"},
            {"id": "w4", "start": [300, 0], "end": [300, 240],
             "thickness": 5.4, "orientation": "v"},
        ],
        "rooms": [
            {"id": "r0", "name": "SALA", "polygon_pts": [
                [0, 0], [300, 0], [300, 240], [0, 240],
            ], "area_pts2": 72000},
            {"id": "r1", "name": "COZINHA", "polygon_pts": [
                [300, 0], [600, 0], [600, 240], [300, 240],
            ], "area_pts2": 72000},
        ],
        "openings": [
            {"id": "o0", "kind_v5": "interior_door", "decision": "clean",
             "confidence": 0.95, "wall_id": "w4",
             "evidence": {"room_left": "SALA", "room_right": "COZINHA"}},
        ],
    }


def _toy_expected_model() -> dict:
    """Matches `_toy_consensus` topology (synthetic 2-room L-style)."""
    return {
        "schema_version": "1.0",
        "plan_id": "synth_test_5b",
        "source_pdf": "synth.pdf",
        "unit": "m",
        "scale_source": "synthetic — wall thickness anchored",
        "global_bbox": {
            "width": 21.1, "height": 8.4, "tolerance_pct": 25,
        },
        "expected_counts": {
            "rooms": 2, "openings": 1, "walls": 5,
            "tolerance": {"rooms_delta": 1, "openings_delta": 1,
                          "walls_delta": 2},
        },
        "rooms": [
            {"id": "sala", "label": "SALA",
             "expected_area_m2_range": [50, 100],
             "must_be_closed": True,
             "manual_confidence": "high",
             "source": "synthetic"},
            {"id": "cozinha", "label": "COZINHA",
             "expected_area_m2_range": [50, 100],
             "must_be_closed": True,
             "manual_confidence": "high",
             "source": "synthetic"},
        ],
        "openings": [
            {"id": "door_sala_cozinha", "kind_v5": "interior_door",
             "expected_room_left": "SALA",
             "expected_room_right": "COZINHA",
             "manual_confidence": "high",
             "source": "synthetic"},
        ],
        "adjacency": [
            {"a": "SALA", "b": "COZINHA", "via": "interior_door"},
        ],
    }


def _override_doc(consensus_sha: str = "deadbeef" * 8) -> dict:
    """Override that flips o0 from interior_door to interior_passage."""
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
                "payload": {"new_kind_v5": "interior_passage"},
                "author": "human",
                "created_at": "2026-05-09T00:00:00Z",
                "reason": "test fixture",
                "signature": "sig",
            },
        ],
        "global": {"block_skp_export": False, "block_reason": None},
        "audit_trail": [],
    }


def _make_report(tmp_path: Path,
                  consensus: dict | None = None,
                  expected: dict | None = None,
                  overrides: dict | None = None,
                  consensus_sha256: str = "deadbeef" * 8,
                  use_explicit_expected: bool = False) -> tuple[
                      SmokeReport, Path | None]:
    """Lay out an out_dir + consensus + (optional) overrides + GT,
    return the SmokeReport plus the explicit expected-model path
    (or None when auto-discover should kick in).
    """
    out_dir = tmp_path / "smoke_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    consensus_dir = tmp_path / "consensus_dir"
    consensus_dir.mkdir(parents=True, exist_ok=True)
    consensus_path = consensus_dir / "consensus.json"
    consensus_path.write_text(
        json.dumps(consensus if consensus is not None else _toy_consensus()),
        encoding="utf-8",
    )
    if overrides is not None:
        (out_dir / "review_overrides.json").write_text(
            json.dumps(overrides), encoding="utf-8",
        )
    explicit_path: Path | None = None
    if expected is not None:
        # When `use_explicit_expected`, write next to the test dir
        # and pass its path explicitly. Otherwise place under
        # tmp_path/ground_truth/<consensus_dir_name>/expected_model.json
        # — but auto-discover looks under REPO_ROOT/ground_truth, so
        # for the auto-discover path we always pass explicit instead
        # of writing into REPO_ROOT.
        if use_explicit_expected:
            expected_path = tmp_path / "expected_model.json"
        else:
            # Auto-discover path test: write to a place that the
            # gate's auto-discovery will check. We can't write into
            # REPO_ROOT without polluting. So always use explicit
            # for tests that supply expected.
            expected_path = tmp_path / "expected_model.json"
        expected_path.write_text(json.dumps(expected), encoding="utf-8")
        explicit_path = expected_path
    return SmokeReport(
        consensus_path=str(consensus_path),
        out_dir=str(out_dir),
        started_at="2026-05-09T00:00:00Z",
        consensus_sha256=consensus_sha256,
    ), explicit_path


def _args(*, no_amended_fidelity: bool = False,
          expected_model: Path | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        no_amended_fidelity=no_amended_fidelity,
        expected_model=expected_model,
    )


# ---- Default-skip semantics (CI byte-equivalent) -------------------

def test_skip_when_no_expected_and_no_overrides(tmp_path):
    report, _ = _make_report(tmp_path)
    result = gate_e_fidelity_amended(_args(), report)
    assert result.status == "skip"
    # Either reason is acceptable; the gate stops early on first
    # missing precondition. In this case expected_model is checked first.
    assert "no expected_model" in result.message


def test_skip_when_no_amended_fidelity_flag(tmp_path):
    report, expected_path = _make_report(
        tmp_path, expected=_toy_expected_model(),
        overrides=_override_doc(),
        use_explicit_expected=True,
    )
    result = gate_e_fidelity_amended(
        _args(no_amended_fidelity=True, expected_model=expected_path),
        report,
    )
    assert result.status == "skip"
    assert "--no-amended-fidelity" in result.message


def test_skip_when_no_overrides_present(tmp_path):
    """expected_model present but no review_overrides → SKIP. The
    raw fidelity report from a separate invocation is already the
    authoritative score; no point producing an `amended` copy that
    would equal the raw."""
    report, expected_path = _make_report(
        tmp_path, expected=_toy_expected_model(),
        use_explicit_expected=True,
    )
    result = gate_e_fidelity_amended(
        _args(expected_model=expected_path), report,
    )
    assert result.status == "skip"
    assert "no review_overrides.json" in result.message


def test_skip_when_no_expected_model_supplied(tmp_path):
    """overrides exist but no expected_model (no flag, auto-discover
    fails) → SKIP."""
    report, _ = _make_report(
        tmp_path, overrides=_override_doc(),
    )
    result = gate_e_fidelity_amended(_args(), report)
    assert result.status == "skip"
    assert "no expected_model" in result.message


def test_skip_byte_equivalent_on_repeated_calls(tmp_path):
    """Default-SKIP path produces identical results on repeat — guards
    against accidental side effects."""
    report, _ = _make_report(tmp_path)
    r1 = gate_e_fidelity_amended(_args(), report)
    r2 = gate_e_fidelity_amended(_args(), report)
    assert r1.status == r2.status == "skip"
    assert r1.message == r2.message


# ---- PASS path ------------------------------------------------------

def test_pass_writes_amended_fidelity_with_pre_and_post(tmp_path):
    report, expected_path = _make_report(
        tmp_path, expected=_toy_expected_model(),
        overrides=_override_doc(),
        use_explicit_expected=True,
    )
    result = gate_e_fidelity_amended(
        _args(expected_model=expected_path), report,
    )
    assert result.status == "pass", result.message
    out_path = Path(report.out_dir) / "fidelity_report_amended.json"
    assert out_path.exists()
    rpt = json.loads(out_path.read_text(encoding="utf-8"))
    # ADR §2.10.5 — both pre and post fidelity must be in the report
    assert "global_fidelity" in rpt
    assert "global_fidelity_pre_override" in rpt
    assert rpt.get("overrides_applied_count") is not None
    # Message reports both scores
    assert "global_fidelity=" in result.message
    assert "pre_override=" in result.message


def test_pass_picks_up_overrides_from_consensus_dir(tmp_path):
    """When review_overrides.json sits next to the consensus, the
    gate should pick it up (same fallback as gate_e_amend / gate_f0)."""
    report, expected_path = _make_report(
        tmp_path, expected=_toy_expected_model(),
        use_explicit_expected=True,
    )
    # Move the override file from out_dir to consensus_dir
    consensus_dir = Path(report.consensus_path).parent
    (consensus_dir / "review_overrides.json").write_text(
        json.dumps(_override_doc()), encoding="utf-8",
    )
    result = gate_e_fidelity_amended(
        _args(expected_model=expected_path), report,
    )
    assert result.status == "pass", result.message


# ---- Failure paths -------------------------------------------------

def test_skip_on_missing_consensus(tmp_path):
    out_dir = tmp_path / "smoke_out"
    out_dir.mkdir()
    report = SmokeReport(
        consensus_path=str(tmp_path / "missing.json"),
        out_dir=str(out_dir),
        started_at="2026-05-09T00:00:00Z",
    )
    result = gate_e_fidelity_amended(_args(), report)
    assert result.status == "skip"
    assert "consensus path missing" in result.message


def test_fail_on_corrupt_overrides_json(tmp_path):
    report, expected_path = _make_report(
        tmp_path, expected=_toy_expected_model(),
        use_explicit_expected=True,
    )
    (Path(report.out_dir) / "review_overrides.json").write_text(
        "{ not json", encoding="utf-8",
    )
    result = gate_e_fidelity_amended(
        _args(expected_model=expected_path), report,
    )
    assert result.status == "fail"
    assert "review_overrides.json" in result.message


def test_fail_on_corrupt_expected_model(tmp_path):
    report, _ = _make_report(
        tmp_path, overrides=_override_doc(),
    )
    bad_expected = tmp_path / "expected_model.json"
    bad_expected.write_text("{ not json", encoding="utf-8")
    result = gate_e_fidelity_amended(
        _args(expected_model=bad_expected), report,
    )
    assert result.status == "fail"
    assert "expected_model" in result.message


# ---- Parser + pipeline integration --------------------------------

def test_no_amended_fidelity_flag_in_parser():
    p = _build_parser()
    args = p.parse_args(["--no-amended-fidelity"])
    assert args.no_amended_fidelity is True
    args = p.parse_args([])
    assert args.no_amended_fidelity is False


def test_expected_model_flag_in_parser(tmp_path):
    p = _build_parser()
    fake = tmp_path / "x.json"
    args = p.parse_args(["--expected-model", str(fake)])
    assert args.expected_model == fake
    args = p.parse_args([])
    assert args.expected_model is None


def test_pipeline_includes_gate_e_fidelity_amended_after_gate_e_amend():
    """Sanity: the pipeline tuple has gate_e_amend → gate_e_fidelity_amended
    → gate_f0 in that order."""
    import re

    import scripts.smoke.smoke_skp_export as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    m = re.search(r"pipeline\s*=\s*\((.*?)\)", src, re.DOTALL)
    assert m is not None
    body = m.group(1)
    for name in ("gate_e_amend", "gate_e_fidelity_amended", "gate_f0"):
        assert name in body, f"{name} missing from pipeline body"
    pos_amend = body.index("gate_e_amend")
    pos_fid = body.index("gate_e_fidelity_amended")
    pos_f0 = re.search(r"\bgate_f0\b(?!\w)", body).start()
    assert pos_amend < pos_fid < pos_f0, (
        f"order wrong: e_amend@{pos_amend}, e_fidelity@{pos_fid}, f0@{pos_f0}"
    )
