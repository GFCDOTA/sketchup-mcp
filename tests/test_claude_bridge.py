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


# ---- session liveness orchestrator (heartbeat) ----------------------


def test_heartbeat_progressing_is_ok():
    import tools.claude_bridge.server as srv
    srv._SESSIONS.clear()
    srv.record_heartbeat("sess-A", 1)
    srv.record_heartbeat("sess-A", 2)  # cycle advanced -> progressing
    v = srv.sessions_view()["sess-A"]
    assert v["cycle"] == 2
    assert v["flags"] == ["OK"]


def test_heartbeat_frozen_cycle_is_paralyzed():
    import tools.claude_bridge.server as srv
    srv._SESSIONS.clear()
    for _ in range(srv.PARALYZED_M + 1):
        srv.record_heartbeat("sess-B", 7)  # same cycle every beat -> stuck
    assert "PARALYZED" in srv.sessions_view()["sess-B"]["flags"]


def test_heartbeat_stalled_when_silent(monkeypatch):
    import tools.claude_bridge.server as srv
    srv._SESSIONS.clear()
    srv.record_heartbeat("sess-C", 1)
    monkeypatch.setattr(srv, "STALL_SECONDS", -1)  # make any age count as "too old"
    assert "STALLED" in srv.sessions_view()["sess-C"]["flags"]


# ---- operational dashboard ------------------------------------------


def test_health_has_model_effort_uptime():
    import tools.claude_bridge.server as srv
    h = srv.health_payload()
    assert h["model"] == "claude-opus-4-8"
    assert h["effort"] == "xhigh"
    assert "uptime_sec" in h
    assert "/" in h["endpoints"] and "/events" in h["endpoints"]


def test_dashboard_html_is_a_page():
    import tools.claude_bridge.server as srv
    assert srv.DASHBOARD_HTML.lstrip().startswith("<!doctype html>")
    assert "Claude Gate" in srv.DASHBOARD_HTML
    assert "/sessions" in srv.DASHBOARD_HTML and "/events" in srv.DASHBOARD_HTML


def test_recent_events_parses_tail_skips_garbage(tmp_path, monkeypatch):
    import tools.claude_bridge.server as srv
    p = tmp_path / "audit.jsonl"
    p.write_text(
        '{"kind":"heartbeat","cycle":1}\nNOT JSON\n{"kind":"consult","mode":"redteam"}\n',
        encoding="utf-8")
    monkeypatch.setattr(srv, "AUDIT_PATH", p)
    ev = srv.recent_events()
    assert len(ev) == 2  # garbage line skipped, not crashed
    assert ev[-1]["kind"] == "consult"


# ---- multi-page app: inventory, plant, artifact serving -------------


def test_skp_inventory_shape():
    import tools.claude_bridge.server as srv
    inv = srv.skp_inventory()
    assert "total" in inv and "total_mb" in inv and "categories" in inv
    assert {"deliverable", "review_evidence", "runs_scratch", "fixtures",
            "other"} == set(inv["categories"])


def test_dashboard_html_serves_the_spa():
    import tools.claude_bridge.server as srv
    html = srv.dashboard_html()
    assert "<!doctype html>" in html.lower()
    assert "SketchUp Creator" in html
    # SPA tabs present (the inline fallback has none of these)
    assert "#lixao" in html and "#sessoes" in html and "#ecossistema" in html


def test_safe_artifact_blocks_escape_and_nonimage():
    import tools.claude_bridge.server as srv
    assert srv.safe_artifact("../../etc/passwd") is None            # traversal
    assert srv.safe_artifact("tools/claude_bridge/server.py") is None  # outside artifacts
    assert srv.safe_artifact("artifacts/notes.txt") is None         # under artifacts, non-image
    assert srv.safe_artifact("../.oauth_token") is None             # secret via traversal


def test_claude_sessions_shape():
    import tools.claude_bridge.server as srv
    d = srv.claude_sessions()
    assert {"sessions", "pending_gate", "total"} <= set(d)
    assert isinstance(d["sessions"], list) and isinstance(d["pending_gate"], list)


def test_ecosystem_shape():
    import tools.claude_bridge.server as srv
    d = srv.ecosystem()
    assert "items" in d and "root" in d and isinstance(d["items"], list)


def test_recent_commits_shape():
    import tools.claude_bridge.server as srv
    d = srv.recent_commits()
    assert "commits" in d and isinstance(d["commits"], list)
