"""FP-030 — `run_skp_visual_review.py` contract tests (maturity 2).

Verifies CLI flags, oracle bridge probe behavior, and BLOCKED output
without actually running the builder (which requires SU).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.run_skp_visual_review import (
    AXES, ORACLE_BRIDGE_URL, SCHEMA_VERSION, check_oracle_bridge_available,
    classify_maturity, load_known_warnings, worst_verdict,
    write_blocked_summary,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL = REPO_ROOT / "tools" / "run_skp_visual_review.py"


def test_tool_exists():
    assert TOOL.exists()


def test_tool_help_contains_oracle_flag():
    text = TOOL.read_text(encoding="utf-8")
    assert "--oracle" in text
    assert "--require-oracle" in text


def test_tool_help_contains_chatgpt_bridge_choice():
    text = TOOL.read_text(encoding="utf-8")
    assert "chatgpt_bridge" in text


def test_axes_canonical():
    assert AXES == [
        "wall_fidelity", "door_fidelity", "window_fidelity",
        "room_fidelity", "scale_rotation", "global_visual",
    ]


def test_schema_version_canonical():
    assert SCHEMA_VERSION == "visual_findings.v1"


def test_check_oracle_bridge_returns_bool():
    """The probe must not raise even when bridge is unreachable."""
    result = check_oracle_bridge_available(url="http://127.0.0.1:1")
    assert result is False


def test_check_oracle_bridge_default_url():
    """Default URL is exposed and documented."""
    assert ORACLE_BRIDGE_URL.startswith("http://")


def test_write_blocked_summary_creates_files(tmp_path: Path):
    write_blocked_summary(
        tmp_path / "final", "test reason", "echo next",
    )
    findings_doc = json.loads(
        (tmp_path / "final" / "visual_findings.json").read_text(encoding="utf-8")
    )
    assert findings_doc["schema_version"] == "visual_findings.v1"
    assert findings_doc["top_level_verdict"] == "FAIL"
    summary = (tmp_path / "final" / "regression_summary.md").read_text(encoding="utf-8")
    assert "BLOCKED" in summary
    assert "test reason" in summary
    assert "echo next" in summary


# ---- maturity classification ----------------------------------------


def test_maturity_full_pipeline_no_oracle():
    """All artifacts present, no oracle: deterministic mode max ~70%."""
    data, pct = classify_maturity(
        skp_ok=True, renders_ok=True, side_by_side_ok=True,
        deterministic_run=True, oracle_status="n/a",
        fail_findings=0,
    )
    assert 50 <= pct <= 70
    assert any(r["layer"] == "Human review required" for r in data["rows"])


def test_maturity_with_oracle_ok_caps_at_85():
    data, pct = classify_maturity(
        skp_ok=True, renders_ok=True, side_by_side_ok=True,
        deterministic_run=True, oracle_status="ok",
        fail_findings=0,
    )
    assert 70 < pct <= 85


def test_maturity_without_side_by_side_drops_below_70():
    data, pct = classify_maturity(
        skp_ok=True, renders_ok=True, side_by_side_ok=False,
        deterministic_run=True, oracle_status="n/a",
        fail_findings=0,
    )
    # Side-by-side missing should drop significantly
    assert pct < 70


def test_maturity_bridge_unavailable_warn():
    data, pct = classify_maturity(
        skp_ok=True, renders_ok=True, side_by_side_ok=True,
        deterministic_run=True, oracle_status="unavailable",
        fail_findings=0,
    )
    # Bridge requested but unavailable: deterministic-only with WARN flag
    bridge_row = [r for r in data["rows"] if r["layer"] == "Visual oracle bridge"][0]
    assert bridge_row["status"] == "WARN"
    assert pct <= 70


# ---- verdict aggregation --------------------------------------------


def test_worst_verdict_pass_pass_pass():
    assert worst_verdict("PASS", "PASS", "PASS") == "PASS"


def test_worst_verdict_pass_warn_pass():
    assert worst_verdict("PASS", "WARN", "PASS") == "WARN"


def test_worst_verdict_warn_documented_below_warn():
    assert worst_verdict("WARN_documented", "WARN") == "WARN"


def test_worst_verdict_warn_documented_above_pass():
    assert worst_verdict("PASS", "WARN_documented") == "WARN_documented"


def test_worst_verdict_fail_dominates():
    assert worst_verdict("FAIL", "PASS", "WARN_documented") == "FAIL"


def test_worst_verdict_blocked_is_top():
    assert worst_verdict("BLOCKED", "FAIL", "PASS") == "BLOCKED"


def test_worst_verdict_empty_returns_pass():
    assert worst_verdict() == "PASS"


# ---- known_warnings carry policy ------------------------------------


def test_known_warnings_planta_74_present():
    warns = load_known_warnings("planta_74")
    assert isinstance(warns, list)
    assert len(warns) >= 3
    ids = {w.get("id") for w in warns}
    assert "room_fidelity_open_plan" in ids
    assert "sb007_ambiguous" in ids
    assert "sb_sliver_group_1" in ids


def test_known_warnings_unknown_fixture_empty():
    assert load_known_warnings("does_not_exist_fixture_xyz") == []


def test_known_warnings_planta_74_carry_axes():
    warns = load_known_warnings("planta_74")
    for w in warns:
        assert w.get("axis") in {
            "wall_fidelity", "door_fidelity", "window_fidelity",
            "room_fidelity", "scale_rotation", "global_visual",
        }


def test_known_warnings_carry_forces_final_warn_documented_when_oracle_pass():
    """Oracle PASS + planta_74 known warnings = WARN_documented final."""
    warns = load_known_warnings("planta_74")
    assert warns
    final = worst_verdict("PASS", "PASS",
                          "WARN_documented" if warns else "PASS")
    assert final == "WARN_documented"


# ---- final artifact mandatory list ----------------------------------


REQUIRED_FINAL_FILES = [
    "model.skp", "model_top.png", "model_iso.png",
    "side_by_side_pdf_vs_skp.png",
    "geometry_report.json", "visual_findings.json",
    "regression_summary.md",
]


def test_required_final_files_documented_in_tool():
    """The tool docstring or code must mention every required file."""
    text = TOOL.read_text(encoding="utf-8")
    for name in REQUIRED_FINAL_FILES:
        assert name in text, f"required final artifact `{name}` not mentioned in tool"
