"""Tests for gate F0 amended-fidelity preference (Slice 5c).

Boundary: when ``fidelity_report_amended.json`` (Slice 5b) exists in
out_dir, gate F0 PREFERS it over the raw ``fidelity_report.json``.
The verdict uses the post-override score; ``pre_skp_review_report.json``
also surfaces ``fidelity_score_pre_override`` and ``fidelity_delta``
so a review cannot make the score look better without leaving
evidence (ADR-001 §2.10.5).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.smoke.smoke_skp_export import (
    SmokeReport,
    _compute_pre_skp_review,
    gate_f0,
)


def _raw_fidelity_report(score: float = 0.50,
                          hard_fails: list[str] | None = None) -> dict:
    """A 'raw' (pre-override) fidelity report. Default score 0.50
    would force a FAIL verdict — useful to prove the amended
    score (e.g. 0.92) is what F0 actually uses."""
    return {
        "schema_version": "fidelity_v1",
        "global_fidelity": score,
        "sub_scores": {},
        "hard_fails": hard_fails or [],
        "warnings": [],
    }


def _amended_fidelity_report(post: float = 0.92,
                              pre: float = 0.50,
                              hard_fails: list[str] | None = None) -> dict:
    """An 'amended' fidelity report with both pre/post scores per
    ADR-001 §2.10.5. Default values exercise the case where a
    human's overrides lifted the score from FAIL → PASS."""
    return {
        "schema_version": "fidelity_v1",
        "global_fidelity": post,
        "global_fidelity_pre_override": pre,
        "sub_scores": {},
        "hard_fails": hard_fails or [],
        "warnings": [],
        "overrides_applied_count": 1,
    }


def _make_report(tmp_path: Path,
                  consensus_sha: str = "deadbeef" * 8) -> SmokeReport:
    out_dir = tmp_path / "smoke_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    consensus_dir = tmp_path / "consensus_dir"
    consensus_dir.mkdir(parents=True, exist_ok=True)
    consensus_path = consensus_dir / "consensus.json"
    consensus_path.write_text(
        json.dumps({"walls": [], "rooms": [], "openings": []}),
        encoding="utf-8",
    )
    return SmokeReport(
        consensus_path=str(consensus_path),
        out_dir=str(out_dir),
        started_at="2026-05-09T00:00:00Z",
        consensus_sha256=consensus_sha,
    )


def _args(*, review_mode: str = "off") -> argparse.Namespace:
    return argparse.Namespace(
        skip_skp=False,
        force_skp=False,
        review_mode=review_mode,
    )


# ---- _compute_pre_skp_review unit (Slice 5c additive fields) -------

def test_compute_pre_skp_omits_amended_fields_when_using_raw():
    """Default behaviour (using_amended_fidelity=False) leaves the
    pre-override fields out of the dict. Back-compat for any
    consumer that read pre_skp_review_v1 before Slice 5c."""
    rpt = _compute_pre_skp_review(
        _raw_fidelity_report(score=0.92),
        overrides_doc=None,
        consensus_sha="x",
    )
    assert rpt["using_amended_fidelity"] is False
    assert "fidelity_score_pre_override" not in rpt
    assert "fidelity_delta" not in rpt


def test_compute_pre_skp_surfaces_pre_score_when_using_amended():
    rpt = _compute_pre_skp_review(
        _amended_fidelity_report(post=0.92, pre=0.50),
        overrides_doc=None,
        consensus_sha="x",
        using_amended_fidelity=True,
    )
    assert rpt["using_amended_fidelity"] is True
    assert rpt["fidelity_score_pre_override"] == 0.50
    assert rpt["fidelity_score"] == 0.92
    assert rpt["fidelity_delta"] == 0.42


def test_compute_pre_skp_no_pre_field_when_amended_lacks_one():
    """Defensive: if caller flips using_amended_fidelity but the
    report happens not to contain global_fidelity_pre_override,
    the helper still doesn't crash and just omits the field."""
    rpt = _compute_pre_skp_review(
        # Missing pre_override key
        {"schema_version": "fidelity_v1", "global_fidelity": 0.92,
         "hard_fails": [], "warnings": [], "sub_scores": {}},
        overrides_doc=None,
        consensus_sha="x",
        using_amended_fidelity=True,
    )
    assert rpt["using_amended_fidelity"] is True
    assert "fidelity_score_pre_override" not in rpt
    assert "fidelity_delta" not in rpt


# ---- gate_f0 prefers amended when both files exist ------------------

def test_gate_f0_uses_amended_when_present(tmp_path):
    report = _make_report(tmp_path)
    out_dir = Path(report.out_dir)
    # Raw says fidelity=0.50 → would FAIL
    (out_dir / "fidelity_report.json").write_text(
        json.dumps(_raw_fidelity_report(score=0.50)), encoding="utf-8",
    )
    # Amended says fidelity=0.92 → PASS — human's overrides fixed it
    (out_dir / "fidelity_report_amended.json").write_text(
        json.dumps(_amended_fidelity_report(post=0.92, pre=0.50)),
        encoding="utf-8",
    )
    result = gate_f0(_args(), report)
    assert result.status == "pass"
    review = json.loads(
        (out_dir / "pre_skp_review_report.json").read_text(
            encoding="utf-8",
        )
    )
    # Verdict is computed from amended (post=0.92) → PASS
    assert review["verdict"] == "PASS"
    assert review["fidelity_score"] == 0.92
    assert review["using_amended_fidelity"] is True
    # Pre-override score is surfaced — review can't hide it
    assert review["fidelity_score_pre_override"] == 0.50
    assert review["fidelity_delta"] == 0.42


