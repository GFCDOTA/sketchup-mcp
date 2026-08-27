"""rag_chat.py — chat leve com o "designer" (Ollama) + memória em Qdrant.

Coleção PRÓPRIA (`felipe_preferences`), separada do `rag_chunks` usado pelo
RAG de fidelidade do sketchup-mcp (tools/rag_embed_backend.py) — não mexe
naquele corpus/reindex. Mesmo padrão de infra (Qdrant :6333 + Ollama :11434,
HTTP puro via urllib, stdlib only, degrada limpo se offline).

Fluxo: Felipe escreve no chat do painel -> resposta do modelo `interior-designer`
(Ollama), com contexto = histórico recente + preferências já salvas relevantes
(busca semântica). Nada é salvo no banco vetorial automaticamente — só quando
Felipe pede explicitamente ("salva isso"), via POST /api/chat/save.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import time
import types
import urllib.error
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HISTORY_FILE = ROOT / "chat_history.json"

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "llama3.1:8b")
# nota: o modelo Ollama "interior-designer" tem Modelfile proprio fixado pra
# SEMPRE devolver JSON de layout de moveis (usado pelo pipeline de furnish) —
# nao serve pra bate-papo solto. Usamos um modelo de chat geral aqui; o
# "designer" deste chat e o SYSTEM_PROMPT abaixo, nao o modelo Ollama named
# "interior-designer".
COLLECTION = "felipe_preferences"
EMBED_DIM = 768

SYSTEM_PROMPT = (
    "Voce e o assistente de design de interiores do Felipe, dono do estudio "
    "que projeta a planta_74 (apartamento 74m2 - banhos, cozinha, sala, "
    "quartos). Sua funcao aqui e CONVERSAR e ANOTAR o gosto dele em tempo "
    "real, sem forcar processo: ele vai comentar o que gosta/nao gosta "
    "(materiais, cores, estilos, erros que ja viu em renders) e voce responde "
    "curto, direto, como um designer de verdade bateria papo - nao burocratico, "
    "nao lista enumerada toda hora. Quando ele pedir pra salvar/lembrar algo, "
    "confirme que anotou. Use as preferencias e o conhecimento tecnico ja "
    "salvos (se houver, no contexto abaixo) pra dar respostas coerentes e "
    "fundamentadas, citando a fonte quando vier de uma regra tecnica ou "
    "decisao anterior do projeto (nao so opiniao solta). Se perguntarem como "
    "melhorar um comodo, proponha algo concreto usando esse contexto, nao "
    "generico. Responda sempre em portugues do Brasil."
)


class InfraUnavailable(RuntimeError):
    pass

# ---------------------------------------------------------------------------
# observabilidade — import DEFENSIVO de propósito
#
# Este módulo é importado como top-level (`import rag_chat`) com o cwd em
# ops/estudio-front, não como parte do pacote. Sem o sys.path abaixo, `core`
# não resolve. E se por qualquer motivo não resolver mesmo assim, a regra
# "observability must not change execution" exige que o chat continue de pé:
# o shim no-op garante isso. Não é framework paralelo — são 8 linhas para não
# deixar o observador derrubar o observado.
# ---------------------------------------------------------------------------
_REPO_ROOT = ROOT.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
try:
    from core import observability as obs
    from core.observability.llm import ContextComposition, ContextSource, from_ollama
except Exception:  # noqa: BLE001 — front fora da árvore do repo
    class _NoObs:
        def emit(self, *a, **k):
            return None

        def run(self, *a, **k):
            return contextlib.nullcontext()

        def stage(self, *a, **k):
            return contextlib.nullcontext(types.SimpleNamespace(meta={}))

        def is_enabled(self):
            return False

    obs = _NoObs()
    ContextComposition = ContextSource = from_ollama = None


def _emit_chunks(collection: str, results: list, *, threshold: float,
                 top_k: int, query: str) -> None:
    """Emite UM evento leve por candidato, marcando quem entrou e quem não.

    Existe porque o corte (`score > threshold`) é uma list-comp que DESCARTA o
    rejeitado no ato: "vieram 9, entraram 4" era informação perdida. O corte em
    si continua idêntico — aqui só se observa a lista antes dele.
    """
    for i, r in enumerate(results):
        score = r.get("score", 0)
        selected = score > threshold
        payload = r.get("payload") or {}
        obs.emit("rag.chunk.selected" if selected else "rag.chunk.rejected",
                 component=f"qdrant.{collection}",
                 meta={"chunkId": str(r.get("id")), "score": score, "rank": i + 1,
                       "collection": collection, "threshold": threshold,
                       "selected": selected,
                       "source": payload.get("source"),
                       "sourceType": payload.get("category"),
                       "chars": len(payload.get("text") or "") or None,
                       "reason": None if selected else "abaixo do threshold"})
    n_sel = sum(1 for r in results if r.get("score", 0) > threshold)
    obs.emit("rag.query.finished", component=f"qdrant.{collection}",
             meta={"retriever": collection, "collection": collection,
                   "indexKind": "VECTOR", "backendRequested": "embed",
                   "backendActual": "embed", "fallbackTriggered": False,
                   "resultingTaxonomy": "VECTOR_SEMANTIC_RAG", "isRag": True,
                   "topK": top_k, "threshold": threshold,
                   "embedModel": EMBED_MODEL, "queryChars": len(query),
                   "candidatesCount": len(results), "nRetrieved": len(results),
                   "nSelected": n_sel, "nRejected": len(results) - n_sel})


def _emit_retrieval_degraded(collection: str, reason: str) -> None:
    obs.emit("rag.degraded", component=f"qdrant.{collection}", status="degraded",
             meta={"retriever": collection, "collection": collection,
                   "indexKind": "VECTOR", "backendRequested": "embed",
                   "backendActual": "none", "fallbackTriggered": True,
                   "fallbackReason": reason, "nRetrieved": 0, "nSelected": 0})



def _http(method: str, url: str, payload: dict | None = None, *, timeout: int = 60) -> dict:
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


def ollama_up(timeout: int = 2) -> bool:
    try:
        _http("GET", f"{OLLAMA_URL}/api/tags", timeout=timeout)
        return True
    except InfraUnavailable:
        return False


def qdrant_up(timeout: int = 2) -> bool:
    try:
        _http("GET", f"{QDRANT_URL}/collections", timeout=timeout)
        return True
    except InfraUnavailable:
        return False


def embed(text: str, *, prefix: str = "") -> list[float]:
    out = _http("POST", f"{OLLAMA_URL}/api/embeddings",
                {"model": EMBED_MODEL, "prompt": prefix + text}, timeout=60)
    vec = out.get("embedding")
    if not vec:
        raise InfraUnavailable("embedding vazio")
    return vec


def _ensure_collection() -> None:
    try:
        _http("GET", f"{QDRANT_URL}/collections/{COLLECTION}", timeout=5)
    except InfraUnavailable:
        _http("PUT", f"{QDRANT_URL}/collections/{COLLECTION}",
              {"vectors": {"size": EMBED_DIM, "distance": "Cosine"}}, timeout=15)


def _point_id(text: str, ts: float) -> int:
    return zlib.crc32(f"{ts}:{text}".encode("utf-8")) & 0x7FFFFFFF


def save_preference(text: str) -> dict:
    """Embeda e upserta no Qdrant. Levanta InfraUnavailable se offline."""
    _ensure_collection()
    ts = time.time()
    vec = embed(text, prefix="search_document: ")
    point = {"id": _point_id(text, ts), "vector": vec,
             "payload": {"text": text, "ts": ts,
                         "when": time.strftime("%Y-%m-%d %H:%M")}}
    _http("PUT", f"{QDRANT_URL}/collections/{COLLECTION}/points?wait=true",
          {"points": [point]}, timeout=30)
    return {"ok": True, "text": text}


def count_preferences() -> int:
    try:
        out = _http("GET", f"{QDRANT_URL}/collections/{COLLECTION}", timeout=5)
        return int(out.get("result", {}).get("points_count", 0))
    except InfraUnavailable:
        return 0


def search_preferences(query: str, top_k: int = 5) -> list[dict]:
    """Busca semântica nas preferências já salvas. [] se offline ou vazio."""
    try:
        _ensure_collection()
        vec = embed(query, prefix="search_query: ")
        out = _http("POST", f"{QDRANT_URL}/collections/{COLLECTION}/points/search",
                    {"vector": vec, "limit": top_k, "with_payload": True}, timeout=15)
        results = out.get("result", [])
        _emit_chunks(COLLECTION, results, threshold=0.3, top_k=top_k, query=query)
        return [r["payload"] for r in results if r.get("score", 0) > 0.3]
    except InfraUnavailable as e:
        _emit_retrieval_degraded(COLLECTION, f"InfraUnavailable: {e}")
        return []


def load_history() -> list[dict]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text("utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def _save_history(hist: list[dict]) -> None:
    HISTORY_FILE.write_text(json.dumps(hist, indent=2, ensure_ascii=False), "utf-8")


def chat(message: str) -> dict:
    """Roda 1 turno: salva a msg do usuario, busca contexto, chama o modelo,
    salva a resposta. Retorna {reply, saved_prefs_used}."""
    hist = load_history()
    hist.append({"role": "user", "text": message, "ts": time.time()})

    if not ollama_up():
        reply = ("Ollama nao esta no ar aqui (127.0.0.1:11434) — nao consigo "
                 "responder agora, mas sua mensagem ficou salva no historico. "
                 "Suba o Ollama e me chama de novo.")
        hist.append({"role": "assistant", "text": reply, "ts": time.time()})
        _save_history(hist)
        return {"reply": reply, "context_used": []}

    prefs = search_preferences(message, top_k=5)
    ctx = ""
    if prefs:
        ctx += "\n\nPreferencias ja salvas relevantes:\n" + "\n".join(
            f"- {p['text']}" for p in prefs)
    _ctx_prefs = ctx          # fatia de PREFERÊNCIA recuperada (só medição)

    # conhecimento tecnico (decisoes anteriores, regras, PDFs quando existirem)
    # — import tardio pra evitar import circular (knowledge_ingest importa este
    # modulo pra reusar embed()/Qdrant helpers)
    kb_hits: list[dict] = []
    try:
        import knowledge_ingest as ki
        kb_hits = ki.search_knowledge(message, top_k=4)
    except Exception:
        pass
    if kb_hits:
        ctx += "\n\nConhecimento tecnico/decisoes anteriores relevantes:\n" + "\n".join(
            f"- [{h.get('category', '?')}/{h.get('source', '?')}] {h['text']}" for h in kb_hits)
    _ctx_kb = ctx[len(_ctx_prefs):]   # fatia de CONHECIMENTO recuperado

    recent = hist[-10:]
    convo = "\n".join(f"{'Felipe' if h['role']=='user' else 'Voce'}: {h['text']}"
                       for h in recent)

    prompt = SYSTEM_PROMPT + ctx + "\n\n" + convo + "\nVoce:"
    if ContextComposition is not None:
        obs.emit("context.build.finished", component="rag_chat",
                 meta=(ContextComposition()
                       .add(ContextSource.SYSTEM_STATIC, SYSTEM_PROMPT)
                       .add(ContextSource.RETRIEVED_PREFERENCES, _ctx_prefs)
                       .add(ContextSource.RETRIEVED_KNOWLEDGE, _ctx_kb)
                       .add(ContextSource.CONVERSATION, convo)
                       ).to_meta(prompt))
    _t0 = time.perf_counter()
    obs.emit("llm.started", component=f"ollama.{CHAT_MODEL}", status="started",
             meta={"model": CHAT_MODEL, "stream": False, "numPredict": 400,
                   "promptChars": len(prompt)})
    out = _http("POST", f"{OLLAMA_URL}/api/generate",
                {"model": CHAT_MODEL, "prompt": prompt, "stream": False,
                 "options": {"num_predict": 400}}, timeout=90)
    if from_ollama is not None:
        _lat = (time.perf_counter() - _t0) * 1000.0
        obs.emit("llm.finished", component=f"ollama.{CHAT_MODEL}",
                 duration_ms=_lat,
                 meta=from_ollama(out, model=CHAT_MODEL, latency_ms=_lat).to_meta())
    reply = (out.get("response") or "").strip() or "…"

    hist.append({"role": "assistant", "text": reply, "ts": time.time()})
    _save_history(hist)
    return {"reply": reply, "context_used": [p["text"] for p in prefs],
            "kb_used": [h["text"][:120] for h in kb_hits]}
