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
    # SPA tabs present (the inline fallback DASHBOARD_HTML has none of these).
    # 8-tab nav consolidated in cockpit Fase 2A (commit 6a4b846); update this
    # list if the nav changes again.
    for tab in ("#home", "#sessoes", "#gate", "#review-skp",
                "#repo", "#backlog", "#artifacts", "#docs"):
        assert tab in html, f"missing SPA tab {tab}"


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
    import tools.claude_bridge.system_inventory as srv
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
    import tools.claude_bridge.skp_inventory as srv
    a = tmp_path / "a.skp"; b = tmp_path / "b.skp"; c = tmp_path / "c.skp"
    a.write_bytes(b"SAME-BYTES-XYZ"); b.write_bytes(b"SAME-BYTES-XYZ")
    c.write_bytes(b"different")
    assert srv._sha256(a) == srv._sha256(b)
    assert srv._sha256(a) != srv._sha256(c)


def test_dedup_by_hash_groups_and_keeper():
    import tools.claude_bridge.skp_inventory as srv
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


def test_learnings_every_entry_has_prevention():
    import tools.claude_bridge.server as srv
    d = srv.learnings()
    assert {"learnings", "total", "source"} <= set(d)
    assert d["total"] >= 5
    for x in d["learnings"]:
        assert x["como_prevenir_regressao"]  # the anti-regression field, mandatory
        assert {"id", "falha_observada", "como_corrigimos"} <= set(x)


def test_status_score_enum():
    import tools.claude_bridge.server as srv
    d = srv.status()
    assert d["score"] in ("GREEN", "YELLOW", "RED")
    assert {"reason", "gate", "sessions", "pending_gate", "open_difficulties"} <= set(d)


def test_canonical_skp_points_to_existing_skp(tmp_path, monkeypatch):
    """Regressao: o resumo /api/status colapsava canonical -> verdict, entao um .skp
    canonico SEM arquivo de veredito aparecia null (parecia 'sem SKP'). O detector
    deve apontar o .skp existente, independente do verdict."""
    import tools.claude_bridge.server as srv
    plant = tmp_path / "artifacts" / "demo_plant"
    plant.mkdir(parents=True)
    (plant / "model.skp").write_bytes(b"SKP")
    (plant / "demo_top.png").write_bytes(b"PNG")
    monkeypatch.setattr(srv, "REPO_ROOT", tmp_path)
    c = srv.skp_timeline()["canonical"]["demo_plant"]
    assert c["has_skp"] is True
    assert c["skp"] and c["skp"].endswith("model.skp")  # aponta o arquivo, nao null
    assert c["verdict"] is None  # sem verdict file: verdict null, mas o skp segue presente


def test_status_canonical_skp_shape_and_planta_74():
    """No repo real cada canonical_skp e {skp, has_skp, verdict}; a planta_74 tem .skp
    commitado -> NAO pode mais sair null so por faltar verdict."""
    import tools.claude_bridge.server as srv
    cs = srv.status()["canonical_skp"]
    assert isinstance(cs, dict)
    for info in cs.values():
        assert {"skp", "has_skp", "verdict"} <= set(info)
    assert "planta_74" in cs and cs["planta_74"]["has_skp"] is True
    assert cs["planta_74"]["skp"] and cs["planta_74"]["skp"].endswith(".skp")


def test_next_best_actions_sorted_by_roi():
    import tools.claude_bridge.server as srv
    d = srv.next_best_actions()
    rois = [a["roi"] for a in d["actions"]]
    assert rois == sorted(rois, reverse=True)
    assert all("roi" in a and "proxima_acao" in a for a in d["actions"])


# ---- acoes corretivas: o cockpit identifica E corrige (nao fica parado) -----


def _bridge_dirs(tmp_path):
    qd = tmp_path / ".ai_bridge" / "questions"
    rd = tmp_path / ".ai_bridge" / "responses"
    qd.mkdir(parents=True)
    rd.mkdir(parents=True)
    return qd, rd


def _drain(srv, max_iters=100):
    import time
    for _ in range(max_iters):
        if not srv.process_consults_state()["running"]:
            return
        time.sleep(0.02)


def test_orphan_consults_finds_only_unanswered(tmp_path, monkeypatch):
    import tools.claude_bridge.server as srv
    qd, rd = _bridge_dirs(tmp_path)
    (qd / "q1.md").write_text("pergunta 1", encoding="utf-8")
    (qd / "q2.md").write_text("pergunta 2", encoding="utf-8")
    (rd / "q1.md").write_text("ja respondida", encoding="utf-8")
    monkeypatch.setattr(srv, "REPO_ROOT", tmp_path)
    orphans = srv._orphan_consults()
    assert [o["id"] for o in orphans] == ["q2"]  # only the unanswered one
    assert orphans[0]["text"] == "pergunta 2"


