"""FP-060/P1 (#606): Durable event store — publish/dedup, fenced claim, retry/DLQ,
transactional outbox with fenced claims, aggregate-level locking, correlation
tracking, restart recovery, crash recovery."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

from tools.orchestration.event_store import CONSUMABLE, EVENT_TYPES, EventStore, LeaseLost


class Clock:
    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float = 1.0):
        self.t += seconds
        return self.t


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def store(tmp_path, clock):
    return EventStore(tmp_path / "test.db", clock=clock)


# -- schema & meta ----------------------------------------------------------
class TestSchema:
    def test_schema_version_stored(self, store):
        with store._conn() as db:
            row = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        assert row["value"] == "1"

    def test_tables_exist(self, store):
        with store._conn() as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert {"events", "transitions", "subprocess_runs", "outbox", "meta"} <= tables

    def test_wal_mode(self, store):
        with store._conn() as db:
            assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    def test_stats(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {"a": 1})
        store.publish("CI_PASSED", "k2", "j1", {"b": 2})
        s = store.stats()
        assert s["events"]["PENDING"] == 1
        assert s["events"]["RECORDED"] == 1
        assert s["schema_version"] == 1

    def test_outbox_has_lease_columns(self, store):
        with store._conn() as db:
            cols = {r[1] for r in db.execute("PRAGMA table_info(outbox)").fetchall()}
        assert {"lease_owner", "lease_token", "lease_until"} <= cols


# -- publish & dedup --------------------------------------------------------
class TestPublish:
    def test_publish_creates_event_with_envelope_fields(self, store, clock):
        eid, created = store.publish("IMPLEMENT_REQUESTED", "key1", "job1", {"x": 1},
                                     correlation_id="cor1", aggregate_type="pull_request",
                                     producer="coordinator")
        assert created is True
        ev = store.get(eid)
        assert ev["event_type"] == "IMPLEMENT_REQUESTED"
        assert ev["status"] == "PENDING"
        assert ev["idempotency_key"] == "key1"
        assert ev["job_id"] == "job1"
        assert ev["correlation_id"] == "cor1"
        assert ev["aggregate_type"] == "pull_request"
        assert ev["producer"] == "coordinator"
        assert ev["event_id"]  # UUID populated
        assert json.loads(ev["payload"]) == {"x": 1}

    def test_dedup_same_key(self, store):
        id1, c1 = store.publish("IMPLEMENT_REQUESTED", "dup", "j1", {"first": True})
        id2, c2 = store.publish("IMPLEMENT_REQUESTED", "dup", "j1", {"second": True})
        assert id1 == id2 and c1 is True and c2 is False
        assert json.loads(store.get(id1)["payload"]) == {"first": True}

    def test_consumable_vs_recorded(self, store):
        for et in CONSUMABLE:
            eid, _ = store.publish(et, f"k-{et}", "j", {})
            assert store.get(eid)["status"] == "PENDING"
        eid, _ = store.publish("CI_PASSED", "k-ci", "j", {})
        assert store.get(eid)["status"] == "RECORDED"

    def test_unknown_event_type_raises(self, store):
        with pytest.raises(ValueError, match="unknown event type"):
            store.publish("NONEXISTENT_TYPE", "k", "j", {})

    def test_transition_logged_on_publish(self, store):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ts = store.transitions()
        assert len(ts) == 1
        assert ts[0]["from_status"] is None
        assert ts[0]["to_status"] == "PENDING"


# -- claim & fencing --------------------------------------------------------
class TestClaim:
    def test_claim_returns_event(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {"data": 42})
        ev = store.claim("IMPLEMENT_REQUESTED", "worker-1", lease_seconds=60)
        assert ev is not None
        assert ev["status"] == "RUNNING"
        assert ev["lease_owner"] == "worker-1"
        assert ev["lease_token"]
        assert ev["payload"] == {"data": 42}

    def test_exclusive_claim(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev1 = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        ev2 = store.claim("IMPLEMENT_REQUESTED", "w2", 60)
        assert ev1 is not None and ev2 is None

    def test_completed_never_reclaimed(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        store.complete(ev, {"ok": True})
        clock.advance(120)
        assert store.claim("IMPLEMENT_REQUESTED", "w2", 60) is None

    def test_expired_lease_reclaimed_with_new_token(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev1 = store.claim("IMPLEMENT_REQUESTED", "w1", 30)
        clock.advance(31)
        ev2 = store.claim("IMPLEMENT_REQUESTED", "w2", 60)
        assert ev2 is not None and ev2["lease_owner"] == "w2"
        assert ev2["lease_token"] != ev1["lease_token"]
        assert ev2["attempt"] == 2

    def test_stale_token_raises_on_complete(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev1 = store.claim("IMPLEMENT_REQUESTED", "w1", 30)
        clock.advance(31)
        store.claim("IMPLEMENT_REQUESTED", "w2", 60)
        with pytest.raises(LeaseLost):
            store.complete(ev1, {"stale": True})

    def test_renew_extends_lease(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 30)
        clock.advance(20)
        assert store.renew(ev, 60) is True
        clock.advance(25)
        assert store.claim("IMPLEMENT_REQUESTED", "w2", 60) is None

    def test_renew_fails_after_expiry(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 10)
        clock.advance(11)
        assert store.renew(ev, 60) is False

    def test_claim_multiple_types(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        store.publish("REVIEW_REQUESTED", "k2", "j2", {})
        ev = store.claim(["IMPLEMENT_REQUESTED", "REVIEW_REQUESTED"], "w1", 60)
        assert ev is not None
        assert ev["event_type"] in ("IMPLEMENT_REQUESTED", "REVIEW_REQUESTED")

    def test_claim_oldest_first(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {"order": 1})
        clock.advance(1)
        store.publish("IMPLEMENT_REQUESTED", "k2", "j2", {"order": 2})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        assert ev["payload"]["order"] == 1


# -- aggregate-level locking ------------------------------------------------
class TestAggregateLock:
    def test_same_job_exclusive(self, store, clock):
        """Two events for same job_id: only one can be RUNNING at a time."""
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {"first": True})
        store.publish("CORRECTION_REQUESTED", "k2", "j1", {"second": True})
        ev1 = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        assert ev1 is not None
        ev2 = store.claim("CORRECTION_REQUESTED", "w2", 60)
        assert ev2 is None

    def test_different_jobs_parallel(self, store, clock):
        """Events for different job_ids can be claimed in parallel."""
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        store.publish("IMPLEMENT_REQUESTED", "k2", "j2", {})
        ev1 = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        ev2 = store.claim("IMPLEMENT_REQUESTED", "w2", 60)
        assert ev1 is not None and ev2 is not None
        assert ev1["job_id"] != ev2["job_id"]

    def test_lock_released_after_completion(self, store, clock):
        """Completing an event releases the aggregate lock for the same job_id."""
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        store.publish("CORRECTION_REQUESTED", "k2", "j1", {})
        ev1 = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        store.complete(ev1, {"ok": True})
        ev2 = store.claim("CORRECTION_REQUESTED", "w2", 60)
        assert ev2 is not None

    def test_lock_released_after_lease_expiry(self, store, clock):
        """Expired lease releases the aggregate lock so a different event can be claimed."""
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        store.publish("CORRECTION_REQUESTED", "k2", "j1", {})
        ev1 = store.claim("IMPLEMENT_REQUESTED", "w1", 30)
        assert ev1 is not None
        clock.advance(31)
        ev2 = store.claim("CORRECTION_REQUESTED", "w2", 60)
        assert ev2 is not None
        assert ev2["event_type"] == "CORRECTION_REQUESTED"

    def test_aggregate_lock_skips_to_next_job(self, store, clock):
        """When first candidate's aggregate is locked, claim picks the next eligible job."""
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        clock.advance(1)
        store.publish("IMPLEMENT_REQUESTED", "k2", "j2", {})
        ev1 = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        assert ev1["job_id"] == "j1"
        store.publish("CORRECTION_REQUESTED", "k3", "j1", {})
        ev2 = store.claim(["IMPLEMENT_REQUESTED", "CORRECTION_REQUESTED"], "w2", 60)
        assert ev2 is not None
        assert ev2["job_id"] == "j2"


