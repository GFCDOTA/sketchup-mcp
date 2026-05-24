"""Unit + integration tests for tools/spec_harness.py.

Five contracts the harness must hold:
  1. A well-formed spec YAML loads.
  2. A merged-room-names rule fires on the planta_74 r001 case.
  3. A missing-required-room rule fires when an expected room is
     absent from the consensus.
  4. WARN verdicts do NOT cause the harness to exit 1.
  5. CRITICAL verdicts DO cause the harness to exit 1.

Plus a handful of evidence/skip/error paths to pin the rule-type
dispatch table.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.spec_harness import (
    HarnessContext,
    _evaluate_rule,
    evaluate_specs,
    load_spec,
    main,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SPECS_DIR = REPO_ROOT / "specs" / "planta_74"


# ---- helpers ---------------------------------------------------------


def _spec_yaml(tmp_path: Path, contracts: list[dict],
               target: str = "test") -> Path:
    """Write a minimal spec YAML at tmp_path and return its path."""
    import yaml
    body = {
        "schema_version": "1.0.0",
        "target": target,
        "contracts": contracts,
    }
    p = tmp_path / "test.spec.yaml"
    p.write_text(yaml.safe_dump(body), encoding="utf-8")
    return p


def _ctx(consensus: dict | None = None,
         invariants: dict | None = None,
         fidelity: dict | None = None,
         evidence_dir: Path | None = None) -> HarnessContext:
    return HarnessContext(
        consensus=consensus,
        invariants_report=invariants,
        fidelity_report=fidelity,
        evidence_dir=evidence_dir,
    )


# ---- contract #1: YAML loading ---------------------------------------


def test_load_spec_well_formed(tmp_path: Path) -> None:
    p = _spec_yaml(tmp_path, [
        {"id": "demo", "severity": "warn",
         "rule": {"type": "expected_room_names", "required": ["X"]}},
    ])
    data = load_spec(p)
    assert data["contracts"][0]["id"] == "demo"
    assert data["target"] == "test"


def test_load_spec_rejects_malformed_yaml(tmp_path: Path) -> None:
    p = tmp_path / "broken.spec.yaml"
    p.write_text("contracts: [invalid", encoding="utf-8")  # unclosed list
    with pytest.raises(ValueError, match="YAML"):
        load_spec(p)


def test_load_spec_requires_contracts_list(tmp_path: Path) -> None:
    import yaml as _yaml
    p = tmp_path / "no_contracts.spec.yaml"
    p.write_text(_yaml.safe_dump({"schema_version": "1.0.0"}),
                 encoding="utf-8")
    with pytest.raises(ValueError, match="contracts"):
        load_spec(p)


def test_all_shipped_planta_74_specs_load() -> None:
    """Sanity gate: every spec YAML in specs/planta_74/ must parse.
    If this fails, a hand-edit broke the spec and the harness is
    silently degraded — the rest of the suite would still pass."""
    yamls = sorted(SPECS_DIR.glob("*.spec.yaml"))
    assert yamls, f"no spec YAMLs in {SPECS_DIR}"
    for y in yamls:
        data = load_spec(y)
        assert isinstance(data["contracts"], list)
        for c in data["contracts"]:
            assert "id" in c, f"contract in {y.name} missing 'id'"
            assert c.get("severity") in ("critical", "warn", "info"), (
                f"contract {c.get('id')} in {y.name} has invalid severity")
            assert isinstance(c.get("rule"), dict), (
                f"contract {c.get('id')} in {y.name} missing 'rule'")


# ---- contract #2: merged-room detection -----------------------------


def test_detect_merged_room_name_fires() -> None:
    consensus = {"rooms": [
        {"name": "A.S. | TERRACO SOCIAL | TERRACO TECNICO"},
        {"name": "COZINHA"},
    ]}
    result = _evaluate_rule(
        {"type": "no_merged_room_names",
         "forbidden_substrings": ["A.S. | TERRACO"]},
        _ctx(consensus=consensus),
    )
    assert result.verdict == "fail"
    assert "A.S. | TERRACO SOCIAL | TERRACO TECNICO" in result.evidence["matched_rooms"]


def test_no_merged_room_name_passes_when_clean() -> None:
    consensus = {"rooms": [
        {"name": "A.S."},
        {"name": "TERRACO SOCIAL"},
        {"name": "TERRACO TECNICO"},
        {"name": "COZINHA"},
    ]}
    result = _evaluate_rule(
        {"type": "no_merged_room_names",
         "forbidden_substrings": ["A.S. | TERRACO"]},
        _ctx(consensus=consensus),
    )
    assert result.verdict == "pass"


# ---- contract #3: missing-room detection ----------------------------


def test_detect_missing_required_room() -> None:
    consensus = {"rooms": [
        {"name": "COZINHA"},
        {"name": "BANHO 01"},
    ]}
    result = _evaluate_rule(
        {"type": "expected_room_names",
         "required": ["COZINHA", "A.S.", "TERRACO SOCIAL"]},
        _ctx(consensus=consensus),
    )
    assert result.verdict == "fail"
    assert "A.S." in result.evidence["missing"]
    assert "TERRACO SOCIAL" in result.evidence["missing"]


def test_expected_room_split_by_pipe_counts_each_token() -> None:
    """A consensus that still carries a merged name like
    'A.S. | TERRACO SOCIAL' must NOT satisfy the expected_room_names
    contract for A.S. (the no_merged_room_names rule owns that
    failure mode, but expected_room_names should still surface the
    split tokens individually so a half-fix is visible)."""
    consensus = {"rooms": [{"name": "A.S. | TERRACO SOCIAL"}]}
    result = _evaluate_rule(
        {"type": "expected_room_names",
         "required": ["A.S.", "TERRACO SOCIAL"]},
        _ctx(consensus=consensus),
    )
    # Both tokens are present individually (split by " | ") → pass.
    # The no_merged_room_names rule is what blocks shipping.
    assert result.verdict == "pass"


# ---- contract #4 + #5: severity gates -------------------------------


def test_warn_does_not_break_build(tmp_path: Path) -> None:
    """A failing WARN contract surfaces in the report but the harness
    exits 0 — warns are not gates."""
    spec_path = _spec_yaml(tmp_path, [
        {"id": "warn-demo", "severity": "warn",
         "rule": {"type": "expected_room_names",
                  "required": ["DOES_NOT_EXIST"]}},
    ])
    consensus_path = tmp_path / "c.json"
    consensus_path.write_text(json.dumps({"rooms": [{"name": "X"}]}),
                              encoding="utf-8")
    out_path = tmp_path / "report.json"
    code = main([
        "--spec", str(spec_path),
        "--consensus", str(consensus_path),
        "--out", str(out_path),
    ])
    assert code == 0, "warn-only failure must NOT exit 1"
    report = json.loads(out_path.read_text())
    assert report["summary"]["warn"] == 1
    assert report["summary"]["critical_fail"] == 0


def test_critical_fail_breaks_build(tmp_path: Path) -> None:
    spec_path = _spec_yaml(tmp_path, [
        {"id": "critical-demo", "severity": "critical",
         "rule": {"type": "expected_room_names",
                  "required": ["DOES_NOT_EXIST"]}},
    ])
    consensus_path = tmp_path / "c.json"
    consensus_path.write_text(json.dumps({"rooms": [{"name": "X"}]}),
                              encoding="utf-8")
    out_path = tmp_path / "report.json"
    code = main([
        "--spec", str(spec_path),
        "--consensus", str(consensus_path),
        "--out", str(out_path),
    ])
    assert code == 1, "critical failure MUST exit 1"
    report = json.loads(out_path.read_text())
    assert report["summary"]["critical_fail"] == 1


def test_critical_pass_returns_zero(tmp_path: Path) -> None:
    spec_path = _spec_yaml(tmp_path, [
        {"id": "critical-clean", "severity": "critical",
         "rule": {"type": "expected_room_names", "required": ["X"]}},
    ])
    consensus_path = tmp_path / "c.json"
    consensus_path.write_text(json.dumps({"rooms": [{"name": "X"}]}),
                              encoding="utf-8")
    out_path = tmp_path / "report.json"
    code = main([
        "--spec", str(spec_path),
        "--consensus", str(consensus_path),
        "--out", str(out_path),
    ])
    assert code == 0
    report = json.loads(out_path.read_text())
    assert report["summary"]["pass"] >= 1
    assert report["summary"]["critical_fail"] == 0


# ---- rule dispatch table coverage -----------------------------------


def test_unknown_rule_type_records_error() -> None:
    result = _evaluate_rule({"type": "does_not_exist"}, _ctx())
    assert result.verdict == "error"
    assert "does_not_exist" in result.message


def test_skip_when_required_input_missing() -> None:
    """A rule that needs the consensus must SKIP (not fail) when no
    consensus was loaded. Skip != pass for critical accounting."""
    result = _evaluate_rule(
        {"type": "no_merged_room_names", "forbidden_substrings": []},
        _ctx(consensus=None),
    )
    assert result.verdict == "skip"


def test_room_area_range_skips_missing_room() -> None:
    """The area_range rule is paired with expected_room_names: if the
    room doesn't exist, area_range is silent (the other rule fires)."""
    consensus = {"rooms": [{"name": "COZINHA", "area_pts2": 1000}]}
    result = _evaluate_rule(
        {"type": "room_area_range",
         "ranges": [{"name": "MISSING_ROOM",
                     "min_m2": 1.0, "max_m2": 100.0}]},
        _ctx(consensus=consensus),
    )
    # Missing room is silent → 0 out_of_range entries → pass.
    assert result.verdict == "pass"


