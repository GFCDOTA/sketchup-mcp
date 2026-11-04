"""FP-058: coletores/controles da barra de agentes (sem Qt, sem processo real). Honestidade: ausencia de dado nunca e verde."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from tools.orchestration.agent_bar import collectors as col
from tools.orchestration.agent_bar import controls as ctl
from tools.orchestration.agent_bar import settings as cfg
from tools.orchestration.agent_bar.models import Level

NOW = dt.datetime(2026, 11, 4, 12, 0, 0, tzinfo=dt.timezone.utc)


def iso(sec_ago: int) -> str:
    return (NOW - dt.timedelta(seconds=sec_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def gov(tmp_path: Path, *, mode="dry-run", poll_ago=30, execute=False, log: str | None = None, bridge: object | None = None, queue=None) -> Path:
    g = tmp_path / "gov"
    g.mkdir()
    if bridge is None:
        bridge = {"mode": mode, "last_poll": iso(poll_ago), "queue": queue or [], "diagnostics": []}
    (g / "event_bridge.json").write_text(bridge if isinstance(bridge, str) else json.dumps(bridge), encoding="utf-8")
    default_log = json.dumps({"at": iso(poll_ago), "execute": execute, "action": "DRY_RUN"}) + "\n"
    (g / "event_bridge.log").write_text(log if log is not None else default_log, encoding="utf-8")
    return g


def py(pid, ppid=1, cmd="python -m tools.orchestration.event_executor run --interval 120", created=None):
    return col.Proc(pid, ppid, "python.exe", cmd, created or iso(500))


LISTENER_OK = [col.Proc(10, 1, "powershell.exe", "powershell -File run_event_bridge.ps1"), py(20, 10), py(21, 20)]


def listener(g, procs, ts="Running"):
    return col.collect_listener(g, procs, ts, NOW)


# ------------------------------------------------------------------------------------------------------------ listener
def test_listener_dry_run_is_green_with_real_heartbeat(tmp_path):
    st, ex = listener(gov(tmp_path), LISTENER_OK)
    assert st.level is Level.GREEN and st.label == "DRY_RUN" and st.pid == 20
    assert ex["heartbeat_age_s"] == 30 and ex["concurrent_instances"] == 1


def test_listener_execute_mode_is_reported_as_execute(tmp_path):
    st, ex = listener(gov(tmp_path, mode="execute", execute=True), LISTENER_OK)
    assert st.level is Level.GREEN and st.label == "EXECUTE" and ex["mode"] == "EXECUTE"


def test_listener_off_is_gray_not_green(tmp_path):
    st, _ = listener(gov(tmp_path), [], ts="Ready")
    assert st.level is Level.GRAY and "Desligado" in st.label


def test_task_running_without_process_is_red(tmp_path):
    st, _ = listener(gov(tmp_path), [], ts="Running")
    assert st.level is Level.RED


def test_stale_heartbeat_is_red(tmp_path):
    st, ex = listener(gov(tmp_path, poll_ago=5000), LISTENER_OK)
    assert st.level is Level.RED and "Heartbeat velho" in st.label and ex["heartbeat_age_s"] == 5000


def test_two_concurrent_executors_are_red_and_both_reported(tmp_path):
    st, ex = listener(gov(tmp_path), LISTENER_OK + [py(30, 99), py(31, 30)])
    assert st.level is Level.RED and ex["concurrent_instances"] == 2 and "concorrentes" in st.label


def test_kill_switch_is_yellow_and_visible(tmp_path):
    g = gov(tmp_path)
    (g / "EXECUTOR_DISABLED").write_text("x", encoding="utf-8")
    st, ex = listener(g, LISTENER_OK)
    assert st.level is Level.YELLOW and ex["kill_switch"] is True


@pytest.mark.parametrize("bridge,log", [("{nao json", None), (None, "lixo\n\x00\x00 \xff\n")])
def test_corrupted_state_or_log_is_never_green(tmp_path, bridge, log):
    st, _ = listener(gov(tmp_path, bridge=bridge, log=log), LISTENER_OK)
    assert st.level in (Level.YELLOW, Level.RED)


def test_bridge_and_log_disagreeing_on_mode_is_ambiguous(tmp_path):
    st, ex = listener(gov(tmp_path, mode="execute", execute=False), LISTENER_OK)
    assert st.level is Level.YELLOW and ex["mode"] == "ambiguo"


def test_process_table_unavailable_is_gray(tmp_path):
    st, _ = listener(gov(tmp_path), None)
    assert st.level is Level.GRAY and "Indisponivel" in st.label


# -------------------------------------------------------------------------------------------------------------- claude
def claude(procs, roots, g):
    return col.collect_claude(procs, roots, g, NOW, installed=lambda: True)


def test_claude_child_of_the_executor_is_blue_executing(tmp_path):
    procs = LISTENER_OK + [col.Proc(40, 21, "claude.exe", "claude -p", iso(90))]
    st = claude(procs, [20], tmp_path)
    assert st.level is Level.BLUE and st.pid == 40 and "90s" in st.detail


def test_claude_not_descended_from_the_executor_is_not_attributed(tmp_path):
    procs = LISTENER_OK + [col.Proc(50, 999, "claude.exe", "claude (sessao do usuario)", iso(900))]
    st = claude(procs, [20], tmp_path)
    assert st.level is Level.YELLOW and st.pid is None and "fora do orquestrador" in st.detail


def test_claude_installed_but_no_listener_is_gray(tmp_path):
    assert claude([], [], tmp_path).level is Level.GRAY


# --------------------------------------------------------------------------------------------------------------- codex
def test_codex_installed_is_still_not_integrated(tmp_path):
    st = col.collect_codex([], [], tmp_path, which=lambda name: "C:/x/codex.cmd", now=NOW)
    assert st.level is Level.GRAY and st.label == "Nao integrado" and "NAO operacional" in st.detail
    assert col.collect_codex([], [], tmp_path, which=lambda name: None, now=NOW).level is Level.GRAY


def codex_proc(pid, ppid, cmd="codex exec --sandbox read-only review"):
    return col.Proc(pid, ppid, "codex.exe", cmd, iso(40))


def test_codex_manual_analysis_is_blue_but_not_attributed_to_the_orchestrator(tmp_path):
    st = col.collect_codex(LISTENER_OK + [codex_proc(70, 999, "codex")], [20], tmp_path, which=lambda n: "x", now=NOW)
    assert st.level is Level.BLUE and st.label == "Analise manual" and st.pid == 70 and "NAO operacional" in st.detail


def test_codex_child_of_the_executor_reviewing_is_linked(tmp_path):
    st = col.collect_codex(LISTENER_OK + [codex_proc(71, 21)], [20], tmp_path, which=lambda n: "x", now=NOW)
    assert st.level is Level.BLUE and st.label == "Revisando PR (vinculado)" and st.pid == 71


def test_codex_node_wrapper_is_recognized_and_unrelated_node_is_not(tmp_path):
    node_codex = col.Proc(80, 999, "node.exe", "node C:/Users/x/npm/node_modules/@openai/codex/bin/codex.js exec")
    node_other = col.Proc(81, 999, "node.exe", "node server.js")
    assert col.collect_codex([node_codex], [], tmp_path, which=lambda n: "x", now=NOW).label == "Analise manual"
    assert col.collect_codex([node_other], [], tmp_path, which=lambda n: "x", now=NOW).label == "Nao integrado"


def test_codex_failed_and_done_records_are_reflected_when_the_integration_writes_them(tmp_path):
    d = tmp_path / "codex"
    d.mkdir()
    rec = d / "last_review.json"
    rec.write_text(json.dumps({"status": "failed", "pr": 7, "sha": "a" * 40, "error": "timeout"}), encoding="utf-8")
    assert col.collect_codex([], [], tmp_path, which=lambda n: "x", now=NOW).level is Level.RED
    rec.write_text(json.dumps({"status": "done", "pr": 7, "verdict": "REQUEST_CHANGES"}), encoding="utf-8")
    st = col.collect_codex([], [], tmp_path, which=lambda n: "x", now=NOW)
    assert st.level is Level.YELLOW and "REQUEST_CHANGES" in st.detail
    rec.write_text("{lixo", encoding="utf-8")
    assert col.collect_codex([], [], tmp_path, which=lambda n: "x", now=NOW).label == "Nao integrado"


# ------------------------------------------------------------------------------------------------------------- github
def pr_json(**kw):
    return json.dumps({"url": "https://github.com/o/r/pull/7", "headRefOid": "a" * 40, "reviewDecision": "", "statusCheckRollup": [], **kw})


def gh_with(rollup, review=""):
    def gh(args):
        if args[:2] == ["api", "user"]:
            return 0, "fmodesto30"
        return 0, pr_json(statusCheckRollup=rollup, reviewDecision=review)
    return gh


def test_github_unavailable_is_red_and_checks_indisponivel():
    st, ex = col.collect_github(7, lambda a: (1, "gh: not logged in"))
    assert st.level is Level.RED and ex["checks"] == "indisponivel"


def test_github_green_pending_and_failing_checks():
    ok = {"conclusion": "SUCCESS"}
    assert col.collect_github(7, gh_with([ok] * 8))[0].level is Level.GREEN
    assert col.collect_github(7, gh_with([ok, {"status": "IN_PROGRESS"}]))[0].level is Level.YELLOW
    assert col.collect_github(7, gh_with([ok, {"conclusion": "FAILURE"}]))[0].level is Level.RED


def test_github_changes_requested_is_not_green():
    assert col.collect_github(7, gh_with([{"conclusion": "SUCCESS"}], "CHANGES_REQUESTED"))[0].level is Level.YELLOW


def test_github_cache_avoids_repeated_queries():
    calls = []
    t = [0.0]
    c = col.GithubCache(ttl_s=60, clock=lambda: t[0])

    def f():
        calls.append(1)
        return "v"
    c.get("k", f)
    c.get("k", f)
    assert len(calls) == 1
    t[0] = 61
    c.get("k", f)
    assert len(calls) == 2


def test_snapshot_end_to_end_with_fakes_and_diagnostic_has_no_secrets(tmp_path):
    g = gov(tmp_path, queue=[{"pr": 7, "state": "QUEUED", "event_id": "review:9", "head_sha": "a" * 40}])

    def gh(args):
        if args[:2] == ["api", "graphql"]:
            return 0, gql({"Ready": 5, "In Progress": 8, "GPT Review": 10, "Blocked": 32, "Done": 26})
        return gh_with([{"conclusion": "SUCCESS"}])(args)
    s = col.collect_snapshot(g, procs_fn=lambda: LISTENER_OK, task_fn=lambda: "Running", gh=gh, now=NOW)
    assert s.pr == 7 and s.listener.level is Level.GREEN and s.codex.label == "Nao integrado"
    assert s.backlog == {"Ready": 5, "In Progress": 8, "GPT Review": 10, "Blocked": 32, "Done": 26} and s.backlog_error is None
    assert s.mode_banner().startswith("DRY_RUN") and "desligada" in s.mode_banner() and "monitorando" in s.work
    d = s.diagnostic()
    assert "PR atual: 7" in d and "review:9" in d and "aaaaaaa" in d and "heartbeat: 30s" in d and "pid 20" in d
    assert "ghp_" not in d and "token" not in d.lower()


# ------------------------------------------------------------------------------------------------------------- backlog
def gql(counts, more=False, cursor=None):
    nodes = [{"fieldValueByName": {"name": k}} for k, n in counts.items() for _ in range(n)]
    nodes.append({"fieldValueByName": None})                                      # item sem status
    return json.dumps({"data": {"organization": {"projectV2": {"items": {
        "pageInfo": {"hasNextPage": more, "endCursor": cursor}, "nodes": nodes}}}}})


def test_backlog_counts_come_from_the_project_and_missing_columns_are_zero():
    c, err, sync = col.collect_backlog(lambda a: (0, gql({"Ready": 2, "Blocked": 1})), now=NOW)
    assert err is None and c["Ready"] == 2 and c["Blocked"] == 1 and c["Done"] == 0 and sync == "2026-11-04T12:00:00Z"


def test_backlog_paginates_until_the_last_page():
    pages = [gql({"Ready": 2}, more=True, cursor="C1"), gql({"Ready": 3, "Done": 4})]
    calls = []

    def gh(args):
        calls.append(args)
        return 0, pages[len(calls) - 1]
    c, err, _ = col.collect_backlog(gh, now=NOW)
    assert err is None and c["Ready"] == 5 and c["Done"] == 4 and len(calls) == 2 and "after=C1" in calls[1]


def test_backlog_refuses_an_incomplete_count_instead_of_guessing():
    c, err, _ = col.collect_backlog(lambda a: (0, gql({"Ready": 1}, more=True, cursor="C")), now=NOW, max_pages=2)
    assert "incompleta" in err and all(v is None for v in c.values())


def test_backlog_error_is_specific_never_a_bare_indisponivel():
    c, err, sync = col.collect_backlog(lambda a: (1, "error: your token is missing required scopes [read:project]"), now=NOW)
    assert all(v is None for v in c.values()) and sync is None and "rc=1" in err and "read:project" in err and "auth refresh" in err
    c, err, _ = col.collect_backlog(lambda a: (1, "GraphQL: API rate limit exceeded for user ID 1"), now=NOW)
    assert "rate limit" in err
    c, err, _ = col.collect_backlog(lambda a: (0, "<html>"), now=NOW)
    assert "ilegivel" in err and all(v is None for v in c.values())
    c, err, _ = col.collect_backlog(lambda a: (0, json.dumps({"errors": [{"message": "Could not resolve to an Organization"}]})), now=NOW)
    assert "Could not resolve" in err


def test_snapshot_keeps_the_last_good_backlog_but_flags_the_error():
    cache = col.GithubCache(ttl_s=0)
    ok = {"state": "good"}

    def gh(args):
        if args[:2] == ["api", "graphql"]:
            return (0, gql({"Ready": 7})) if ok["state"] == "good" else (1, "GraphQL: API rate limit exceeded")
        return 1, "offline"
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        g = gov(Path(d))
        s1 = col.collect_snapshot(g, procs_fn=lambda: LISTENER_OK, task_fn=lambda: "Running", gh=gh, backlog_cache=cache, now=NOW)
        ok["state"] = "bad"
        import shutil as _sh
        _sh.rmtree(g)
        g = gov(Path(d))
        s2 = col.collect_snapshot(g, procs_fn=lambda: LISTENER_OK, task_fn=lambda: "Running", gh=gh, backlog_cache=cache, now=NOW)
    assert s1.backlog["Ready"] == 7 and s1.backlog_error is None
    assert s2.backlog["Ready"] == 7 and "rate limit" in s2.backlog_error and s2.backlog_synced == s1.backlog_synced


# -------------------------------------------------------------------------------------------------------- historico
def test_repeated_dry_run_events_are_grouped_per_item_with_count_and_span():
    ev = [col.Event(iso(10 * i), "DRY_RUN", "review:1:597:abc", "dry-run: nao executa") for i in range(5)]
    ev.insert(2, col.Event(iso(15), "FAILED", "review:1:597:abc", "terminou sem commit"))
    g = col.group_events(ev)
    assert [(x.action, x.count) for x in g] == [("DRY_RUN", 2), ("FAILED", 1), ("DRY_RUN", 3)]
    assert g[1].error and not g[0].error and g[0].pr_label() == "PR #597"
    assert g[0].last_at == iso(0) and g[0].first_at == iso(10)


def test_event_grouping_keeps_distinct_reviews_apart():
    ev = [col.Event(iso(1), "DRY_RUN", "review:1:597:a", "x"), col.Event(iso(2), "DRY_RUN", "review:2:598:b", "x")]
    assert len(col.group_events(ev)) == 2


# --------------------------------------------------------------------------------------- claude vivo x historico / lock
def test_desktop_helpers_and_interactive_sessions_are_not_counted_as_orchestrator_work(tmp_path):
    procs = LISTENER_OK + [
        col.Proc(90, 1, "claude.exe", '"C:/AnthropicClaude/app-4/claude.exe" --type=gpu-process', iso(900)),
        col.Proc(91, 1, "claude.exe", '"C:/AnthropicClaude/app-4/claude.exe" --type=renderer', iso(900)),
        col.Proc(92, 1, "claude.exe", "C:/Roaming/claude-code/2.1/claude.exe --output-format stream-json", iso(900))]
    st = claude(procs, [20], tmp_path)
    assert st.level is Level.YELLOW and st.pid is None
    assert "1 sessao(oes) interativa(s) viva(s)" in st.detail and "2 processo(s) auxiliar(es)" in st.detail and "pid 92" in st.detail


def test_lock_is_correlated_with_the_real_process_chain():
    roots = [20]
    assert "vivo e da cadeia" in col.lock_status("21", LISTENER_OK, roots)
    assert "FORA da cadeia" in col.lock_status("10", LISTENER_OK, roots)
    assert "NAO existe" in col.lock_status("999", LISTENER_OK, roots)
    assert "sem lock" in col.lock_status(None, LISTENER_OK, roots)
    assert "nao verificavel" in col.lock_status("21", None, roots) and "invalido" in col.lock_status("abc", LISTENER_OK, roots)


def test_executor_summary_reports_failures_attempts_and_working_state():
    bridge = {"queue": [{"pr": 7, "state": "FAILED", "attempts": 1, "event_id": "review:9", "head_sha": "b" * 40},
                        {"pr": 8, "state": "RUNNING", "event_id": "review:10", "head_sha": "c" * 40}],
              "runs": [iso(60), iso(90000)]}
    summary, work, ref = col.executor_summary(bridge, NOW)
    assert "falhas: PR #7 tentativa 1/3" in summary and "execucoes 24h: 1/6" in summary
    assert work.startswith("TRABALHANDO") and "review:10" in ref and "ccccccc" in ref
    assert col.executor_summary(None, NOW)[0] == "indisponivel"


# ------------------------------------------------------------------------------------------------------------ controles
class Ran:
    def __init__(self, ok=True, out=""):
        self.calls, self.ok, self.out = [], ok, out

    def __call__(self, script):
        self.calls.append(script)
        return (0 if self.ok else 1), self.out


class World:
    """Processos que somem depois do Stop-ScheduledTask (ou nao, se stuck=True)."""

    def __init__(self, stuck=False, execute=False, unreadable=False, fail=None, busy=False, table=True):
        self.stopped, self.stuck, self.execute, self.unreadable, self.fail, self.busy, self.table = False, stuck, execute, unreadable, fail, busy, table
        self.calls = []

    def procs(self):
        if not self.table:
            return None
        base = [] if self.stopped and not self.stuck else list(LISTENER_OK)
        return base + ([col.Proc(40, 21, "claude.exe", "claude -p")] if self.busy and base else [])

    def run(self, script):
        self.calls.append(script)
        if "Get-ScheduledTask" in script:
            if self.unreadable:
                return 1, "acesso negado"
            return 0, "-File x.ps1 -Execute" if self.execute else "-File x.ps1"
        if self.fail and self.fail in script:
            return 1, "acesso negado"
        if "Stop-ScheduledTask" in script:
            self.stopped = True
        return 0, ""

    def mutated(self):
        return any("Stop-ScheduledTask" in c or "Start-ScheduledTask" in c for c in self.calls)


def kw(w, tmp_path):
    return {"procs_fn": w.procs, "run": w.run, "gov": tmp_path, "wait_s": 2, "sleep": lambda s: None}


OPS = [ctl.stop_listener, ctl.restart_listener_dry_run]


@pytest.mark.parametrize("op", OPS)
def test_both_controls_require_confirmation_and_touch_nothing_without_it(op, tmp_path):
    w = World()
    assert not op(**kw(w, tmp_path)).ok and w.calls == []


@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("world,needle", [
    (dict(execute=True), "-Execute"), (dict(unreadable=True), "nao foi possivel ler a acao da tarefa"),
    (dict(busy=True), "execucao ativa"), (dict(table=False), "indisponivel")])
def test_stop_and_restart_share_one_fail_closed_preflight(op, world, needle, tmp_path):
    w = World(**world)
    res = op(confirmed=True, **kw(w, tmp_path))
    assert not res.ok and needle in res.message and not w.mutated()


@pytest.mark.parametrize("op", OPS)
def test_kill_switch_blocks_both_controls_and_nothing_is_even_queried(op, tmp_path):
    (tmp_path / "EXECUTOR_DISABLED").write_text("x", encoding="utf-8")
    w = World()
    res = op(confirmed=True, **kw(w, tmp_path))
    assert not res.ok and "kill switch" in res.message and w.calls == []


def test_stop_uses_only_the_scheduled_task_never_taskkill_by_name_and_proves_the_executor_is_gone(tmp_path):
    w = World()
    assert ctl.stop_listener(confirmed=True, **kw(w, tmp_path)).ok
    stop_calls = [c for c in w.calls if "ScheduledTask" in c and "Stop-" in c]
    assert len(stop_calls) == 1
    assert all("taskkill" not in c.lower() and "Stop-Process" not in c for c in w.calls)


def test_stop_does_not_claim_success_when_the_executor_survives(tmp_path):
    w = World(stuck=True)
    res = ctl.stop_listener(confirmed=True, **kw(w, tmp_path))
    assert not res.ok and "ainda esta vivo" in res.message


def test_failed_stop_command_is_reported_with_the_real_error(tmp_path):
    w = World(fail="Stop-ScheduledTask")
    res = ctl.stop_listener(confirmed=True, **kw(w, tmp_path))
    assert not res.ok and "acesso negado" in res.message


def test_failed_start_command_is_reported_with_the_real_error(tmp_path):
    w = World(fail="Start-ScheduledTask")
    res = ctl.restart_listener_dry_run(confirmed=True, **kw(w, tmp_path))
    assert not res.ok and "acesso negado" in res.message


def test_restart_does_not_start_a_second_instance_if_the_old_one_is_still_alive(tmp_path):
    w = World(stuck=True)
    res = ctl.restart_listener_dry_run(confirmed=True, **kw(w, tmp_path))
    assert not res.ok and not any("Start-ScheduledTask" in c for c in w.calls)


def test_restart_dry_run_stops_waits_for_the_lock_release_then_starts(tmp_path):
    w = World()
    assert ctl.restart_listener_dry_run(confirmed=True, **kw(w, tmp_path)).ok
    order = ["stop" if "Stop-ScheduledTask" in c else "start" for c in w.calls if "Stop-ScheduledTask" in c or "Start-ScheduledTask" in c]
    assert order == ["stop", "start"]


def test_restart_when_already_stopped_just_starts(tmp_path):
    w = World()
    w.stopped = True
    assert ctl.restart_listener_dry_run(confirmed=True, **kw(w, tmp_path)).ok
    assert not any("Stop-ScheduledTask" in c for c in w.calls) and any("Start-ScheduledTask" in c for c in w.calls)


def test_open_url_only_accepts_github():
    seen = []
    assert ctl.open_url("https://github.com/GFCDOTA/sketchup-mcp/pull/1", seen.append).ok and seen
    assert not ctl.open_url("http://evil.example/x", seen.append).ok and not ctl.open_url(None, seen.append).ok


def test_no_module_of_the_bar_can_commit_push_merge_or_launch_claude():
    src = "".join(p.read_text(encoding="utf-8") for p in Path(ctl.__file__).parent.glob("*.py"))
    for forbidden in ("git push", "git commit", "taskkill", "Stop-Process", "claude -p", "gh pr merge", "--execute"):
        assert forbidden not in src, forbidden


# ------------------------------------------------------------------------------------------------------------ settings
def test_settings_roundtrip_clamp_and_corrupt_file(tmp_path):
    p = tmp_path / "s.json"
    cfg.save(cfg.Settings(x=10, y=20, opacity=5, local_interval_s=0, github_interval_s=1), p)
    got = cfg.load(p)
    assert (got.x, got.y) == (10, 20) and got.opacity == 1.0 and got.local_interval_s == 2 and got.github_interval_s == 15
    p.write_text("{corrompido", encoding="utf-8")
    assert cfg.load(p) == cfg.Settings()


def test_process_helpers_find_roots_and_descendants_only():
    procs = LISTENER_OK + [col.Proc(60, 999, "python.exe", "python outro.py")]
    assert [p.pid for p in col.executor_roots(procs)] == [20]
    assert {p.pid for p in col.descendants(procs, {20})} == {21}


def test_gui_is_frameless_topmost_550x65_with_four_indicators(tmp_path):
    pytest.importorskip("PySide6.QtWidgets")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from tools.orchestration.agent_bar import window as w
    app = QApplication.instance() or QApplication([])
    bar = w.Bar(cfg.Settings(), gov=tmp_path)
    try:
        f = bar.windowFlags()
        assert f & Qt.WindowType.FramelessWindowHint and f & Qt.WindowType.WindowStaysOnTopHint
        assert (bar.width(), bar.height()) == (550, 65)
        assert set(bar.labels) == {"Claude", "Codex", "Listener", "GitHub"}
    finally:
        bar.worker.stop()
        app.processEvents()


def test_every_subprocess_of_the_bar_is_created_without_a_console_window():
    import re
    for f in Path(ctl.__file__).parent.glob("*.py"):
        src = f.read_text(encoding="utf-8")
        for m in re.finditer(r"subprocess\.run\(", src):
            call = src[m.start():src.index("\n    ", m.start() + 40) if False else m.start() + 700]
            assert "creationflags=" in call.split("subprocess.run(", 2)[1][:700], f"{f.name}: subprocess.run sem creationflags"


# ---------------------------------------------------------------------------------------- botoes (GUI offscreen, um a um)
@pytest.fixture()
def gui(tmp_path):
    pytest.importorskip("PySide6.QtWidgets")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from tools.orchestration.agent_bar import window as w
    app = QApplication.instance() or QApplication([])
    (tmp_path / "event_bridge.log").write_text("{}\n", encoding="utf-8")
    bar = w.Bar(cfg.Settings(), gov=tmp_path)
    bar.worker.snapshot.disconnect(bar.on_snapshot)                    # sem coleta de fundo: o teste injeta o Snapshot
    bar.worker.stop()
    yield bar, app, tmp_path
    bar.details.close()
    app.processEvents()


def status(bar):
    return bar.details.status.text()


def snap(tmp_path, pr_url="https://github.com/GFCDOTA/sketchup-mcp/pull/7"):
    (tmp_path / "x").mkdir(exist_ok=True)
    s = col.collect_snapshot(gov(tmp_path / "x", queue=[{"pr": 7, "state": "QUEUED"}]), procs_fn=lambda: LISTENER_OK, task_fn=lambda: "Running",
                             gh=lambda a: (1, "offline"), now=NOW)
    s.pr_url = pr_url
    return s


def wait_for(app, cond, secs=5):
    import time
    end = time.time() + secs
    while time.time() < end and not cond():
        app.processEvents()
        time.sleep(0.02)
    return cond()


def test_button_repo_and_project_open_the_right_urls_and_report(gui, monkeypatch):
    bar, app, _ = gui
    opened = []
    monkeypatch.setattr(ctl.webbrowser, "open", lambda u: opened.append(u))
    bar.details.buttons["repo"].click()
    bar.details.buttons["project"].click()
    app.processEvents()
    assert opened == [ctl.REPO_URL, ctl.PROJECT_URL] and "\u2713" in status(bar) or "&#10003;" in status(bar)


def test_button_pr_without_a_known_pr_reports_failure_not_success(gui, monkeypatch):
    bar, app, _ = gui
    monkeypatch.setattr(ctl.webbrowser, "open", lambda u: pytest.fail("nao deve abrir sem URL"))
    bar.details.buttons["pr"].click()
    app.processEvents()
    assert "&#10007;" in status(bar) and "indisponivel" in status(bar)


def test_button_pr_opens_the_current_pr_when_known(gui, monkeypatch):
    bar, app, tmp = gui
    opened = []
    monkeypatch.setattr(ctl.webbrowser, "open", lambda u: opened.append(u))
    bar.on_snapshot(snap(tmp))
    bar.details.buttons["pr"].click()
    assert opened == ["https://github.com/GFCDOTA/sketchup-mcp/pull/7"] and "&#10003;" in status(bar)


def test_button_logs_opens_the_latest_log_or_reports_absence(gui, monkeypatch):
    bar, app, tmp = gui
    opened = []
    monkeypatch.setattr(ctl, "open_path", lambda p: (opened.append(p), ctl.Result(True, str(p)))[1])
    bar.details.buttons["logs"].click()
    assert opened and opened[0].name == "event_bridge.log" and "&#10003;" in status(bar)
    (tmp / "event_bridge.log").unlink()
    bar.details.buttons["logs"].click()
    assert "&#10007;" in status(bar) and "nenhum log" in status(bar)


def test_button_copy_diagnostic_really_copies_and_verifies(gui):
    bar, app, tmp = gui
    bar.details.buttons["diag"].click()
    assert "&#10007;" in status(bar) and "nada para copiar" in status(bar)           # sem coleta: nao finge sucesso
    bar.on_snapshot(snap(tmp))
    bar.details.buttons["diag"].click()
    from PySide6.QtWidgets import QApplication
    assert "&#10003;" in status(bar) and "Agent bar snapshot" in QApplication.clipboard().text()


def test_button_refresh_confirms_only_when_a_new_snapshot_arrives(gui):
    bar, app, tmp = gui
    bar.details.buttons["refresh"].click()
    assert bar._refresh_pending is True and "&#10003;" not in status(bar)
    bar.on_snapshot(snap(tmp))
    assert "atualizado" in status(bar) and bar._refresh_pending is None
    bar._refresh_pending = True
    bar._refresh_timeout()
    assert "&#10007;" in status(bar) and "sem resposta" in status(bar)


def test_buttons_stop_and_restart_do_nothing_without_confirmation(gui, monkeypatch):
    bar, app, _ = gui
    monkeypatch.setattr(bar, "confirm", lambda text: False)
    monkeypatch.setattr(ctl, "stop_listener", lambda **k: pytest.fail("nao pode parar sem confirmacao"))
    monkeypatch.setattr(ctl, "restart_listener_dry_run", lambda **k: pytest.fail("nao pode reiniciar sem confirmacao"))
    bar.details.buttons["stop"].click()
    bar.details.buttons["restart"].click()


def test_button_stop_and_restart_show_the_real_result_including_refusals(gui, monkeypatch):
    bar, app, _ = gui
    monkeypatch.setattr(bar, "confirm", lambda text: True)
    monkeypatch.setattr(ctl, "stop_listener", lambda **k: ctl.Result(False, "parada recusada: execucao ativa"))
    bar.details.buttons["stop"].click()
    assert wait_for(app, lambda: "parada recusada" in status(bar)) and "&#10007;" in status(bar)
    monkeypatch.setattr(ctl, "restart_listener_dry_run", lambda **k: ctl.Result(True, "tarefa reiniciada em DRY_RUN"))
    bar.details.buttons["restart"].click()
    assert wait_for(app, lambda: "reiniciada em DRY_RUN" in status(bar)) and "&#10003;" in status(bar)


def test_a_control_that_raises_is_reported_as_failure(gui, monkeypatch):
    bar, app, _ = gui
    monkeypatch.setattr(bar, "confirm", lambda text: True)

    def boom(**k):
        raise RuntimeError("falhou feio")
    monkeypatch.setattr(ctl, "stop_listener", boom)
    bar.details.buttons["stop"].click()
    assert wait_for(app, lambda: "falhou feio" in status(bar)) and "&#10007;" in status(bar)


def test_panel_is_compact_and_events_scroll_instead_of_growing(gui):
    bar, app, tmp = gui
    s = snap(tmp)
    s.events = [col.GroupedEvent(iso(i), iso(i), "DRY_RUN", f"review:{i}:{i}:a", "x", 1, False) for i in range(20)]
    bar.on_snapshot(s)
    bar.details.show()
    app.processEvents()
    assert bar.details.height() < 600 and bar.details.events.count() == 20
    assert bar.details.events.height() <= 6 * 40
