"""Card 🧠 Memória vetorial do :8782 — contratos de degradação honesta.

O status NUNCA levanta (o /api/state não pode cair por causa do RAG); a busca
semântica com infra off devolve erro claro, jamais hits fabricados; o comparador
consulta os DOIS backends e reporta `moved` fiel à diferença de ordem.
"""
import tools.studio_dashboard as sd


def test_rag_status_never_raises_and_has_infra_flags():
    sd._RAG_CACHE.update(t=0.0, v=None)   # limpa o cache -> caminho real
    out = sd._rag_status()
    assert isinstance(out, dict)
    assert "qdrant_up" in out and "ollama_up" in out
    assert "verdicts" in out
    assert out.get("generator_backend") in ("faceted", "embed")


def test_rag_status_is_cached():
    sd._RAG_CACHE.update(t=0.0, v=None)
    first = sd._rag_status()
    assert sd._rag_status() is first   # segundo hit vem do cache (20s)


def test_rag_search_empty_query_is_error():
    out = sd._rag_search({"q": "   "})
    assert out["ok"] is False and "hits" not in out


def test_rag_search_infra_off_degrades_honest(monkeypatch):
    import tools.rag_embed_backend as reb

    def _boom(*a, **k):
        raise reb.InfraUnavailable("qdrant off (teste)")

    monkeypatch.setattr(reb, "semantic_recall", _boom)
    out = sd._rag_search({"q": "bancada madeira escura"})
    # erro claro (infra off OU índice vazio) — nunca resultado fabricado
    assert out["ok"] is False and "hits" not in out


def test_rag_compare_queries_both_backends_and_flags_moved(monkeypatch):
    import tools.reference_db as rdb
    calls = []

    def _fake(room, style=None, budget=None, *, con=None, top_n=6, backend="faceted"):
        calls.append(backend)
        names = ["b", "a"] if backend == "embed" else ["a", "b"]
        return {"tokens": [{"name": n} for n in names],
                "retrieved_chunks": [], "notes": [], "rag_corpus_version": "cv-test"}

    monkeypatch.setattr(rdb, "retrieve", _fake)
    out = sd._rag_compare({"room": "kitchen", "style": "warm_compact"})
    assert out["ok"] is True and out["moved"] is True
    assert calls == ["faceted", "embed"]


def test_rag_compare_same_order_not_moved(monkeypatch):
    import tools.reference_db as rdb

    def _fake(room, style=None, budget=None, *, con=None, top_n=6, backend="faceted"):
        return {"tokens": [{"name": "a"}, {"name": "b"}],
                "retrieved_chunks": [], "notes": [], "rag_corpus_version": "cv-test"}

    monkeypatch.setattr(rdb, "retrieve", _fake)
    out = sd._rag_compare({"room": "kitchen"})
    assert out["ok"] is True and out["moved"] is False