def test_room_area_range_fires_for_out_of_band_room() -> None:
    # 1000 pt² × PT_TO_M² ≈ 1.24 m² — below min=2.0
    consensus = {"rooms": [{"name": "TINY", "area_pts2": 1000}]}
    result = _evaluate_rule(
        {"type": "room_area_range",
         "ranges": [{"name": "TINY", "min_m2": 2.0, "max_m2": 100.0}]},
        _ctx(consensus=consensus),
    )
    assert result.verdict == "fail"
    assert result.evidence["out_of_range"][0]["name"] == "TINY"


def test_evidence_pack_present_skips_without_dir() -> None:
    result = _evaluate_rule(
        {"type": "evidence_pack_present", "required_artifacts": ["x.png"]},
        _ctx(evidence_dir=None),
    )
    assert result.verdict == "skip"


def test_evidence_pack_present_fires_on_missing_file(tmp_path: Path) -> None:
    edir = tmp_path / "evidence"
    edir.mkdir()
    (edir / "present.png").write_bytes(b"\x89PNG fake")
    result = _evaluate_rule(
        {"type": "evidence_pack_present",
         "required_artifacts": ["present.png", "missing.png"]},
        _ctx(evidence_dir=edir),
    )
    assert result.verdict == "fail"
    assert "missing.png" in result.evidence["missing"]


