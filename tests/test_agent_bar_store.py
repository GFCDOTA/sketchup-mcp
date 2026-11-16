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
    s = snap({"state": "ok", "counts": {"PENDING": 2}, "backoff": 1, "live_leases": [], "zombies": 0, "dlq": [], "retries": 0, "last_error": None,
                "outbox": {"counts": {}, "zombies": 0, "retries": 0, "dlq": []}})
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


# -- 3a revisao do Codex (#663): mesmo caminho do produtor, credenciais fora do painel, ultimo erro pela FALHA mais recente ---------------------------------
def test_the_store_path_follows_the_producer_contract_not_just_the_bar_directory(tmp_path, monkeypatch):
    other = tmp_path / "outro" / "real.db"
    other.parent.mkdir()
    (tmp_path / "gov").mkdir()
    producer = EventStore(other, clock=Clock())
    producer.publish("CORRECTION_REQUESTED", "k-real", "pr:1", {"x": 1})
    decoy = EventStore(tmp_path / "gov" / "event_store.db", clock=Clock())                           # outro banco no diretorio padrao da barra
    for n in range(3):
        decoy.publish("CORRECTION_REQUESTED", f"k-decoy{n}", f"pr:{n}", {"x": 1})
    monkeypatch.delenv("EVENT_BRIDGE_STATE_PATH", raising=False)
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(other))
    assert col.collect_store(tmp_path / "gov", NOW)["counts"] == {"PENDING": 1}                       # le o banco DO PRODUTOR (1 evento), nao o do diretorio da barra (3)
    monkeypatch.delenv("EVENT_STORE_DB_PATH")
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "outro" / "bridge.json"))           # sem a variavel do banco: ao lado do estado do bridge, como o produtor
    other.rename(other.with_name("event_store.db"))
    assert col.collect_store(tmp_path / "gov", NOW)["counts"] == {"PENDING": 1}
    monkeypatch.delenv("EVENT_BRIDGE_STATE_PATH")
    assert col.collect_store(tmp_path / "gov", NOW)["counts"] == {"PENDING": 3}                       # nada configurado: o diretorio de governanca da barra


def test_a_configured_but_missing_database_is_absent_even_if_another_exists_in_the_default_directory(tmp_path, monkeypatch):
    (tmp_path / "gov").mkdir()
    EventStore(tmp_path / "gov" / "event_store.db", clock=Clock())
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(tmp_path / "configurado" / "nao-existe.db"))
    out = col.collect_store(tmp_path / "gov", NOW)
    assert out["state"] == "ausente" and snap(out).store_ok() is False


SECRETS = ["ghp_" + "a" * 36, "github_pat_" + "B" * 40, "sk-proj-" + "d" * 40, "Bearer " + "x" * 30, "xoxb-" + "1" * 12 + "-" + "g" * 12, "api_key=" + "z" * 20]


@pytest.mark.parametrize("secret", SECRETS)
def test_a_credential_in_an_error_never_reaches_the_panel_or_the_copied_diagnostic(store, tmp_path, secret):
    store.publish("CORRECTION_REQUESTED", "k1", "pr:1", {"x": 1}, max_attempts=1)
    ev = store.claim(("CORRECTION_REQUESTED",), "w", 60)
    store.fail(ev, f"falhou autenticando com {secret} no GitHub")
    out = col.collect_store(tmp_path, NOW)
    text = str(out) + snap(out).store_line()
    assert secret not in text and "<segredo>" in text
    assert out["dlq"][0]["error"].count("<segredo>") == 1 and "<segredo>" in out["last_error"]["error"]


def test_the_model_redacts_again_even_if_a_raw_error_reaches_it():
    raw = {"state": "ok", "counts": {}, "backoff": 0, "live_leases": [], "zombies": 0, "dlq": [], "retries": 0,
           "last_error": {"key": "k", "error": "token " + "ghp_" + "q" * 30}}
    line = snap(raw).store_line()
    assert "ghp_" not in line and "<segredo>" in line


