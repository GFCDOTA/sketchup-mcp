"""Deterministic resilience tests for event_store/workers (no LLM calls).

Real OS processes are used where the property is about processes (crash,
concurrent consumers). The LLM-backed paths are exercised by
run_real_e2e.py / live_resilience.py, never faked here.
"""
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from event_store import EventStore, LeaseLost
from workers import JobPaths, handle_changes, handle_review, sha256_file, validate_review

HERE = Path(__file__).resolve().parent


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.clock = Clock()
        self.store = EventStore(self.dir / "q.sqlite", clock=self.clock)

    def tearDown(self):
        self.tmp.cleanup()


class TestStore(Base):
    def test_event_row_has_required_fields(self):
        eid, _ = self.store.publish("IMPLEMENT_REQUESTED", "k1", "j", {"round": 1})
        row = self.store.get(eid)
        for f in ("id", "event_type", "payload", "status", "attempt", "created_at", "updated_at",
                  "idempotency_key", "lease_owner", "lease_token", "lease_until"):
            self.assertIn(f, row)

    def test_duplicate_publish_does_not_create_second_job_nor_overwrite(self):
        a, c1 = self.store.publish("IMPLEMENT_REQUESTED", "k", "j", {"round": 1})
        b, c2 = self.store.publish("IMPLEMENT_REQUESTED", "k", "j", {"round": 1, "evil": True})
        self.assertEqual((a, c1, c2), (b, True, False))
        self.assertEqual(len(self.store.events()), 1)
        self.assertNotIn("evil", json.loads(self.store.get(a)["payload"]))

    def test_only_one_of_two_claimers_wins(self):
        self.store.publish("REVIEW_REQUESTED", "k", "j", {})
        first = self.store.claim("REVIEW_REQUESTED", "w1", 30)
        second = self.store.claim("REVIEW_REQUESTED", "w2", 30)
        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_completed_job_is_never_claimed_again(self):
        self.store.publish("IMPLEMENT_REQUESTED", "k", "j", {})
        ev = self.store.claim("IMPLEMENT_REQUESTED", "w", 30)
        self.store.complete(ev, {"ok": 1})
        self.clock.t += 10_000
        self.assertIsNone(self.store.claim("IMPLEMENT_REQUESTED", "w", 30))
        # re-delivery of the same event key is also a no-op
        _, created = self.store.publish("IMPLEMENT_REQUESTED", "k", "j", {})
        self.assertFalse(created)
        self.assertIsNone(self.store.claim("IMPLEMENT_REQUESTED", "w", 30))

    def test_expired_lease_is_recovered_and_old_owner_is_fenced(self):
        self.store.publish("IMPLEMENT_REQUESTED", "k", "j", {})
        old = self.store.claim("IMPLEMENT_REQUESTED", "old", 5)
        self.clock.t += 2
        self.assertIsNone(self.store.claim("IMPLEMENT_REQUESTED", "new", 5))
        self.clock.t += 4
        new = self.store.claim("IMPLEMENT_REQUESTED", "new", 5)
        self.assertEqual(new["id"], old["id"])
        self.assertEqual(new["attempt"], 2)
        with self.assertRaises(LeaseLost):
            self.store.complete(old, {"stale": True})
        with self.assertRaises(LeaseLost):
            self.store.fail(old, "stale")
        self.assertFalse(self.store.renew(old, 5))
        self.store.complete(new, {"ok": True})
        self.assertEqual(self.store.get(new["id"])["status"], "DONE")

    def test_retry_then_dlq_records_job_failed(self):
        self.store.publish("IMPLEMENT_REQUESTED", "k", "j", {}, max_attempts=3)
        states = []
        for _ in range(3):
            ev = self.store.claim("IMPLEMENT_REQUESTED", "w", 30)
            self.assertIsNotNone(ev)
            states.append(self.store.fail(ev, "boom", retry_delay=1))
            self.assertIsNone(self.store.claim("IMPLEMENT_REQUESTED", "w", 30))  # backoff respected
            self.clock.t += 2
        self.assertEqual(states, ["PENDING", "PENDING", "DLQ"])
        self.assertIsNone(self.store.claim("IMPLEMENT_REQUESTED", "w", 30))
        self.assertEqual(self.store.job_terminal("j"), "JOB_FAILED")

    def test_complete_publishes_follow_ups_atomically_and_idempotently(self):
        self.store.publish("IMPLEMENT_REQUESTED", "k", "j", {})
        ev = self.store.claim("IMPLEMENT_REQUESTED", "w", 30)
        f = [{"event_type": "REVIEW_REQUESTED", "idempotency_key": "j:rev", "payload": {}}]
        ids = self.store.complete(ev, {}, follow_ups=f)
        self.assertEqual(self.store.get(ids[0])["parent_event_id"], ev["id"])
        self.assertEqual(self.store.get(ids[0])["status"], "PENDING")

    def test_restart_persistence(self):
        self.store.publish("IMPLEMENT_REQUESTED", "k", "j", {})
        reopened = EventStore(self.store.path, clock=self.clock)
        self.assertIsNotNone(reopened.claim("IMPLEMENT_REQUESTED", "w", 30))


class FakeCtx:
    def __init__(self, run_dir):
        self.run_dir, self.lease, self.timeout, self.bins, self.extra_env = run_dir, 30, 5, {}, {}


