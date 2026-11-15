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


def quarantined(p: Path) -> list[Path]:
    return sorted(p.parent.glob(p.name + ".corrupt-*"))


# -- corrupcao: explicita, preservada, sem traceback ----------------------------------------------------------------------------
@pytest.mark.parametrize("content", [
    b"\x00" * 20888,                           # o caso real de producao
    b"", b"  \n\t", b"\x00\x00\x00\x00",      # vazio e quase vazio
    b'{"queue": [{"key": "k1"', b'{"schema_version": 1, "queue": [',        # truncado no meio do JSON
    b"[]", b'"texto"', b"42",                  # JSON valido que nao e um objeto
    b"\xff\xfe\x00\x00 nao e utf-8",           # codificacao invalida
], ids=["zeros-producao", "vazio", "espacos", "quatro-nulos", "truncado-a", "truncado-b", "array", "string", "numero", "utf8-invalido"])
def test_a_corrupt_state_file_is_preserved_and_replaced_by_a_clean_state_with_a_diagnostic(tmp_path, content):
    p = tmp_path / "event_bridge.json"
    p.write_bytes(content)

    loaded = eb.load(p)

    assert loaded["queue"] == [] and loaded["cursor_comments"] is None and loaded["seen"] == []     # sera reconstruido do GitHub
    (kept,) = quarantined(p)
    assert kept.read_bytes() == content and not p.exists()                                        # nada foi apagado
    assert any("corrompido" in d["message"] and kept.name in d["message"] and "GitHub" in d["message"] for d in loaded["diagnostics"])
    assert eb.load(p)["queue"] == [] and len(quarantined(p)) == 1                                  # a 2a leitura nao quarentena de novo


def test_the_previous_good_version_is_restored_when_the_main_file_is_corrupt(tmp_path):
    p = tmp_path / "event_bridge.json"
    eb.save(state(1), p)
    eb.save(state(2), p)                                                                            # .bak guarda a versao 1
    p.write_bytes(b"\x00" * 500)

    loaded = eb.load(p)

    assert loaded["queue"] == [{"key": "k1"}] and any("restaurado" in d["message"] for d in loaded["diagnostics"])
    assert eb.load(p, recover=False)["queue"] == [{"key": "k1"}]                                    # o principal voltou a ser valido
    assert quarantined(p)[0].read_bytes() == b"\x00" * 500


def test_a_corrupt_backup_is_not_used_and_the_queue_is_rebuilt(tmp_path):
    p = tmp_path / "event_bridge.json"
    p.write_bytes(b"\x00" * 10)
    p.with_name(p.name + ".bak").write_bytes(b"{ quebrado")

    loaded = eb.load(p)

    assert loaded["queue"] == [] and any("GitHub" in d["message"] for d in loaded["diagnostics"])


def test_a_reader_that_must_not_touch_anything_gets_an_explicit_error_and_the_file_stays_as_it_was(tmp_path):
    p = tmp_path / "event_bridge.json"
    p.write_bytes(b"\x00" * 100)

    with pytest.raises(eb.BridgeStateCorrupt, match="zero|nulos|vazio"):
        eb.load(p, recover=False)

    assert p.read_bytes() == b"\x00" * 100 and quarantined(p) == []


def test_recovering_a_file_another_process_already_moved_is_not_an_error(tmp_path):
    p = tmp_path / "event_bridge.json"                                                              # ja nao existe: outro processo quarentenou
    loaded = eb._recover(p, ValueError("arquivo vazio"))
    assert loaded["queue"] == [] and any("corrompido" in d["message"] for d in loaded["diagnostics"])


def test_a_healthy_state_round_trips_and_a_missing_file_is_a_default_state(tmp_path):
    p = tmp_path / "event_bridge.json"
    assert eb.load(p) == eb.default_bridge_state()
    eb.save(state(7), p)
    assert eb.load(p, recover=False)["queue"] == [{"key": "k7"}] and quarantined(p) == []


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
    assert p.read_bytes() == before and eb.load(p, recover=False)["queue"] == [{"key": "k1"}]


def test_the_backup_is_never_overwritten_by_a_corrupt_main_file(tmp_path):
    p = tmp_path / "event_bridge.json"
    eb.save(state(1), p)
    eb.save(state(2), p)                                                                            # .bak = versao 1
    p.write_bytes(b"\x00" * 64)

    eb.save(state(3), p)                                                                            # grava sem recuperar antes

    assert json.loads(p.with_name(p.name + ".bak").read_text(encoding="utf-8"))["queue"] == [{"key": "k1"}]
    assert eb.load(p, recover=False)["queue"] == [{"key": "k3"}]


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
        loaded = eb.load(p, recover=False)                                                           # nao pode levantar
        assert isinstance(loaded["backoff_s"], int) and quarantined(p) == []


def test_losing_the_race_to_quarantine_the_file_is_not_an_error(tmp_path, monkeypatch):
    p = tmp_path / "event_bridge.json"
    p.write_bytes(b"\x00" * 10)
    monkeypatch.setattr(os, "replace", lambda a, b: (_ for _ in ()).throw(FileNotFoundError()))     # outro processo ja o moveu

    loaded = eb._recover(p, ValueError("arquivo vazio"))

    assert loaded["queue"] == [] and any("outro processo" in d["message"] for d in loaded["diagnostics"])


def test_if_the_corrupt_file_cannot_be_preserved_nothing_is_recreated_and_the_error_is_explicit(tmp_path, monkeypatch):
    p = tmp_path / "event_bridge.json"
    p.write_bytes(b"\x00" * 10)
    monkeypatch.setattr(os, "replace", lambda a, b: (_ for _ in ()).throw(PermissionError("em uso")))

    with pytest.raises(eb.BridgeStateCorrupt, match="preserva"):
        eb.load(p)

    monkeypatch.undo()
    assert p.read_bytes() == b"\x00" * 10 and quarantined(p) == []
