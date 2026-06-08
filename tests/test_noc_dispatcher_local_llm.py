"""Roteamento kind:local_llm no NOC dispatcher. Hermético: mocka ollama_client.generate
e o ledger; NÃO toca git, Ollama real, nem .ai_bridge real."""
from __future__ import annotations

import pytest

from tools.claude_bridge import noc_dispatcher as nd
from tools.claude_bridge import ollama_client


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    """Isola ledger (captura em lista) e o dir de saída (tmp)."""
    rows: list = []
    monkeypatch.setattr(nd, "ledger_append", rows.append)
    monkeypatch.setattr(nd, "LOCAL_LLM_DIR", tmp_path / "local_llm")
    return rows


def test_local_llm_done_writes_artifact_and_ledger(monkeypatch, sandbox):
    monkeypatch.setattr(ollama_client, "generate",
                        lambda prompt, **kw: {"response": "ok resumido", "latency_ms": 120,
                                              "load_ms": 30, "eval_count": 5})
    task = {"id": "L1", "kind": "local_llm", "purpose": "summarize_log",
            "title": "resume log", "prompt": "centenas de linhas de log..."}
    res = nd.dispatch_local_llm(task)
    assert res["status"] == "LOCAL_LLM_DONE"
    assert res["backend"] == "ollama"
    assert res["model"] == "llama3.1:8b"          # default por purpose
    assert res["latency_ms"] == 120
    assert (nd.LOCAL_LLM_DIR / "L1.md").exists()
    assert sandbox[-1]["status"] == "LOCAL_LLM_DONE"   # auditado


def test_local_llm_model_override(monkeypatch, sandbox):
    monkeypatch.setattr(ollama_client, "generate",
                        lambda prompt, **kw: {"response": "x", "latency_ms": 1})
    task = {"id": "L1b", "kind": "local_llm", "purpose": "cheap_triage",
            "model": "qwen2.5-coder:14b", "prompt": "y"}
    assert nd.dispatch_local_llm(task)["model"] == "qwen2.5-coder:14b"


def test_local_llm_purpose_not_allowed_blocks(sandbox):
    task = {"id": "L2", "kind": "local_llm", "purpose": "edit_repo", "prompt": "x"}
    res = nd.dispatch_local_llm(task)
    assert res["status"] == "SKIPPED_PURPOSE_NOT_ALLOWED"


def test_local_llm_empty_prompt_noop(sandbox):
    res = nd.dispatch_local_llm({"id": "L2b", "kind": "local_llm",
                                 "purpose": "cheap_triage", "prompt": "   "})
    assert res["status"] == "NOOP"


def test_local_llm_offline_explicit_error(monkeypatch, sandbox):
    def boom(prompt, **kw):
        raise ollama_client.OllamaUnavailable("daemon down")

    monkeypatch.setattr(ollama_client, "generate", boom)
    res = nd.dispatch_local_llm({"id": "L3", "kind": "local_llm",
                                 "purpose": "cheap_triage", "prompt": "x"})
    assert res["status"] == "LOCAL_LLM_OFFLINE"


def test_local_llm_offline_fallback_claude_signaled(monkeypatch, sandbox):
    def boom(prompt, **kw):
        raise ollama_client.OllamaUnavailable("daemon down")

    monkeypatch.setattr(ollama_client, "generate", boom)
    res = nd.dispatch_local_llm({"id": "L4", "kind": "local_llm", "purpose": "cheap_triage",
                                 "prompt": "x", "on_offline": "claude"})
    assert res["status"] == "LOCAL_LLM_FALLBACK_CLAUDE"


def test_local_llm_dry_run_does_not_call_model(monkeypatch, sandbox):
    def must_not_call(prompt, **kw):
        raise AssertionError("generate NÃO deve ser chamado em dry-run")

    monkeypatch.setattr(ollama_client, "generate", must_not_call)
    res = nd.dispatch_local_llm({"id": "L5", "kind": "local_llm",
                                 "purpose": "cheap_triage", "prompt": "x"}, dry_run=True)
    assert res["status"] == "DRY_RUN"


def test_dispatch_by_kind_tool_is_skipped(sandbox):
    res = nd.dispatch_by_kind({"id": "T9", "kind": "tool", "title": "montage"})
    assert res["status"] == "SKIPPED_KIND_TOOL"


def test_dispatch_by_kind_routes_local_llm(monkeypatch, sandbox):
    monkeypatch.setattr(ollama_client, "generate",
                        lambda prompt, **kw: {"response": "r", "latency_ms": 9})
    res = nd.dispatch_by_kind({"id": "L6", "kind": "local_llm",
                               "purpose": "prompt_prepare", "prompt": "z"})
    assert res["status"] == "LOCAL_LLM_DONE"