def test_the_last_error_is_the_most_recent_FAILURE_not_the_most_recently_touched_event(store, tmp_path):
    clock = store.clock_handle
    store.publish("CORRECTION_REQUESTED", "k-old", "pr:1", {"x": 1})
    store.publish("CORRECTION_REQUESTED", "k-new", "pr:2", {"x": 1})
    old = store.claim(("CORRECTION_REQUESTED",), "w1", 60)
    clock.t += 10
    store.fail(old, "erro ANTIGO", retry_delay=1000)                                                   # falha do k-old em T0+10
    new = store.claim(("CORRECTION_REQUESTED",), "w2", 60)
    assert new["idempotency_key"] == "k-new"
    clock.t += 10
    store.fail(new, "erro RECENTE", retry_delay=100000)                                                # falha do k-new em T0+20 (a mais recente)
    clock.t += 1500
    again = store.claim(("CORRECTION_REQUESTED",), "w3", 60)                                           # o k-old e reivindicado de novo: updated_at dele passa a ser o MAIOR
    assert again["idempotency_key"] == "k-old"
    clock.t += 5
    assert store.renew(again, 60) is True                                                              # e a renovacao do lease tambem o "toca"
    out = col.collect_store(tmp_path, NOW)
    assert out["last_error"] == {"key": "k-new", "error": "erro RECENTE"}


def test_an_event_that_later_completed_is_not_the_current_error(store, tmp_path):
    clock = store.clock_handle
    store.publish("CORRECTION_REQUESTED", "k-ok", "pr:1", {"x": 1})
    ev = store.claim(("CORRECTION_REQUESTED",), "w1", 60)
    clock.t += 5
    store.fail(ev, "falha transitoria", retry_delay=0)
    again = store.claim(("CORRECTION_REQUESTED",), "w2", 60)
    clock.t += 5
    store.complete(again, {"ok": True})
    assert col.collect_store(tmp_path, NOW)["last_error"] is None


# -- 3a revisao automatica do Codex (#663): JSON estruturado, TODO campo textual do banco, EXECUTION_STATE_PATH -----------------------------------------
@pytest.mark.parametrize("text", ['{"password":"minha-senha-longa"}', "{'token': 'abcd1234efgh'}", 'cfg={"api_key" : "k-123456789"}', "secret=valor-secreto", 'x "access_token":"zzzzzzzz"'])
def test_credentials_in_structured_messages_are_redacted(store, tmp_path, text):
    store.publish("CORRECTION_REQUESTED", "k1", "pr:1", {"x": 1}, max_attempts=1)
    ev = store.claim(("CORRECTION_REQUESTED",), "w", 60)
    store.fail(ev, f"falhou com {text}")
    out = col.collect_store(tmp_path, NOW)
    shown = str(out) + snap(out).store_line()
    for leaked in ("minha-senha-longa", "abcd1234efgh", "k-123456789", "valor-secreto", "zzzzzzzz"):
        assert leaked not in shown, leaked
    assert "<segredo>" in shown


def test_the_lease_owner_and_the_idempotency_key_are_redacted_everywhere_they_are_shown(store, tmp_path):
    token = "ghp_" + "k" * 36
    store.publish("CORRECTION_REQUESTED", f"key-{token}", "pr:1", {"x": 1}, max_attempts=1)
    live = store.claim(("CORRECTION_REQUESTED",), f"owner-{token}", 600)                                 # RUNNING com lease vivo: o dono aparece
    out = col.collect_store(tmp_path, NOW)
    assert token not in str(out) and token not in snap(out).store_line() and out["live_leases"][0]["owner"].startswith("owner-<segredo>")
    store.fail(live, "falha final")                                                                       # vai para a DLQ: a chave aparece no painel
    out = col.collect_store(tmp_path, NOW)
    assert token not in str(out) and token not in snap(out).store_line() and out["dlq"][0]["key"].startswith("key-<segredo>")


def test_the_model_redacts_owner_and_key_even_if_raw_values_reach_it():
    token = "ghp_" + "q" * 30
    raw = {"state": "ok", "counts": {}, "backoff": 0, "live_leases": [{"key": "k", "owner": token, "seconds_left": 5}], "zombies": 0,
           "dlq": [{"id": 1, "key": "k-" + token, "error": "e"}], "retries": 0, "last_error": None}
    line = snap(raw).store_line()
    assert token not in line and line.count("<segredo>") == 2


