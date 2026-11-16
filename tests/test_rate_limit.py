"""FP-060 (resiliencia): limite de USO da conta do revisor e estado persistente, nao falha tecnica. Relogio injetado, EventStore REAL (SQLite), sem Codex nem GitHub.
O fluxo completo pelo `pr_lifecycle.work` (defer sem gastar tentativa, sonda unica, HEAD revalidado, reinicio) esta em `test_pr_lifecycle.py`."""
from __future__ import annotations

import datetime as dt
import threading

import pytest

from tools.orchestration import rate_limit as rl
from tools.orchestration.event_store import EventStore

ACC = "codex:fmmodesto"
T0 = dt.datetime(2026, 11, 16, 12, 20, 0).timestamp()          # horario LOCAL: o texto do Codex e do relogio local


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def store(tmp_path, clock):
    return EventStore(tmp_path / "events.db", clock=clock)


@pytest.fixture()
def gate(store):
    return rl.RateLimitGate(store)


def at(h, m=0, day=16):
    return dt.datetime(2026, 11, day, h, m).timestamp()


# ------------------------------------------------------------------------------------------------------------------------------ classificacao
REAL = "ERROR: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:05 PM."


def test_the_real_message_of_2026_11_16_is_a_usage_limit_with_the_reset_at_15_05_local():
    f = rl.classify(1, REAL, observed=T0)
    assert f.kind == rl.USAGE_LIMIT and f.reset_at == at(15, 5) and not f.ambiguous


@pytest.mark.parametrize("text,kind", [
    ("Not logged in, please login", rl.AUTH),
    ("401 Unauthorized", rl.AUTH),
    ("invalid api key", rl.AUTH),
    ("503 Service Unavailable", rl.TRANSIENT),
    ("connection reset by peer", rl.TRANSIENT),
    ("stream disconnected: network error", rl.TRANSIENT),
    ("panic: index out of range", rl.FATAL),
    ("", rl.FATAL),
    ("429 Too Many Requests", rl.USAGE_LIMIT),
    ("insufficient_quota", rl.USAGE_LIMIT),
    ("You exceeded your current quota", rl.USAGE_LIMIT),
])
def test_failures_are_told_apart_by_kind(text, kind):
    assert rl.classify(1, text, observed=T0).kind == kind


def test_a_timeout_is_transient_and_never_suspends_the_account_by_itself():
    assert rl.classify(None, "", timed_out=True, observed=T0).kind == rl.TRANSIENT


def test_usage_limit_wins_over_auth_words_in_the_same_message():
    assert rl.classify(1, "unauthorized: usage limit reached, try again at 3:05 PM", observed=T0).kind == rl.USAGE_LIMIT


@pytest.mark.parametrize("text,expected", [
    ("try again at 3:05 PM", at(15, 5)),
    ("try again at 9 AM", None),                                    # 09:00 ja passou hoje (observado 12:20): proximo dia ou fuso? ambiguo
    ("try again at 15:05", at(15, 5)),                              # 24 h sem AM/PM e inequivoco
    ("try again at 3:05", None),                                    # sem AM/PM e <= 12: 03:05 ou 15:05
    ("try again at 12:00 AM", None),                                # meia-noite de hoje ja passou
    ("try again at 13:61", None),
    ("try again in 2 hours 5 minutes", T0 + 2 * 3600 + 300),
    ("try again in 45 minutes", T0 + 45 * 60),
    ("try again in 3 days", T0 + 3 * 86400),
    ("try again in 30 days", None),                                 # alem de 7 dias: nao confia
    ("Retry-After: 90", T0 + 90),
    ("try again at Nov 20th, 2026 3:05 PM", at(15, 5, day=20)),
    ("try again at Nov 1st, 2026 3:05 PM", None),                   # no passado
    ("resets at 2026-11-16T20:00:00Z", dt.datetime(2026, 11, 16, 20, 0, tzinfo=dt.timezone.utc).timestamp()),
    ("2026-11-16T20:00:00 sem fuso", None),
    ("try again later", None),
    ("try again at 3:05 PM or try again in 2 hours", None),         # duas previsoes divergentes
])
def test_reset_parsing_is_conservative(text, expected):
    got = rl.parse_reset(text, T0)
    assert got == expected


def test_a_reset_is_resolved_against_when_the_error_was_observed_not_against_now():
    observed = at(12, 20)
    assert rl.parse_reset("try again at 3:05 PM", observed) == at(15, 5)
    assert rl.parse_reset("try again at 3:05 PM", at(15, 30)) is None   # visto as 15:30: o "3:05 PM" ja passou => ambiguo, nao "amanha"


# ------------------------------------------------------------------------------------------------------------------------------ estado da conta
def test_a_healthy_account_is_admitted_without_any_probe(gate):
    assert gate.peek(ACC) is None
    adm = gate.admit(ACC, "w1")
    assert adm.allowed and not adm.probe


