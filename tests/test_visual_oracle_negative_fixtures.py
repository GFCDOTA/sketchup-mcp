"""FP-030 — Negative fixtures must produce FAIL findings.

Proves the deterministic heuristics catch bad input. Each fixture is
a synthetic (consensus.json + geometry_report.json) pair under
`fixtures/visual_oracle_negative/<class>/` that is broken in exactly
one way.

If a fixture stops failing, the heuristic regressed.
"""
from __future__ import annotations

import json
from pathlib import Path

from tools.run_skp_visual_review import (
    axes_verdict_from_findings, inspect_report, top_level_verdict,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
NEG = REPO_ROOT / "fixtures" / "visual_oracle_negative"


def _load(class_name: str) -> tuple[dict, dict]:
    base = NEG / class_name
    rep = json.loads((base / "geometry_report.json").read_text(encoding="utf-8"))
    con = json.loads((base / "consensus.json").read_text(encoding="utf-8"))
    return rep, con


def _find_types(findings: list[dict]) -> set[str]:
    return {f["type"] for f in findings}


# ---- floating_door fixture ------------------------------------------


def test_floating_door_fixture_produces_floating_door_finding():
    rep, con = _load("floating_door")
    findings = inspect_report(rep, con)
    assert "floating_door" in _find_types(findings)


def test_floating_door_fixture_severity_is_FAIL():
    rep, con = _load("floating_door")
    findings = inspect_report(rep, con)
    floating = [f for f in findings if f["type"] == "floating_door"]
    assert all(f["severity"] == "FAIL" for f in floating)


def test_floating_door_fixture_top_level_is_FAIL():
    rep, con = _load("floating_door")
    findings = inspect_report(rep, con)
    axes = axes_verdict_from_findings(findings)
    assert top_level_verdict(findings, axes) == "FAIL"


# ---- orphan_glass fixture --------------------------------------------


def test_orphan_glass_fixture_produces_orphan_glass_finding():
    rep, con = _load("orphan_glass")
    findings = inspect_report(rep, con)
    types = _find_types(findings)
    # Either orphan_glass_panel OR window_count_mismatch is acceptable
    # because the synthetic has 2 glass groups vs 1 window in consensus.
    assert "orphan_glass_panel" in types or "window_count_mismatch" in types


def test_orphan_glass_fixture_top_level_is_FAIL():
    rep, con = _load("orphan_glass")
    findings = inspect_report(rep, con)
    axes = axes_verdict_from_findings(findings)
    assert top_level_verdict(findings, axes) == "FAIL"


# ---- full_height_window fixture --------------------------------------


def test_full_height_window_fixture_produces_height_finding():
    """height_m=2.7 is well outside [0.9, 1.5] range."""
    rep, con = _load("full_height_window")
    findings = inspect_report(rep, con)
    assert "bad_window_aperture" in _find_types(findings)


def test_full_height_window_fixture_produces_z_min_finding():
    """z_min=0 means no peitoril — should trigger full_height_window_void."""
    rep, con = _load("full_height_window")
    findings = inspect_report(rep, con)
    assert "full_height_window_void" in _find_types(findings)


def test_full_height_window_fixture_top_level_is_FAIL():
    rep, con = _load("full_height_window")
    findings = inspect_report(rep, con)
    axes = axes_verdict_from_findings(findings)
    assert top_level_verdict(findings, axes) == "FAIL"


# ---- planta_74 (positive sanity, no negative fixture) ---------------


def test_planta_74_real_fixture_does_NOT_produce_negative_finding_types():
    """Sanity: the real planta_74 build must NOT trip the negative
    heuristics that the synthetic fixtures above exercise."""
    rep_path = (
        REPO_ROOT / "artifacts" / "planta_74" / "geometry_report.json"
    )
    con_path = (
        REPO_ROOT / "fixtures" / "planta_74"
        / "consensus_with_human_walls_and_soft_barriers.json"
    )
    if not rep_path.exists() or not con_path.exists():
        import pytest
        pytest.skip("planta_74 baseline artifacts not present")
    rep = json.loads(rep_path.read_text(encoding="utf-8"))
    con = json.loads(con_path.read_text(encoding="utf-8"))
    findings = inspect_report(rep, con)
    bad_types = {
        "floating_door", "orphan_glass_panel",
        "bad_window_aperture", "full_height_window_void",
        "window_count_mismatch", "door_count_mismatch",
        "glazed_balcony_count_mismatch", "soft_barrier_routed_as_window",
        "duplicate_window_application", "floor_leak",
    }
    triggered = _find_types(findings) & bad_types
    assert not triggered, (
        f"planta_74 real build tripped negative heuristics: {triggered}"
    )
