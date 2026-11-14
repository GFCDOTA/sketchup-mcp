"""FP-060 M2 (#606): publicador do outbox — efeito externo com reconciliacao antes de cada envio.

Suite deterministica: o sistema externo e um alvo falso em memoria ou o `LedgerTarget` (arquivo local). Nada aqui fala com o
GitHub."""
from __future__ import annotations

import json

import pytest

from tools.orchestration import outbox_publisher as op
from tools.orchestration.event_store import EventStore
from tools.orchestration.outbox_publisher import LedgerTarget, TargetError

LEASE = 30.0


class Clock:
    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class Crash(BaseException):
    """Morte abrupta do publicador: nao e Exception, nenhum handler a engole."""


class FakeTarget:
    """Sistema externo em memoria: guarda os efeitos por chave de idempotencia."""

    def __init__(self):
        self.effects: list[str] = []
        self.seen: list[dict] = []
        self.find_error = self.send_error = None
        self.during_find = self.during_send = None

    def find(self, entry: dict) -> str | None:
        self.seen.append(entry)
        if self.during_find:
            self.during_find()
        if self.find_error:
            raise TargetError(self.find_error)
        key = entry["idempotency_key"]
        return f"fake:{self.effects.index(key)}" if key in self.effects else None

    def send(self, entry: dict) -> str:
        if self.send_error:
            raise TargetError(self.send_error)
        self.effects.append(entry["idempotency_key"])
        if self.during_send:
            self.during_send()
        return f"fake:{len(self.effects) - 1}"


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def store(tmp_path, clock):
    return EventStore(tmp_path / "events.db", clock=clock)


def queue(store, *keys, target="fake", payload=None, max_attempts=5):
    """Um evento concluido que deixa uma entrada de outbox por chave (mesma transacao, como em producao)."""
    store.publish("REVIEW_REQUESTED", f"ev:{keys[0]}", f"job:{keys[0]}", {})
    ev = store.claim("REVIEW_REQUESTED", "worker", 60)
    _, ids = store.complete(ev, {}, outbox_entries=[
        {"target": target, "operation": "publish_review", "payload": payload or {"pr": 7}, "idempotency_key": key,
         "max_attempts": max_attempts} for key in keys])
    return ids


def status(store, outbox_id):
    return next(e for e in store.outbox_entries() if e["id"] == outbox_id)["status"]


def publish(store, target, owner="pub-1", **kw):
    return op.publish_one(store, {"fake": target}, owner, lease_seconds=LEASE, **kw)


# -- caminho feliz e reconciliacao ------------------------------------------------------------------------------------------
def test_pending_entry_is_sent_once_and_acknowledged(store):
    target = FakeTarget()
    (oid,) = queue(store, "k1")

    res = publish(store, target)

    assert res == {"action": "SENT", "outbox": oid, "key": "k1", "target": "fake", "reference": "fake:0", "attempt": 1}
    assert target.effects == ["k1"] and status(store, oid) == "DONE"
    assert publish(store, target) == {"action": "IDLE"}


def test_target_receives_the_payload_already_decoded(store):
    target = FakeTarget()
    queue(store, "k1", payload={"pr": 7, "head_sha": "abc"})
    publish(store, target)
    assert target.seen[0]["payload"] == {"pr": 7, "head_sha": "abc"} and target.seen[0]["operation"] == "publish_review"


def test_publisher_that_died_after_the_effect_is_reconciled_without_a_second_send(store, clock):
    target = FakeTarget()
    (oid,) = queue(store, "k1")

    def die(entry, reference):
        raise Crash

    with pytest.raises(Crash):
        publish(store, target, after_send=die)
    assert target.effects == ["k1"] and status(store, oid) == "RUNNING"       # efeito feito, ACK nunca gravado
    assert publish(store, target, owner="pub-2") == {"action": "IDLE"}         # o lease do morto ainda vale
    clock.advance(LEASE + 1)

    res = publish(store, target, owner="pub-2")

    assert (res["action"], res["reference"], res["attempt"]) == ("RECONCILED", "fake:0", 2)
    assert target.effects == ["k1"] and status(store, oid) == "DONE"


def test_effect_already_present_remotely_is_reconciled_on_the_first_attempt(store):
    target = FakeTarget()
    target.effects.append("k1")
    (oid,) = queue(store, "k1")

    res = publish(store, target)

    assert res["action"] == "RECONCILED" and target.effects == ["k1"] and status(store, oid) == "DONE"


# -- falhas: nunca enviar sem reconciliar, nunca dar ACK sem efeito ---------------------------------------------------------
def test_reconciliation_failure_sends_nothing_and_goes_back_to_the_queue(store, clock):
    target = FakeTarget()
    target.find_error = "API indisponivel"
    (oid,) = queue(store, "k1")

    res = publish(store, target, retry_delay=5.0)

    assert (res["action"], res["to"]) == ("FAILED", "PENDING") and "API indisponivel" in res["reason"]
    assert target.effects == [] and status(store, oid) == "PENDING"
    assert publish(store, target) == {"action": "IDLE"}                         # ainda dentro do atraso de retry
    target.find_error = None
    clock.advance(6)
    assert publish(store, target)["action"] == "SENT" and target.effects == ["k1"]


def test_send_failure_is_retried_and_dead_lettered_at_the_attempt_limit(store, clock):
    target = FakeTarget()
    target.send_error = "422 do alvo"
    (oid,) = queue(store, "k1", max_attempts=2)

    first = publish(store, target, retry_delay=1.0)
    clock.advance(2)
    second = publish(store, target, retry_delay=1.0)
    clock.advance(2)

    assert (first["to"], second["to"]) == ("PENDING", "DLQ")
    assert status(store, oid) == "DLQ" and target.effects == [] and publish(store, target) == {"action": "IDLE"}