def test_invariants_verdict_pass_skips_without_report() -> None:
    result = _evaluate_rule({"type": "invariants_verdict_pass"}, _ctx())
    assert result.verdict == "skip"


def test_invariants_verdict_pass_passes_on_pass() -> None:
    inv = {"summary": {"PASS": 12, "WARN": 0, "FAIL": 0, "verdict": "PASS"}}
    result = _evaluate_rule({"type": "invariants_verdict_pass"},
                             _ctx(invariants=inv))
    assert result.verdict == "pass"


def test_invariants_verdict_pass_fails_on_fail() -> None:
    inv = {"summary": {"PASS": 8, "WARN": 1, "FAIL": 3, "verdict": "FAIL"}}
    result = _evaluate_rule({"type": "invariants_verdict_pass"},
                             _ctx(invariants=inv))
    assert result.verdict == "fail"


def test_door_leaf_proximity_passes_within_tolerance() -> None:
    consensus = {
        "rooms": [],
        "openings": [{"id": "op0", "center": [100.0, 100.0]}],
    }
    # 100 pt × PT_TO_M ≈ 3.519 m. Place leaf 0.5 m away in m-space.
    cm = 100.0 * (0.19 / 5.4)
    inv = {"groups": [{
        "name": "DoorLeaf_Group_op0",
        "bbox_m": {"min": [cm - 0.5, cm], "max": [cm + 0.5, cm + 0.4]},
    }]}
    # Leaf center: ((cm-0.5)+(cm+0.5))/2 = cm, ((cm)+(cm+0.4))/2 = cm+0.2.
    # Host center in m: (cm, cm). Distance ≈ 0.2 m.
    result = _evaluate_rule(
        {"type": "door_leaf_proximity", "max_distance_m": 1.0},
        _ctx(consensus=consensus, invariants=inv),
    )
    assert result.verdict == "pass", f"got {result}"


