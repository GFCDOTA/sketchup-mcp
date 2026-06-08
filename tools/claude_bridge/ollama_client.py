"""Ollama text client — chamada LOCAL barata (papel "Ollama = compute grátis" do
brain_muscle.md; backend do `kind:local_llm` do NOC dispatcher).

Texto puro: summarize / triage / draft / classify. NÃO é o caminho visual — esse é
`tools/oracle_providers.py::OllamaVisionProvider` (imagens → visual_findings.v1).
Aqui: prompt → resposta + latência, token=0, offline-first, sem rede externa.

Stdlib `urllib` (zero dependência nova), espelhando o idioma já provado no
OllamaVisionProvider (probe via /api/tags, POST /api/generate, stream=False).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

OLLAMA_URL = "http://127.0.0.1:11434"
HEALTH_TIMEOUT_SEC = 4
GENERATE_TIMEOUT_SEC = 300  # teto por chamada; cabe load frio de modelo grande (~25s p/ 8B)


class OllamaUnavailable(RuntimeError):
    """Daemon Ollama não respondeu / erro de rede ou parse. O chamador decide o
    fallback (ex.: status OFFLINE explícito, ou cair pro claude se configurado)."""


def probe(url: str = OLLAMA_URL, model: str | None = None,
          timeout: int = HEALTH_TIMEOUT_SEC) -> tuple[bool, str]:
    """(ok, detalhe). Se `model` for dado, exige que esteja instalado. Nunca levanta."""
    try:
        req = urllib.request.Request(f"{url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 200:
                return False, f"/api/tags retornou {resp.status}"
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            OSError, ValueError) as e:
        return False, f"ollama unreachable em {url}: {e!r}"
    installed = [m.get("name") for m in data.get("models", [])]
    if model and model not in installed:
        return False, f"model {model!r} not installed; disponiveis={installed}"
    return True, f"ollama ok ({len(installed)} modelos)"


def generate(prompt: str, model: str = "llama3.1:8b", *, purpose: str | None = None,
             options: dict | None = None, url: str = OLLAMA_URL,
             timeout: int = GENERATE_TIMEOUT_SEC) -> dict:
    """POST /api/generate (stream=False). Retorna dict compacto:
    {response, model, purpose, latency_ms, eval_count, load_ms, eval_ms}.
    Levanta ValueError p/ prompt vazio e OllamaUnavailable se o daemon falhar."""
    if not prompt or not prompt.strip():
        raise ValueError("prompt vazio")
    opts = {"temperature": 0, "num_predict": 512}
    if options:
        opts.update(options)
    payload = {"model": model, "prompt": prompt, "stream": False, "options": opts}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{url}/api/generate", data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            OSError, ValueError) as e:
        raise OllamaUnavailable(f"ollama /api/generate falhou: {e!r}") from e
    return {
        "response": (body.get("response") or "").strip(),
        "model": model,
        "purpose": purpose,
        "latency_ms": round((time.time() - t0) * 1000),
        "eval_count": body.get("eval_count"),
        "load_ms": round((body.get("load_duration") or 0) / 1e6),
        "eval_ms": round((body.get("eval_duration") or 0) / 1e6),
    }
