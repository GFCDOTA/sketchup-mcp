"""Integration tests for EventStore shadow wiring (FP-060).

Tests that the bridge dual-writes to both JSON and SQLite, and that the
executor syncs results back to the EventStore after completing a JSON item.
"""
from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path

import pytest

from tools.orchestration import event_bridge as eb
from tools.orchestration import event_executor as ee
from tools.orchestration import store_factory as sf
from tools.orchestration.event_store import EventStore

NOW = dt.datetime(2026, 11, 8, 12, 0, tzinfo=dt.timezone.utc)
HEAD = "b" * 40
POLICY = {"reviewers": ["fmmodesto"], "executor_logins": ["fmodesto30"]}


def review(rid=1, login="fmmodesto", state="CHANGES_REQUESTED", commit=HEAD):
    return {"id": rid, "user": {"login": login}, "state": state, "commit_id": commit,
            "html_url": f"https://x/r/{rid}", "submitted_at": "2026-11-08T11:00:00Z"}


HEAD2 = "c" * 40


def fake_gh(reviews=(), head=HEAD, body="Refs #606"):
    def gh(path):
        if path.startswith("repos/GFCDOTA/sketchup-mcp/pulls?"):
            return [{"number": 10, "head": {"sha": head}, "body": body}]
        if "/reviews" in path:
            return list(reviews)
        if "/issues/comments" in path:
            return []
        raise AssertionError(path)
    return gh


def fake_gh_two_prs(reviews_pr10=(), reviews_pr20=()):
    """Two open PRs: #10 and #20, each with its own reviews."""
    def gh(path):
        if path.startswith("repos/GFCDOTA/sketchup-mcp/pulls?"):
            return [{"number": 10, "head": {"sha": HEAD}, "body": "Refs #606"},
                    {"number": 20, "head": {"sha": HEAD2}, "body": "Refs #607"}]
        if "/pulls/10/reviews" in path:
            return list(reviews_pr10)
        if "/pulls/20/reviews" in path:
            return list(reviews_pr20)
        if "/issues/comments" in path:
            return []
        raise AssertionError(path)
    return gh


@pytest.fixture
def store(tmp_path):
    return EventStore(tmp_path / "test.db")


@pytest.fixture(autouse=True)
def _reset_singleton():
    sf.reset_store()
    yield
    sf.reset_store()


# ---- bridge dual-write ---------------------------------------------------