class TestStaleVersions(Base):
    """Reviews of an old artifact version must never be applied to a new one.
    These paths are rejected BEFORE any CLI is launched (bins={} would crash)."""

    def setUp(self):
        super().setUp()
        self.paths = JobPaths(self.dir, "job")
        self.paths.artifact.write_text("v1", encoding="utf-8")
        self.v1 = sha256_file(self.paths.artifact)
        self.paths.artifact.write_text("v2", encoding="utf-8")  # a newer version landed

    def test_stale_review_request_is_superseded(self):
        self.store.publish("REVIEW_REQUESTED", "r", "job", {"round": 1, "artifact_sha256": self.v1})
        ev = self.store.claim("REVIEW_REQUESTED", "codex", 30)
        handle_review(self.store, ev, FakeCtx(self.dir))
        self.assertEqual(self.store.get(ev["id"])["status"], "SUPERSEDED")
        self.assertEqual(self.store.runs(), [])  # no CLI launched

    def test_stale_change_request_does_not_trigger_new_round(self):
        review = {"issues": [{"severity": "major", "description": "x", "suggested_fix": "y"}], "summary": "s"}
        self.store.publish("REVIEW_CHANGES_REQUESTED", "c", "job", {"round": 1, "artifact_sha256": self.v1, "review": review})
        ev = self.store.claim("REVIEW_CHANGES_REQUESTED", "coord", 30)
        handle_changes(self.store, ev, FakeCtx(self.dir))
        self.assertEqual(self.store.get(ev["id"])["status"], "SUPERSEDED")
        self.assertFalse(any(e["event_type"] == "IMPLEMENT_REQUESTED" for e in self.store.events()))

    def test_round_limit_produces_job_failed(self):
        v2 = sha256_file(self.paths.artifact)
        review = {"issues": [{"severity": "major", "description": "x", "suggested_fix": "y"}], "summary": "s"}
        self.store.publish("REVIEW_CHANGES_REQUESTED", "c", "job", {"round": 3, "artifact_sha256": v2, "review": review})
        handle_changes(self.store, self.store.claim("REVIEW_CHANGES_REQUESTED", "coord", 30), FakeCtx(self.dir))
        self.assertEqual(self.store.job_terminal("job"), "JOB_FAILED")


class TestReviewValidation(unittest.TestCase):
    def good(self, **kw):
        r = {"verdict": "APPROVE", "artifact_sha256": "abc",
             "requirements": [{"id": i, "met": True, "evidence": "e"} for i in ("lowercase", "strip_ends", "collapse_spaces", "example")],
             "tests_assessment": {"adequate": True, "notes": ""}, "issues": [], "summary": "ok"}
        r.update(kw)
        return r

    def test_accepts_consistent_approval(self):
        validate_review(self.good(), "abc")

    def test_rejects_review_of_other_version(self):
        with self.assertRaises(ValueError):
            validate_review(self.good(), "def")

    def test_rejects_approve_with_unmet_requirement(self):
        r = self.good()
        r["requirements"][0]["met"] = False
        with self.assertRaises(ValueError):
            validate_review(r, "abc")

    def test_rejects_changes_without_issues(self):
        with self.assertRaises(ValueError):
            validate_review(self.good(verdict="REQUEST_CHANGES"), "abc")


CHILD = r'''
import sys, time
sys.path.insert(0, sys.argv[2])
from event_store import EventStore
s = EventStore(sys.argv[1])
ev = s.claim("IMPLEMENT_REQUESTED", "doomed-worker", 2)
print("CLAIMED", ev["id"], flush=True)
time.sleep(60)
'''

RACER = r'''
import sys
sys.path.insert(0, sys.argv[2])
from event_store import EventStore
s = EventStore(sys.argv[1])
got = []
while True:
    ev = s.claim("REVIEW_REQUESTED", "racer-" + sys.argv[3], 60)
    if not ev: break
    got.append(ev["id"])
    s.complete(ev, {"by": sys.argv[3]})
print(",".join(map(str, got)))
'''


class TestRealProcesses(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "q.sqlite"
        self.store = EventStore(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_killed_worker_does_not_lose_event_and_restart_recovers(self):
        eid, _ = self.store.publish("IMPLEMENT_REQUESTED", "k", "j", {})
        child = subprocess.Popen([sys.executable, "-c", CHILD, str(self.db), str(HERE)], stdout=subprocess.PIPE, text=True)
        self.assertTrue(child.stdout.readline().startswith("CLAIMED"))
        child.kill()
        child.wait()
        child.stdout.close()
        row = self.store.get(eid)
        self.assertEqual((row["status"], row["lease_owner"]), ("RUNNING", "doomed-worker"))
        time.sleep(2.2)
        ev = self.store.claim("IMPLEMENT_REQUESTED", "restarted-worker", 30)
        self.assertEqual((ev["id"], ev["attempt"]), (eid, 2))

    def test_two_consumer_processes_never_share_a_job(self):
        for i in range(40):
            self.store.publish("REVIEW_REQUESTED", f"k{i}", "j", {})
        racers = [subprocess.Popen([sys.executable, "-c", RACER, str(self.db), str(HERE), str(n)],
                                   stdout=subprocess.PIPE, text=True) for n in range(2)]
        outs = [r.communicate(timeout=60)[0].strip() for r in racers]
        ids = [int(x) for o in outs for x in o.split(",") if x]
        self.assertEqual(sorted(ids), sorted(e["id"] for e in self.store.events()))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(e["status"] == "DONE" for e in self.store.events()))


if __name__ == "__main__":
    unittest.main()
