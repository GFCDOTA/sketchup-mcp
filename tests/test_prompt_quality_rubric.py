"""Structural test for the prompt quality rubric.

Pins the shape of `docs/learning/prompt_quality_rubric.md` so future PRs
can't silently gut the rubric. Pure stdlib + pytest, no new deps.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RUBRIC = REPO_ROOT / "docs" / "learning" / "prompt_quality_rubric.md"

CRITERIA = [
    "Sufficient context",
    "Explicit goal",
    "Clear action verb",
    "Allowed scope",
    "Forbidden scope",
    "Constraints",
    "Sequential steps",
    "Output format",
    "Mandatory validation",
    "Stop criteria",
    "Rollback",
    "Before/after evidence",
    "When to ask the human",
    "When to proceed autonomously",
    "When only to document",
]

CHECKLIST_PHRASES = [
    "Avoids ambiguity",
    "Limits allowed files",
    "Defines branch + PR base",
    "Defines validation commands",
    "Names what NOT to do",
    "Defines final output shape",
    "One PR = one idea",
    "Requires before/after evidence",
]

CONTRACT_FIELDS = [
    "Context:",
    "Goal:",
    "Allowed files:",
    "Forbidden files:",
    "Steps:",
    "Validation:",
    "Stop conditions:",
    "PR body:",
    "Final output:",
]


@pytest.fixture(scope="module")
def rubric_text() -> str:
    assert RUBRIC.exists(), f"rubric file missing: {RUBRIC}"
    return RUBRIC.read_text(encoding="utf-8")


def test_rubric_has_15_criteria(rubric_text: str) -> None:
    lower = rubric_text.lower()
    missing = [c for c in CRITERIA if c.lower() not in lower]
    assert not missing, f"missing criterion headings: {missing}"


def test_rubric_has_8_checklist_items(rubric_text: str) -> None:
    missing = [p for p in CHECKLIST_PHRASES if p not in rubric_text]
    assert not missing, f"missing checklist phrases: {missing}"


def test_rubric_has_contract_template(rubric_text: str) -> None:
    missing = [f for f in CONTRACT_FIELDS if f not in rubric_text]
    assert not missing, f"missing contract fields: {missing}"


def test_rubric_no_copyright_leak(rubric_text: str) -> None:
    lower = rubric_text.lower()
    forbidden = ["mike reuben", "prompts que fazem"]
    leaked = [t for t in forbidden if t in lower]
    assert not leaked, f"copyright leak in rubric: {leaked}"
