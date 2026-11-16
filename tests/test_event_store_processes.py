"""FP-060 MT-08 (#627): recuperacao e concorrencia do EventStore com PROCESSOS REAIS do SO (nao threads, nao relogio simulado).
Cobre linhas da matriz da SPEC §9: dois workers disputam um job, evento duplicado, worker encerrado, SQLite reiniciado, falha permanente => DLQ."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tools.orchestration.event_store import EventStore, LeaseLost

ROOT = Path(__file__).resolve().parents[1]
LEASE_S = 2.0
TYPE = "REVIEW_REQUESTED"

CLAIM_AND_HANG = """
import json, sys, time
from tools.orchestration.event_store import EventStore
s = EventStore(sys.argv[1])
ev = s.claim(("REVIEW_REQUESTED",), sys.argv[2], float(sys.argv[3]))
print(json.dumps({"claimed": ev["id"] if ev else None, "token": ev["lease_token"] if ev else None, "attempt": ev["attempt"] if ev else None}), flush=True)
time.sleep(120)
"""

DRAIN = """
import json, sys
from tools.orchestration.event_store import EventStore
s = EventStore(sys.argv[1])
done = []
while True:
    ev = s.claim(("REVIEW_REQUESTED",), sys.argv[2], 30.0)
    if ev is None:
        break
    s.complete(ev, {"by": sys.argv[2]})
    done.append(ev["id"])
print(json.dumps(done), flush=True)
"""

PUBLISH = """
import json, sys
from tools.orchestration.event_store import EventStore
s = EventStore(sys.argv[1])
print(json.dumps(s.publish("REVIEW_REQUESTED", sys.argv[2], "job:dup", {"x": 1})), flush=True)
"""


def child(code: str, *args: str, **kw) -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"}
    return subprocess.Popen([sys.executable, "-c", code, *args], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kw)


def first_line(proc: subprocess.Popen, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = proc.stdout.readline()
        if line.strip():
            return json.loads(line)
        if proc.poll() is not None:
            raise AssertionError(f"filho terminou sem responder: {proc.stderr.read()[:400]}")
    raise AssertionError("filho nao respondeu a tempo")


@pytest.fixture()
def db(tmp_path):
    return tmp_path / "events.db"


def only(store: EventStore, key: str) -> dict:
    return next(e for e in store.events() if e["idempotency_key"] == key)


def test_a_worker_process_killed_after_claiming_is_recovered_once_and_its_late_result_is_fenced(db):
    store = EventStore(db)
    store.publish(TYPE, "k1", "job:1", {"pr": 1})
    proc = child(CLAIM_AND_HANG, str(db), "worker-dead", str(LEASE_S))
    info = first_line(proc)
    proc.kill()                                                                              # morte real do processo dono, sem aviso
    proc.wait(timeout=10)
    assert info["claimed"] and only(store, "k1")["status"] == "RUNNING"

    assert store.claim((TYPE,), "worker-new", LEASE_S) is None                              # o lease do morto ainda vale: ninguem rouba antes
    time.sleep(LEASE_S + 0.5)
    new = store.claim((TYPE,), "worker-new", LEASE_S)
    assert new is not None and new["id"] == info["claimed"] and new["attempt"] == 2          # recuperado, mesma identidade do evento

    stale = {**new, "lease_token": info["token"], "lease_owner": "worker-dead"}
    with pytest.raises(LeaseLost):
        store.complete(stale, {"by": "o morto"})                                              # resultado do dono antigo recusado
    assert store.renew(stale, 5.0) is False and store.renew(new, 5.0) is True                 # o heartbeat do morto nao renova o lease do novo dono
    store.complete(new, {"by": "worker-new"})
    assert only(store, "k1")["status"] == "DONE" and store.claim((TYPE,), "worker-3", LEASE_S) is None   # um unico efeito


def test_several_real_processes_racing_for_the_queue_claim_each_event_exactly_once(db):
    store = EventStore(db)
    ids = [store.publish(TYPE, f"k{n}", f"job:{n}", {"n": n})[0] for n in range(16)]
    procs = [child(DRAIN, str(db), f"w{i}") for i in range(4)]
    claimed: list[int] = []
    for proc in procs:
        out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err[:400]
        claimed += json.loads(out.strip().splitlines()[-1])
    assert sorted(claimed) == sorted(ids) and len(claimed) == len(set(claimed))              # ninguem repetiu, ninguem ficou de fora
    assert {e["status"] for e in store.events()} == {"DONE"} and {e["attempt"] for e in store.events()} == {1}


def test_the_same_event_published_by_many_real_processes_is_created_once(db):
    EventStore(db)
    procs = [child(PUBLISH, str(db), "dup-key") for _ in range(6)]
    results = []
    for proc in procs:
        out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err[:400]
        results.append(json.loads(out.strip().splitlines()[-1]))
    assert sum(1 for _id, created in results if created) == 1 and len({r[0] for r in results}) == 1
    assert len(EventStore(db).events()) == 1


def test_a_job_that_keeps_killing_its_workers_ends_in_the_dlq_with_a_diagnostic(db):
    store = EventStore(db)
    store.publish(TYPE, "poison", "job:poison", {"x": 1}, max_attempts=2)
    for n in range(2):
        proc = child(CLAIM_AND_HANG, str(db), f"victim-{n}", str(LEASE_S))
        assert first_line(proc)["attempt"] == n + 1
        proc.kill()
        proc.wait(timeout=10)
        time.sleep(LEASE_S + 0.5)
    assert store.claim((TYPE,), "survivor", LEASE_S) is None                                  # esgotou as tentativas: nao volta a ser reivindicado
    ev = only(store, "poison")
    assert ev["status"] == "DLQ" and "lease expired" in (ev["error"] or "")
    assert any(e["event_type"] == "JOB_FAILED" for e in store.events())                       # a falha permanente deixa o fato registrado


def test_events_survive_closing_and_reopening_the_database_in_another_process(db):
    store = EventStore(db)
    store.publish(TYPE, "persist", "job:p", {"keep": "me"})
    ev = store.claim((TYPE,), "w0", 60.0)
    store.fail(ev, "falha transitoria", retry_delay=0)
    del store
    proc = child(DRAIN, str(db), "after-restart")
    out, err = proc.communicate(timeout=120)
    assert proc.returncode == 0, err[:400]
    reopened = EventStore(db)
    assert json.loads(out.strip().splitlines()[-1]) and only(reopened, "persist")["status"] == "DONE"
    assert only(reopened, "persist")["attempt"] == 2 and len(reopened.transitions()) >= 4        # o historico atravessou o reinicio
