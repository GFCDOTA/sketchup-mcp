"""Regression: validator/vision.py:_build_prompt must not leak GT.

CLAUDE.md §2.6: scores are observational only; the prompt must not
hardcode the ground-truth area of any fixture (e.g. planta_74).
"""
from pathlib import Path

from validator.scorers.base import ScorerContext
from validator.vision import _build_prompt


def _ctx(expected_area_m2=None):
    return ScorerContext(
        repo_root=Path("/tmp/repo"),
        entry={"kind": "axon"},
        consensus={"walls": [], "rooms": [], "openings": []},
        inspect_report=None,
        expected_area_m2=expected_area_m2,
    )


def test_default_prompt_has_no_hardcoded_planta_74_area():
    """Default prompt (no expected_area_m2) must not say '74 m2'."""
    p = _build_prompt({"kind": "axon"}, _ctx())
    assert "74 m2" not in p
    assert "74m2" not in p
    assert "planta_74" not in p
    assert "arquitetonica" in p  # generic fallback


def test_prompt_includes_expected_area_when_provided():
    p = _build_prompt({"kind": "axon"}, _ctx(expected_area_m2=120.0))
    assert "120" in p
    assert "m2" in p


def test_expected_area_does_not_inject_74_by_default():
    p = _build_prompt({"kind": "axon"}, _ctx())
    # Defensive: even substring match for the leaked literal must be absent
    assert " 74 " not in p
    assert "de 74" not in p