# -- complete with follow-ups & outbox -------------------------------------
class TestComplete:
    def test_complete_marks_done(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        store.complete(ev, {"result": "ok"})
        done = store.get(ev["id"])
        assert done["status"] == "DONE"
        assert json.loads(done["result"]) == {"result": "ok"}

    def test_transactional_followups(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        fids, _ = store.complete(ev, {"ok": True}, follow_ups=[
            {"event_type": "REVIEW_REQUESTED", "idempotency_key": "k-review", "payload": {"pr": 7}},
        ])
        assert len(fids) == 1
        fu = store.get(fids[0])
        assert fu["event_type"] == "REVIEW_REQUESTED"
        assert fu["status"] == "PENDING"
        assert fu["parent_event_id"] == ev["id"]

    def test_followup_inherits_correlation(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {}, correlation_id="chain-1")
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        fids, _ = store.complete(ev, {}, follow_ups=[
            {"event_type": "REVIEW_REQUESTED", "idempotency_key": "k-rev", "payload": {}},
        ])
        fu = store.get(fids[0])
        assert fu["correlation_id"] == "chain-1"

    def test_transactional_outbox(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        _, oids = store.complete(ev, {"ok": True}, outbox_entries=[
            {"target": "github", "operation": "request_review",
             "payload": {"pr": 7}, "idempotency_key": "ob-1"},
        ])
        assert len(oids) == 1
        pending = store.pending_outbox("github")
        assert len(pending) == 1
        assert json.loads(pending[0]["payload"]) == {"pr": 7}

    def test_outbox_claim_complete(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        _, oids = store.complete(ev, {}, outbox_entries=[
            {"target": "github", "operation": "comment", "payload": {}, "idempotency_key": "ob-2"},
        ])
        entry = store.claim_outbox("github", "worker", 60)
        assert entry is not None
        assert entry["lease_token"]
        store.complete_outbox(entry)
        assert store.pending_outbox("github") == []

    def test_outbox_retry_then_dlq(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        _, oids = store.complete(ev, {}, outbox_entries=[
            {"target": "github", "operation": "post", "payload": {}, "idempotency_key": "ob-3"},
        ])
        for i in range(4):
            entry = store.claim_outbox("github", "worker", 60)
            assert entry is not None, f"claim should succeed on retry {i}"
            result = store.fail_outbox(entry, f"err-{i}")
            assert result == "PENDING"
        entry = store.claim_outbox("github", "worker", 60)
        assert entry is not None
        assert store.fail_outbox(entry, "final") == "DLQ"


# -- outbox fencing ---------------------------------------------------------
class TestOutboxFencing:
    def _make_outbox_entry(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        store.complete(ev, {}, outbox_entries=[
            {"target": "github", "operation": "comment", "payload": {"x": 1},
             "idempotency_key": "ob-fence"},
        ])

    def test_claim_outbox_returns_fenced_entry(self, store, clock):
        self._make_outbox_entry(store, clock)
        entry = store.claim_outbox("github", "worker-1", 60)
        assert entry is not None
        assert entry["lease_owner"] == "worker-1"
        assert entry["lease_token"]
        assert entry["status"] == "RUNNING"
        assert entry["payload"] == {"x": 1}

    def test_outbox_exclusive_claim(self, store, clock):
        self._make_outbox_entry(store, clock)
        e1 = store.claim_outbox("github", "w1", 60)
        e2 = store.claim_outbox("github", "w2", 60)
        assert e1 is not None and e2 is None

    def test_outbox_expired_lease_reclaimed(self, store, clock):
        self._make_outbox_entry(store, clock)
        e1 = store.claim_outbox("github", "w1", 30)
        clock.advance(31)
        e2 = store.claim_outbox("github", "w2", 60)
        assert e2 is not None
        assert e2["lease_token"] != e1["lease_token"]
        assert e2["lease_owner"] == "w2"

    def test_outbox_complete_with_stale_token_raises(self, store, clock):
        self._make_outbox_entry(store, clock)
        e1 = store.claim_outbox("github", "w1", 30)
        clock.advance(31)
        store.claim_outbox("github", "w2", 60)
        with pytest.raises(LeaseLost):
            store.complete_outbox(e1)

    def test_outbox_fail_with_stale_token_raises(self, store, clock):
        self._make_outbox_entry(store, clock)
        e1 = store.claim_outbox("github", "w1", 30)
        clock.advance(31)
        store.claim_outbox("github", "w2", 60)
        with pytest.raises(LeaseLost):
            store.fail_outbox(e1, "too late")

    def test_done_outbox_never_reclaimable(self, store, clock):
        self._make_outbox_entry(store, clock)
        entry = store.claim_outbox("github", "worker", 60)
        store.complete_outbox(entry)
        assert store.claim_outbox("github", "worker", 60) is None

    def test_dlq_outbox_never_reclaimable(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        store.complete(ev, {}, outbox_entries=[
            {"target": "github", "operation": "post", "payload": {},
             "idempotency_key": "ob-dlq", "max_attempts": 1},
        ])
        entry = store.claim_outbox("github", "worker", 60)
        assert store.fail_outbox(entry, "fatal") == "DLQ"
        assert store.claim_outbox("github", "worker", 60) is None


# -- fail / retry / DLQ ---------------------------------------------------
class TestFailRetryDlq:
    def test_retry_returns_to_pending(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {}, max_attempts=3)
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        result = store.fail(ev, "transient error")
        assert result == "PENDING"
        refreshed = store.get(ev["id"])
        assert refreshed["status"] == "PENDING"
        assert refreshed["error"] == "transient error"

    def test_exhaust_attempts_goes_to_dlq(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {}, max_attempts=2)
        for attempt in range(2):
            ev = store.claim("IMPLEMENT_REQUESTED", f"w{attempt}", 60)
            assert ev is not None, f"claim should succeed on attempt {attempt}"
            result = store.fail(ev, f"err-{attempt}")
            clock.advance(2)
        assert result == "DLQ"
        assert store.get(ev["id"])["status"] == "DLQ"

    def test_dlq_records_job_failed_fact(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {}, max_attempts=1)
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        store.fail(ev, "fatal")
        events = store.events("j1")
        failed_facts = [e for e in events if e["event_type"] == "JOB_FAILED"]
        assert len(failed_facts) == 1
        assert failed_facts[0]["status"] == "RECORDED"

    def test_retry_delay(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {}, max_attempts=3)
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        store.fail(ev, "err", retry_delay=10.0)
        assert store.claim("IMPLEMENT_REQUESTED", "w2", 60) is None
        clock.advance(11)
        ev2 = store.claim("IMPLEMENT_REQUESTED", "w2", 60)
        assert ev2 is not None


# -- supersede -------------------------------------------------------------
class TestSupersede:
    def test_supersede_marks_superseded(self, store, clock):
        store.publish("REVIEW_REQUESTED", "k1", "j1", {})
        ev = store.claim("REVIEW_REQUESTED", "w1", 60)
        store.supersede(ev, "new HEAD pushed")
        assert store.get(ev["id"])["status"] == "SUPERSEDED"

    def test_superseded_not_reclaimable(self, store, clock):
        store.publish("REVIEW_REQUESTED", "k1", "j1", {})
        ev = store.claim("REVIEW_REQUESTED", "w1", 60)
        store.supersede(ev, "stale")
        clock.advance(120)
        assert store.claim("REVIEW_REQUESTED", "w2", 60) is None


# -- subprocess audit ------------------------------------------------------
class TestSubprocessAudit:
    def test_run_lifecycle(self, store, clock):
        eid, _ = store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        rid = store.run_started(eid, "claude", ["python", "-c", "pass"], "/tmp", 1234, "/tmp/out", "/tmp/err")
        clock.advance(5)
        store.run_finished(rid, exit_code=0, timed_out=False, outcome="success")
        runs = store.runs()
        assert len(runs) == 1
        assert runs[0]["agent"] == "claude"
        assert runs[0]["exit_code"] == 0
        assert runs[0]["timed_out"] == 0


# -- correlation tracking --------------------------------------------------
class TestCorrelation:
    def test_full_chain_shares_correlation_id(self, store, clock):
        cor = uuid.uuid4().hex
        store.publish("IMPLEMENT_REQUESTED", "k-impl", "j1", {}, correlation_id=cor)
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        fids, _ = store.complete(ev, {}, follow_ups=[
            {"event_type": "REVIEW_REQUESTED", "idempotency_key": "k-rev", "payload": {}},
        ])
        rev_ev = store.claim("REVIEW_REQUESTED", "w2", 60)
        store.complete(rev_ev, {}, follow_ups=[
            {"event_type": "CI_PASSED", "idempotency_key": "k-ci", "payload": {}},
        ])
        all_evs = store.events("j1")
        for e in all_evs:
            assert e["correlation_id"] == cor


# -- reads ------------------------------------------------------------------
class TestReads:
    def test_events_by_job(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        store.publish("IMPLEMENT_REQUESTED", "k2", "j2", {})
        assert len(store.events("j1")) == 1
        assert len(store.events()) == 2

    def test_job_terminal(self, store, clock):
        store.publish("REVIEW_APPROVED", "k-ok", "j1", {})
        assert store.job_terminal("j1") == "REVIEW_APPROVED"
        assert store.job_terminal("j-none") is None


# -- persistence & restart --------------------------------------------------
class TestPersistence:
    def test_survives_restart(self, tmp_path, clock):
        path = tmp_path / "persist.db"
        s1 = EventStore(path, clock=clock)
        s1.publish("IMPLEMENT_REQUESTED", "k1", "j1", {"survive": True})
        s1.claim("IMPLEMENT_REQUESTED", "w1", 300)
        del s1

        s2 = EventStore(path, clock=clock)
        events = s2.events("j1")
        assert len(events) == 1
        assert events[0]["status"] == "RUNNING"
        assert json.loads(events[0]["payload"]) == {"survive": True}

    def test_expired_lease_recovered_after_restart(self, tmp_path, clock):
        path = tmp_path / "recover.db"
        s1 = EventStore(path, clock=clock)
        s1.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        s1.claim("IMPLEMENT_REQUESTED", "crashed-worker", 30)
        del s1

        clock.advance(31)
        s2 = EventStore(path, clock=clock)
        ev = s2.claim("IMPLEMENT_REQUESTED", "new-worker", 60)
        assert ev is not None and ev["lease_owner"] == "new-worker"


# -- crash, retry, lease expiry, late messages, duplicate effects -----------
class TestCrashAndLateMessages:
    def test_crash_recovery_event_lease_expires(self, store, clock):
        """Worker crashes mid-processing; lease expires; new worker reclaims."""
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev1 = store.claim("IMPLEMENT_REQUESTED", "crashed-worker", 30)
        clock.advance(31)
        ev2 = store.claim("IMPLEMENT_REQUESTED", "recovery-worker", 60)
        assert ev2 is not None
        assert ev2["lease_owner"] == "recovery-worker"
        assert ev2["lease_token"] != ev1["lease_token"]
        assert ev2["attempt"] == 2

    def test_late_complete_after_reclaim_raises(self, store, clock):
        """Crashed worker's stale complete is rejected; recovery worker succeeds."""
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev1 = store.claim("IMPLEMENT_REQUESTED", "w1", 30)
        clock.advance(31)
        ev2 = store.claim("IMPLEMENT_REQUESTED", "w2", 60)
        with pytest.raises(LeaseLost):
            store.complete(ev1, {"stale": True})
        store.complete(ev2, {"ok": True})
        assert store.get(ev2["id"])["status"] == "DONE"

    def test_duplicate_complete_raises(self, store, clock):
        """Completing an already-completed event raises LeaseLost (no double effects)."""
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        store.complete(ev, {"first": True})
        with pytest.raises(LeaseLost):
            store.complete(ev, {"second": True})

    def test_outbox_crash_and_reclaim(self, store, clock):
        """Outbox entry claimed, worker crashes, new worker reclaims after lease expiry."""
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        store.complete(ev, {}, outbox_entries=[
            {"target": "github", "operation": "comment", "payload": {},
             "idempotency_key": "ob-crash"},
        ])
        e1 = store.claim_outbox("github", "worker-1", 30)
        assert e1 is not None
        clock.advance(31)
        e2 = store.claim_outbox("github", "worker-2", 60)
        assert e2 is not None
        assert e2["lease_token"] != e1["lease_token"]
        with pytest.raises(LeaseLost):
            store.complete_outbox(e1)
        store.complete_outbox(e2)

    def test_late_outbox_fail_on_done_entry(self, store, clock):
        """Late fail callback on a DONE outbox entry raises LeaseLost."""
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        store.complete(ev, {}, outbox_entries=[
            {"target": "github", "operation": "post", "payload": {},
             "idempotency_key": "ob-late"},
        ])
        entry = store.claim_outbox("github", "worker", 60)
        store.complete_outbox(entry)
        with pytest.raises(LeaseLost):
            store.fail_outbox(entry, "too late")

    def test_lease_expiry_during_outbox_processing(self, store, clock):
        """Outbox lease expires while processing; complete with stale token raises."""
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        store.complete(ev, {}, outbox_entries=[
            {"target": "github", "operation": "post", "payload": {},
             "idempotency_key": "ob-expire"},
        ])
        entry = store.claim_outbox("github", "worker", 10)
        clock.advance(11)
        with pytest.raises(LeaseLost):
            store.complete_outbox(entry)
        e2 = store.claim_outbox("github", "worker-2", 60)
        assert e2 is not None
        store.complete_outbox(e2)


# -- real process concurrency -----------------------------------------------
class TestRealConcurrency:
    def test_concurrent_claim_barrier(self, tmp_path):
        """4 processes claim simultaneously via multiprocessing.Barrier; exactly one wins."""
        repo_root = Path(__file__).resolve().parent.parent
        path = tmp_path / "concurrent.db"
        store = EventStore(path)
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})

        script = textwrap.dedent(f"""\
            import sys, json
            sys.path.insert(0, r"{repo_root}")
            import multiprocessing

            def worker(barrier, db_path, wid, results):
                from tools.orchestration.event_store import EventStore
                s = EventStore(db_path)
                barrier.wait()
                ev = s.claim("IMPLEMENT_REQUESTED", f"w-{{wid}}", 60)
                results[wid] = ev is not None

            if __name__ == "__main__":
                manager = multiprocessing.Manager()
                results = manager.dict()
                barrier = multiprocessing.Barrier(4)
                procs = []
                for i in range(4):
                    p = multiprocessing.Process(target=worker,
                        args=(barrier, r"{path}", i, results))
                    procs.append(p)
                for p in procs:
                    p.start()
                for p in procs:
                    p.join(timeout=30)
                claims = [results.get(i, False) for i in range(4)]
                print(json.dumps({{"winners": sum(claims)}}))
        """)
        script_path = tmp_path / "conc_claim.py"
        script_path.write_text(script, encoding="utf-8")

        r = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, timeout=60,
            cwd=str(repo_root),
        )
        assert r.returncode == 0, f"script failed: {r.stderr}"
        result = json.loads(r.stdout.strip())
        assert result["winners"] == 1

    def test_concurrent_aggregate_lock(self, tmp_path):
        """Two events for same job_id, concurrent claims via Barrier: only one wins."""
        repo_root = Path(__file__).resolve().parent.parent
        path = tmp_path / "agg.db"
        store = EventStore(path)
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        store.publish("CORRECTION_REQUESTED", "k2", "j1", {})

        script = textwrap.dedent(f"""\
            import sys, json
            sys.path.insert(0, r"{repo_root}")
            import multiprocessing

            def worker(barrier, db_path, wid, etype, results):
                from tools.orchestration.event_store import EventStore
                s = EventStore(db_path)
                barrier.wait()
                ev = s.claim(etype, f"w-{{wid}}", 60)
                results[wid] = ev is not None

            if __name__ == "__main__":
                manager = multiprocessing.Manager()
                results = manager.dict()
                barrier = multiprocessing.Barrier(2)
                types = ["IMPLEMENT_REQUESTED", "CORRECTION_REQUESTED"]
                procs = []
                for i in range(2):
                    p = multiprocessing.Process(target=worker,
                        args=(barrier, r"{path}", i, types[i], results))
                    procs.append(p)
                for p in procs:
                    p.start()
                for p in procs:
                    p.join(timeout=30)
                claims = [results.get(i, False) for i in range(2)]
                print(json.dumps({{"winners": sum(claims)}}))
        """)
        script_path = tmp_path / "conc_agg.py"
        script_path.write_text(script, encoding="utf-8")

        r = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, timeout=60,
            cwd=str(repo_root),
        )
        assert r.returncode == 0, f"script failed: {r.stderr}"
        result = json.loads(r.stdout.strip())
        assert result["winners"] == 1

    def test_concurrent_outbox_claim(self, tmp_path):
        """3 processes claim the same outbox entry via Barrier; exactly one wins."""
        repo_root = Path(__file__).resolve().parent.parent
        path = tmp_path / "outbox_conc.db"
        store = EventStore(path)
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 300)
        store.complete(ev, {}, outbox_entries=[
            {"target": "github", "operation": "comment", "payload": {},
             "idempotency_key": "ob-conc"},
        ])

        script = textwrap.dedent(f"""\
            import sys, json
            sys.path.insert(0, r"{repo_root}")
            import multiprocessing

            def worker(barrier, db_path, wid, results):
                from tools.orchestration.event_store import EventStore
                s = EventStore(db_path)
                barrier.wait()
                entry = s.claim_outbox("github", f"w-{{wid}}", 60)
                results[wid] = entry is not None

            if __name__ == "__main__":
                manager = multiprocessing.Manager()
                results = manager.dict()
                barrier = multiprocessing.Barrier(3)
                procs = []
                for i in range(3):
                    p = multiprocessing.Process(target=worker,
                        args=(barrier, r"{path}", i, results))
                    procs.append(p)
                for p in procs:
                    p.start()
                for p in procs:
                    p.join(timeout=30)
                claims = [results.get(i, False) for i in range(3)]
                print(json.dumps({{"winners": sum(claims)}}))
        """)
        script_path = tmp_path / "conc_outbox.py"
        script_path.write_text(script, encoding="utf-8")

        r = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, timeout=60,
            cwd=str(repo_root),
        )
        assert r.returncode == 0, f"script failed: {r.stderr}"
        result = json.loads(r.stdout.strip())
        assert result["winners"] == 1


# -- event types completeness ----------------------------------------------
class TestEventTypes:
    def test_consumable_is_subset_of_event_types(self):
        assert CONSUMABLE <= EVENT_TYPES

    def test_all_spec_event_types_present(self):
        required = {
            "ISSUE_READY", "PR_OPENED", "PR_HEAD_UPDATED", "CI_PASSED", "CI_FAILED",
            "GITHUB_REVIEW_SUBMITTED", "PR_MERGED", "ISSUE_UNBLOCKED",
            "IMPLEMENT_REQUESTED", "IMPLEMENT_STARTED", "IMPLEMENT_COMPLETED",
            "IMPLEMENT_FAILED", "CORRECTION_REQUESTED",
            "REVIEW_REQUESTED", "REVIEW_STARTED", "REVIEW_APPROVED",
            "REVIEW_CHANGES_REQUESTED", "REVIEW_BLOCKED",
            "JOB_RETRY_SCHEDULED", "JOB_SUPERSEDED", "JOB_FAILED", "JOB_DEAD_LETTERED",
            "PUBLISH_REQUESTED", "PUBLISH_COMPLETED", "PUBLISH_FAILED",
            "WORKFLOW_COMPLETED",
        }
        assert required <= EVENT_TYPES
