"""Tests for tools/lint_specs.py — spec YAML linter."""
from __future__ import annotations

from pathlib import Path

import yaml

from tools.lint_specs import lint_dir, lint_one, main

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write(path: Path, body: dict) -> None:
    path.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")


def test_live_repo_specs_pass(tmp_path: Path) -> None:
    """Every shipped spec must lint clean — if a hand-edit breaks one,
    this is the gate that catches it before CI."""
    specs = REPO_ROOT / "specs"
    if not specs.exists():
        import pytest
        pytest.skip("live specs/ not present in test env")
    errors, _, _ = lint_dir(specs)
    assert errors == [], errors


def test_well_formed_spec_passes(tmp_path: Path) -> None:
    p = tmp_path / "demo.spec.yaml"
    _write(p, {
        "schema_version": "1.0.0",
        "target": "x",
        "contracts": [
            {"id": "c1", "severity": "warn",
             "description": "demo",
             "rule": {"type": "expected_room_names", "required": []}},
        ],
    })
    errors, warnings = lint_one(p)
    assert errors == []
    assert warnings == []


def test_malformed_yaml_is_error(tmp_path: Path) -> None:
    p = tmp_path / "broken.spec.yaml"
    p.write_text("contracts: [oops", encoding="utf-8")
    errors, _ = lint_one(p)
    assert errors
    assert "YAML parse error" in errors[0]


def test_missing_contracts_key(tmp_path: Path) -> None:
    p = tmp_path / "no_contracts.spec.yaml"
    _write(p, {"schema_version": "1.0.0", "target": "x"})
    errors, _ = lint_one(p)
    assert any("missing required top-level key" in e and "contracts" in e
               for e in errors)


def test_unknown_rule_type_is_error(tmp_path: Path) -> None:
    p = tmp_path / "demo.spec.yaml"
    _write(p, {
        "schema_version": "1.0.0",
        "target": "x",
        "contracts": [
            {"id": "c1", "severity": "warn", "description": "d",
             "rule": {"type": "no_such_rule"}},
        ],
    })
    errors, _ = lint_one(p)
    assert any("unknown rule type" in e for e in errors)


def test_invalid_severity_is_error(tmp_path: Path) -> None:
    p = tmp_path / "demo.spec.yaml"
    _write(p, {
        "schema_version": "1.0.0",
        "target": "x",
        "contracts": [
            {"id": "c1", "severity": "blocker",  # not in {critical, warn, info}
             "description": "d",
             "rule": {"type": "expected_room_names", "required": []}},
        ],
    })
    errors, _ = lint_one(p)
    assert any("severity" in e and "blocker" in e for e in errors)


def test_duplicate_id_in_same_file_is_error(tmp_path: Path) -> None:
    p = tmp_path / "demo.spec.yaml"
    _write(p, {
        "schema_version": "1.0.0",
        "target": "x",
        "contracts": [
            {"id": "c1", "severity": "warn", "description": "a",
             "rule": {"type": "expected_room_names", "required": []}},
            {"id": "c1", "severity": "warn", "description": "b",
             "rule": {"type": "expected_room_names", "required": []}},
        ],
    })
    errors, _ = lint_one(p)
    assert any("duplicates an earlier contract id" in e for e in errors)


def test_global_id_collision_across_files(tmp_path: Path) -> None:
    """The same contract id in TWO different spec files breaks the
    KNOWN_FP_SPEC_LINKS references (which key on id alone). The
    linter must surface that case."""
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    body = {
        "schema_version": "1.0.0",
        "target": "x",
        "contracts": [
            {"id": "shared-id", "severity": "warn", "description": "d",
             "rule": {"type": "expected_room_names", "required": []}},
        ],
    }
    _write(specs_dir / "a.spec.yaml", body)
    _write(specs_dir / "b.spec.yaml", body)
    errors, _, _ = lint_dir(specs_dir)
    assert any("globally unique" in e for e in errors)


def test_missing_description_is_warning(tmp_path: Path) -> None:
    p = tmp_path / "demo.spec.yaml"
    _write(p, {
        "schema_version": "1.0.0",
        "target": "x",
        "contracts": [
            # no 'description' field
            {"id": "c1", "severity": "warn",
             "rule": {"type": "expected_room_names", "required": []}},
        ],
    })
    errors, warnings = lint_one(p)
    assert errors == []
    assert any("missing 'description'" in w for w in warnings)


def test_strict_warns_promotes_to_error(tmp_path: Path) -> None:
    """--strict-warns must turn warning-only specs into exit 1."""
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    _write(specs_dir / "demo.spec.yaml", {
        "schema_version": "1.0.0",
        "target": "x",
        "contracts": [
            {"id": "c1", "severity": "warn",
             # no description → warning, not error
             "rule": {"type": "expected_room_names", "required": []}},
        ],
    })
    # Without strict-warns: exit 0
    assert main(["--specs-dir", str(specs_dir)]) == 0
    # With strict-warns: exit 1
    assert main(["--specs-dir", str(specs_dir), "--strict-warns"]) == 1


def test_main_returns_1_on_nonexistent_specs_dir(tmp_path: Path) -> None:
    nonexistent = tmp_path / "nope"
    assert main(["--specs-dir", str(nonexistent)]) == 1
