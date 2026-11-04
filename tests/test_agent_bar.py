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
def test_codex_installed_is_still_not_integrated():
    st = col.collect_codex(lambda name: "C:/x/codex.cmd")
    assert st.level is Level.GRAY and st.label == "Nao integrado"
    assert col.collect_codex(lambda name: None).level is Level.GRAY


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
    g = gov(tmp_path, queue=[{"pr": 7, "state": "QUEUED"}])
    s = col.collect_snapshot(g, procs_fn=lambda: LISTENER_OK, task_fn=lambda: "Running", gh=gh_with([{"conclusion": "SUCCESS"}]), now=NOW)
    assert s.pr == 7 and s.listener.level is Level.GREEN and s.codex.label == "Nao integrado" and s.backlog["Ready"] is None
    d = s.diagnostic()
    assert "PR atual: 7" in d and "ghp_" not in d and "token" not in d.lower()


# ------------------------------------------------------------------------------------------------------------ controles
class Ran:
    def __init__(self, ok=True, out=""):
        self.calls, self.ok, self.out = [], ok, out

    def __call__(self, script):
        self.calls.append(script)
        return (0 if self.ok else 1), self.out


def test_stop_requires_confirmation_and_does_nothing_without_it():
    r = Ran()
    assert not ctl.stop_listener(lambda: LISTENER_OK, r).ok and r.calls == []


def test_stop_refused_while_claude_is_executing_and_kills_nothing():
    r = Ran()
    procs = LISTENER_OK + [col.Proc(40, 21, "claude.exe", "claude -p")]
    res = ctl.stop_listener(lambda: procs, r, confirmed=True)
    assert not res.ok and "execucao ativa" in res.message and r.calls == []


def test_stop_refused_when_process_table_is_unavailable():
    r = Ran()
    assert not ctl.stop_listener(lambda: None, r, confirmed=True).ok and r.calls == []


def test_stop_uses_only_the_scheduled_task_never_taskkill_by_name():
    r = Ran()
    assert ctl.stop_listener(lambda: LISTENER_OK, r, confirmed=True).ok
    assert len(r.calls) == 1 and "Stop-ScheduledTask" in r.calls[0]
    assert "taskkill" not in r.calls[0].lower() and "Stop-Process" not in r.calls[0]


def test_restart_refused_if_task_has_execute_or_is_unreadable():
    ex = Ran(out="-File x.ps1 -Execute")
    assert "-Execute" in ctl.restart_listener_dry_run(lambda: LISTENER_OK, ex, confirmed=True).message
    assert not any("Start-ScheduledTask" in c for c in ex.calls)
    assert not ctl.restart_listener_dry_run(lambda: LISTENER_OK, Ran(ok=False), confirmed=True).ok


def test_restart_dry_run_stops_then_starts_the_task():
    r = Ran(out="-File x.ps1")
    assert ctl.restart_listener_dry_run(lambda: LISTENER_OK, r, confirmed=True).ok
    order = ["stop" if "Stop-ScheduledTask" in c else "start" for c in r.calls if "Stop-ScheduledTask" in c or "Start-ScheduledTask" in c]
    assert order == ["stop", "start"]


def test_control_command_failure_is_reported_not_swallowed():
    res = ctl.stop_listener(lambda: LISTENER_OK, Ran(ok=False, out="acesso negado"), confirmed=True)
    assert not res.ok and "acesso negado" in res.message


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