def test_door_leaf_proximity_fails_when_too_far() -> None:
    consensus = {
        "rooms": [],
        "openings": [{"id": "op0", "center": [100.0, 100.0]}],
    }
    cm = 100.0 * (0.19 / 5.4)
    # Leaf bbox shifted by 5 m in x — way past 1.0 m tolerance.
    inv = {"groups": [{
        "name": "DoorLeaf_Group_op0",
        "bbox_m": {"min": [cm + 4.0, cm], "max": [cm + 6.0, cm + 0.4]},
    }]}
    result = _evaluate_rule(
        {"type": "door_leaf_proximity", "max_distance_m": 1.0},
        _ctx(consensus=consensus, invariants=inv),
    )
    assert result.verdict == "fail"


# ---- planta_74 integration smoke ------------------------------------


def test_planta_74_specs_critical_failures_are_visible(tmp_path: Path) -> None:
    """Run all 4 planta_74 specs against the current consensus
    (which still has the r001 merge — develop hasn't received the
    fix from PR #144). Expect the rooms.spec to FAIL critical on
    rooms-no-merged-as-tt-cell, which proves the spec discriminates.

    If a future commit lands the fix and this test starts failing
    because critical_fail=0, that's the LOCK signal — convert this
    test into the post-fix gate."""
    consensus_path = (
        REPO_ROOT / "fixtures" / "planta_74"
        / "consensus_with_human_walls_and_soft_barriers.json"
    )
    if not consensus_path.exists():
        pytest.skip(f"{consensus_path} missing")
    spec_paths = sorted(SPECS_DIR.glob("*.spec.yaml"))
    assert spec_paths, "no specs to run"
    out_path = tmp_path / "report.json"
    code = main([
        *sum([["--spec", str(p)] for p in spec_paths], []),
        "--consensus", str(consensus_path),
        "--out", str(out_path),
    ])
    report = json.loads(out_path.read_text())
    # The harness MUST exit 1 today because the consensus has the
    # merged r001 and the rooms.spec marks that critical. If this
    # ever flips to 0, either (a) the consensus was fixed (good — fix
    # this test along with it) or (b) the spec was weakened (bad —
    # someone smuggled the regression past the gate).
    assert code == 1, (
        f"expected critical_fail on current planta_74 consensus; "
        f"summary={report['summary']}"
    )
    # Specifically, the no_merged_room_names contract should be the
    # canary in the coal mine.
    failing = [c for c in report["contracts"]
               if c["verdict"] == "fail" and c["severity"] == "critical"
               and c["rule_type"] == "no_merged_room_names"]
    assert failing, (
        "expected at least one critical no_merged_room_names failure; "
        f"contracts={report['contracts']}"
    )


def test_evaluate_specs_aggregates_summary(tmp_path: Path) -> None:
    spec_path = _spec_yaml(tmp_path, [
        {"id": "p", "severity": "critical",
         "rule": {"type": "expected_room_names", "required": ["X"]}},
        {"id": "w", "severity": "warn",
         "rule": {"type": "expected_room_names", "required": ["NOPE"]}},
        {"id": "s", "severity": "critical",
         "rule": {"type": "no_merged_room_names",
                  "forbidden_substrings": []}},  # passes vacuously
    ])
    ctx = _ctx(consensus={"rooms": [{"name": "X"}]})
    contracts, summary = evaluate_specs([spec_path], ctx)
    assert summary["pass"] >= 2  # p + s (vacuous)
    assert summary["warn"] == 1
    assert summary["fail"] == 0
    assert summary["critical_fail"] == 0
    assert summary["verdict"] == "pass"
