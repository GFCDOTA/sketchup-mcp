"""Issue #589: recuperacao REAL entre processos do SO (crash duro, reinicio, 2 executores). Sem Claude, sem GitHub: o `gh` e o filho sao
falsos DENTRO de um subprocesso Python; o estado e o arquivo real do bridge. Complementa os testes em-processo de test_event_executor.py."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tools.orchestration import event_bridge as eb
from tools.orchestration import event_executor as ex

ROOT = ex.repo_root()
HEAD, NEWHEAD, REPO = "a" * 40, "d" * 40, eb.REPO
NOW = dt.datetime(2026, 11, 4, 12, 0, tzinfo=dt.timezone.utc)

HARNESS = r'''
import datetime as dt, json, sys, time
from pathlib import Path
from tools.orchestration import event_executor as ex
mode, marker, now_iso = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
HEAD, REPO = "a" * 40, ex.eb.REPO
POLICY = {"reviewers": ["fmmodesto"], "executor_logins": ["fmodesto30"]}
class Gh:
    head = HEAD
    def __call__(self, path):
        if path == "user": return {"login": "fmodesto30"}
        if path == f"repos/{REPO}/pulls/7":
            return {"number": 7, "body": "Refs #589", "state": "open", "head": {"sha": self.head, "ref": "feat/x", "repo": {"full_name": REPO}}}
        if path == f"repos/{REPO}/pulls/7/reviews/9":
            return {"id": 9, "user": {"login": "fmmodesto"}, "state": "CHANGES_REQUESTED", "commit_id": HEAD}
        raise AssertionError(path)
gh = Gh()
def child(argv, cwd, env, stdin, timeout, cancel=None):
    marker.write_text("child-started", encoding="utf-8")
    if mode == "block":
        time.sleep(120)                         # simula o Claude em andamento (sera morto de fora)
    gh.head = "d" * 40                          # "publica" um commit
    return 0, "", "", False
now = dt.datetime.strptime(now_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
res = ex.process_one(gh, POLICY, REPO, True, child, "claude", lambda pr, b, s, r: (True, "", Path("wt")), now, None, 0.05)
print(json.dumps(res), flush=True)
'''


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "bridge.json"))
    monkeypatch.setenv("EXECUTION_STATE_PATH", str(tmp_path / "exec.json"))
    monkeypatch.setenv("BRIDGE_WORKTREE_ROOT", str(tmp_path / "wt"))
    eb.save({**eb.default_bridge_state(), "queue": [{
        "key": f"review:9:7:{HEAD}", "kind": "review", "event_id": "review:9", "pr": 7, "issue": 589, "head_sha": HEAD,
        "author": "fmmodesto", "url": "x", "state": "QUEUED", "queued_at": "2026-11-04T11:00:00Z"}]})
    return tmp_path


def spawn(mode: str, marker: Path, now: dt.datetime) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", HARNESS, mode, str(marker), now.strftime("%Y-%m-%dT%H:%M:%SZ")], cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def wait_for(path: Path, secs: float = 30) -> None:
    end = time.time() + secs
    while not path.exists():
        assert time.time() < end, f"timeout esperando {path}"
        time.sleep(0.05)


def run_to_end(mode: str, marker: Path, now: dt.datetime) -> dict:
    p = spawn(mode, marker, now)
    out, err = p.communicate(timeout=60)
    assert p.returncode == 0, err
    return json.loads(out.strip().splitlines()[-1])


def test_hard_killed_executor_leaves_a_recoverable_running_item_that_is_not_stolen_early_and_runs_once_after_the_lease(env):
    live = dt.datetime.now(dt.timezone.utc)                                   # lease real (o heartbeat usa o relogio real)
    p = spawn("block", env / "m1", live)
    wait_for(env / "m1")
    disk = eb.load()["queue"][0]
    assert disk["state"] == "RUNNING" and disk["owner"]                       # claim duravel ANTES do filho
    ex.kill_tree(p)                                                           # crash duro da ARVORE (shim do venv + python real): sem finally, sem release
    p.communicate(timeout=30)
    assert eb.load()["queue"][0]["state"] == "RUNNING"                        # nada limpou: e o que um crash real deixa
    # reinicio logo em seguida: lease ainda valido => NAO rouba o item
    assert run_to_end("ok", env / "m2", live + dt.timedelta(seconds=30))["action"] == "IDLE"
    assert not (env / "m2").exists()
    # passado o lease (dono morto): recupera, executa UMA vez e conclui
    after = live + dt.timedelta(seconds=ex.LEASE_S + ex.HEARTBEAT_S + 600)
    assert run_to_end("ok", env / "m3", after)["action"] == "DONE"
    final = eb.load()["queue"][0]
    assert final["state"] == "DONE_AWAITING_REREVIEW" and "owner" not in final and final["new_head"] == NEWHEAD
    assert run_to_end("ok", env / "m4", after)["action"] == "IDLE"            # concluido: nunca reexecuta


def test_two_real_os_processes_never_run_the_same_item(env):
    live = dt.datetime.now(dt.timezone.utc)
    first = spawn("block", env / "a", live)
    try:
        wait_for(env / "a")
        second = run_to_end("ok", env / "b", live + dt.timedelta(seconds=5))
        assert second["action"] == "IDLE" and not (env / "b").exists()        # 2o processo nao executa o item do 1o
    finally:
        ex.kill_tree(first)
        first.communicate(timeout=30)


def test_restart_after_the_child_already_published_never_reruns_the_old_review(env):
    live = dt.datetime.now(dt.timezone.utc)
    b = eb.load()
    b["queue"][0].update(state="RUNNING", owner="morto", lease_expires=ex.es.now_iso(live - dt.timedelta(minutes=5)))
    eb.save(b)

    code = HARNESS.replace('head = HEAD', 'head = "d" * 40')
    p = subprocess.run([sys.executable, "-c", code, "ok", str(env / "x"), live.strftime("%Y-%m-%dT%H:%M:%SZ")], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout.strip().splitlines()[-1])["action"] == "SUPERSEDED" and not (env / "x").exists()


# ------------------------------------- uma unica instancia por fila + sem orfaos (achado do Stop-ScheduledTask real, 2026-11-04)
def dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_pid_alive_distinguishes_a_live_process_from_a_finished_one():
    import os
    assert ex.pid_alive(os.getpid()) and not ex.pid_alive(dead_pid())


def test_instance_lock_is_exclusive_across_real_processes_and_released_by_the_os_on_a_hard_kill(tmp_path):
    lock_path = tmp_path / "inst.lock"
    code = ("import sys,time; from pathlib import Path; from tools.orchestration.event_executor import InstanceLock; "
            "l=InstanceLock(Path(sys.argv[1])); ok=l.acquire(); Path(sys.argv[2]).write_text(str(ok)); time.sleep(120)")
    holder = subprocess.Popen([sys.executable, "-c", code, str(lock_path), str(tmp_path / "ok")], cwd=ROOT)
    try:
        wait_for(tmp_path / "ok")
        assert (tmp_path / "ok").read_text() == "True"
        mine = ex.InstanceLock(lock_path)
        assert mine.acquire() is False and ex.pid_alive(int(mine.holder()))    # 2a instancia nao consome a fila e sabe quem e o dono
    finally:
        ex.kill_tree(holder)
        holder.wait(30)
    again = ex.InstanceLock(lock_path)
    assert again.acquire() is True                                            # o SO soltou o lock com o processo morto: sem pidfile velho
    again.release()


def test_main_refuses_to_start_a_second_executor_and_never_polls(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ex.eb, "check_identity", lambda gh, policy: "fmodesto30")
    monkeypatch.setattr(ex, "run_cycle", lambda *a, **k: pytest.fail("a 2a instancia nao pode consumir a fila"))
    first = ex.InstanceLock(ex.instance_lock_path())
    assert first.acquire()
    try:
        assert ex.main(["run", "--once"]) == 4
    finally:
        first.release()
    assert "outra instancia" in capsys.readouterr().out


def test_main_exits_when_the_launcher_pid_is_gone_and_heartbeat_cancels_the_child(monkeypatch, capsys):
    monkeypatch.setattr(ex.eb, "check_identity", lambda gh, policy: "fmodesto30")
    monkeypatch.setattr(ex, "run_cycle", lambda *a, **k: pytest.fail("sem launcher vivo nao roda ciclo"))
    gone = dead_pid()
    assert ex.main(["run", "--watch-pid", str(gone)]) == 5
    assert "encerrou" in capsys.readouterr().out
    assert ex.sleep_watching(30, gone) is False and ex.sleep_watching(0.1, None) is True


def test_launcher_death_cancels_a_running_child_instead_of_leaving_an_orphan(monkeypatch):
    import threading
    monkeypatch.setattr(ex, "WATCH_PID", dead_pid())
    cancel = threading.Event()
    hb = ex.Heartbeat("k", "owner", 0.05)
    hb.cancel = cancel
    hb.start()
    assert cancel.wait(5) is True                                              # tarefa/launcher encerrado => o filho e derrubado
    hb.stop()


def test_launcher_passes_its_own_pid_so_the_executor_never_outlives_it():
    ps1 = (ROOT / "tools/orchestration/run_event_bridge.ps1").read_text(encoding="ascii")
    assert ps1.count('"--watch-pid", $PID') == 2                               # dry-run e -Execute
