"""Gate framework §6.5 — claude-bridge /ask + /health robustness.

Pure parser/contract tests (no `claude` binary, no live server needed).
"""
from __future__ import annotations

import json

from tools.claude_bridge.server import (
    ASK_FIELDS,
    VERDICT_ENUM,
    apply_mode,
    health_payload,
    parse_ask_mode,
    parse_ask_payload,
)


def _body(d: dict) -> bytes:
    return json.dumps(d, ensure_ascii=False).encode("utf-8")


def test_parse_prompt_field():
    assert parse_ask_payload(_body({"prompt": "decide A vs B"})) == "decide A vs B"


def test_parse_question_field_accepted():
    # flexible field: the caller shouldn't have to guess 'prompt'
    assert parse_ask_payload(_body({"question": "decide A vs B"})) == "decide A vs B"


def test_parse_prefers_prompt_over_question():
    assert parse_ask_payload(_body({"prompt": "p", "question": "q"})) == "p"


def test_parse_utf8_non_ascii_does_not_crash():
    # the exact byte class that 500'd the bridge once (ã in "NÃO")
    assert parse_ask_payload(_body({"prompt": "NÃO PARE — siga"})) == "NÃO PARE — siga"


def test_parse_invalid_utf8_byte_is_replaced_not_raised():
    raw = b'{"prompt": "ab\xc3 cd"}'  # lone 0xc3 continuation byte
    out = parse_ask_payload(raw)       # must NOT raise
    assert "ab" in out and "cd" in out


def test_parse_empty_returns_blank():
    assert parse_ask_payload(b"") == ""
    assert parse_ask_payload(_body({"prompt": ""})) == ""
    assert parse_ask_payload(_body({})) == ""
    assert parse_ask_payload(_body({"prompt": "   "})) == ""


def test_health_exposes_contract():
    h = health_payload()
    assert h["status"] == "ok"
    assert h["oracle"] == "claude"
    assert h["ask_field"] == list(ASK_FIELDS)
    assert "prompt" in h["ask_field"] and "question" in h["ask_field"]
    assert set(h["verdict_enum"]) == set(VERDICT_ENUM)
    assert "VISUAL_REVIEW" in h["verdict_enum"]


# ---- §6.2 red-team mode ----
def test_parse_ask_mode_redteam():
    assert parse_ask_mode(_body({"prompt": "q", "mode": "redteam"})) == "redteam"
    assert parse_ask_mode(_body({"prompt": "q", "mode": "REDTEAM"})) == "redteam"


def test_parse_ask_mode_default_blank():
    assert parse_ask_mode(_body({"prompt": "q"})) == ""
    assert parse_ask_mode(b"") == ""


def test_apply_mode_redteam_prepends_steelman():
    out = apply_mode("Should we do A or B?", "redteam")
    assert "AGAINST" in out
    assert "Should we do A or B?" in out
    assert len(out) > len("Should we do A or B?")


def test_apply_mode_default_is_noop():
    assert apply_mode("Q", "") == "Q"
    assert apply_mode("Q", "whatever") == "Q"


def test_health_advertises_redteam_mode():
    assert "redteam" in health_payload()["modes"]
