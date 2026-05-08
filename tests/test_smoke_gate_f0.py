"""Unit tests for ``scripts/smoke/smoke_skp_export.py`` gate_f0.

Validates ADR-001 §2.8 verdict matrix + the ``--review-mode`` flag's
three modes (off, warn, block).

Tests load the smoke harness via importlib (same pattern as
``tests/smoke/test_smoke_skp_export.py``) so we can exercise gate_f0
without spawning subprocesses.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "smoke" / "smoke_skp_export.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "smoke_skp_export_for_f0", SCRIPT_PATH,
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["smoke_skp_export_for_f0"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def smoke():
    return _load_module()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fidelity_report(score: float = 0.917,
                      hard_fails: list[str] | None = None,
                      warnings: list[str] | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "global_fidelity": score,
        "sub_scores": {"room_score": 0.95, "count_score": 1.0},
        "hard_fails": hard_fails or [],
        "warnings": warnings or [],
        "would_block_strict": hard_fails or [],
    }


def _overrides_doc(overrides: list[dict] | None = None,
                    consensus_sha: str = "0" * 64,
                    block: bool = False,
                    block_reason: str | None = None) -> dict:
    return {
        "schema_version": "review_overrides_v1",
        "run_id": "test_run",
        "consensus_sha256": consensus_sha,
        "consensus_path": "runs/test_run/consensus.json",
        "created_at": "2026-05-08T20:00:00Z",
        "last_updated_at": "2026-05-08T20:00:00Z",
        "overrides": overrides or [],
        "global": {
            "block_skp_export": block,
            "block_reason": block_reason,
        },
        "audit_trail": [],
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
        "reason": "test",
        "signature": "sig",
    }


def _make_args(smoke, **overrides):
    parser = smoke._build_parser()
    args = parser.parse_args([])
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


def _make_report(smoke, **overrides):
    defaults = {
        "consensus_path": "/x/consensus.json",
        "out_dir": "/x/out",
        "started_at": "2026-05-08T00:00:00Z",
    }
    defaults.update(overrides)
    return smoke.SmokeReport(**defaults)


# ---------------------------------------------------------------------------
# Argparse: --review-mode flag
# ---------------------------------------------------------------------------


def test_parser_review_mode_default_off(smoke):
    args = smoke._build_parser().parse_args([])
    assert args.review_mode == "off"


def test_parser_review_mode_block(smoke):
    args = smoke._build_parser().parse_args(["--review-mode", "block"])
    assert args.review_mode == "block"


def test_parser_review_mode_invalid_rejected(smoke):
    with pytest.raises(SystemExit):
        smoke._build_parser().parse_args(["--review-mode", "fancy"])


def test_parser_review_mode_in_help(smoke, capsys):
    """--help must surface the new flag for grep-ability."""
    parser = smoke._build_parser()
    parser.print_help()
    out = capsys.readouterr().out
    assert "--review-mode" in out


# ---------------------------------------------------------------------------
# Pure verdict logic (ADR-001 §2.8)
# ---------------------------------------------------------------------------


def test_compute_pre_skp_review_pass(smoke):
    """High fidelity, zero hard_fails, few warnings → PASS."""
    fid = _fidelity_report(score=0.917, hard_fails=[], warnings=["w1"])
    review = smoke._compute_pre_skp_review(fid, None, "abc")
    assert review["verdict"] == "PASS"
    assert review["recommendation"] == "safe to export SKP"
    assert review["fidelity_score"] == 0.917
    assert review["hard_fails_count"] == 0
    assert review["warnings_count"] == 1
    assert review["block_skp_export"] is False


def test_compute_pre_skp_review_warn_marginal_fidelity(smoke):
    """Fidelity in [0.69, 0.85) → WARN."""
    fid = _fidelity_report(score=0.78, hard_fails=[], warnings=[])
    review = smoke._compute_pre_skp_review(fid, None, "abc")
    assert review["verdict"] == "WARN"
    assert review["recommendation"] == "review before SKP"


def test_compute_pre_skp_review_warn_too_many_warnings(smoke):
    fid = _fidelity_report(
        score=0.95, hard_fails=[],
        warnings=["w1", "w2", "w3", "w4", "w5"],
    )
    review = smoke._compute_pre_skp_review(fid, None, "abc")
    assert review["verdict"] == "WARN"


def test_compute_pre_skp_review_fail_low_fidelity(smoke):
    fid = _fidelity_report(score=0.50, hard_fails=[], warnings=[])
    review = smoke._compute_pre_skp_review(fid, None, "abc")
    assert review["verdict"] == "FAIL"
    assert review["recommendation"] == "do not export SKP"


def test_compute_pre_skp_review_fail_hard_fail(smoke):
    fid = _fidelity_report(
        score=0.95, hard_fails=["hf:something"], warnings=[],
    )
    review = smoke._compute_pre_skp_review(fid, None, "abc")
    assert review["verdict"] == "FAIL"
    assert review["hard_fails_count"] == 1


def test_compute_pre_skp_review_fail_no_fidelity_report(smoke):
    review = smoke._compute_pre_skp_review(None, None, "abc")
    assert review["verdict"] == "FAIL"
    assert "no_fidelity_report" in review["reasons"]


def test_compute_pre_skp_review_fail_block_skp_export(smoke):
    """Even with PASS fidelity, block_skp_export forces FAIL."""
    fid = _fidelity_report(score=0.95, hard_fails=[], warnings=[])
    doc = _overrides_doc(block=True, block_reason="needs reviewer")
    review = smoke._compute_pre_skp_review(fid, doc, "abc")
    assert review["verdict"] == "FAIL"
    assert review["block_skp_export"] is True


def test_compute_pre_skp_review_fail_sha_mismatch(smoke):
    fid = _fidelity_report(score=0.95, hard_fails=[], warnings=[])
    doc = _overrides_doc(consensus_sha="ff" * 32)
    review = smoke._compute_pre_skp_review(fid, doc, "00" * 32)
    assert review["verdict"] == "FAIL"
    assert any(
        "consensus_sha256_mismatch" in r for r in review["reasons"]
    )


def test_compute_pre_skp_review_warn_high_severity_suspect(smoke):
    """A mark_suspect severity=high in overrides bumps to WARN."""
    fid = _fidelity_report(score=0.95, hard_fails=[], warnings=[])
    ov = _override("mark_suspect", "opening", "o0",
                   payload={"severity": "high", "tag": "needs_review"})
    # Use the matching sha so we don't trigger sha-mismatch FAIL.
    doc = _overrides_doc(overrides=[ov], consensus_sha="abc")
    review = smoke._compute_pre_skp_review(fid, doc, "abc")
    assert review["verdict"] == "WARN"


def test_compute_pre_skp_review_active_overrides_count(smoke):
    fid = _fidelity_report(score=0.95)
    ov1 = _override("approve_element", "opening", "o0")
    ov2 = _override("approve_element", "room", "r0")
    doc = _overrides_doc(overrides=[ov1, ov2])
    review = smoke._compute_pre_skp_review(fid, doc, "abc")
    assert review["active_overrides_count"] == 2


# ---------------------------------------------------------------------------
# gate_f0 with --review-mode=off
# ---------------------------------------------------------------------------


def test_gate_f0_off_mode_passes_on_pass_verdict(smoke, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "fidelity_report.json").write_text(
        json.dumps(_fidelity_report(score=0.917)), encoding="utf-8",
    )
    args = _make_args(smoke, out_dir=out_dir, review_mode="off")
    report = _make_report(smoke, out_dir=str(out_dir),
                          consensus_path=str(out_dir / "c.json"),
                          consensus_sha256="abc")
    g = smoke.gate_f0(args, report)
    assert g.status == "pass"
    assert (out_dir / "pre_skp_review_report.json").exists()
    review = json.loads(
        (out_dir / "pre_skp_review_report.json").read_text("utf-8"),
    )
    assert review["verdict"] == "PASS"


def test_gate_f0_off_mode_passes_on_fail_verdict(smoke, tmp_path):
    """ADR-001 §2.8 table: --review-mode=off ALWAYS passes the gate,
    even when the verdict is FAIL. Only the verdict file changes."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "fidelity_report.json").write_text(
        json.dumps(_fidelity_report(score=0.30)), encoding="utf-8",
    )
    args = _make_args(smoke, out_dir=out_dir, review_mode="off")
    report = _make_report(smoke, out_dir=str(out_dir),
                          consensus_path=str(out_dir / "c.json"),
                          consensus_sha256="abc")
    g = smoke.gate_f0(args, report)
    assert g.status == "pass"  # gate passes regardless
    review = json.loads(
        (out_dir / "pre_skp_review_report.json").read_text("utf-8"),
    )
    assert review["verdict"] == "FAIL"


