"""FP-060 MT-09 (#628): o Agent Bar mostra o EventStore (SQLite) real, somente leitura, e nunca apresenta banco ausente/ilegivel como saudavel."""
from __future__ import annotations

import datetime as dt
import sqlite3

import pytest

from tools.orchestration.agent_bar import collectors as col
from tools.orchestration.agent_bar.models import AgentStatus, Snapshot
from tools.orchestration.event_store import EventStore

NOW = dt.datetime(2026, 11, 16, 12, 0, tzinfo=dt.timezone.utc)
T0 = NOW.timestamp()


class Clock:
    t = T0

    def __call__(self):
        return self.t


@pytest.fixture()
def store(tmp_path):
    clock = Clock()
    s = EventStore(tmp_path / "event_store.db", clock=clock)
    s.clock_handle = clock
    return s


def snap(store_dict) -> Snapshot:
    a = AgentStatus(name="x", label="y", level="ok", detail="d", pid=None, command=None, since=None)
    return Snapshot(at="t", claude=a, codex=a, listener=a, github=a, store=store_dict)


def test_a_missing_database_is_reported_as_absent_and_never_healthy(tmp_path):
    out = col.collect_store(tmp_path, NOW)
    assert out["state"] == "ausente" and not (tmp_path / "event_store.db").exists()                 # nada foi criado
    s = snap(out)
    assert s.store_ok() is False and "NAO e saudavel" in s.store_line()


def test_an_unreadable_database_is_reported_as_unavailable(tmp_path):
    (tmp_path / "event_store.db").write_bytes(b"isto nao e um banco sqlite" * 50)
    out = col.collect_store(tmp_path, NOW)
    assert out["state"] == "indisponivel" and snap(out).store_ok() is False and "NAO e saudavel" in snap(out).store_line()


def test_an_empty_healthy_store_reads_as_ok_with_zero_counts(store, tmp_path):
    out = col.collect_store(tmp_path, NOW)
    assert out["state"] == "ok" and out["counts"] == {} and out["dlq"] == [] and out["zombies"] == 0
    assert snap(out).store_ok() is True and "0 pendente(s)" in snap(out).store_line()


def test_the_queue_leases_backoff_retries_dlq_and_last_error_come_from_the_real_rows(store, tmp_path):
    clock = store.clock_handle
    store.publish("CORRECTION_REQUESTED", "k-live", "pr:1", {"x": 1})
    store.publish("CORRECTION_REQUESTED", "k-backoff", "pr:2", {"x": 1})
    store.publish("CORRECTION_REQUESTED", "k-dlq", "pr:3", {"x": 1}, max_attempts=1)
    store.publish("CORRECTION_REQUESTED", "k-wait", "pr:4", {"x": 1})
    live = store.claim(("CORRECTION_REQUESTED",), "worker-A", 300, job_id="pr:1")
    bo = store.claim(("CORRECTION_REQUESTED",), "w", 60, job_id="pr:2")
    store.fail(bo, "falha transitoria", retry_delay=900)                                            # PENDING em backoff, attempt 1
    dl = store.claim(("CORRECTION_REQUESTED",), "w", 60, job_id="pr:3")
    store.fail(dl, "esgotou", retry_delay=0)                                                       # DLQ
    clock.t += 5

    out = col.collect_store(tmp_path, dt.datetime.fromtimestamp(clock.t, dt.timezone.utc))

    assert out["counts"] == {"RUNNING": 1, "PENDING": 2, "DLQ": 1, "RECORDED": 1}                   # RECORDED = o fato JOB_FAILED do DLQ
    assert out["backoff"] == 1 and out["zombies"] == 0 and len(out["live_leases"]) == 1
    assert out["live_leases"][0]["owner"] == "worker-A" and 0 < out["live_leases"][0]["seconds_left"] <= 300
    assert [d["key"] for d in out["dlq"]] == ["k-dlq"] and out["retries"] == 0 and live["id"]
    assert out["last_error"]["error"] in ("esgotou", "falha transitoria")
    s = snap(out)
    assert s.store_ok() is False and "DLQ: #" in s.store_line() and "worker-A" in s.store_line()


