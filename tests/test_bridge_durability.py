"""FP-060 #633: o estado do bridge sobrevive a parada abrupta e a corrupcao — nunca derruba o executor, nunca perde evidencia.

Medido em producao: `event_bridge.json` ficou com 20.888 bytes todos zero e `load()` levantava JSONDecodeError. A causa provavel e a
gravacao sem `fsync` antes do `os.replace`; estes testes travam o `fsync` e a recuperacao explicita."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tools.orchestration import event_bridge as eb
from tools.validation import execution_state as es

ROOT = Path(__file__).resolve().parents[1]


def state(n=1, **kw):
    return {**eb.default_bridge_state(), "queue": [{"key": f"k{n}"}], "backoff_s": n, **kw}


def fail_on_corrupt(monkeypatch, p: Path, exc: Exception) -> None:
    """Faz so a troca que move o arquivo CORROMPIDO para a quarentena falhar; as demais gravacoes (estado pendente) seguem reais."""
    real = os.replace

    def replace(src, dst):
        if Path(src) == p:
            raise exc
        return real(src, dst)
    monkeypatch.setattr(os, "replace", replace)


def quarantined(p: Path) -> list[Path]:
    return sorted(p.parent.glob(p.name + ".corrupt-*"))


# -- leitura: sem efeito colateral, explicita --------------------------------------------------------------------------------------
CORRUPT = [
    b"\x00" * 20888,                           # o caso real de producao
    b"", b"  \n\t", b"\x00\x00\x00\x00",      # vazio e quase vazio
    b'{"queue": [{"key": "k1"', b'{"schema_version": 1, "queue": [',        # truncado no meio do JSON
    b"[]", b'"texto"', b"42",                  # JSON valido que nao e um objeto
    b"\xff\xfe\x00\x00 nao e utf-8",           # codificacao invalida
]
IDS = ["zeros-producao", "vazio", "espacos", "quatro-nulos", "truncado-a", "truncado-b", "array", "string", "numero", "utf8-invalido"]


@pytest.mark.parametrize("content", CORRUPT, ids=IDS)
def test_reading_a_corrupt_state_raises_explicitly_and_never_touches_the_file(tmp_path, content):
    p = tmp_path / "event_bridge.json"
    p.write_bytes(content)

    with pytest.raises(eb.BridgeStateCorrupt, match="corrompido"):
        eb.load(p)

    assert p.read_bytes() == content and quarantined(p) == []                                      # leitor sem trava (status) nunca recupera


def test_a_corrupt_state_error_is_a_value_error_so_existing_guards_contain_it():
    assert issubclass(eb.BridgeStateCorrupt, ValueError)


def test_a_healthy_state_round_trips_and_a_missing_file_is_a_default_state(tmp_path):
    p = tmp_path / "event_bridge.json"
    assert eb.load(p) == eb.default_bridge_state()
    eb.save(state(7), p)
    assert eb.load(p)["queue"] == [{"key": "k7"}] and quarantined(p) == []


# -- recuperacao: so sob a trava, preservada, com diagnostico persistido, sem restaurar copia velha ---------------------------------------
@pytest.mark.parametrize("content", CORRUPT, ids=IDS)
def test_recovery_preserves_the_corrupt_file_and_persists_a_clean_state_with_the_diagnostic(tmp_path, content):
    p = tmp_path / "event_bridge.json"
    p.write_bytes(content)

    with es.locked(p):
        recovered = eb.recover_state(p)

    assert recovered["queue"] == [] and recovered["seen"] == [] and recovered["cursor_comments"] is None
    (kept,) = quarantined(p)
    assert kept.read_bytes() == content                                                            # nada foi apagado
    assert any("corrompido" in d["message"] and kept.name in d["message"] for d in recovered["diagnostics"])
    again = eb.load(p)                                                                             # o diagnostico foi GRAVADO: leituras seguintes ainda o veem
    assert again["diagnostics"] == recovered["diagnostics"] and len(quarantined(p)) == 1
    assert not p.with_name(p.name + ".bak").exists()                                               # nao existe copia anterior para restaurar


def test_recovery_never_restores_an_older_copy_that_could_resurrect_a_claimed_task(tmp_path):
    p = tmp_path / "event_bridge.json"
    eb.save(state(1, queue=[{"key": "k1", "state": "QUEUED"}]), p)
    eb.save(state(2, queue=[{"key": "k1", "state": "RUNNING", "owner": "w"}]), p)                 # claim gravado
    p.write_bytes(b"\x00" * 64)

    with es.locked(p):
        recovered = eb.recover_state(p)

    assert recovered["queue"] == [] and not any("QUEUED" in json.dumps(recovered) for _ in [0])    # nunca volta a versao em que a tarefa estava QUEUED
    assert [f for f in p.parent.iterdir() if f.name.endswith(".bak")] == []


def test_recovery_rereads_under_the_lock_and_does_not_quarantine_a_state_that_is_already_valid(tmp_path):
    p = tmp_path / "event_bridge.json"
    eb.save(state(5), p)                                                                           # outro processo ja recuperou/gravou

    with es.locked(p):
        recovered = eb.recover_state(p)

    assert recovered["queue"] == [{"key": "k5"}] and quarantined(p) == []


def test_recovering_a_file_another_process_already_moved_is_not_an_error(tmp_path):
    p = tmp_path / "event_bridge.json"
    with es.locked(p):
        recovered = eb.recover_state(p)                                                            # ausente = estado padrao valido
    assert recovered["queue"] == [] and quarantined(p) == []


def test_losing_the_race_to_quarantine_the_file_is_not_an_error(tmp_path, monkeypatch):
    p = tmp_path / "event_bridge.json"
    p.write_bytes(b"\x00" * 10)
    fail_on_corrupt(monkeypatch, p, FileNotFoundError())                                           # outro processo ja o moveu

    recovered = eb.recover_state(p)

    assert recovered["queue"] == [] and any("outro processo" in d["message"] for d in recovered["diagnostics"])


def test_if_the_corrupt_file_cannot_be_preserved_nothing_is_recreated_and_the_error_is_explicit(tmp_path, monkeypatch):
    p = tmp_path / "event_bridge.json"
    p.write_bytes(b"\x00" * 10)
    fail_on_corrupt(monkeypatch, p, PermissionError("em uso"))

    with es.locked(p), pytest.raises(eb.BridgeStateCorrupt, match="preserva"):
        eb.recover_state(p)

    monkeypatch.undo()
    assert p.read_bytes() == b"\x00" * 10 and quarantined(p) == []


def test_quarantine_names_are_unique_so_two_recoveries_never_overwrite_each_other(tmp_path):
    p = tmp_path / "event_bridge.json"
    names = set()
    for n in range(3):
        p.write_bytes(b"\x00" * (n + 1))
        with es.locked(p):
            eb.recover_state(p)
        names |= {k.name for k in quarantined(p)}
    assert len(names) == 3 and sorted(k.read_bytes() for k in quarantined(p)) == [b"\x00", b"\x00\x00", b"\x00\x00\x00"]


def test_run_cycle_is_the_locked_entry_point_that_heals_a_corrupt_state_and_persists_it(tmp_path):
    p = tmp_path / "event_bridge.json"
    p.write_bytes(b"\x00" * 2048)

    counts = eb.run_cycle(lambda path: [], {"reviewers": ["r"], "executor_logins": ["e"]}, bpath=p, repo="o/r")

    assert isinstance(counts, dict) and len(quarantined(p)) == 1
    healed = eb.load(p)                                                                            # valido de novo e com o diagnostico gravado
    assert any("corrompido" in d["message"] for d in healed["diagnostics"])


def test_status_readers_racing_with_a_recovery_never_move_or_corrupt_anything(tmp_path):
    import threading
    p = tmp_path / "event_bridge.json"
    p.write_bytes(b"\x00" * 4096)
    seen, errors = [], []

    def reader():
        for _ in range(40):
            try:
                seen.append(eb.load(p)["queue"])                                                   # leitor sem trava: valido ou erro explicito, nunca mexe
            except eb.BridgeStateCorrupt:
                seen.append("corrupt")
            except BaseException as exc:                                                           # noqa: BLE001
                errors.append(repr(exc))

    def healer():
        for _ in range(5):
            with es.locked(p):
                eb.recover_state(p)

    ts_ = [threading.Thread(target=reader) for _ in range(3)] + [threading.Thread(target=healer)]
    [t.start() for t in ts_]
    [t.join() for t in ts_]
    assert errors == [] and len(quarantined(p)) == 1                                               # exatamente uma quarentena, apesar das 5 recuperacoes
    assert set(map(str, seen)) <= {"corrupt", "[]"} and eb.load(p)["queue"] == []


# -- gravacao duravel ---------------------------------------------------------------------------------------------------------------
def test_the_new_content_is_flushed_to_disk_before_it_replaces_the_old_one(tmp_path, monkeypatch):
    calls = []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(os, "fsync", lambda fd: calls.append("fsync") or real_fsync(fd))
    monkeypatch.setattr(os, "replace", lambda a, b: calls.append("replace") or real_replace(a, b))

    eb.save(state(1), tmp_path / "event_bridge.json")

    assert calls == ["fsync", "replace"]


def test_the_execution_state_file_uses_the_same_durable_write(tmp_path, monkeypatch):
    calls = []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(os, "fsync", lambda fd: calls.append("fsync") or real_fsync(fd))
    monkeypatch.setattr(os, "replace", lambda a, b: calls.append("replace") or real_replace(a, b))

    es.save(es.default_state(), tmp_path / "execution_state.json")

    assert calls == ["fsync", "replace"]


def test_a_failed_replace_leaves_the_previous_file_intact(tmp_path, monkeypatch):
    p = tmp_path / "event_bridge.json"
    eb.save(state(1), p)
    before = p.read_bytes()
    monkeypatch.setattr(os, "replace", lambda a, b: (_ for _ in ()).throw(OSError("disco cheio")))

    with pytest.raises(OSError):
        eb.save(state(2), p)

    monkeypatch.undo()
    assert p.read_bytes() == before and eb.load(p)["queue"] == [{"key": "k1"}]


def test_secrets_are_still_refused_and_nothing_is_written(tmp_path):
    p = tmp_path / "event_bridge.json"
    with pytest.raises(ValueError, match="segredos"):
        eb.save(state(1, diagnostics=[{"at": "x", "message": "ghp_abcdef"}]), p)
    assert not p.exists()


# -- processo real morto no meio da gravacao ----------------------------------------------------------------------------------------
CHILD = """
import sys
from pathlib import Path
from tools.orchestration import event_bridge as eb

