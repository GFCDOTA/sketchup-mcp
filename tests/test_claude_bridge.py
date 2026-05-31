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


def test_gate_ledger_shape_and_invariant():
    import tools.claude_bridge.server as srv
    d = srv.gate_ledger()
    assert {"entries", "total", "answered", "pending"} <= set(d)
    assert d["total"] == d["answered"] + d["pending"]


def test_extract_verdict():
    import tools.claude_bridge.server as srv
    assert srv._extract_verdict("- Verdict: GO\n- Confidence: high") == "GO"
    assert srv._extract_verdict("Verdict: NO-GO\n...") == "NO-GO"
    assert srv._extract_verdict("- Verdict: VISUAL_REVIEW") == "VISUAL_REVIEW"
    assert srv._extract_verdict("nada de veredito aqui") is None


def test_system_map_shape():
    import tools.claude_bridge.server as srv
    d = srv.system_map()
    assert {"items", "root", "unknown"} <= set(d)
    for i in d["items"]:
        assert {"name", "type", "expl", "risk", "can_delete", "mb"} <= set(i)


def test_classify_dir_known_and_unknown(tmp_path):
    import tools.claude_bridge.server as srv
    assert srv._classify_dir(tmp_path / "wt-foo")["type"] == "WORKTREE"
    assert srv._classify_dir(tmp_path / "sketchup-mcp")["type"] == "CANONICAL_REPO"
    assert srv._classify_dir(tmp_path / "zxqv-random")["type"] == "UNKNOWN"


def test_git_inventory_shape_no_crash():
    import tools.claude_bridge.server as srv
    d = srv.git_inventory()
    assert {"repos", "dirty"} <= set(d) and isinstance(d["repos"], list)
    for r in d["repos"]:  # dirs without .git are skipped, so no crash
        assert {"path", "branch", "dirty", "untracked"} <= set(r)


def test_sha256_identical_content_same_hash(tmp_path):
    import tools.claude_bridge.server as srv
    a = tmp_path / "a.skp"; b = tmp_path / "b.skp"; c = tmp_path / "c.skp"
    a.write_bytes(b"SAME-BYTES-XYZ"); b.write_bytes(b"SAME-BYTES-XYZ")
    c.write_bytes(b"different")
    assert srv._sha256(a) == srv._sha256(b)
    assert srv._sha256(a) != srv._sha256(c)


def test_dedup_by_hash_groups_and_keeper():
    import tools.claude_bridge.server as srv
    files = [
        {"path": "sketchup-mcp/artifacts/p/p.skp", "sha": "AAA", "git": "tracked"},
        {"path": "sketchup-mcp/runs/p/model.skp", "sha": "AAA", "git": "ignored"},
        {"path": "wt-gh/artifacts/review/x.skp", "sha": "BBB", "git": "tracked"},
    ]
    srv._dedup_and_classify(files)
    by = {f["path"]: f for f in files}
    assert by["sketchup-mcp/artifacts/p/p.skp"]["category"] == "CANONICAL_DELIVERABLE"
    assert by["sketchup-mcp/artifacts/p/p.skp"]["action"] == "KEEP"
    # same hash as the canonical -> the runs/ copy is a DUPLICATE, not a separate file
    assert by["sketchup-mcp/runs/p/model.skp"]["category"] == "DUPLICATE"
    assert by["sketchup-mcp/runs/p/model.skp"]["dup_of"] == "sketchup-mcp/artifacts/p/p.skp"
    assert by["sketchup-mcp/runs/p/model.skp"]["action"] == "DELETE_CANDIDATE"
    assert by["wt-gh/artifacts/review/x.skp"]["category"] == "REVIEW_ARTIFACT"


def test_skp_inventory_v2_shape():
    import tools.claude_bridge.server as srv
    d = srv.skp_inventory_v2()
    assert {"total", "total_mb", "dup_groups", "by_category", "files"} <= set(d)
    assert isinstance(d["files"], list)


def test_difficulties_every_entry_has_why_not_fixed():
    import tools.claude_bridge.server as srv
    d = srv.difficulties()
    assert {"difficulties", "total", "source"} <= set(d)
    assert d["total"] >= 6
    for x in d["difficulties"]:
        assert x["why_not_fixed_yet"]  # mandatory + non-empty in EVERY entry
        assert {"id", "titulo", "status", "severidade", "acceptance_criteria"} <= set(x)


def test_read_jsonl_tolerates_garbage(tmp_path):
    import tools.claude_bridge.server as srv
    p = tmp_path / "x.jsonl"
    p.write_text('{"a": 1}\nGARBAGE NOT JSON\n\n{"b": 2}\n', encoding="utf-8")
    assert srv._read_jsonl(p) == [{"a": 1}, {"b": 2}]


def test_skp_timeline_shape():
    import tools.claude_bridge.server as srv
    d = srv.skp_timeline()
    assert "canonical" in d and "timeline" in d
    assert isinstance(d["timeline"], list) and isinstance(d["canonical"], dict)


def test_find_verdict_from_regression_summary(tmp_path):
    import tools.claude_bridge.server as srv
    (tmp_path / "regression_summary.md").write_text(
        "# resumo\n## VERDICT: IMPROVED\nblah", encoding="utf-8")
    assert srv._find_verdict(tmp_path) == "IMPROVED"
    empty = tmp_path / "empty"; empty.mkdir()
    assert srv._find_verdict(empty) is None