class TestBridgeDualWrite:
    def test_accepted_review_is_published_to_store(self, tmp_path, store):
        bp = tmp_path / "bridge.json"
        counts = eb.run_cycle(fake_gh(reviews=[review()]), POLICY, bp, now=NOW, store=store)
        assert counts["ACCEPT"] == 1
        b = eb.load(bp)
        assert len(b["queue"]) == 1
        events = store.events()
        assert len(events) == 1
        ev = events[0]
        assert ev["event_type"] == "CORRECTION_REQUESTED"
        assert ev["status"] == "PENDING"
        payload = json.loads(ev["payload"]) if isinstance(ev["payload"], str) else ev["payload"]
        assert payload["pr"] == 10
        assert payload["head_sha"] == HEAD

    def test_duplicate_review_is_not_published_twice(self, tmp_path, store):
        bp = tmp_path / "bridge.json"
        gh = fake_gh(reviews=[review()])
        eb.run_cycle(gh, POLICY, bp, now=NOW, store=store)
        eb.run_cycle(gh, POLICY, bp, now=NOW, store=store)
        assert len(store.events()) == 1

    def test_ignored_review_is_not_published(self, tmp_path, store):
        bp = tmp_path / "bridge.json"
        eb.run_cycle(fake_gh(reviews=[review(login="intruso")]), POLICY, bp, now=NOW, store=store)
        assert len(store.events()) == 0

    def test_stale_review_is_not_published(self, tmp_path, store):
        bp = tmp_path / "bridge.json"
        eb.run_cycle(fake_gh(reviews=[review(commit="c" * 40)]), POLICY, bp, now=NOW, store=store)
        assert len(store.events()) == 0

    def test_approved_review_is_not_published(self, tmp_path, store):
        bp = tmp_path / "bridge.json"
        eb.run_cycle(fake_gh(reviews=[review(state="APPROVED")]), POLICY, bp, now=NOW, store=store)
        assert len(store.events()) == 0

    def test_bridge_without_store_works_unchanged(self, tmp_path):
        bp = tmp_path / "bridge.json"
        counts = eb.run_cycle(fake_gh(reviews=[review()]), POLICY, bp, now=NOW, store=None)
        assert counts["ACCEPT"] == 1
        b = eb.load(bp)
        assert len(b["queue"]) == 1

    def test_store_failure_does_not_block_json_queue(self, tmp_path):
        """If the EventStore is broken, the bridge still works (shadow is best-effort)."""
        bp = tmp_path / "bridge.json"

        class BrokenStore:
            def publish(self, **kw):
                raise RuntimeError("disk full")

        counts = eb.run_cycle(fake_gh(reviews=[review()]), POLICY, bp, now=NOW, store=BrokenStore())
        assert counts["ACCEPT"] == 1
        b = eb.load(bp)
        assert len(b["queue"]) == 1

    def test_idempotency_key_matches_bridge_task_key(self, tmp_path, store):
        bp = tmp_path / "bridge.json"
        eb.run_cycle(fake_gh(reviews=[review()]), POLICY, bp, now=NOW, store=store)
        b = eb.load(bp)
        bridge_key = b["queue"][0]["key"]
        ev = store.events()[0]
        assert ev["idempotency_key"] == bridge_key


# ---- store factory -------------------------------------------------------

class TestStoreFactory:
    def test_singleton_returns_same_instance(self, tmp_path):
        s1 = sf.get_store(tmp_path / "a.db")
        sf.reset_store()
        s2 = sf.get_store(tmp_path / "a.db")
        sf.reset_store()
        assert isinstance(s1, EventStore) and isinstance(s2, EventStore)

    def test_bridge_event_type_mapping(self):
        assert sf.bridge_event_type({"kind": "review", "state": "CHANGES_REQUESTED"}) == "CORRECTION_REQUESTED"
        assert sf.bridge_event_type({"kind": "review", "state": "APPROVED"}) is None
        assert sf.bridge_event_type({"kind": "comment"}) is None

    def test_bridge_to_store_args_produces_valid_publish_kwargs(self):
        event = {"kind": "review", "state": "CHANGES_REQUESTED", "event_id": "review:42",
                 "pr": 10, "author": "fmmodesto", "url": "https://x/r/42"}
        facts = {"head_sha": HEAD, "refs": [606]}
        args = sf.bridge_to_store_args(event, facts)
        assert args is not None
        assert args["event_type"] == "CORRECTION_REQUESTED"
        assert args["job_id"] == "pr:10"
        assert args["payload"]["pr"] == 10
        assert args["payload"]["issue"] == 606
        assert args["payload"]["head_sha"] == HEAD

    def test_unmapped_event_returns_none(self):
        event = {"kind": "comment", "state": None, "event_id": "comment:1"}
        assert sf.bridge_to_store_args(event, {}) is None


# ---- result sync ----------------------------------------------------------