def test_gate_f0_falls_back_to_raw_when_amended_missing(tmp_path):
    report = _make_report(tmp_path)
    out_dir = Path(report.out_dir)
    # Only raw — no amended
    (out_dir / "fidelity_report.json").write_text(
        json.dumps(_raw_fidelity_report(score=0.92)), encoding="utf-8",
    )
    result = gate_f0(_args(), report)
    assert result.status == "pass"
    review = json.loads(
        (out_dir / "pre_skp_review_report.json").read_text(
            encoding="utf-8",
        )
    )
    assert review["fidelity_score"] == 0.92
    assert review["using_amended_fidelity"] is False
    assert "fidelity_score_pre_override" not in review


def test_gate_f0_falls_back_to_raw_when_amended_corrupt(tmp_path, capsys):
    report = _make_report(tmp_path)
    out_dir = Path(report.out_dir)
    # Amended exists but is malformed → fall back to raw, log to stderr
    (out_dir / "fidelity_report_amended.json").write_text(
        "{ not json", encoding="utf-8",
    )
    (out_dir / "fidelity_report.json").write_text(
        json.dumps(_raw_fidelity_report(score=0.92)), encoding="utf-8",
    )
    result = gate_f0(_args(), report)
    assert result.status == "pass"
    review = json.loads(
        (out_dir / "pre_skp_review_report.json").read_text(
            encoding="utf-8",
        )
    )
    assert review["fidelity_score"] == 0.92
    assert review["using_amended_fidelity"] is False
    captured = capsys.readouterr()
    assert "fidelity_report_amended.json failed to parse" in captured.err


def test_gate_f0_uses_amended_post_score_for_verdict_even_when_pre_would_fail(tmp_path):
    """The motivating case: raw fidelity=0.40 (FAIL band), amended
    fidelity=0.95 (PASS band) because the human rejected the bad
    elements. F0 should PASS the verdict, but the pre-override
    score remains visible in the report."""
    report = _make_report(tmp_path)
    out_dir = Path(report.out_dir)
    (out_dir / "fidelity_report.json").write_text(
        json.dumps(_raw_fidelity_report(score=0.40,
                                          hard_fails=["3 phantom openings"])),
        encoding="utf-8",
    )
    (out_dir / "fidelity_report_amended.json").write_text(
        json.dumps(_amended_fidelity_report(post=0.95, pre=0.40,
                                              hard_fails=[])),
        encoding="utf-8",
    )
    result = gate_f0(_args(), report)
    assert result.status == "pass"
    review = json.loads(
        (out_dir / "pre_skp_review_report.json").read_text(
            encoding="utf-8",
        )
    )
    assert review["verdict"] == "PASS"
    assert review["hard_fails_count"] == 0  # amended dropped them
    assert review["fidelity_score"] == 0.95
    assert review["fidelity_score_pre_override"] == 0.40
    assert review["fidelity_delta"] == 0.55


def test_gate_f0_amended_fail_still_fails_in_block_mode(tmp_path):
    """If even after applying overrides the fidelity is still bad,
    F0 in block mode should still FAIL the smoke. This proves the
    Slice 5c preference doesn't accidentally hide bad outcomes."""
    report = _make_report(tmp_path)
    out_dir = Path(report.out_dir)
    (out_dir / "fidelity_report.json").write_text(
        json.dumps(_raw_fidelity_report(score=0.30)), encoding="utf-8",
    )
    (out_dir / "fidelity_report_amended.json").write_text(
        # Amended improves but still in FAIL band
        json.dumps(_amended_fidelity_report(post=0.50, pre=0.30,
                                              hard_fails=[])),
        encoding="utf-8",
    )
    result = gate_f0(_args(review_mode="block"), report)
    assert result.status == "fail", result.message
    review = json.loads(
        (out_dir / "pre_skp_review_report.json").read_text(
            encoding="utf-8",
        )
    )
    assert review["verdict"] == "FAIL"
    assert review["fidelity_score"] == 0.50
    assert review["fidelity_score_pre_override"] == 0.30


def test_review_dict_carries_using_amended_field_in_default_path(tmp_path):
    """The new `using_amended_fidelity` field should appear in the
    output even when raw is used (value False) — schema additivity
    is consistent."""
    report = _make_report(tmp_path)
    out_dir = Path(report.out_dir)
    (out_dir / "fidelity_report.json").write_text(
        json.dumps(_raw_fidelity_report(score=0.92)), encoding="utf-8",
    )
    gate_f0(_args(), report)
    review = json.loads(
        (out_dir / "pre_skp_review_report.json").read_text(
            encoding="utf-8",
        )
    )
    assert "using_amended_fidelity" in review
    assert review["using_amended_fidelity"] is False
