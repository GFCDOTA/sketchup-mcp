"""FP-060 (#633/#635): gravacao DURAVEL do estado de execucao (`tools/validation/execution_state.py`): temporario -> flush -> fsync -> troca atomica,
sincronizacao do diretorio em POSIX e troca repetida enquanto o Windows a recusa por instantes."""
from __future__ import annotations

import os

import pytest

from tools.validation import execution_state as es


def test_write_durable_fsyncs_the_temporary_file_before_the_atomic_replace(tmp_path, monkeypatch):
    order = []
    real_fsync, real_replace = os.fsync, es.replace_retry
    monkeypatch.setattr(es.os, "fsync", lambda fd: order.append("fsync") or real_fsync(fd))
    monkeypatch.setattr(es, "replace_retry", lambda src, dst, **kw: order.append("replace") or real_replace(src, dst, **kw))
    target = tmp_path / "state.json"
    es.write_durable(target, '{"queue": []}\n')
    assert target.read_text(encoding="utf-8") == '{"queue": []}\n' and not (tmp_path / "state.json.tmp").exists()
    assert order.index("fsync") < order.index("replace")                                           # o conteudo vai ao disco ANTES da troca


def test_write_durable_never_leaves_a_partial_target_when_the_write_fails(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_text("ANTIGO", encoding="utf-8")

    def boom(fd):
        raise OSError("disco cheio")
    monkeypatch.setattr(es.os, "fsync", boom)
    with pytest.raises(OSError):
        es.write_durable(target, "NOVO")
    assert target.read_text(encoding="utf-8") == "ANTIGO"                                          # sem fsync, nada substitui o arquivo bom


def test_replace_retry_retries_a_transient_windows_refusal_then_succeeds(tmp_path, monkeypatch):
    src, dst = tmp_path / "a.tmp", tmp_path / "a"
    src.write_text("x", encoding="utf-8")
    calls = []
    real = os.replace

    def flaky(a, b):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError(32, "arquivo em uso")
        return real(a, b)
    monkeypatch.setattr(es.os, "replace", flaky)
    es.replace_retry(src, dst, tries=5, pause=0)
    assert dst.read_text(encoding="utf-8") == "x" and len(calls) == 3


def test_replace_retry_gives_up_after_its_budget_and_raises(tmp_path, monkeypatch):
    src, dst = tmp_path / "a.tmp", tmp_path / "a"
    src.write_text("x", encoding="utf-8")

    def always(a, b):
        raise PermissionError(5, "acesso negado")
    monkeypatch.setattr(es.os, "replace", always)
    with pytest.raises(PermissionError):
        es.replace_retry(src, dst, tries=3, pause=0)
    assert not dst.exists() and src.exists()                                                       # nunca grava por cima de outro jeito


def test_fsync_dir_is_a_no_op_on_windows_and_never_raises(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(es.os, "open", lambda *a, **k: opened.append(a) or (_ for _ in ()).throw(OSError("nao abre diretorio")))
    es.fsync_dir(tmp_path)                                                                          # Windows: no-op; POSIX: falha de abertura engolida
    if os.name == "nt":
        assert opened == []
