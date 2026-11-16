"""FP-060 MT-08 (#627): recuperacao e concorrencia do EventStore com PROCESSOS REAIS do SO (nao threads, nao relogio simulado).
Cobre linhas da matriz da SPEC §9: dois workers disputam um job, evento duplicado, worker encerrado, SQLite reiniciado, falha permanente => DLQ."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
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

BARRIER = """
def wait_for(path, limit=30.0):
    import os, time
    end = time.time() + limit
    while not os.path.exists(path):
        if time.time() > end:
            raise SystemExit("barreira nao liberada")
        time.sleep(0.01)
"""

# todos os filhos avisam "ready", esperam o arquivo GO e so entao disputam: a disputa e simultanea de verdade, nao sequencial
DRAIN = BARRIER + """
import json, sys
from tools.orchestration.event_store import EventStore
s = EventStore(sys.argv[1])
print(json.dumps({"ready": True}), flush=True)
wait_for(sys.argv[3])
done = []
while True:
    ev = s.claim(("REVIEW_REQUESTED",), sys.argv[2], 30.0)
    if ev is None:
        break
    s.complete(ev, {"by": sys.argv[2]})
    done.append(ev["id"])
print(json.dumps(done), flush=True)
"""

# cada filho tenta reivindicar UMA vez o mesmo evento e MANTEM o claim (nao completa) ate o arquivo RELEASE existir:
# o vencedor continua dono enquanto os demais tentam, entao so um pode obte-lo
CLAIM_ONCE_AND_HOLD = BARRIER + """
import json, sys
from tools.orchestration.event_store import EventStore
s = EventStore(sys.argv[1])
print(json.dumps({"ready": True}), flush=True)
wait_for(sys.argv[3])
ev = s.claim(("REVIEW_REQUESTED",), sys.argv[2], 60.0)
print(json.dumps({"claimed": ev["id"] if ev else None, "owner": sys.argv[2]}), flush=True)
wait_for(sys.argv[4])
"""

PUBLISH = BARRIER + """
import json, sys
from tools.orchestration.event_store import EventStore
s = EventStore(sys.argv[1])
print(json.dumps({"ready": True}), flush=True)
wait_for(sys.argv[3])
print(json.dumps(s.publish("REVIEW_REQUESTED", sys.argv[2], "job:dup", {"x": 1})), flush=True)
"""


class Child:
    """Processo filho com leitura de stdout COM PRAZO (thread + fila: `readline` bloqueante nao respeita prazo, nem no Windows)."""

    def __init__(self, code: str, *args: str):
        env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"}
        self.proc = subprocess.Popen([sys.executable, "-c", code, *args], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.lines: queue.Queue = queue.Queue()
        self.stderr = ""
        threading.Thread(target=self._pump, daemon=True).start()
        threading.Thread(target=self._pump_err, daemon=True).start()

    def _pump(self):
        for ln in self.proc.stdout:
            self.lines.put(ln)
        self.lines.put(None)                                                                  # EOF

    def _pump_err(self):
        self.stderr = self.proc.stderr.read()[:400]

    def line(self, timeout: float = 30.0):
        try:
            ln = self.lines.get(timeout=timeout)
        except queue.Empty:
            raise AssertionError(f"filho nao respondeu em {timeout}s") from None
        if ln is None:
            raise AssertionError(f"filho terminou sem responder: {self.stderr}")
        return json.loads(ln)

    def finish(self, timeout: float = 60.0) -> int:
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.kill()
            raise AssertionError("filho nao terminou a tempo") from None

    def kill(self):
        if self.proc.poll() is None:
            self.proc.kill()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass


@pytest.fixture()
def children():
    """Todo filho nasce aqui e e morto e aguardado no fim, passe ou falhe o teste (nenhum processo orfao)."""
    made: list[Child] = []

    def spawn(code: str, *args: str) -> Child:
        c = Child(code, *args)
        made.append(c)
        return c
    yield spawn
    for c in made:
        c.kill()


@pytest.fixture()
def db(tmp_path):
    return tmp_path / "events.db"


def only(store: EventStore, key: str) -> dict:
    return next(e for e in store.events() if e["idempotency_key"] == key)


def test_a_worker_process_killed_after_claiming_is_recovered_once_and_its_late_result_is_fenced(db, children):
    store = EventStore(db)
    store.publish(TYPE, "k1", "job:1", {"pr": 1})
    proc = children(CLAIM_AND_HANG, str(db), "worker-dead", str(LEASE_S))
    info = proc.line()
    proc.kill()                                                                              # morte real do processo dono, sem aviso
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


def test_several_real_processes_racing_for_the_queue_claim_each_event_exactly_once(db, children, tmp_path):
    store = EventStore(db)
    ids = [store.publish(TYPE, f"k{n}", f"job:{n}", {"n": n})[0] for n in range(16)]
    go = tmp_path / "go"
    procs = [children(DRAIN, str(db), f"w{i}", str(go)) for i in range(4)]
    assert all(p.line() == {"ready": True} for p in procs)                                   # os 4 estao de pe e esperando a barreira
    go.write_text("go")                                                                      # largada simultanea
    claimed: list[int] = []
    for proc in procs:
        claimed += proc.line(60)
        assert proc.finish() == 0, proc.stderr
    assert sorted(claimed) == sorted(ids) and len(claimed) == len(set(claimed))              # ninguem repetiu, ninguem ficou de fora
    assert {e["status"] for e in store.events()} == {"DONE"} and {e["attempt"] for e in store.events()} == {1}


def test_workers_contending_for_one_event_while_the_winner_still_holds_it_only_one_gets_it(db, children, tmp_path):
    store = EventStore(db)
    ev_id = store.publish(TYPE, "only-one", "job:one", {"x": 1})[0]
    go, release = tmp_path / "go", tmp_path / "release"
    procs = [children(CLAIM_ONCE_AND_HOLD, str(db), f"w{i}", str(go), str(release)) for i in range(5)]
    assert all(p.line() == {"ready": True} for p in procs)
    go.write_text("go")
    answers = [p.line(60) for p in procs]                                                    # todos tentaram; o vencedor continua DONO (nao completou)
    winners = [a for a in answers if a["claimed"] is not None]
    assert len(winners) == 1 and winners[0]["claimed"] == ev_id                              # so UM obteve o evento
    assert only(store, "only-one")["status"] == "RUNNING" and only(store, "only-one")["attempt"] == 1
    assert [a["claimed"] for a in answers].count(None) == 4                                  # os outros 4 viram a fila vazia
    release.write_text("done")
    assert all(p.finish() == 0 for p in procs)


def test_the_same_event_published_by_many_real_processes_is_created_once(db, children, tmp_path):
    EventStore(db)
    go = tmp_path / "go"
    procs = [children(PUBLISH, str(db), "dup-key", str(go)) for _ in range(6)]
    assert all(p.line() == {"ready": True} for p in procs)
    go.write_text("go")                                                                      # as 6 publicacoes saem juntas
    results = []
    for proc in procs:
        results.append(proc.line(60))
        assert proc.finish() == 0, proc.stderr
    assert sum(1 for _id, created in results if created) == 1 and len({r[0] for r in results}) == 1
    assert len(EventStore(db).events()) == 1


def test_a_job_that_keeps_killing_its_workers_ends_in_the_dlq_with_a_diagnostic(db, children):
    store = EventStore(db)
    store.publish(TYPE, "poison", "job:poison", {"x": 1}, max_attempts=2)
    for n in range(2):
        proc = children(CLAIM_AND_HANG, str(db), f"victim-{n}", str(LEASE_S))
        assert proc.line()["attempt"] == n + 1
        proc.kill()
        time.sleep(LEASE_S + 0.5)
    assert store.claim((TYPE,), "survivor", LEASE_S) is None                                  # esgotou as tentativas: nao volta a ser reivindicado
    ev = only(store, "poison")
    assert ev["status"] == "DLQ" and "lease expired" in (ev["error"] or "")
    assert any(e["event_type"] == "JOB_FAILED" for e in store.events())                       # a falha permanente deixa o fato registrado


def test_events_survive_closing_and_reopening_the_database_in_another_process(db, children, tmp_path):
    store = EventStore(db)
    store.publish(TYPE, "persist", "job:p", {"keep": "me"})
    ev = store.claim((TYPE,), "w0", 60.0)
    store.fail(ev, "falha transitoria", retry_delay=0)
    del store
    go = tmp_path / "go"
    go.write_text("go")                                                                      # sem disputa aqui: a barreira ja esta liberada
    proc = children(DRAIN, str(db), "after-restart", str(go))
    assert proc.line() == {"ready": True}
    done = proc.line(60)
    assert proc.finish() == 0, proc.stderr
    reopened = EventStore(db)
    assert done and only(reopened, "persist")["status"] == "DONE"
    assert only(reopened, "persist")["attempt"] == 2 and len(reopened.transitions()) >= 4        # o historico atravessou o reinicio


def test_a_child_that_never_answers_fails_by_timeout_and_is_killed(children):
    silent = children("import time; time.sleep(120)")
    t0 = time.time()
    with pytest.raises(AssertionError, match="nao respondeu"):
        silent.line(timeout=0.5)
    assert time.time() - t0 < 5                                                               # o prazo e efetivo mesmo com o filho vivo e mudo
    silent.kill()
    assert silent.proc.poll() is not None                                                     # nao fica orfao
