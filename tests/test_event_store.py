"""FP-060/P1 (#606): Durable event store — publish/dedup, fenced claim, retry/DLQ,
transactional outbox, correlation tracking, restart recovery."""
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

    def test_outbox_complete_and_fail(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        _, oids = store.complete(ev, {}, outbox_entries=[
            {"target": "github", "operation": "comment", "payload": {}, "idempotency_key": "ob-2"},
        ])
        store.complete_outbox(oids[0])
        assert store.pending_outbox("github") == []

    def test_outbox_retry_then_dlq(self, store, clock):
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})
        ev = store.claim("IMPLEMENT_REQUESTED", "w1", 60)
        _, oids = store.complete(ev, {}, outbox_entries=[
            {"target": "github", "operation": "post", "payload": {}, "idempotency_key": "ob-3"},
        ])
        oid = oids[0]
        for i in range(4):
            result = store.fail_outbox(oid, f"err-{i}")
            assert result == "PENDING"
        assert store.fail_outbox(oid, "final") == "DLQ"


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


# -- real process isolation -------------------------------------------------
class TestRealProcesses:
    def test_two_consumers_never_share_a_job(self, tmp_path, clock):
        repo_root = Path(__file__).resolve().parent.parent
        path = tmp_path / "race.db"
        store = EventStore(path, clock=clock)
        store.publish("IMPLEMENT_REQUESTED", "k1", "j1", {})

        script = textwrap.dedent(f"""\
            import sys, json
            sys.path.insert(0, r"{repo_root}")
            from tools.orchestration.event_store import EventStore
            s = EventStore(r"{path}")
            ev = s.claim("IMPLEMENT_REQUESTED", f"proc-{{sys.argv[1]}}", 60)
            print(json.dumps({{"claimed": ev is not None}}))
        """)
        script_path = tmp_path / "claimer.py"
        script_path.write_text(script, encoding="utf-8")

        results = []
        for i in range(2):
            r = subprocess.run(
                [sys.executable, str(script_path), str(i)],
                capture_output=True, text=True, timeout=10,
                cwd=str(repo_root),
            )
            results.append(json.loads(r.stdout.strip()))

        claims = [r["claimed"] for r in results]
        assert claims.count(True) == 1


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