def test_gate_f0_off_mode_no_fidelity_still_passes(smoke, tmp_path):
    """No fidelity_report.json → verdict=FAIL, but in off-mode the
    gate still passes (advisory)."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    args = _make_args(smoke, out_dir=out_dir, review_mode="off")
    report = _make_report(smoke, out_dir=str(out_dir),
                          consensus_path=str(out_dir / "c.json"),
                          consensus_sha256="abc")
    g = smoke.gate_f0(args, report)
    assert g.status == "pass"
    review = json.loads(
        (out_dir / "pre_skp_review_report.json").read_text("utf-8"),
    )
    assert review["verdict"] == "FAIL"
    assert "no_fidelity_report" in review["reasons"]


# ---------------------------------------------------------------------------
# gate_f0 with --review-mode=warn
# ---------------------------------------------------------------------------


def test_gate_f0_warn_mode_passes_on_warn_verdict(smoke, tmp_path, capsys):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "fidelity_report.json").write_text(
        json.dumps(_fidelity_report(score=0.78)), encoding="utf-8",
    )
    args = _make_args(smoke, out_dir=out_dir, review_mode="warn")
    report = _make_report(smoke, out_dir=str(out_dir),
                          consensus_path=str(out_dir / "c.json"),
                          consensus_sha256="abc")
    g = smoke.gate_f0(args, report)
    assert g.status == "pass"
    err = capsys.readouterr().err
    assert "[WARN]" in err
    review = json.loads(
        (out_dir / "pre_skp_review_report.json").read_text("utf-8"),
    )
    assert review["verdict"] == "WARN"


def test_gate_f0_warn_mode_passes_on_fail_verdict(smoke, tmp_path, capsys):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "fidelity_report.json").write_text(
        json.dumps(_fidelity_report(score=0.30)), encoding="utf-8",
    )
    args = _make_args(smoke, out_dir=out_dir, review_mode="warn")
    report = _make_report(smoke, out_dir=str(out_dir),
                          consensus_path=str(out_dir / "c.json"),
                          consensus_sha256="abc")
    g = smoke.gate_f0(args, report)
    # warn mode never aborts
    assert g.status == "pass"


# ---------------------------------------------------------------------------
# gate_f0 with --review-mode=block
# ---------------------------------------------------------------------------


def test_gate_f0_block_mode_aborts_on_fail_verdict(smoke, tmp_path):
    """ADR-001 §2.8: only --review-mode=block + verdict=FAIL aborts."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "fidelity_report.json").write_text(
        json.dumps(_fidelity_report(score=0.30)), encoding="utf-8",
    )
    args = _make_args(smoke, out_dir=out_dir, review_mode="block")
    report = _make_report(smoke, out_dir=str(out_dir),
                          consensus_path=str(out_dir / "c.json"),
                          consensus_sha256="abc")
    g = smoke.gate_f0(args, report)
    assert g.status == "fail"
    assert "FAIL" in g.message