class TestResultSync:
    def _setup_bridge_item(self, tmp_path, store):
        bp = tmp_path / "bridge.json"
        eb.run_cycle(fake_gh(reviews=[review()]), POLICY, bp, now=NOW, store=store)
        b = eb.load(bp)
        return b["queue"][0], bp

    def test_sync_done_marks_store_event_done(self, tmp_path, store):
        item, _ = self._setup_bridge_item(tmp_path, store)
        ee._sync_result_to_store(store, item, {"action": "DONE", "item": item["key"], "new_head": "d" * 40})
        ev = store.events()[0]
        assert ev["status"] == "DONE"

    def test_sync_superseded_marks_store_event_superseded(self, tmp_path, store):
        item, _ = self._setup_bridge_item(tmp_path, store)
        ee._sync_result_to_store(store, item, {"action": "SUPERSEDED", "item": item["key"], "reason": "HEAD changed"})
        ev = store.events()[0]
        assert ev["status"] == "SUPERSEDED"

    def test_sync_failed_marks_store_event_for_retry(self, tmp_path, store):
        item, _ = self._setup_bridge_item(tmp_path, store)
        ee._sync_result_to_store(store, item, {"action": "FAILED", "item": item["key"], "reason": "test failure"})
        ev = store.events()[0]
        assert ev["status"] == "PENDING"

    def test_sync_without_store_is_noop(self, tmp_path, store):
        item, _ = self._setup_bridge_item(tmp_path, store)
        ee._sync_result_to_store(None, item, {"action": "DONE"})
        ev = store.events()[0]
        assert ev["status"] == "PENDING"

    def test_sync_already_claimed_event_is_skipped(self, tmp_path, store):
        """If the EventStore event was already claimed by someone else, sync is skipped."""
        item, _ = self._setup_bridge_item(tmp_path, store)
        store.claim(("CORRECTION_REQUESTED",), "other-owner", 60.0)
        ee._sync_result_to_store(store, item, {"action": "DONE"})
        ev = store.events()[0]
        assert ev["status"] == "RUNNING"

    def test_sync_dry_run_fails_event(self, tmp_path, store):
        item, _ = self._setup_bridge_item(tmp_path, store)
        ee._sync_result_to_store(store, item, {"action": "DRY_RUN", "item": item["key"]})
        ev = store.events()[0]
        assert ev["status"] == "PENDING"

    def test_two_prs_sync_never_touches_other_pr_event(self, tmp_path, store):
        """Adversarial order: PR #20 published first (lower event ID), PR #10 second.
        Syncing PR #10's result must not claim PR #20's event."""
        bp = tmp_path / "bridge.json"
        r10 = review(rid=1, commit=HEAD)
        r20 = {"id": 2, "user": {"login": "fmmodesto"}, "state": "CHANGES_REQUESTED",
               "commit_id": HEAD2, "html_url": "https://x/r/2", "submitted_at": "2026-11-08T10:00:00Z"}
        gh = fake_gh_two_prs(reviews_pr10=[r10], reviews_pr20=[r20])
        eb.run_cycle(gh, POLICY, bp, now=NOW, store=store)
        b = eb.load(bp)
        assert len(b["queue"]) == 2
        events = store.events()
        assert len(events) == 2
        pr10_item = next(t for t in b["queue"] if t["pr"] == 10)
        ee._sync_result_to_store(store, pr10_item, {"action": "DONE", "item": pr10_item["key"], "new_head": "d" * 40})
        pr10_ev = next(e for e in store.events() if e["job_id"] == "pr:10")
        pr20_ev_after = next(e for e in store.events() if e["job_id"] == "pr:20")
        assert pr10_ev["status"] == "DONE"
        assert pr20_ev_after["status"] == "PENDING"


# ---- shadow diagnostics ---------------------------------------------------