def test_process_consults_answers_queue_and_clears_pending(tmp_path, monkeypatch):
    import tools.claude_bridge.server as srv
    qd, rd = _bridge_dirs(tmp_path)
    (qd / "c1.md").write_text("decida isso", encoding="utf-8")
    (qd / "c2.md").write_text("e isso", encoding="utf-8")
    monkeypatch.setattr(srv, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(srv, "ask_claude", lambda q: "analise...\nVerdict: GO")
    srv._ACTIONS.clear()
    start = srv.process_consults_start()
    assert start["started"] == 2 and start["total"] == 2
    _drain(srv)
    st = srv.process_consults_state()
    assert st["done"] == 2 and st["running"] is False
    assert st["pending_now"] == 0  # respostas gravadas -> fila zerada
    assert {r["verdict"] for r in st["results"]} == {"GO"}
    assert (rd / "c1.md").exists() and (rd / "c2.md").exists()


def test_process_consults_idempotent_when_empty(tmp_path, monkeypatch):
    import tools.claude_bridge.server as srv
    _bridge_dirs(tmp_path)  # sem perguntas
    monkeypatch.setattr(srv, "REPO_ROOT", tmp_path)
    srv._ACTIONS.clear()
    start = srv.process_consults_start()
    assert start["started"] == 0 and start["running"] is False


def test_process_consults_one_error_does_not_kill_queue(tmp_path, monkeypatch):
    import tools.claude_bridge.server as srv
    qd, rd = _bridge_dirs(tmp_path)
    (qd / "a.md").write_text("ok", encoding="utf-8")
    (qd / "b.md").write_text("boom", encoding="utf-8")
    monkeypatch.setattr(srv, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "AUDIT_PATH", tmp_path / "audit.jsonl")

    def fake(q):
        if "boom" in q:
            raise RuntimeError("gate down")
        return "Verdict: GO"

    monkeypatch.setattr(srv, "ask_claude", fake)
    srv._ACTIONS.clear()
    srv.process_consults_start()
    _drain(srv)
    st = srv.process_consults_state()
    assert st["done"] == 2  # ambos tentados, erro nao derruba a fila
    errs = [r for r in st["results"] if r["error"]]
    assert len(errs) == 1 and "gate down" in errs[0]["error"]
    assert (rd / "a.md").exists()  # o bom foi gravado mesmo assim


def test_actions_overview_maps_every_problem_to_an_action():
    import tools.claude_bridge.server as srv
    o = srv.actions_overview()
    assert {"score", "reason", "actions"} <= set(o)
    keys = {a["key"] for a in o["actions"]}
    assert {"process-consults", "dirty-detail", "open-difficulty"} <= keys
    for a in o["actions"]:
        assert a["kind"] in ("auto", "diagnose", "manual")
        assert a["label"] and a["detail"]


def test_dirty_detail_shape_no_crash():
    import tools.claude_bridge.server as srv
    d = srv.dirty_detail()
    assert "dirty" in d and isinstance(d["dirty"], list)
    for r in d["dirty"]:
        assert r["kind"] in ("review", "guarded", "ignorable")
        assert {"repo", "branch", "recommendation", "runtime", "real"} <= set(r)


def test_classify_processes_splits_desktop_app_from_cli_sessions():
    import tools.claude_bridge.system_inventory as srv
    procs = [
        {"ProcessId": 100, "WorkingSetSize": 400 * 1024 * 1024,
         "CommandLine": r"...app\Claude.exe --type=renderer"},
        {"ProcessId": 101, "WorkingSetSize": 150 * 1024 * 1024,
         "CommandLine": r"...app\Claude.exe --type=gpu-process"},
        {"ProcessId": 200, "WorkingSetSize": 300 * 1024 * 1024,
         "KernelModeTime": 50 * 10**7, "UserModeTime": 100 * 10**7,
         "CommandLine": r"claude-code\2.1.156\claude.exe --output-format stream-json --effort max"},
    ]
    out = srv._classify_processes(procs)
    assert out["cli_count"] == 1  # so o claude-code conta como sessao que pode custar
    assert out["desktop_app"]["processes"] == 2
    assert out["desktop_app"]["ram_mb"] == 550  # 400 + 150, o app desktop e so RAM
    s = out["cli_sessions"][0]
    assert s["pid"] == 200 and s["effort"] == "max" and s["ram_mb"] == 300
    assert s["cpu_sec"] == 150  # (50+100)*1e7 / 1e7


def test_classify_processes_empty_is_zero_cost():
    import tools.claude_bridge.system_inventory as srv
    out = srv._classify_processes([])
    assert out["cli_count"] == 0 and out["desktop_app"]["processes"] == 0


# ---- route table (Command pattern) — replaces the do_GET/do_POST if/elif ------


def test_route_tables_are_callable_and_cover_known_paths():
    """Regression guard vs the old 28-branch if/elif: every path the cockpit and
    ask_gpt_gate rely on must stay routed, and every route value must be callable."""
    import tools.claude_bridge.server as srv
    assert all(callable(h) for h in srv.GET_ROUTES.values())
    assert all(callable(h) for h in srv.POST_ROUTES.values())
    # "" is the rstrip'd form of "/" and "/dashboard"
    expected_get = {
        "", "/dashboard", "/health", "/sessions", "/events",
        "/api/skp-inventory", "/api/plant", "/api/claude-sessions",
        "/api/ecosystem", "/api/recent-commits", "/api/gate-ledger",
        "/api/system-map", "/api/git-inventory", "/api/processes",
        "/api/skp-inventory-v2", "/api/difficulties", "/api/skp-timeline",
        "/api/learnings", "/api/status", "/api/next-best-actions",
        "/api/actions", "/api/actions/process-consults",
        "/api/actions/dirty-detail", "/artifact",
    }
    assert expected_get <= set(srv.GET_ROUTES)
    assert {"/ask", "/heartbeat", "/api/actions/process-consults"} <= set(srv.POST_ROUTES)


def test_health_endpoints_are_single_source_of_truth():
    """/health.endpoints must be DERIVED from the route tables (no drift). The old
    hardcoded list named 6 of ~26 real routes; the dashboard shows this count."""
    import tools.claude_bridge.server as srv
    assert set(srv.health_payload()["endpoints"]) == set(srv.advertised_endpoints())
    eps = srv.health_payload()["endpoints"]
    for e in ("/", "/ask", "/health", "/events", "/api/status"):
        assert e in eps
    assert "" not in eps  # the "" route key is advertised as "/", never empty
    assert len(eps) >= 20  # the real surface, not the stale 6
