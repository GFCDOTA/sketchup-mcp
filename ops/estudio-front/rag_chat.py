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

import json
import os
import time
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
    "confirme que anotou. Use as preferencias ja salvas (se houver, no contexto "
    "abaixo) pra dar respostas coerentes com o gosto dele ja conhecido. "
    "Responda sempre em portugues do Brasil."
)


class InfraUnavailable(RuntimeError):
    pass


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


def search_preferences(query: str, top_k: int = 5) -> list[dict]:
    """Busca semântica nas preferências já salvas. [] se offline ou vazio."""
    try:
        _ensure_collection()
        vec = embed(query, prefix="search_query: ")
        out = _http("POST", f"{QDRANT_URL}/collections/{COLLECTION}/points/search",
                    {"vector": vec, "limit": top_k, "with_payload": True}, timeout=15)
        return [r["payload"] for r in out.get("result", []) if r.get("score", 0) > 0.3]
    except InfraUnavailable:
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
        ctx = "\n\nPreferencias ja salvas relevantes:\n" + "\n".join(
            f"- {p['text']}" for p in prefs)

    recent = hist[-10:]
    convo = "\n".join(f"{'Felipe' if h['role']=='user' else 'Voce'}: {h['text']}"
                       for h in recent)

    prompt = SYSTEM_PROMPT + ctx + "\n\n" + convo + "\nVoce:"
    out = _http("POST", f"{OLLAMA_URL}/api/generate",
                {"model": CHAT_MODEL, "prompt": prompt, "stream": False,
                 "options": {"num_predict": 400}}, timeout=90)
    reply = (out.get("response") or "").strip() or "…"

    hist.append({"role": "assistant", "text": reply, "ts": time.time()})
    _save_history(hist)
    return {"reply": reply, "context_used": [p["text"] for p in prefs]}