class TestShadowDiagnostics:
    def test_publish_ok_increments_counter(self, tmp_path, store):
        bp = tmp_path / "bridge.json"
        eb.run_cycle(fake_gh(reviews=[review()]), POLICY, bp, now=NOW, store=store)
        diag = sf.shadow_diagnostics()
        assert diag["publish_ok"] >= 1
        assert diag["publish_err"] == 0

    def test_publish_error_records_last_error(self, tmp_path):
        bp = tmp_path / "bridge.json"

        class BrokenStore:
            def publish(self, **kw):
                raise RuntimeError("disk full")

        eb.run_cycle(fake_gh(reviews=[review()]), POLICY, bp, now=NOW, store=BrokenStore())
        diag = sf.shadow_diagnostics()
        assert diag["publish_err"] >= 1
        assert "disk full" in (diag["last_error"] or "")

    def test_sync_ok_increments_counter(self, tmp_path, store):
        bp = tmp_path / "bridge.json"
        eb.run_cycle(fake_gh(reviews=[review()]), POLICY, bp, now=NOW, store=store)
        b = eb.load(bp)
        item = b["queue"][0]
        ee._sync_result_to_store(store, item, {"action": "DONE", "item": item["key"], "new_head": "d" * 40})
        diag = sf.shadow_diagnostics()
        assert diag["sync_ok"] >= 1

    def test_claim_job_id_filter_isolates_aggregates(self, tmp_path):
        """EventStore.claim(job_id=...) only returns events for that job."""
        s = EventStore(tmp_path / "test.db")
        s.publish(event_type="CORRECTION_REQUESTED", idempotency_key="k1",
                  job_id="pr:10", payload={"pr": 10}, producer="test")
        s.publish(event_type="CORRECTION_REQUESTED", idempotency_key="k2",
                  job_id="pr:20", payload={"pr": 20}, producer="test")
        claimed = s.claim(("CORRECTION_REQUESTED",), "owner", 30.0, job_id="pr:20")
        assert claimed is not None
        assert claimed["job_id"] == "pr:20"
        pr10_ev = next(e for e in s.events() if e["job_id"] == "pr:10")
        assert pr10_ev["status"] == "PENDING"


# ---- claim_by_id adversarial tests ------------------------------------------

