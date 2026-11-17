"""FP-060 MT-09 (#663): `Snapshot.store_line`/`store_ok` — a linha do EventStore no painel e no diagnostico copiado e honesta:
so `ok` sem DLQ, sem lease morto e com a outbox lida conta como saudavel; ausente/indisponivel nunca parece saudavel."""
from __future__ import annotations

from tests.test_agent_bar_store import snap

OK = {"state": "ok", "counts": {"PENDING": 2, "RUNNING": 1, "DLQ": 0}, "backoff": 1, "retries": 3, "live_leases": [{"owner": "w1", "seconds_left": 40}],
      "zombies": 0, "dlq": [], "last_error": None, "outbox": {"counts": {"PENDING": 0}, "zombies": 0, "dlq": []}}


def test_a_healthy_store_line_shows_counts_leases_and_outbox():
    s = snap(OK)
    line = s.store_line()
    assert s.store_ok() is True
    assert "2 pendente(s) (1 em backoff), 1 rodando, DLQ 0, retries 3" in line and "w1 (40s)" in line and "outbox: 0 pendente(s)" in line


def test_a_missing_or_unreadable_store_is_never_healthy_and_says_so():
    for st in ({"state": "ausente", "error": "sem event_store.db"}, {"state": "indisponivel", "error": "database is locked"}, {}):
        s = snap(st)
        assert s.store_ok() is False and "NAO e saudavel" in s.store_line()


def test_dlq_zombies_or_an_unread_outbox_make_the_store_unhealthy():
    for change in ({"dlq": [{"id": 9, "key": "k"}]}, {"zombies": 1}, {"outbox": None}, {"outbox": {}}, {"outbox": {"counts": {}}}, {"outbox": {"dlq": [], "zombies": 0}},
                   {"outbox": {"counts": {"DLQ": 2}, "zombies": 0, "dlq": []}}, {"outbox": {"counts": {}, "zombies": 1, "dlq": []}},
                   {"outbox": {"counts": {}, "zombies": 0, "dlq": [{"id": 1, "target": "github", "key": "k"}]}}):
        assert snap({**OK, **change}).store_ok() is False


def test_an_outbox_dlq_entry_warns_to_reconcile_before_republishing_instead_of_claiming_loss():
    line = snap({**OK, "outbox": {"counts": {"DLQ": 1}, "zombies": 0, "dlq": [{"id": 1, "target": "github", "key": "review:k"}]}}).store_line()
    assert "reconciliar com o GitHub ANTES de republicar" in line and "perdid" not in line


def test_the_store_line_is_part_of_the_copied_diagnostic():
    s = snap({**OK, "last_error": {"key": "k", "error": "gh falhou: Authorization: OAuth abcdefghijklmnop"}})
    assert s.store_line() in s.diagnostic() and "abcdefghijklmnop" not in s.diagnostic()
