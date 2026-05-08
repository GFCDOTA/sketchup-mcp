"""Integration tests for ``cockpit.history_view.pre_skp_review``
reading the F0 gate's ``pre_skp_review_report.json`` (Slice 3 / ADR-001 §4).

Confirms two things:
1. When the F0 report exists in a run dir, ``pre_skp_review`` reads it
   and returns the F0 verdict directly (with ``source="f0_report"``).
2. When the F0 report is absent, the cockpit falls back to the
   Cycle 12f in-memory computation (``source="in_memory"``) — i.e.
   existing behaviour for legacy runs is preserved.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cockpit.history_view import (
    PRE_SKP_PASS_FIDELITY,
    pre_skp_review,
    summarise_run,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _consensus_payload() -> dict:
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "plan_id": "test_fixture",
        "metadata": {
            "git": {"branch": "feature/x", "commit": "abc123"},
            "stage": "5_classify",
            "generated_at": "2026-05-08T10:00:00Z",
            "plan_id": "test_fixture",
        },
        "walls": [
            {"id": "w0", "start": [0, 0], "end": [100, 0],
             "thickness": 5.4, "orientation": "h"},
        ],
        "rooms": [
            {"id": "r0", "name": "SALA",
             "polygon_pts": [[0, 0], [100, 0], [100, 100], [0, 100]],
             "area_pts2": 10000.0},
        ],
        "openings": [],
        "soft_barriers": [],
    }


def _fidelity_payload(score: float = 0.917,
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


def _f0_report(verdict: str = "PASS",
                fidelity: float = 0.917,
                hard_fails: int = 0,
                warnings: int = 0,
                active_overrides: int = 0,
                block_skp_export: bool = False,
                reasons: list[str] | None = None) -> dict:
    if verdict == "PASS":
        rec = "safe to export SKP"
    elif verdict == "WARN":
        rec = "review before SKP"
    else:
        rec = "do not export SKP"
    return {
        "schema_version": "pre_skp_review_v1",
        "verdict": verdict,
        "reasons": reasons or [f"verdict={verdict} from F0 gate"],
        "fidelity_score": fidelity,
        "hard_fails_count": hard_fails,
        "warnings_count": warnings,
        "active_overrides_count": active_overrides,
        "block_skp_export": block_skp_export,
        "recommendation": rec,
    }


def _materialise_run(repo: Path, run_id: str,
                      consensus: dict | None = None,
                      fidelity: dict | None = None,
                      f0: dict | None = None) -> Path:
    rd = repo / "runs" / run_id
    rd.mkdir(parents=True, exist_ok=True)
    if consensus is not None:
        (rd / "consensus_with_room_context.json").write_text(
            json.dumps(consensus), encoding="utf-8",
        )
    if fidelity is not None:
        (rd / "fidelity_report.json").write_text(
            json.dumps(fidelity), encoding="utf-8",
        )
    if f0 is not None:
        (rd / "pre_skp_review_report.json").write_text(
            json.dumps(f0), encoding="utf-8",
        )
    return rd


# ---------------------------------------------------------------------------
# Test 1 — F0 report present → cockpit reads it directly
# ---------------------------------------------------------------------------


def test_pre_skp_review_uses_f0_report_when_present_pass(tmp_path):
    """ADR-001 §4: when pre_skp_review_report.json exists, it is the
    source of truth. Cockpit must NOT recompute."""
    rd = _materialise_run(
        tmp_path, "run_with_f0",
        consensus=_consensus_payload(),
        fidelity=_fidelity_payload(score=0.917),
        f0=_f0_report(verdict="PASS", fidelity=0.917),
    )
    rs = summarise_run(rd, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["status"] == "PASS"
    assert review["source"] == "f0_report"
    assert review["fidelity_score"] == 0.917
    assert review["recommendation"] == "safe"


def test_pre_skp_review_uses_f0_report_when_present_warn(tmp_path):
    rd = _materialise_run(
        tmp_path, "run_with_f0_warn",
        consensus=_consensus_payload(),
        fidelity=_fidelity_payload(score=0.78),
        f0=_f0_report(verdict="WARN", fidelity=0.78,
                       reasons=["fidelity=0.780 < 0.85"]),
    )
    rs = summarise_run(rd, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["status"] == "WARN"
    assert review["source"] == "f0_report"
    assert review["recommendation"] == "review"
    assert any("0.780" in r for r in review["reasons"])


def test_pre_skp_review_uses_f0_report_when_present_fail(tmp_path):
    rd = _materialise_run(
        tmp_path, "run_with_f0_fail",
        consensus=_consensus_payload(),
        fidelity=_fidelity_payload(score=0.30),
        f0=_f0_report(verdict="FAIL", fidelity=0.30, hard_fails=2,
                       reasons=["fidelity below threshold"]),
    )
    rs = summarise_run(rd, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["status"] == "FAIL"
    assert review["source"] == "f0_report"
    assert review["hard_fails_count"] == 2


def test_pre_skp_review_f0_block_flag_surfaces_in_return(tmp_path):
    """When F0 set block_skp_export=true, the cockpit return shape
    surfaces it via f0_block_skp_export so the UI can show the banner."""
    rd = _materialise_run(
        tmp_path, "run_blocked",
        consensus=_consensus_payload(),
        fidelity=_fidelity_payload(score=0.95),
        f0=_f0_report(verdict="FAIL", fidelity=0.95,
                       block_skp_export=True,
                       reasons=["block_skp_export=true (reviewer)"]),
    )
    rs = summarise_run(rd, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["status"] == "FAIL"
    assert review["f0_block_skp_export"] is True


def test_pre_skp_review_f0_active_overrides_count_surfaces(tmp_path):
    rd = _materialise_run(
        tmp_path, "run_with_overrides",
        consensus=_consensus_payload(),
        fidelity=_fidelity_payload(score=0.95),
        f0=_f0_report(verdict="PASS", fidelity=0.95, active_overrides=3),
    )
    rs = summarise_run(rd, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["f0_active_overrides_count"] == 3


# ---------------------------------------------------------------------------
# Test 2 — F0 report absent → fall back to Cycle 12f in-memory logic
# ---------------------------------------------------------------------------


def test_pre_skp_review_falls_back_to_in_memory_when_no_f0(tmp_path):
    """ADR-001 §4: legacy runs without F0 reports must keep their
    Cycle 12f behaviour byte-equivalently."""
    rd = _materialise_run(
        tmp_path, "legacy_run",
        consensus=_consensus_payload(),
        fidelity=_fidelity_payload(score=0.92, warnings=["w1"]),
        f0=None,  # No F0 report — fallback path
    )
    rs = summarise_run(rd, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["status"] == "PASS"
    assert review["source"] == "in_memory"
    assert review["fidelity_score"] == 0.92


def test_pre_skp_review_in_memory_warn_path(tmp_path):
    """Marginal fidelity in 12f's WARN band still flips to WARN
    when the F0 report is missing."""
    rd = _materialise_run(
        tmp_path, "marginal_legacy",
        consensus=_consensus_payload(),
        fidelity=_fidelity_payload(score=0.78),
        f0=None,
    )
    rs = summarise_run(rd, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["status"] == "WARN"
    assert review["source"] == "in_memory"


def test_pre_skp_review_in_memory_fail_path(tmp_path):
    rd = _materialise_run(
        tmp_path, "fail_legacy",
        consensus=_consensus_payload(),
        fidelity=_fidelity_payload(
            score=0.95, hard_fails=["hf:something"]),
        f0=None,
    )
    rs = summarise_run(rd, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["status"] == "FAIL"
    assert review["source"] == "in_memory"


def test_pre_skp_review_in_memory_no_fidelity_report(tmp_path):
    rd = _materialise_run(
        tmp_path, "ungraded",
        consensus=_consensus_payload(),
        fidelity=None,
        f0=None,
    )
    rs = summarise_run(rd, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["status"] == "FAIL"
    assert review["source"] == "in_memory"
    assert any("no fidelity_report" in r for r in review["reasons"])


# ---------------------------------------------------------------------------
# Test 3 — Corrupt F0 report → safe fallback
# ---------------------------------------------------------------------------


def test_pre_skp_review_corrupt_f0_report_falls_back(tmp_path):
    """If pre_skp_review_report.json is unparseable, fall back rather
    than raise."""
    rd = tmp_path / "runs" / "corrupt_f0"
    rd.mkdir(parents=True)
    (rd / "consensus.json").write_text(
        json.dumps(_consensus_payload()), encoding="utf-8",
    )
    (rd / "fidelity_report.json").write_text(
        json.dumps(_fidelity_payload(score=0.917)), encoding="utf-8",
    )
    # Corrupt JSON
    (rd / "pre_skp_review_report.json").write_text(
        "{not valid json", encoding="utf-8",
    )
    rs = summarise_run(rd, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["source"] == "in_memory"
    assert review["status"] == "PASS"


def test_pre_skp_review_unknown_verdict_in_f0_falls_back(tmp_path):
    """If F0 report has a verdict outside {PASS, WARN, FAIL},
    fall back to in-memory."""
    rd = _materialise_run(
        tmp_path, "weird_verdict",
        consensus=_consensus_payload(),
        fidelity=_fidelity_payload(score=0.95),
        f0={"schema_version": "pre_skp_review_v1",
            "verdict": "MAYBE_OK", "reasons": [],
            "fidelity_score": 0.95, "hard_fails_count": 0,
            "warnings_count": 0, "active_overrides_count": 0,
            "block_skp_export": False,
            "recommendation": "?"},
    )
    rs = summarise_run(rd, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["source"] == "in_memory"


# ---------------------------------------------------------------------------
# Test 4 — Return shape compatibility (existing callers still work)
# ---------------------------------------------------------------------------


def test_pre_skp_review_return_shape_has_legacy_keys(tmp_path):
    """Existing UI callers depend on the same keys whether F0 was used
    or not. Both paths must surface status/reasons/recommendation/
    fidelity_score/hard_fails_count/warnings_count/thresholds."""
    EXPECTED = {
        "status", "reasons", "recommendation", "fidelity_score",
        "hard_fails_count", "warnings_count", "thresholds", "source",
    }
    # F0 path
    rd = _materialise_run(
        tmp_path, "f0_path",
        consensus=_consensus_payload(),
        fidelity=_fidelity_payload(score=0.917),
        f0=_f0_report(verdict="PASS"),
    )
    review = pre_skp_review(summarise_run(rd, repo=tmp_path))
    assert EXPECTED.issubset(review.keys())
    # in-memory path
    rd2 = _materialise_run(
        tmp_path, "memory_path",
        consensus=_consensus_payload(),
        fidelity=_fidelity_payload(score=0.917),
        f0=None,
    )
    review2 = pre_skp_review(summarise_run(rd2, repo=tmp_path))
    assert EXPECTED.issubset(review2.keys())


def test_pre_skp_review_thresholds_kwargs_apply_to_in_memory_only(tmp_path):
    """Custom thresholds passed to ``pre_skp_review`` are honoured
    only by the in-memory path. The F0 report path returns the
    pre-computed verdict regardless."""
    rd = _materialise_run(
        tmp_path, "threshold_inmem",
        consensus=_consensus_payload(),
        fidelity=_fidelity_payload(score=0.80),
        f0=None,
    )
    rs = summarise_run(rd, repo=tmp_path)
    review_default = pre_skp_review(rs)
    assert review_default["status"] == "WARN"
    review_loose = pre_skp_review(rs, pass_fidelity=0.75)
    assert review_loose["status"] == "PASS"
