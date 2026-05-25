"""Smoke tests for tools.audit_soft_barriers.

Read-only auditor that classifies soft_barriers per the user-mandated
conservative rules (FP-006 classifies; never deletes). The CLI requires
a source PDF for overlay rendering, so end-to-end CLI is not exercised
here — these tests cover the pure-Python `classify()` function and
its documented decision boundaries, plus `--help` to confirm imports
resolve.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools.audit_soft_barriers import classify

REPO_ROOT = Path(__file__).resolve().parent.parent


def _metrics(*, overlap: float = 0.0, length_m: float = 1.0,
             segs: int = 2, near_wb=None,
             dist_wall_m: float = 0.1) -> dict:
    """Build a minimal metrics dict consumed by classify()."""
    return {
        "overlap_fraction_with_walls": overlap,
        "length_m": length_m,
        "segment_count": segs,
        "near_window_or_balcony_edge": near_wb,
        "distance_to_nearest_wall_m": dist_wall_m,
    }


# ---- classify() decision boundaries ------------------------------------


def test_classify_returns_two_tuple_decision_and_reason() -> None:
    decision, reason = classify(_metrics())
    assert decision in ("keep", "warn", "reject")
    assert isinstance(reason, str) and reason


def test_reject_when_overlap_above_50_percent_fp006() -> None:
    decision, reason = classify(_metrics(overlap=0.60))
    assert decision == "reject"
    assert "FP-006" in reason
    assert "60%" in reason


def test_reject_boundary_at_50_pct_is_not_reject() -> None:
    # rule: reject ONLY when overlap > 0.50 (strict)
    decision, _ = classify(_metrics(overlap=0.50, length_m=3.0, segs=4,
                                    dist_wall_m=0.2))
    assert decision != "reject"


def test_keep_when_short_simple_and_close_to_wall() -> None:
    decision, reason = classify(_metrics(length_m=2.0, segs=5,
                                         dist_wall_m=0.3))
    assert decision == "keep"
    assert "close-to-wall" in reason
    assert "0.30m" in reason


def test_keep_when_near_window_or_balcony_opening() -> None:
    decision, reason = classify(_metrics(length_m=1.0, segs=2,
                                         near_wb=("window-1", 0.05),
                                         dist_wall_m=2.0))
    assert decision == "keep"
    assert "window/balcony" in reason


def test_warn_when_polyline_too_long() -> None:
    decision, reason = classify(_metrics(length_m=8.5, segs=5,
                                         dist_wall_m=0.1))
    assert decision == "warn"
    assert "8.5m polyline" in reason


def test_warn_when_too_many_segments() -> None:
    decision, reason = classify(_metrics(length_m=1.0, segs=20,
                                         dist_wall_m=0.1))
    assert decision == "warn"
    assert "20 segs" in reason


def test_warn_when_far_from_wall_and_no_window() -> None:
    decision, reason = classify(_metrics(length_m=1.0, segs=2,
                                         dist_wall_m=2.5))
    assert decision == "warn"
    assert "not near any window/balcony" in reason
    assert "2.50m from nearest wall" in reason


def test_warn_reason_concatenates_multiple_bits() -> None:
    decision, reason = classify(_metrics(length_m=7.0, segs=25,
                                         dist_wall_m=3.0))
    assert decision == "warn"
    # reason should mention all three problems
    assert "7.0m polyline" in reason
    assert "25 segs" in reason
    assert "3.00m from nearest wall" in reason


# ---- CLI smoke ---------------------------------------------------------


def test_cli_help_loads_cleanly() -> None:
    result = subprocess.run(
        [sys.executable, "tools/audit_soft_barriers.py", "--help"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "soft_barrier" in result.stdout.lower()
    assert "--out" in result.stdout
    assert "--pdf" in result.stdout
    assert "--overlays-dir" in result.stdout


def test_cli_missing_required_args_fails_cleanly() -> None:
    # No args at all -> argparse should exit 2 (usage error)
    result = subprocess.run(
        [sys.executable, "tools/audit_soft_barriers.py"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 2
    assert "consensus" in result.stderr.lower() or "required" in result.stderr.lower()
