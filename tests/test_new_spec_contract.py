"""Tests for tools/new_spec_contract.py — scaffolding."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tools.new_spec_contract import (
    _RULE_SKELETONS,
    main,
    scaffold,
)


def test_scaffold_creates_new_spec_file(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    p, created = scaffold(
        specs, planta="planta_x", aspect="rooms",
        contract_id="rooms-test-1", severity="warn",
        rule_type="expected_room_names",
    )
    assert created is True
    assert p == specs / "planta_x" / "rooms.spec.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0.0"
    assert data["target"] == "planta_x"
    assert len(data["contracts"]) == 1
    c = data["contracts"][0]
    assert c["id"] == "rooms-test-1"
    assert c["severity"] == "warn"
    assert c["rule"]["type"] == "expected_room_names"
    assert "required" in c["rule"]  # skeleton merged in


def test_scaffold_appends_to_existing_file(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    scaffold(specs, "p", "rooms", "c1", "warn", "expected_room_names")
    p, created = scaffold(
        specs, "p", "rooms", "c2", "critical",
        rule_type="no_merged_room_names",
    )
    assert created is False
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    ids = [c["id"] for c in data["contracts"]]
    assert ids == ["c1", "c2"]


def test_scaffold_rejects_id_collision_without_force(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    scaffold(specs, "p", "rooms", "c1", "warn", "expected_room_names")
    with pytest.raises(ValueError, match="already exists"):
        scaffold(specs, "p", "rooms", "c1", "warn", "expected_room_names")


def test_scaffold_replaces_with_force(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    scaffold(specs, "p", "rooms", "c1", "warn", "expected_room_names")
    p, _ = scaffold(specs, "p", "rooms", "c1", "critical",
                     "no_merged_room_names", force=True)
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert len(data["contracts"]) == 1  # not duplicated
    assert data["contracts"][0]["severity"] == "critical"
    assert data["contracts"][0]["rule"]["type"] == "no_merged_room_names"


def test_scaffold_rejects_unknown_rule_type(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    with pytest.raises(ValueError, match="unknown rule type"):
        scaffold(specs, "p", "rooms", "c1", "warn", "no_such_rule")


def test_scaffold_rejects_invalid_severity(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    with pytest.raises(ValueError, match="severity"):
        scaffold(specs, "p", "rooms", "c1", "blocker",
                  "expected_room_names")


def test_all_dispatched_rule_types_have_skeleton() -> None:
    """Adding a new rule type to spec_harness should also add a
    skeleton here so the scaffolder doesn't emit empty rule bodies."""
    from tools.spec_harness import _RULE_DISPATCHERS
    missing = set(_RULE_DISPATCHERS) - set(_RULE_SKELETONS)
    assert not missing, (
        f"new rule types in spec_harness have no scaffold skeleton: "
        f"{sorted(missing)}"
    )


def test_cli_creates_spec(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    code = main([
        "--specs-dir", str(specs),
        "--planta", "planta_y",
        "--aspect", "openings",
        "--id", "openings-test-cli",
        "--severity", "warn",
        "--rule-type", "openings_count_range",
    ])
    assert code == 0
    p = specs / "planta_y" / "openings.spec.yaml"
    assert p.exists()


def test_cli_rejects_collision(tmp_path: Path) -> None:
    specs = tmp_path / "specs"
    main(["--specs-dir", str(specs), "--planta", "p",
          "--aspect", "rooms", "--id", "c1",
          "--severity", "warn", "--rule-type", "expected_room_names"])
    code = main(["--specs-dir", str(specs), "--planta", "p",
                  "--aspect", "rooms", "--id", "c1",
                  "--severity", "warn",
                  "--rule-type", "expected_room_names"])
    assert code == 1


def test_scaffolded_spec_passes_lint(tmp_path: Path) -> None:
    """A freshly-scaffolded spec must pass tools.lint_specs without
    errors — there should be NO impedance mismatch between the
    scaffolder's output and the linter's expectations. (Warnings
    are tolerated — the description is intentionally a TODO until
    the operator fills it in, but the linter only WARNs on missing
    description so the freshly-scaffolded spec doesn't trigger a
    warning since the scaffolder emits a TODO description.)"""
    from tools.lint_specs import lint_dir
    specs = tmp_path / "specs"
    scaffold(specs, "p", "rooms", "c1", "warn", "expected_room_names")
    errors, warnings, _ = lint_dir(specs)
    assert errors == [], errors
    # The TODO description IS present (non-empty) so no warning.
    assert warnings == [], warnings
