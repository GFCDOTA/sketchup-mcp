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
    p.kill()                                                                  # crash duro (TerminateProcess): sem finally, sem release
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
        first.kill()
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