def test_entry_for_an_unknown_target_fails_closed(store):
    (oid,) = queue(store, "k1", target="slack")

    res = op.publish_one(store, {"fake": FakeTarget()}, "pub-1", lease_seconds=LEASE)

    assert res["action"] == "FAILED" and "alvo desconhecido" in res["reason"] and status(store, oid) == "PENDING"


def test_target_filter_only_claims_entries_of_that_target(store):
    target = FakeTarget()
    queue(store, "k1", target="slack")
    assert op.publish_one(store, {"fake": target}, "pub-1", lease_seconds=LEASE, target="fake") == {"action": "IDLE"}
    assert target.seen == []


# -- fencing ----------------------------------------------------------------------------------------------------------------
def test_publisher_that_lost_the_lease_while_reconciling_does_not_send(store, clock):
    target = FakeTarget()
    target.during_find = lambda: clock.advance(LEASE + 1)
    (oid,) = queue(store, "k1")

    res = publish(store, target)

    assert res["action"] == "LEASE_LOST" and target.effects == [] and status(store, oid) == "RUNNING"


def test_lease_lost_during_the_send_is_not_acknowledged_and_the_next_publisher_reconciles(store, clock):
    target = FakeTarget()
    target.during_send = lambda: clock.advance(LEASE + 1)
    (oid,) = queue(store, "k1")

    first = publish(store, target)
    target.during_send = None
    second = publish(store, target, owner="pub-2")

    assert first["action"] == "LEASE_LOST" and status(store, oid) == "DONE"
    assert second["action"] == "RECONCILED" and target.effects == ["k1"]


def test_second_publisher_cannot_take_an_entry_that_is_being_published(store):
    target, inner = FakeTarget(), []
    target.during_find = lambda: inner.append(op.publish_one(store, {"fake": FakeTarget()}, "pub-2", lease_seconds=LEASE))
    queue(store, "k1")

    res = publish(store, target)

    assert inner == [{"action": "IDLE"}] and res["action"] == "SENT" and target.effects == ["k1"]


# -- drenagem ---------------------------------------------------------------------------------------------------------------
def test_drain_publishes_every_available_entry_in_order_and_stops_when_idle(store):
    target = FakeTarget()
    queue(store, "k1", "k2", "k3")

    results = op.drain(store, {"fake": target}, "pub-1", lease_seconds=LEASE)

    assert [r["action"] for r in results] == ["SENT", "SENT", "SENT"] and target.effects == ["k1", "k2", "k3"]


def test_drain_is_bounded(store):
    target = FakeTarget()
    queue(store, "k1", "k2", "k3")
    assert len(op.drain(store, {"fake": target}, "pub-1", lease_seconds=LEASE, limit=2)) == 2 and target.effects == ["k1", "k2"]


def test_drain_does_not_spin_on_an_entry_that_keeps_failing(store):
    target = FakeTarget()
    target.send_error = "fora do ar"
    queue(store, "k1")

    results = op.drain(store, {"fake": target}, "pub-1", lease_seconds=LEASE, retry_delay=5.0)

    assert [r["action"] for r in results] == ["FAILED"]                        # a entrada so volta depois do atraso


# -- alvo local (arquivo que faz o papel do sistema externo) ------------------------------------------------------------------
def test_ledger_target_appends_one_line_per_key_and_finds_it_again(tmp_path, store):
    ledger = LedgerTarget(tmp_path / "external" / "ledger.jsonl")
    queue(store, "k1", "k2", target="ledger", payload={"verdict": "APPROVE"})

    results = op.drain(store, {"ledger": ledger}, "pub-1", lease_seconds=LEASE)

    assert [r["reference"] for r in results] == ["ledger:1", "ledger:2"]
    lines = LedgerTarget(tmp_path / "external" / "ledger.jsonl").lines()        # outra instancia: o estado e o arquivo
    assert [(ln["key"], ln["operation"], ln["payload"]) for ln in lines] == [
        ("k1", "publish_review", {"verdict": "APPROVE"}), ("k2", "publish_review", {"verdict": "APPROVE"})]
    assert ledger.find({"idempotency_key": "k2"}) == "ledger:2" and ledger.find({"idempotency_key": "k9"}) is None


def test_ledger_that_cannot_be_read_blocks_the_send_instead_of_risking_a_duplicate(tmp_path, store):
    path = tmp_path / "ledger.jsonl"
    path.write_text('{"key": "k0"}\nlinha corrompida\n', encoding="utf-8")
    (oid,) = queue(store, "k1", target="ledger")

    res = op.publish_one(store, {"ledger": LedgerTarget(path)}, "pub-1", lease_seconds=LEASE)

    assert res["action"] == "FAILED" and "ilegivel" in res["reason"]
    assert path.read_text(encoding="utf-8").count("\n") == 2 and status(store, oid) == "PENDING"


# -- leitura do outbox no EventStore ------------------------------------------------------------------------------------------
def test_outbox_entries_lists_every_entry_whatever_its_status(store):
    target = FakeTarget()
    ids = queue(store, "k1", "k2")
    publish(store, target)

    entries = store.outbox_entries()

    assert [(e["id"], e["status"], e["attempts"]) for e in entries] == [(ids[0], "DONE", 1), (ids[1], "PENDING", 0)]
    assert json.loads(entries[0]["payload"]) == {"pr": 7}