def test_a_known_reset_blocks_until_reset_plus_margin_and_persists_across_a_new_store_object(tmp_path, clock):
    s1 = EventStore(tmp_path / "e.db", clock=clock)
    blk = rl.RateLimitGate(s1).record_block(ACC, rl.Failure(rl.USAGE_LIMIT, "x", at(15, 5)))
    assert blk.until == at(15, 5) + rl.MARGIN_S and blk.reset_known and blk.state == rl.LIMITED
    s2 = EventStore(tmp_path / "e.db", clock=clock)                       # "reinicio": objetos novos sobre o mesmo arquivo
    g2 = rl.RateLimitGate(s2)
    assert g2.peek(ACC).until == blk.until
    clock.t = at(15, 6)
    assert g2.peek(ACC) is not None                                       # ainda dentro da folga
    clock.t = at(15, 8) + 1
    assert g2.peek(ACC) is None                                           # passou: pode sondar


def test_without_a_reliable_forecast_the_wait_escalates_30m_1h_2h_4h_6h_and_stays_at_6h(gate, clock):
    waits = []
    for _ in range(7):
        blk = gate.record_block(ACC, rl.Failure(rl.USAGE_LIMIT, "x", None, True))
        waits.append(blk.until - clock.t)
        clock.t = blk.until + 1                                            # a sonda seguinte tambem bateu no limite
    assert waits == [1800.0, 3600.0, 7200.0, 14400.0, 21600.0, 21600.0, 21600.0]


def test_workers_failing_in_the_same_episode_count_once_and_never_shorten_the_block(gate, clock):
    a = gate.record_block(ACC, rl.Failure(rl.USAGE_LIMIT, "x", at(15, 5)))
    b = gate.record_block(ACC, rl.Failure(rl.USAGE_LIMIT, "y", at(13, 0)))          # outro worker leu um reset mais cedo
    c = gate.record_block(ACC, rl.Failure(rl.USAGE_LIMIT, "z", None, True))
    assert a.episodes == b.episodes == c.episodes == 1
    assert b.until == c.until == a.until


def test_after_the_reset_exactly_one_worker_gets_the_probe_and_the_others_wait(gate, clock):
    gate.record_block(ACC, rl.Failure(rl.USAGE_LIMIT, "x", at(15, 5)))
    clock.t = at(15, 10)
    gate2 = rl.RateLimitGate(gate.store)
    first = gate.admit(ACC, "w2")
    assert first.allowed and first.probe
    assert gate2.admit(ACC, "w3").allowed is False and gate2.peek(ACC, "w3").probing
    assert gate.admit(ACC, "w2").allowed                                    # o dono da sonda segue autorizado (idempotente)


def test_a_dead_probe_frees_its_slot_after_the_probe_lease(gate, clock):
    gate.record_block(ACC, rl.Failure(rl.USAGE_LIMIT, "x", at(15, 5)))
    clock.t = at(15, 10)
    assert gate.admit(ACC, "dead").probe
    clock.t += rl.PROBE_LEASE_S + 1
    assert gate.admit(ACC, "alive").probe


def test_probe_concurrency_only_one_of_many_threads_gets_the_slot(tmp_path, clock):
    store = EventStore(tmp_path / "c.db", clock=clock)
    rl.RateLimitGate(store).record_block(ACC, rl.Failure(rl.USAGE_LIMIT, "x", at(15, 5)))
    clock.t = at(15, 10)
    results, barrier = [], threading.Barrier(8)

    def worker(i):
        g = rl.RateLimitGate(EventStore(tmp_path / "c.db", clock=clock))
        barrier.wait()
        results.append(g.admit(ACC, f"w{i}"))

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)
    assert len(results) == 8 and sum(1 for r in results if r.allowed) == 1 and sum(1 for r in results if r.probe) == 1


def test_a_successful_run_clears_the_account_and_resets_the_episode_counter(gate, clock):
    gate.record_block(ACC, rl.Failure(rl.USAGE_LIMIT, "x", None, True))
    clock.t += 2000
    gate.admit(ACC, "w1")
    gate.record_success(ACC)
    assert gate.peek(ACC) is None and gate.status() == []
    assert gate.record_block(ACC, rl.Failure(rl.USAGE_LIMIT, "x", None, True)).episodes == 1


def test_releasing_a_probe_that_proved_nothing_keeps_the_block_and_frees_the_slot(gate, clock):
    gate.record_block(ACC, rl.Failure(rl.USAGE_LIMIT, "x", at(15, 5)))
    clock.t = at(15, 10)
    gate.admit(ACC, "w1")
    gate.release_probe(ACC, "intruso")                                      # so o dono libera
    assert gate.peek(ACC, "w2").probing
    gate.release_probe(ACC, "w1")
    assert gate.admit(ACC, "w2").probe


def test_an_auth_failure_pauses_briefly_and_is_its_own_state(gate, clock):
    blk = gate.record_block(ACC, rl.Failure(rl.AUTH, "x"))
    assert blk.state == rl.AUTH_FAILED and blk.until == clock.t + rl.AUTH_BACKOFF_S and not blk.reset_known