def test_only_execution_state_path_configured_still_follows_the_producer_contract(tmp_path, monkeypatch):
    (tmp_path / "gov").mkdir()
    (tmp_path / "estado").mkdir()
    producer = EventStore(tmp_path / "estado" / "event_store.db", clock=Clock())                          # ao lado do estado: store_path -> bridge_path -> state_path
    producer.publish("CORRECTION_REQUESTED", "k-real", "pr:1", {"x": 1})
    decoy = EventStore(tmp_path / "gov" / "event_store.db", clock=Clock())
    for n in range(3):
        decoy.publish("CORRECTION_REQUESTED", f"k-decoy{n}", f"pr:{n}", {"x": 1})
    for var in ("EVENT_STORE_DB_PATH", "EVENT_BRIDGE_STATE_PATH"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("EXECUTION_STATE_PATH", str(tmp_path / "estado" / "execution_state.json"))
    assert col.collect_store(tmp_path / "gov", NOW)["counts"] == {"PENDING": 1}                           # le o banco do PRODUTOR (1), nao o do diretorio da barra (3)


def test_an_event_that_failed_and_was_then_superseded_is_not_the_current_error(store, tmp_path):
    clock = store.clock_handle
    store.publish("CORRECTION_REQUESTED", "k-sup", "pr:1", {"x": 1})
    ev = store.claim(("CORRECTION_REQUESTED",), "w1", 60)
    clock.t += 5
    store.fail(ev, "falha antiga", retry_delay=0)
    again = store.claim(("CORRECTION_REQUESTED",), "w2", 60)
    clock.t += 5
    store.supersede(again, "HEAD mudou: pedido obsoleto")                                         # o motivo da supersessao NAO e um erro de falha
    assert col.collect_store(tmp_path, NOW)["last_error"] is None


def test_a_real_failure_elsewhere_is_still_reported_when_another_event_was_superseded(store, tmp_path):
    clock = store.clock_handle
    store.publish("CORRECTION_REQUESTED", "k-a", "pr:1", {"x": 1})
    store.publish("CORRECTION_REQUESTED", "k-b", "pr:2", {"x": 1})
    a = store.claim(("CORRECTION_REQUESTED",), "w1", 60)
    clock.t += 5
    store.fail(a, "erro real", retry_delay=1000)
    b = store.claim(("CORRECTION_REQUESTED",), "w2", 60)
    clock.t += 5
    store.fail(b, "outro erro", retry_delay=1000)
    clock.t += 1500
    again = store.claim(("CORRECTION_REQUESTED",), "w3", 60)
    store.supersede(again, "obsoleto")
    assert col.collect_store(tmp_path, NOW)["last_error"]["error"] == "outro erro"


def _event_with_outbox(store, key="k-ob", max_attempts=1):
    store.publish("CORRECTION_REQUESTED", key, "pr:9", {"x": 1})
    ev = store.claim(("CORRECTION_REQUESTED",), "w", 60, job_id="pr:9")
    store.complete(ev, {"ok": True}, outbox_entries=[{"target": "github", "operation": "review", "payload": {"b": 1}, "idempotency_key": key + ":out",
                                                      "max_attempts": max_attempts}])


def test_a_lost_publication_in_the_outbox_dlq_is_not_hidden_by_a_done_event(store, tmp_path):
    _event_with_outbox(store)
    entry = store.claim_outbox("pub", 30)
    assert store.fail_outbox(entry, "401 do GitHub", retry_delay=0) == "DLQ"
    out = col.collect_store(tmp_path, dt.datetime.fromtimestamp(store.clock_handle.t, dt.timezone.utc))
    assert out["dlq"] == [] and out["counts"].get("DLQ", 0) == 0                                      # a fila de EVENTOS esta limpa...
    assert [d["key"] for d in out["outbox"]["dlq"]] == ["k-ob:out"] and out["outbox"]["counts"] == {"DLQ": 1}
    s = snap(out)
    assert s.store_ok() is False and "DLQ DA OUTBOX" in s.store_line() and "reconciliar" in s.store_line() and "k-ob:out" in s.store_line()


def test_an_outbox_entry_with_an_expired_lease_is_flagged_and_a_clean_outbox_is_healthy(store, tmp_path):
    _event_with_outbox(store, max_attempts=3)
    clean = col.collect_store(tmp_path, dt.datetime.fromtimestamp(store.clock_handle.t, dt.timezone.utc))
    assert clean["outbox"]["counts"] == {"PENDING": 1} and snap(clean).store_ok() is True and "outbox: 1 pendente(s)" in snap(clean).store_line()
    store.claim_outbox("morto", 5)
    store.clock_handle.t += 60
    out = col.collect_store(tmp_path, dt.datetime.fromtimestamp(store.clock_handle.t, dt.timezone.utc))
    assert out["outbox"]["zombies"] == 1 and snap(out).store_ok() is False and "lease vencido" in snap(out).store_line()


def test_a_store_dict_without_the_outbox_reading_is_never_reported_healthy():
    legacy = {"state": "ok", "counts": {}, "backoff": 0, "live_leases": [], "zombies": 0, "dlq": [], "retries": 0, "last_error": None}
    assert snap(legacy).store_ok() is False


@pytest.mark.parametrize("var", ["EVENT_STORE_DB_PATH", "EVENT_BRIDGE_STATE_PATH", "EXECUTION_STATE_PATH"])
def test_a_relative_store_path_variable_is_indeterminate_and_never_healthy(tmp_path, monkeypatch, var):
    (tmp_path / "event_store.db").write_bytes(b"")                                                    # mesmo existindo um banco no cwd/gov: nao e lido
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(var, "relativo/event_store.db")
    out = col.collect_store(tmp_path, NOW)
    assert out["state"] == "indisponivel" and "relativo" in out["error"] and snap(out).store_ok() is False and "NAO e saudavel" in snap(out).store_line()


def test_an_absolute_store_path_variable_is_read_normally(store, tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(tmp_path / "event_store.db"))
    assert col.collect_store(tmp_path, NOW)["state"] == "ok"


@pytest.mark.parametrize("effective,ignored", [("EVENT_STORE_DB_PATH", "EVENT_BRIDGE_STATE_PATH"), ("EVENT_STORE_DB_PATH", "EXECUTION_STATE_PATH"),
                                               ("EVENT_BRIDGE_STATE_PATH", "EXECUTION_STATE_PATH")])
def test_a_relative_variable_of_lower_precedence_is_ignored_like_the_producer_does(store, tmp_path, monkeypatch, effective, ignored):
    for var in ("EVENT_STORE_DB_PATH", "EVENT_BRIDGE_STATE_PATH", "EXECUTION_STATE_PATH"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(effective, str(tmp_path / ("event_store.db" if effective == "EVENT_STORE_DB_PATH" else "event_bridge.json")))
    monkeypatch.setenv(ignored, "relativo/qualquer.json")
    assert col.collect_store(tmp_path, NOW)["state"] == "ok"


def test_the_effective_relative_variable_is_refused_even_if_a_lower_one_is_absolute(tmp_path, monkeypatch):
    for var in ("EVENT_STORE_DB_PATH", "EVENT_BRIDGE_STATE_PATH", "EXECUTION_STATE_PATH"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("EVENT_STORE_DB_PATH", "relativo/event_store.db")
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "event_bridge.json"))
    assert col.collect_store(tmp_path, NOW)["state"] == "indisponivel"


def test_an_outbox_dlq_after_an_expired_final_lease_is_reported_as_unknown_remote_outcome_not_as_lost(store, tmp_path):
    _event_with_outbox(store, key="k-unk", max_attempts=1)
    store.claim_outbox("pub", 5)
    store.clock_handle.t += 60                                                                    # o lease venceu na ultima tentativa: a chamada remota pode ter acontecido
    assert store.claim_outbox("outro", 5) is None                                                 # o claim move o evento para a DLQ com o aviso de reconciliacao
    out = col.collect_store(tmp_path, dt.datetime.fromtimestamp(store.clock_handle.t, dt.timezone.utc))
    assert out["outbox"]["dlq"][0]["unknown_outcome"] is True
    line = snap(out).store_line()
    assert snap(out).store_ok() is False and "reconciliar" in line and "PUBLICACAO PERDIDA" not in line


def test_a_free_text_publication_failure_never_claims_the_publication_was_lost(store, tmp_path):
    _event_with_outbox(store, key="k-lost", max_attempts=1)
    entry = store.claim_outbox("pub", 30)
    store.fail_outbox(entry, "401 do GitHub", retry_delay=0)
    out = col.collect_store(tmp_path, dt.datetime.fromtimestamp(store.clock_handle.t, dt.timezone.utc))
    line = snap(out).store_line()
    assert snap(out).store_ok() is False and "PUBLICACAO PERDIDA" not in line and "reconciliar" in line      # falha livre (ex.: 401 ou timeout): sem prova de que o remoto NAO aplicou


@pytest.mark.parametrize("raw", ['{"password":"abc,def"}', '{"password": "abc def, ghi"}', "password='a,b;c d'", '{"token":"x\\"y,z"}', 'api_key=abc,def', '{"secret":"s3,cr3t"}',
                                  'Authorization failed: {"access_token": "a b,c"} fim'])
def test_structured_credential_values_with_delimiters_never_reach_the_panel(raw):
    out = col.redact_secrets(raw)
    for leaked in ("abc", "def", "ghi", "a,b", "s3", "cr3t", "y,z", "a b"):
        assert leaked not in out.replace("<segredo>", ""), (leaked, out)
    assert "<segredo>" in out


def test_an_unrelated_text_with_the_word_token_in_prose_is_left_alone():
    assert col.redact_secrets("o token expirou") == "o token expirou"
    assert col.redact_secrets("sem segredo aqui, so virgulas e: dois pontos") == "sem segredo aqui, so virgulas e: dois pontos"


def test_two_failures_at_the_same_instant_are_ordered_by_the_persisted_transitions_not_by_event_ids(store, tmp_path):
    clock = store.clock_handle
    store.publish("CORRECTION_REQUESTED", "k-low", "pr:1", {"x": 1})
    store.publish("CORRECTION_REQUESTED", "k-high", "pr:2", {"x": 1})
    high = store.claim(("CORRECTION_REQUESTED",), "w", 60, job_id="pr:2")                         # o evento de id MAIOR falha primeiro...
    low = store.claim(("CORRECTION_REQUESTED",), "w", 60, job_id="pr:1")
    store.fail(high, "falha do evento de id maior", retry_delay=900)
    store.fail(low, "falha do evento de id menor (a mais recente)", retry_delay=900)               # ...e o de id MENOR falha depois, no MESMO instante (relogio fixo)
    out = col.collect_store(tmp_path, dt.datetime.fromtimestamp(clock.t, dt.timezone.utc))
    assert out["last_error"]["key"] == "k-low" and "id menor" in out["last_error"]["error"]



# -- revisao do Codex (#663): Bearer depois de `token=`, relogio que recua, coleta em uma passagem -------------------------------------------------------
@pytest.mark.parametrize("raw", ["token=Bearer abcdefghijklmnop", "Authorization: bearer abcdefghijklmnop", "TOKEN: BEARER abcdefghijklmnop",
                                 '{"client_secret": "xyz-123-abc"}', "refresh_token=r3fr3sh-t0k3n"])
def test_the_whole_credential_is_redacted_including_bearer_after_token_and_any_case(raw):
    out = col.redact_secrets(raw)
    assert "abcdefghijklmnop" not in out and "xyz-123-abc" not in out and "r3fr3sh" not in out and "<segredo>" in out


def test_the_most_recent_failure_follows_the_persisted_order_even_if_the_wall_clock_goes_back(store, tmp_path):
    clock = store.clock_handle
    store.publish("CORRECTION_REQUESTED", "k-old", "pr:1", {"x": 1})
    store.publish("CORRECTION_REQUESTED", "k-new", "pr:2", {"x": 1})
    a = store.claim(("CORRECTION_REQUESTED",), "w", 3600 * 2, job_id="pr:1")
    b = store.claim(("CORRECTION_REQUESTED",), "w", 3600 * 2, job_id="pr:2")
    store.fail(a, "erro ANTIGO", retry_delay=900)
    clock.t -= 3600                                                                                  # o relogio recuou uma hora
    store.fail(b, "erro RECENTE", retry_delay=900)                                                   # persistida DEPOIS, com horario MENOR
    out = col.collect_store(tmp_path, dt.datetime.fromtimestamp(clock.t, dt.timezone.utc))
    assert out["last_error"]["error"] == "erro RECENTE"


def test_the_failure_query_is_a_single_grouped_pass_without_a_correlated_subquery(store, tmp_path, monkeypatch):
    seen = []
    real = sqlite3.connect

    def spy(*a, **k):
        conn = real(*a, **k)
        conn.set_trace_callback(seen.append)
        return conn
    monkeypatch.setattr(sqlite3, "connect", spy)
    col.collect_store(tmp_path, NOW)
    q = [s for s in seen if "transitions" in s]
    assert q and all("GROUP BY event_id" in s and s.count("FROM transitions") == 1 for s in q)



@pytest.mark.parametrize("raw", ["Authorization: Basic dXNlcjpwYXNzd29yZA==", "authorization: basic dXNlcjpwYXNzd29yZA==", "auth=Basic dXNlcjpwYXNzd29yZA=="])
def test_basic_credentials_are_redacted_through_the_persisted_failure_to_the_panel_and_the_copied_diagnostic(store, tmp_path, raw):
    store.publish("CORRECTION_REQUESTED", "k", "pr:1", {"x": 1})
    ev = store.claim(("CORRECTION_REQUESTED",), "w", 60, job_id="pr:1")
    store.fail(ev, f"gh falhou: {raw}", retry_delay=900)
    out = col.collect_store(tmp_path, NOW)
    s = snap(out)
    assert "dXNlcjpwYXNzd29yZA" not in s.store_line() and "dXNlcjpwYXNzd29yZA" not in str(out.get("last_error"))
    assert "dXNlcjpwYXNzd29yZA" not in col.redact_secrets(raw)


# -- revisao do Codex (#663, ae31eb2a): `Authorization: token <x>` (esquema do GitHub) passava inteiro --------------------------------------------------------
@pytest.mark.parametrize("raw", ["Authorization: token abcdefghijklmnop", "authorization: TOKEN abcdefghijklmnop", "Proxy-Authorization: token abcdefghijklmnop",
                                 "Authorization=token abcdefghijklmnop", "Authorization: abcdefghijklmnop", '"Authorization": "token abcdefghijklmnop"'])
def test_github_token_scheme_credentials_are_redacted_through_the_persisted_failure_to_the_panel_and_the_copied_diagnostic(store, tmp_path, raw):
    store.publish("CORRECTION_REQUESTED", "k", "pr:1", {"x": 1})
    ev = store.claim(("CORRECTION_REQUESTED",), "w", 60, job_id="pr:1")
    store.fail(ev, f"gh falhou: {raw}", retry_delay=900)
    out = col.collect_store(tmp_path, NOW)
    s = snap(out)
    assert "abcdefghijklmnop" not in s.store_line() and "abcdefghijklmnop" not in str(out.get("last_error"))
    assert "abcdefghijklmnop" not in col.redact_secrets(raw)


def test_the_word_authorization_in_prose_is_not_mistaken_for_a_credential():
    assert col.redact_secrets("authorization denied by the server") == "authorization denied by the server"


def test_a_configured_store_path_with_a_credential_never_reaches_the_panel(tmp_path, monkeypatch):
    secret_dir = tmp_path / ("ghp_" + "z" * 30)
    secret_dir.mkdir()
    out = col.collect_store(secret_dir, NOW)
    assert out["state"] == "ausente"
    line = snap(out).store_line()
    assert "ghp_" not in line and "NAO e saudavel" in line
