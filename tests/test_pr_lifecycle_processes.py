"""FP-060 MT-17: recuperacao do ciclo padrao de PR com PROCESSOS REAIS do SO (morte dura do worker de revisao) e launchers do Windows."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.test_pr_lifecycle import HEAD, POLICY, REPO, World, pending
from tools.orchestration import pr_lifecycle as pl
from tools.orchestration.event_store import EventStore

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "tools/orchestration"

CHILD = """
import sys, time
from tests.test_pr_lifecycle import REPO, POLICY, World
from tools.orchestration import pr_lifecycle as pl
from tools.orchestration.event_store import EventStore
pl.LEASE_S = float(sys.argv[2])
store = EventStore(sys.argv[1])
world = World().add(7)
def hang(pr, gh, policy, repo, do_publish=False, **kw):
    print("reviewing", flush=True)
    time.sleep(300)
pl.work(world, store, POLICY, REPO, hang, owner="worker-morto", heartbeat_s=3600)
"""


def test_a_review_worker_killed_hard_mid_review_is_recovered_once_and_the_old_result_is_fenced(tmp_path):
    db = tmp_path / "events.db"
    store = EventStore(db)
    pl.enqueue(World().add(7), store, POLICY, REPO, execute=True)
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"}
    child = subprocess.Popen([sys.executable, "-c", CHILD, str(db), "1.5"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "reviewing"                                        # o worker reivindicou e esta no meio da revisao
        running = pending(store)[0]
        assert running["status"] == "RUNNING" and running["lease_owner"] == "worker-morto"
        stale = dict(running)
    finally:
        child.kill()                                                                                  # morte dura, sem aviso
        child.wait(timeout=10)
    calls = []

    def review(pr, gh, policy, repo, do_publish=False, **kw):
        calls.append(pr)
        return {"action": "DONE", "verdict": "APPROVE"}
    assert pl.work(World().add(7), store, POLICY, REPO, review)["action"] == "IDLE" and calls == []   # lease do morto ainda vale: ninguem rouba antes
    time.sleep(2.0)
    out = pl.work(World().add(7), store, POLICY, REPO, review)
    assert out["action"] == "DONE" and calls == [7]                                                   # recuperado: a revisao roda UMA vez
    ev = pending(store)[0]
    assert ev["status"] == "DONE" and ev["attempt"] == 2
    with pytest.raises(Exception):
        store.complete(stale, {"by": "o morto"})                                                      # o resultado do dono antigo e recusado (fencing)
    assert pl.work(World().add(7), store, POLICY, REPO, review)["action"] == "IDLE" and calls == [7]  # nada se repete


def test_events_and_dedup_survive_reopening_the_database_in_another_process(tmp_path):
    db = tmp_path / "events.db"
    pl.enqueue(World().add(7, requested=("fmmodesto",)), EventStore(db), POLICY, REPO, execute=True)
    code = ("import json,sys\nfrom tools.orchestration.event_store import EventStore\n"
            "print(json.dumps([[e['idempotency_key'], e['status']] for e in EventStore(sys.argv[1]).events()]))")
    done = subprocess.run([sys.executable, "-c", code, str(db)], cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)}, capture_output=True, text=True, timeout=60)
    assert json.loads(done.stdout) == [[pl.request_key(REPO, 7, HEAD), "PENDING"]]
    assert pl.enqueue(World().add(7, requested=("fmmodesto",)), EventStore(db), POLICY, REPO, execute=True) == []     # apos reabrir: nada duplica


@pytest.mark.parametrize("name", ["run_pr_lifecycle.ps1", "install_pr_lifecycle_task.ps1"])
def test_the_windows_scripts_are_ascii_so_powershell_5_1_reads_them(name):
    raw = (SCRIPTS / name).read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and all(b < 128 for b in raw)


def test_the_launcher_is_fail_closed_on_identity_and_never_embeds_a_secret():
    text = (SCRIPTS / "run_pr_lifecycle.ps1").read_text(encoding="ascii")
    assert 'ExpectedLogin = "fmodesto30"' in text and "gh autenticado como" in text and "Remove-Item Env:GH_TOKEN" in text
    assert "--execute" in text and text.count("CODEX_REVIEWER_GH_TOKEN") >= 2 and "ghp_" not in text and "github_pat_" not in text
    assert '"--watch-pid", $PID' in text                                                               # o ciclo morre junto com o launcher: nenhum orfao


def test_the_task_installer_resumes_at_logon_runs_one_instance_and_defaults_to_the_plan_mode():
    text = (SCRIPTS / "install_pr_lifecycle_task.ps1").read_text(encoding="ascii")
    assert "-AtLogOn" in text and "-MultipleInstances IgnoreNew" in text and "-RestartCount 3" in text and "-StartWhenAvailable" in text
    assert 'if ($Execute) { $argLine += " -Execute" }' in text                                         # sem -Execute registra o modo plano
    assert "-RunLevel Limited" in text                                                                 # sem admin


def test_the_run_loop_holds_an_instance_lock_so_two_loops_never_review_at_once(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "bridge.json"))
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1", "EVENT_BRIDGE_STATE_PATH": str(tmp_path / "bridge.json"), "GH_BIN": "nao-existe"}
    code = ("import sys\nfrom tools.orchestration import event_executor as ex, event_bridge as eb\n"
            "lock = ex.InstanceLock(eb.bridge_path().with_name('pr_lifecycle.instance.lock'))\nassert lock.acquire()\n"
            "print('held', flush=True)\nsys.stdin.readline()")
    holder = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        second = subprocess.run([sys.executable, "-m", "tools.orchestration.pr_lifecycle", "run", "--interval", "1"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        assert second.returncode == 4 and "outra instancia" in second.stdout
    finally:
        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=10)