def test_a_running_event_whose_lease_expired_is_flagged_as_a_dead_worker(store, tmp_path):
    clock = store.clock_handle
    store.publish("CORRECTION_REQUESTED", "k1", "pr:1", {"x": 1})
    store.claim(("CORRECTION_REQUESTED",), "morto", 5)
    clock.t += 60
    out = col.collect_store(tmp_path, dt.datetime.fromtimestamp(clock.t, dt.timezone.utc))
    assert out["zombies"] == 1 and out["live_leases"] == []
    s = snap(out)
    assert s.store_ok() is False and "ATENCAO 1 RUNNING com lease vencido" in s.store_line()


def test_collecting_never_writes_to_the_database(store, tmp_path):
    store.publish("CORRECTION_REQUESTED", "k1", "pr:1", {"x": 1})
    db = tmp_path / "event_store.db"
    before = db.read_bytes()
    col.collect_store(tmp_path, NOW)
    assert db.read_bytes() == before
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM events")
    conn.close()


@pytest.mark.parametrize("dirname", ["a#b", "p%20q", "com espaco"])
def test_a_directory_with_uri_special_characters_is_still_opened_read_only(tmp_path, dirname):
    folder = tmp_path / dirname
    folder.mkdir()
    EventStore(folder / "event_store.db").publish("CORRECTION_REQUESTED", "k", "pr:1", {"x": 1})
    assert col.collect_store(folder, NOW)["state"] == "ok"


def test_the_snapshot_diagnostic_carries_the_store_line_and_the_default_is_never_healthy():
    s = snap({"state": "ok", "counts": {"PENDING": 2}, "backoff": 1, "live_leases": [], "zombies": 0, "dlq": [], "retries": 0, "last_error": None})
    assert s.store_line() in s.diagnostic() and s.store_ok() is True
    default = Snapshot(at="t", claude=s.claude, codex=s.codex, listener=s.listener, github=s.github)
    assert default.store_ok() is False and "NAO e saudavel" in default.store_line()


def test_collect_snapshot_carries_the_real_store_into_the_snapshot_and_its_diagnostic(store, tmp_path):
    from tests.test_agent_bar import LISTENER_OK, gh_with, gov
    from tests.test_agent_bar import NOW as BAR_NOW
    store.publish("CORRECTION_REQUESTED", "k1", "pr:1", {"x": 1})
    (tmp_path / "bar").mkdir()
    g = gov(tmp_path / "bar")
    (g / "event_store.db").write_bytes((tmp_path / "event_store.db").read_bytes())
    s = col.collect_snapshot(g, procs_fn=lambda: LISTENER_OK, task_fn=lambda: "Running", gh=gh_with([{"conclusion": "SUCCESS"}]), now=BAR_NOW)
    assert s.store["state"] == "ok" and s.store["counts"] == {"PENDING": 1} and "EventStore: 1 pendente(s)" in s.diagnostic()


def test_collect_snapshot_without_a_database_says_so_in_the_diagnostic(tmp_path):
    from tests.test_agent_bar import LISTENER_OK, gh_with, gov
    from tests.test_agent_bar import NOW as BAR_NOW
    (tmp_path / "bar2").mkdir()
    g = gov(tmp_path / "bar2")
    s = col.collect_snapshot(g, procs_fn=lambda: LISTENER_OK, task_fn=lambda: "Running", gh=gh_with([{"conclusion": "SUCCESS"}]), now=BAR_NOW)
    assert s.store["state"] == "ausente" and "NAO e saudavel" in s.diagnostic()


def test_the_database_is_always_opened_with_the_sqlite_read_only_uri(store, tmp_path, monkeypatch):
    seen = []
    real = sqlite3.connect
    monkeypatch.setattr(col.__dict__.get("sqlite3", sqlite3), "connect", lambda target, *a, **k: (seen.append((target, k.get("uri"))), real(target, *a, **k))[1])
    col.collect_store(tmp_path, NOW)
    assert len(seen) == 1 and seen[0][0].endswith("?mode=ro") and seen[0][1] is True