class TestClaimByIdAdversarial:
    """Adversarial tests for exact-ID claiming (review finding #1 fix)."""

    def test_claim_by_id_targets_exact_event(self, tmp_path):
        """Two events of the same type in the same job: claim_by_id gets only
        the one we ask for; the other stays PENDING."""
        s = EventStore(tmp_path / "test.db")
        eid1, _ = s.publish(event_type="CORRECTION_REQUESTED", idempotency_key="round1",
                            job_id="pr:10", payload={"round": 1}, producer="test")
        eid2, _ = s.publish(event_type="CORRECTION_REQUESTED", idempotency_key="round2",
                            job_id="pr:10", payload={"round": 2}, producer="test")
        claimed = s.claim_by_id(eid2, "owner-a", 30.0)
        assert claimed is not None
        assert claimed["id"] == eid2
        ev1 = next(e for e in s.events() if e["id"] == eid1)
        assert ev1["status"] == "PENDING"

    def test_two_events_same_pr_sync_targets_exact_one(self, tmp_path, store):
        """Two CORRECTION_REQUESTED events for the same PR (different rounds).
        _sync_result_to_store completes only the one whose idempotency_key matches."""
        store.publish(event_type="CORRECTION_REQUESTED", idempotency_key="review:42:10:" + HEAD,
                      job_id="pr:10", payload={"pr": 10, "round": 1}, producer="bridge")
        store.publish(event_type="CORRECTION_REQUESTED", idempotency_key="review:99:10:" + HEAD,
                      job_id="pr:10", payload={"pr": 10, "round": 2}, producer="bridge")
        item = {"event_id": "review:42", "pr": 10, "head_sha": HEAD, "key": "review:42:10:" + HEAD}
        ee._sync_result_to_store(store, item, {"action": "DONE", "item": item["key"], "new_head": "d" * 40})
        events = store.events(job_id="pr:10")
        round1 = next(e for e in events if e["idempotency_key"] == "review:42:10:" + HEAD)
        round2 = next(e for e in events if e["idempotency_key"] == "review:99:10:" + HEAD)
        assert round1["status"] == "DONE"
        assert round2["status"] == "PENDING"

    def test_claim_by_id_concurrent_threads(self, tmp_path):
        """Two threads claim different events simultaneously: each gets its own,
        neither gets the other's."""
        s = EventStore(tmp_path / "test.db")
        eid1, _ = s.publish(event_type="CORRECTION_REQUESTED", idempotency_key="k1",
                            job_id="pr:10", payload={"pr": 10}, producer="test")
        eid2, _ = s.publish(event_type="CORRECTION_REQUESTED", idempotency_key="k2",
                            job_id="pr:20", payload={"pr": 20}, producer="test")
        results = [None, None]
        barrier = threading.Barrier(2)

        def claim_event(idx, event_id, owner):
            barrier.wait()
            results[idx] = s.claim_by_id(event_id, owner, 30.0)

        t1 = threading.Thread(target=claim_event, args=(0, eid1, "thread-A"))
        t2 = threading.Thread(target=claim_event, args=(1, eid2, "thread-B"))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)
        assert results[0] is not None and results[0]["id"] == eid1
        assert results[1] is not None and results[1]["id"] == eid2
        assert results[0]["lease_owner"] == "thread-A"
        assert results[1]["lease_owner"] == "thread-B"

    def test_claim_by_id_concurrent_same_event(self, tmp_path):
        """Two threads race on the SAME event: exactly one wins."""
        s = EventStore(tmp_path / "test.db")
        eid, _ = s.publish(event_type="CORRECTION_REQUESTED", idempotency_key="k1",
                           job_id="pr:10", payload={"pr": 10}, producer="test")
        results = [None, None]
        barrier = threading.Barrier(2)

        def claim_event(idx, owner):
            barrier.wait()
            results[idx] = s.claim_by_id(eid, owner, 30.0)

        t1 = threading.Thread(target=claim_event, args=(0, "racer-A"))
        t2 = threading.Thread(target=claim_event, args=(1, "racer-B"))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)
        winners = [r for r in results if r is not None]
        assert len(winners) == 1, f"expected exactly 1 winner, got {len(winners)}"
        assert winners[0]["id"] == eid

    def test_claim_by_id_crash_retry_after_lease_expiry(self, tmp_path):
        """Claim, simulate crash (lease expires), re-claim succeeds."""
        clock_time = [0.0]
        s = EventStore(tmp_path / "test.db", clock=lambda: clock_time[0])
        eid, _ = s.publish(event_type="CORRECTION_REQUESTED", idempotency_key="k1",
                           job_id="pr:10", payload={"pr": 10}, producer="test")
        claimed = s.claim_by_id(eid, "worker-1", 10.0)
        assert claimed is not None
        assert claimed["lease_owner"] == "worker-1"
        clock_time[0] = 5.0
        stale = s.claim_by_id(eid, "worker-2", 10.0)
        assert stale is None, "lease still valid — should not be claimable"
        clock_time[0] = 11.0
        recovered = s.claim_by_id(eid, "worker-2", 10.0)
        assert recovered is not None
        assert recovered["lease_owner"] == "worker-2"
        assert recovered["attempt"] == 2

    def test_claim_by_id_respects_aggregate_exclusion(self, tmp_path):
        """If another event in the same aggregate is actively RUNNING,
        claim_by_id refuses even for a PENDING event in that aggregate."""
        s = EventStore(tmp_path / "test.db")
        eid1, _ = s.publish(event_type="CORRECTION_REQUESTED", idempotency_key="k1",
                            job_id="pr:10", payload={"pr": 10}, producer="test")
        eid2, _ = s.publish(event_type="CORRECTION_REQUESTED", idempotency_key="k2",
                            job_id="pr:10", payload={"pr": 10}, producer="test")
        claimed1 = s.claim_by_id(eid1, "worker-a", 60.0)
        assert claimed1 is not None
        blocked = s.claim_by_id(eid2, "worker-b", 60.0)
        assert blocked is None, "aggregate sibling RUNNING — claim should be blocked"

    def test_claim_by_id_nonexistent_returns_none(self, tmp_path):
        s = EventStore(tmp_path / "test.db")
        assert s.claim_by_id(9999, "owner", 30.0) is None