def test_gate_f0_block_mode_passes_on_warn_verdict(smoke, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "fidelity_report.json").write_text(
        json.dumps(_fidelity_report(score=0.78)), encoding="utf-8",
    )
    args = _make_args(smoke, out_dir=out_dir, review_mode="block")
    report = _make_report(smoke, out_dir=str(out_dir),
                          consensus_path=str(out_dir / "c.json"),
                          consensus_sha256="abc")
    g = smoke.gate_f0(args, report)
    # block mode passes WARN — only FAIL aborts
    assert g.status == "pass"


def test_gate_f0_block_mode_passes_on_pass_verdict(smoke, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "fidelity_report.json").write_text(
        json.dumps(_fidelity_report(score=0.95)), encoding="utf-8",
    )
    args = _make_args(smoke, out_dir=out_dir, review_mode="block")
    report = _make_report(smoke, out_dir=str(out_dir),
                          consensus_path=str(out_dir / "c.json"),
                          consensus_sha256="abc")
    g = smoke.gate_f0(args, report)
    assert g.status == "pass"


# ---------------------------------------------------------------------------
# gate_f0 reads sibling fidelity_report next to consensus
# ---------------------------------------------------------------------------


def test_gate_f0_reads_sibling_fidelity_report(smoke, tmp_path):
    """When out_dir has no fidelity_report.json, gate_f0 falls back to
    the consensus's sibling fidelity_report.json."""
    consensus_dir = tmp_path / "runs" / "feature_run"
    consensus_dir.mkdir(parents=True)
    consensus_path = consensus_dir / "consensus.json"
    consensus_path.write_text("{}", encoding="utf-8")
    (consensus_dir / "fidelity_report.json").write_text(
        json.dumps(_fidelity_report(score=0.917)), encoding="utf-8",
    )
    out_dir = tmp_path / "smoke_out"
    out_dir.mkdir()
    args = _make_args(smoke, out_dir=out_dir, review_mode="off")
    report = _make_report(smoke, out_dir=str(out_dir),
                          consensus_path=str(consensus_path),
                          consensus_sha256="abc")
    g = smoke.gate_f0(args, report)
    assert g.status == "pass"
    review = json.loads(
        (out_dir / "pre_skp_review_report.json").read_text("utf-8"),
    )
    assert review["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# gate_f0 picks up overrides from out_dir
# ---------------------------------------------------------------------------


def test_gate_f0_reads_overrides_doc_from_out_dir(smoke, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "fidelity_report.json").write_text(
        json.dumps(_fidelity_report(score=0.95)), encoding="utf-8",
    )
    doc = _overrides_doc(block=True, block_reason="reviewer says no")
    (out_dir / "review_overrides.json").write_text(
        json.dumps(doc), encoding="utf-8",
    )
    args = _make_args(smoke, out_dir=out_dir, review_mode="off")
    report = _make_report(smoke, out_dir=str(out_dir),
                          consensus_path=str(out_dir / "c.json"),
                          consensus_sha256="abc")
    g = smoke.gate_f0(args, report)
    assert g.status == "pass"  # off-mode never aborts
    review = json.loads(
        (out_dir / "pre_skp_review_report.json").read_text("utf-8"),
    )
    assert review["verdict"] == "FAIL"  # block_skp_export → FAIL
    assert review["block_skp_export"] is True


# ---------------------------------------------------------------------------
# Integration: full pipeline tuple includes gate_f0 before gate_f
# ---------------------------------------------------------------------------


def test_pipeline_tuple_includes_gate_f0_before_gate_f(smoke):
    """Defensive: the pipeline order matters. gate_f0 MUST run before
    gate_f so the verdict is computed before SKP export."""
    # Easiest way: parse main()'s pipeline tuple by reading the source
    # and confirming gate_f0 comes before gate_f. We do it by
    # introspecting the function names in order.
    import inspect
    src = inspect.getsource(smoke.main)
    # Find the 'pipeline = (' line and check ordering
    assert "gate_f0" in src
    f0_idx = src.find("gate_f0")
    f_idx = src.find("gate_f,")  # 'gate_f, gate_g' (with comma)
    assert f0_idx > 0 and f_idx > 0
    assert f0_idx < f_idx, (
        "gate_f0 must come BEFORE gate_f in the pipeline tuple"
    )