p, i = Path(sys.argv[1]), 0
while True:
    eb.save({**eb.default_bridge_state(), "backoff_s": i, "diagnostics": [{"at": "t", "message": "x" * 300000}]}, p)
    i += 1
"""


def test_a_writer_killed_at_a_random_moment_never_leaves_an_unreadable_state_file(tmp_path):
    p = tmp_path / "event_bridge.json"
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    for delay in (0.15, 0.31, 0.47, 0.23):
        child = subprocess.Popen([sys.executable, "-c", CHILD, str(p)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 30
        while not p.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        time.sleep(delay)
        child.kill()
        child.wait(timeout=30)
        loaded = eb.load(p)                                                                          # nao pode levantar
        assert isinstance(loaded["backoff_s"], int) and quarantined(p) == []


def test_a_transient_sharing_violation_on_the_atomic_replace_is_retried(tmp_path, monkeypatch):
    p = tmp_path / "event_bridge.json"
    real, calls = os.replace, []

    def flaky(a, b):
        calls.append(1)
        if len(calls) <= 3:
            raise PermissionError(13, "em uso", None, 32)
        return real(a, b)
    monkeypatch.setattr(os, "replace", flaky)
    eb.save(state(4), p)
    monkeypatch.undo()
    assert len(calls) == 4 and eb.load(p)["queue"] == [{"key": "k4"}]


def test_a_status_reader_holding_the_file_open_does_not_make_the_writer_fail(tmp_path):
    import threading
    p = tmp_path / "event_bridge.json"
    eb.save(state(1), p)
    opened, release = threading.Event(), threading.Event()

    def reader():
        with open(p, "rb") as handle:                                                              # leitor sem trava com o arquivo aberto
            handle.read(1)
            opened.set()
            release.wait(5)
    t = threading.Thread(target=reader)
    t.start()
    opened.wait(5)
    threading.Timer(0.3, release.set).start()
    eb.save(state(2), p)                                                                           # no Windows o replace recusa ate o leitor fechar
    t.join()
    assert eb.load(p)["queue"] == [{"key": "k2"}]


def test_a_transient_permission_error_while_another_process_swaps_the_file_is_retried_by_the_reader(tmp_path, monkeypatch):
    p = tmp_path / "event_bridge.json"
    eb.save(state(3), p)
    real, calls = Path.read_bytes, []

    def flaky(self):
        calls.append(1)
        if len(calls) <= 3:
            raise PermissionError(13, "negado", None, 5)
        return real(self)
    monkeypatch.setattr(Path, "read_bytes", flaky)
    assert eb.load(p)["queue"] == [{"key": "k3"}] and len(calls) == 4


def test_a_persistent_permission_error_is_not_swallowed_by_the_reader(tmp_path, monkeypatch):
    p = tmp_path / "event_bridge.json"
    eb.save(state(3), p)
    monkeypatch.setattr(Path, "read_bytes", lambda self: (_ for _ in ()).throw(PermissionError(13, "negado", None, 5)))
    with pytest.raises(PermissionError):
        eb.load(p)


# -- achados da 2a revisao do Codex: recuperacao retomavel, leitor sem trava, dedup nao reexecuta ------------------------------------
def test_a_recovery_interrupted_after_quarantine_loses_nothing_and_the_next_run_completes_it(tmp_path, monkeypatch):
    p = tmp_path / "event_bridge.json"
    p.write_bytes(b"\x00" * 64)
    real = os.replace

    def crash_on_final_swap(src, dst):                                                             # morre depois da quarentena, antes do estado novo tomar o lugar
        if Path(src).name.endswith(".recovered"):
            raise KeyboardInterrupt("processo morto")
        return real(src, dst)
    monkeypatch.setattr(os, "replace", crash_on_final_swap)
    with es.locked(p), pytest.raises(KeyboardInterrupt):
        eb.recover_state(p)
    monkeypatch.undo()

    assert not p.exists() and len(quarantined(p)) == 1                                              # o corrompido esta preservado, o estado oficial ainda nao existe
    seen = eb.load(p)                                                                               # nao e o estado padrao mudo: o diagnostico NAO se perdeu
    assert any("preservado em" in d["message"] for d in seen["diagnostics"])
    with es.locked(p):
        done = eb.recover_state(p)                                                                  # a proxima recuperacao conclui o passo que faltou
    assert p.exists() and eb.load(p)["diagnostics"] == done["diagnostics"] and len(quarantined(p)) == 1
    assert not eb._pending_path(p).exists()


def test_a_stale_pending_file_never_overrides_an_official_state(tmp_path):
    p = tmp_path / "event_bridge.json"
    eb._write_state(eb._pending_path(p), {**eb.default_bridge_state(), "queue": [{"key": "antigo"}]})
    eb.save(state(3), p)
    assert eb.load(p)["queue"] == [{"key": "k3"}] and not eb._pending_path(p).exists()


def test_a_reader_whose_file_is_moved_between_exists_and_open_sees_it_as_missing(tmp_path, monkeypatch):
    p = tmp_path / "event_bridge.json"
    p.write_bytes(b"\x00" * 64)
    real = eb._read_bytes

    def moved_first(path, *a, **k):                                                                 # recover_state move o arquivo depois do exists() do leitor
        if Path(path) == p:
            os.replace(p, tmp_path / "quarentena")
        return real(path, *a, **k)
    monkeypatch.setattr(eb, "_read_bytes", moved_first)
    assert eb.load(p) == eb.default_bridge_state()                                                  # contrato de ausente, sem FileNotFoundError


def test_after_a_recovery_a_review_whose_head_moved_is_stale_and_is_not_requeued(tmp_path):
    p = tmp_path / "event_bridge.json"
    p.write_bytes(b"\x00" * 64)                                                                    # o estado que sabia do review ja atendido foi perdido
    policy = {"reviewers": ["rev"], "executor_logins": ["exe"]}
    review = {"kind": "review", "author": "rev", "repo": "o/r", "state": "CHANGES_REQUESTED", "commit_id": "a" * 40, "id": 1}
    served_pr = {"head_sha": "b" * 40, "refs": [1]}                                                 # o executor JA publicou: o HEAD do PR andou
    with es.locked(p):
        eb.recover_state(p)
    assert eb.classify(review, served_pr, policy, "o/r")[0] == "STALE"                              # o HEAD e a prova duravel: nao ha reexecucao


def test_after_a_recovery_an_unserved_review_is_requeued_exactly_once_not_every_poll(tmp_path):
    from tests.test_event_bridge import NOW, POLICY, fake_gh, review
    p = tmp_path / "event_bridge.json"
    p.write_bytes(b"\x00" * 64)                                                                    # estado perdido: o review pendente ainda e valido no GitHub
    gh = fake_gh(reviews=[review(9)])
    eb.run_cycle(gh, POLICY, p, now=NOW)
    first = eb.load(p)["queue"]
    eb.run_cycle(gh, POLICY, p, now=NOW)
    second = eb.load(p)["queue"]
    assert len(first) == 1 and second == first                                                     # reenfileirado UMA vez (o HEAD nao andou: nada foi publicado) e nao duplica


def test_a_review_that_the_executor_already_served_is_never_requeued_after_a_recovery(tmp_path):
    from tests.test_event_bridge import HEAD, NOW, POLICY, fake_gh, review
    p = tmp_path / "event_bridge.json"
    p.write_bytes(b"\x00" * 64)
    served = fake_gh(reviews=[review(9)], head="b" * 40)                                           # o executor ja publicou: o HEAD do PR andou
    counts = eb.run_cycle(served, POLICY, p, now=NOW)
    assert eb.load(p)["queue"] == [] and counts["STALE"] == 1 and review(9)["commit_id"] == HEAD
