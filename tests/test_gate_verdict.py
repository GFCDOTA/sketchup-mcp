"""Gate framework §6.4 — Verdict parser (confidence + assumptions)."""
from __future__ import annotations

from tools.gate_verdict import ANSWER_FORMAT, VERDICT_ENUM, parse_verdict

SAMPLE = """- Verdict: GO
- Confidence: medium
- Reasoning: Option B fixes the root cause; the merge is clean.
- Assumptions:
  - the SKP faces come from the polygon (NOT verified from the prompt)
  - no downstream fixture references the old wall ids
- Risks:
  - merging could eat a real corner if tolerance is loose
- Suggested next action: implement B, then run the detectors
"""


def test_parses_all_fields():
    v = parse_verdict(SAMPLE)
    assert v["verdict"] == "GO"
    assert v["confidence"] == "medium"
    assert len(v["assumptions"]) == 2
    assert "SKP faces" in v["assumptions"][0]
    assert v["risks"] and "corner" in v["risks"][0]
    assert "root cause" in v["reasoning"]
    assert "implement B" in v["next_action"]


def test_no_go_not_confused_with_go():
    assert parse_verdict("- Verdict: NO-GO\n- Reasoning: x")["verdict"] == "NO-GO"


def test_visual_review_both_spellings():
    assert parse_verdict("Verdict: VISUAL_REVIEW")["verdict"] == "VISUAL_REVIEW"
    assert parse_verdict("- **Verdict**: VISUAL-REVIEW")["verdict"] == "VISUAL_REVIEW"


def test_bold_and_numbered_tolerant():
    v = parse_verdict("1. **Verdict:** GO\n2. **Confidence:** HIGH")
    assert v["verdict"] == "GO"
    assert v["confidence"] == "high"


def test_missing_fields_safe():
    v = parse_verdict("just unstructured text, no verdict here")
    assert v["verdict"] is None
    assert v["confidence"] is None
    assert v["assumptions"] == []
    assert v["risks"] == []


def test_answer_format_advertises_new_fields():
    assert "Confidence" in ANSWER_FORMAT
    assert "Assumptions" in ANSWER_FORMAT
    assert "VISUAL_REVIEW" in ANSWER_FORMAT
    for v in VERDICT_ENUM:
        assert v in ANSWER_FORMAT
