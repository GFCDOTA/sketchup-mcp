"""Tests for tools.assumptions_loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.assumptions_loader import (
    ASSUMPTIONS_SCHEMA_VERSION,
    DEFAULT_ASSUMPTIONS_PATH,
    AmbiguityPolicy,
    load_assumptions,
)


def test_default_assumptions_yaml_loads():
    a = load_assumptions(DEFAULT_ASSUMPTIONS_PATH)
    assert a.schema_version == ASSUMPTIONS_SCHEMA_VERSION
    assert a.goal in {"furniture_layout", "visual_review", "as_built"}
    assert a.risk_policy in {"conservative", "balanced", "aggressive"}
    assert isinstance(a.ambiguity, AmbiguityPolicy)


def test_ambiguity_policy_thresholds_monotonic():
    a = load_assumptions(DEFAULT_ASSUMPTIONS_PATH)
    p = a.ambiguity
    assert 0.0 <= p.drop_below <= p.debug_above <= p.clean_above <= 1.0


@pytest.mark.parametrize("conf,expected", [
    (0.05, "drop"),
    (0.20, "ask"),
    (0.49, "ask"),
    (0.50, "debug"),
    (0.74, "debug"),
    (0.75, "clean"),
    (0.99, "clean"),
])
def test_ambiguity_policy_decide_routes_correctly(conf, expected):
    p = AmbiguityPolicy()
    assert p.decide(conf) == expected


def test_strict_blockers_present_in_default():
    a = load_assumptions(DEFAULT_ASSUMPTIONS_PATH)
    # Stage 1 default config lists at least these blockers
    expected_subset = {
        "opening_decision_ask",
        "opening_decision_drop",
        "floating_door",
    }
    assert expected_subset.issubset(set(a.strict_blockers))


def test_unsupported_schema_version_raises(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text("schema_version: '99.0'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        load_assumptions(p)


def test_thresholds_out_of_order_raises(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text(
        "schema_version: '1.0'\n"
        "ambiguity:\n"
        "  drop_below: 0.8\n"
        "  debug_above: 0.5\n"
        "  clean_above: 0.7\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="thresholds"):
        load_assumptions(p)


def test_missing_file_raises(tmp_path: Path):
    p = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError):
        load_assumptions(p)