def test_after_too_many_consecutive_limits_the_account_is_escalated_makes_no_calls_and_waits_for_the_owner(gate, clock):
    for _ in range(rl.MAX_EPISODES + 1):
        blk = gate.record_block(ACC, rl.Failure(rl.USAGE_LIMIT, "x", None, True))
        clock.t = blk.until + 1
    assert blk.state == rl.ESCALATED and blk.escalated
    assert gate.peek(ACC) is not None and gate.admit(ACC, "w1").allowed is False       # mesmo muito depois do "reset": ninguem sonda
    clock.t += 30 * 86400
    assert gate.admit(ACC, "w1").allowed is False
    gate.clear(ACC)                                                                    # decisao do proprietario
    assert gate.admit(ACC, "w1").allowed


def test_seed_block_never_shortens_and_never_counts_an_episode(gate, clock):
    gate.record_block(ACC, rl.Failure(rl.USAGE_LIMIT, "x", at(18, 0)))
    gate.seed_block(ACC, at(15, 5), "legado")
    assert gate.peek(ACC).until == at(18, 0) + rl.MARGIN_S
    gate.clear(ACC)
    gate.seed_block(ACC, at(15, 5), "legado")
    assert gate.peek(ACC).until == at(15, 5) and gate.peek(ACC).episodes == 1


# --------------------------------------------------------------------------------------------------------------------------- EventStore.defer
def _claimed(store, key="k1", attempts=5):
    store.publish("REVIEW_REQUESTED", key, "pr:1", {"pr": 1}, producer="review_dispatch", max_attempts=attempts)
    return store.claim("REVIEW_REQUESTED", "w", 300)


def test_defer_returns_to_pending_without_consuming_the_attempt_and_waits_until_the_time(store, clock):
    ev = _claimed(store)
    assert ev["attempt"] == 1
    store.defer(ev, "RATE_LIMITED", clock.t + 7200)
    row = next(e for e in store.events() if e["id"] == ev["id"])
    assert row["status"] == "PENDING" and row["attempt"] == 0 and row["lease_until"] == 0 and row["available_at"] == clock.t + 7200
    assert store.claim("REVIEW_REQUESTED", "w2", 300) is None                      # nao e entregue antes do reset
    clock.t += 7201
    again = store.claim("REVIEW_REQUESTED", "w2", 300)
    assert again["id"] == ev["id"] and again["attempt"] == 1


def test_deferring_many_times_never_dead_letters_the_event(store, clock):
    ev = _claimed(store, attempts=2)
    for _ in range(20):
        store.defer(ev, "RATE_LIMITED", clock.t + 60)
        clock.t += 61
        ev = store.claim("REVIEW_REQUESTED", "w", 300)
        assert ev is not None
    assert next(e for e in store.events() if e["id"] == ev["id"])["status"] == "RUNNING"
    assert not [e for e in store.events() if e["event_type"] == "JOB_FAILED"]


def test_defer_by_a_worker_that_lost_the_lease_is_refused(store, clock):
    from tools.orchestration.event_store import LeaseLost
    ev = _claimed(store)
    clock.t += 301
    store.claim("REVIEW_REQUESTED", "w2", 300)                                       # reivindicou o lease vencido
    with pytest.raises(LeaseLost):
        store.defer(ev, "RATE_LIMITED", clock.t + 60)


# ----------------------------------------------------------------------------------------------------------------- DLQ legada por cota (idempotente)
def _dlq(store, clock, error):
    ev = _claimed(store, key="legacy", attempts=1)
    assert store.fail(ev, error) == "DLQ"
    return ev["id"]


def test_a_legacy_dlq_by_usage_limit_is_requeued_with_the_account_blocked_until_the_reset_and_it_is_idempotent(store, gate, clock):
    eid = _dlq(store, clock, "REVIEW_BLOCKED: auth/limite de uso: " + REAL)
    first = rl.requeue_quota_dlq(store, gate, ACC, "review_dispatch")
    assert first == [{"event": eid, "action": "REQUEUED_QUOTA_DLQ"}]
    row = next(e for e in store.events() if e["id"] == eid)
    assert row["status"] == "PENDING" and row["attempt"] == 0 and row["available_at"] == at(15, 5) + rl.MARGIN_S
    assert gate.peek(ACC).until == at(15, 5) + rl.MARGIN_S
    assert rl.requeue_quota_dlq(store, gate, ACC, "review_dispatch") == []            # nada a refazer


def test_a_dlq_that_was_not_caused_by_usage_limit_is_left_alone(store, gate, clock):
    eid = _dlq(store, clock, "REVIEW_BLOCKED: veredito NEEDS_HUMAN: escalar ao proprietario")
    assert rl.requeue_quota_dlq(store, gate, ACC, "review_dispatch") == []
    assert next(e for e in store.events() if e["id"] == eid)["status"] == "DLQ"


def test_the_account_key_comes_from_the_reviewer_login_in_the_policy():
    assert rl.account_key({"reviewers": ["fmmodesto"]}) == "codex:fmmodesto"
    assert rl.account_key({}) == "codex:default"
