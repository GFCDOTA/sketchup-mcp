"""rag_embed_backend.py — FP-037 Camada 2: adapter Qdrant + Ollama pro backend embed.

Recall SEMÂNTICO OPCIONAL. Embeda a query via Ollama (`nomic-embed-text`, 768d) e
busca no Qdrant (collection `rag_chunks`, cosine) FILTRANDO por is_active=true E
corpus_version==atual no payload. O resultado semântico só melhora RECALL — os
facets/gates do FP-035 continuam decidindo confidence.

Decisão de design: HTTP PURO via `urllib` (stdlib) pro Qdrant E pro Ollama. Zero
dependência nova no caminho quente; o CI (que instala só `[dev]`) nunca importa
`qdrant_client`. Imports de urllib/json são stdlib e ficam no topo; as chamadas de
REDE vivem dentro das funções — se Qdrant/Ollama estão off, cada função levanta
`InfraUnavailable`, e o CHAMADOR (reference_db.retrieve backend=embed) degrada pro
faceted, LOGA, e NÃO infla confidence.

O reindex incremental (só embeda chunk com embedded=0) é orquestrado por
`reindex_qdrant()`, chamado pela CLI `reference_db reindex` (ou este módulo direto).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger("rag_embed_backend")

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
COLLECTION = os.environ.get("RAG_COLLECTION", "rag_chunks")
EMBED_DIM = 768   # nomic-embed-text

# nomic-embed-text é instruction-tuned p/ retrieval ASSIMÉTRICO: documentos e
# queries levam prefixos distintos. Sem eles o recall degrada de graça. Doc e
# query DEVEM viver com o mesmo esquema -> mudar aqui exige `reference_db reindex
# --rebuild` p/ re-embedar o corpus com o prefixo de documento.
EMBED_DOC_PREFIX = "search_document: "
EMBED_QUERY_PREFIX = "search_query: "


class InfraUnavailable(RuntimeError):
    """Qdrant ou Ollama off/erro — o chamador deve degradar pro faceted."""


# ---------------------------------------------------------------------------
# HTTP puro (urllib) — helpers
# ---------------------------------------------------------------------------
def _http(method: str, url: str, payload: dict | None = None, *,
          timeout: int = 30) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        raise InfraUnavailable(f"{method} {url} falhou: {e!r}") from e


# ---------------------------------------------------------------------------
# probes rápidos — pro skip automático dos testes de integração
# ---------------------------------------------------------------------------
def qdrant_up(timeout: int = 2) -> bool:
    try:
        _http("GET", f"{QDRANT_URL}/collections", timeout=timeout)
        return True
    except InfraUnavailable:
        return False


def ollama_up(timeout: int = 3) -> bool:
    try:
        _http("GET", f"{OLLAMA_URL}/api/tags", timeout=timeout)
        return True
    except InfraUnavailable:
        return False


def infra_up(timeout: int = 3) -> bool:
    return qdrant_up(timeout) and ollama_up(timeout)


# ---------------------------------------------------------------------------
# Ollama embed (urllib)
# ---------------------------------------------------------------------------
def embed(text: str, *, prefix: str = "", timeout: int = 120) -> list[float]:
    """Embedding via Ollama nomic-embed-text (768d). `prefix` = esquema assimétrico
    do nomic (EMBED_DOC_PREFIX no índice, EMBED_QUERY_PREFIX na query). Levanta
    InfraUnavailable se off ou vazio -> chamador degrada."""
    body = _http("POST", f"{OLLAMA_URL}/api/embeddings",
                 {"model": EMBED_MODEL, "prompt": f"{prefix}{text}"}, timeout=timeout)
    vec = body.get("embedding") or []
    if not vec:
        raise InfraUnavailable(
            f"embedding vazio p/ texto de {len(text)} chars (modelo {EMBED_MODEL!r})")
    return [float(x) for x in vec]


# ---------------------------------------------------------------------------
# Qdrant — collection lifecycle
# ---------------------------------------------------------------------------
def ensure_collection(*, dim: int = EMBED_DIM, timeout: int = 15) -> None:
    """Cria a collection cosine se não existir. Idempotente."""
    existing = _http("GET", f"{QDRANT_URL}/collections", timeout=timeout)
    names = {c.get("name") for c in
             (existing.get("result", {}).get("collections") or [])}
    if COLLECTION in names:
        return
    _http("PUT", f"{QDRANT_URL}/collections/{COLLECTION}",
          {"vectors": {"size": dim, "distance": "Cosine"}}, timeout=timeout)
    log.info("qdrant: collection %s criada (dim=%d, cosine)", COLLECTION, dim)


def _point_id(chunk_id: str) -> int:
    """Qdrant point id: inteiro determinístico derivado do chunk_id (hex->int trunc)."""
    return int(chunk_id[:15], 16)


def upsert_points(points: list[dict], *, timeout: int = 60) -> None:
    """points: [{chunk_id, vector, payload}]. Upsert idempotente (id determinístico)."""
    if not points:
        return
    body = {"points": [
        {"id": _point_id(p["chunk_id"]), "vector": p["vector"], "payload": p["payload"]}
        for p in points]}
    _http("PUT", f"{QDRANT_URL}/collections/{COLLECTION}/points?wait=true",
          body, timeout=timeout)


def delete_points(chunk_ids: list[str], *, timeout: int = 30) -> None:
    if not chunk_ids:
        return
    _http("POST", f"{QDRANT_URL}/collections/{COLLECTION}/points/delete?wait=true",
          {"points": [_point_id(c) for c in chunk_ids]}, timeout=timeout)


def search(vector: list[float], *, corpus_version: str, top_k: int = 12,
           source_type: str | None = None, timeout: int = 30) -> list[dict]:
    """Busca semântica FILTRANDO por is_active=true E corpus_version==atual no
    payload. `source_type` (ex. 'token') filtra NATIVO no Qdrant — sem ele os
    chunks-de-token ficam esparsos no top_k do corpus inteiro e a fusão colapsa.
    Devolve [{chunk_id, score, payload}] ordenado por score desc."""
    must = [
        {"key": "is_active", "match": {"value": True}},
        {"key": "corpus_version", "match": {"value": corpus_version}},
    ]
    if source_type is not None:
        must.append({"key": "source_type", "match": {"value": source_type}})
    body = {
        "vector": vector,
        "limit": top_k,
        "with_payload": True,
        "filter": {"must": must},
    }
    res = _http("POST", f"{QDRANT_URL}/collections/{COLLECTION}/points/search",
                body, timeout=timeout)
    out = []
    for hit in res.get("result") or []:
        payload = hit.get("payload") or {}
        out.append({
            "chunk_id": payload.get("chunk_id"),
            "score": float(hit.get("score", 0.0)),
            "payload": payload,
        })
    return out


# ---------------------------------------------------------------------------
# reindex incremental do Qdrant a partir do índice de freshness
#
# Só embeda chunk com embedded=0 (hash novo). Chunk inativo -> deleta do Qdrant.
# Marca embedded=1 após upsert. Determinístico na ordem (por chunk_id).
# ---------------------------------------------------------------------------
def reindex_qdrant(con, *, corpus_version: str, now_iso: str,
                   batch: int = 32) -> dict:
    """Popula o Qdrant a partir dos chunks do rag_freshness.db. INCREMENTAL:
    embeda só embedded=0. Levanta InfraUnavailable se Qdrant/Ollama off (o
    caller decide se aborta ou ignora). Retorna relatório de contagens."""
    ensure_collection()

    # chunks ativos do corpus atual ainda não embedados
    pending = con.execute(
        "SELECT chunk_id, document_id, document_version, title, text, chunk_hash, "
        "corpus_version, source_path, source_type FROM chunk "
        "WHERE is_active=1 AND corpus_version=? AND embedded=0 "
        "ORDER BY chunk_id", (corpus_version,)).fetchall()

    report = {"embedded": 0, "deleted": 0, "skipped_already_embedded": 0}

    buf: list[dict] = []
    for r in pending:
        vec = embed(f"[{r['source_type']}] {r['title'] or ''}\n{r['text']}",
                    prefix=EMBED_DOC_PREFIX)
        buf.append({
            "chunk_id": r["chunk_id"],
            "vector": vec,
            "payload": {
                "chunk_id": r["chunk_id"],
                "document_id": r["document_id"],
                "document_version": r["document_version"],
                "corpus_version": r["corpus_version"],
                "source_path": r["source_path"],
                "source_type": r["source_type"],
                "title": r["title"],
                "text": r["text"],
                "is_active": True,
            },
        })
        if len(buf) >= batch:
            upsert_points(buf)
            for p in buf:
                con.execute("UPDATE chunk SET embedded=1 WHERE chunk_id=?",
                            (p["chunk_id"],))
            con.commit()
            report["embedded"] += len(buf)
            buf = []
    if buf:
        upsert_points(buf)
        for p in buf:
            con.execute("UPDATE chunk SET embedded=1 WHERE chunk_id=?",
                        (p["chunk_id"],))
        con.commit()
        report["embedded"] += len(buf)

    # chunks inativos -> remove do Qdrant (não polui recall)
    inactive = [r["chunk_id"] for r in con.execute(
        "SELECT chunk_id FROM chunk WHERE is_active=0 ORDER BY chunk_id")]
    if inactive:
        delete_points(inactive)
        report["deleted"] = len(inactive)

    log.info("reindex_qdrant: embedded=%d deleted=%d corpus=%s",
             report["embedded"], report["deleted"], corpus_version[:12])
    return report


def semantic_recall(query: str, *, corpus_version: str, top_k: int = 12,
                    source_type: str | None = None) -> list[dict]:
    """Embeda a query (com o prefixo de QUERY do nomic) e busca no Qdrant,
    opcionalmente filtrando por source_type. Levanta InfraUnavailable se off.
    Devolve [{chunk_id, score, payload}]."""
    vec = embed(query, prefix=EMBED_QUERY_PREFIX)
    return search(vec, corpus_version=corpus_version, top_k=top_k,
                  source_type=source_type)
