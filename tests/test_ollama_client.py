"""Contrato do cliente Ollama-texto (kind:local_llm). Hermético: mocka urllib,
NÃO depende do daemon Ollama real nem de rede."""
from __future__ import annotations

import json
import urllib.error

import pytest

from tools.claude_bridge import ollama_client


class _FakeResp:
    """Context-manager mínimo no formato de urlopen()."""

    def __init__(self, payload: dict, status: int = 200):
        self._b = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_generate_parses_compact_result(monkeypatch):
    def fake_urlopen(req, timeout=None):
        return _FakeResp({"response": "  resumo curto ", "eval_count": 12,
                          "load_duration": 2_000_000_000, "eval_duration": 100_000_000})

    monkeypatch.setattr(ollama_client.urllib.request, "urlopen", fake_urlopen)
    out = ollama_client.generate("um log qualquer", model="llama3.1:8b",
                                 purpose="cheap_triage")
    assert out["response"] == "resumo curto"          # strip aplicado
    assert out["model"] == "llama3.1:8b"
    assert out["purpose"] == "cheap_triage"
    assert out["eval_count"] == 12
    assert out["load_ms"] == 2000                     # ns -> ms
    assert isinstance(out["latency_ms"], int)


def test_generate_raises_ollama_unavailable_when_down(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(ollama_client.urllib.request, "urlopen", boom)
    with pytest.raises(ollama_client.OllamaUnavailable):
        ollama_client.generate("oi")


def test_generate_rejects_empty_prompt():
    with pytest.raises(ValueError):
        ollama_client.generate("   ")


def test_probe_false_when_unreachable(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(ollama_client.urllib.request, "urlopen", boom)
    ok, detail = ollama_client.probe()
    assert ok is False
    assert "unreachable" in detail.lower()


def test_probe_requires_model_installed(monkeypatch):
    def fake(req, timeout=None):
        return _FakeResp({"models": [{"name": "llama3.1:8b"}]})

    monkeypatch.setattr(ollama_client.urllib.request, "urlopen", fake)
    ok, _ = ollama_client.probe(model="llama3.1:8b")
    assert ok is True
    ok2, detail2 = ollama_client.probe(model="missing:99b")
    assert ok2 is False
    assert "not installed" in detail2.lower()
