"""Optional vision-LLM critique via local Ollama qwen2.5vl:7b.

Skipped silently if Ollama isn't reachable or the model isn't pulled.
The validator's main signal is the structural heuristics; this is a
qualitative supplement matching memory feedback_gpt_critico_imagens
("nao aceitar 'parece ok'").
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

try:
    import requests
except ModuleNotFoundError:  # optional: only needed for live Ollama call
    requests = None  # type: ignore[assignment]

from .scorers.base import ScorerContext

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5vl:7b"
TIMEOUT_S = 120


def _b64(p: Path) -> str:
    with p.open("rb") as f:
        return base64.b64encode(f.read()).decode()


def _build_prompt(entry: dict, ctx: ScorerContext) -> str:
    kind = entry.get("kind", "?")
    src = entry.get("source", {}) or {}
    consensus = ctx.consensus or {}
    rooms = len(consensus.get("rooms", []))
    walls = len(consensus.get("walls", []))
    openings = len(consensus.get("openings", []))

    pdf_hint = ""
    if src.get("pdf") and not src["pdf"].get("missing"):
        pdf_hint = (
            f"A planta-baixa original e o arquivo {src['pdf']['path']} "
            f"(comparar com a render se possivel)."
        )

    area_hint = (
        f"com area esperada informada de {ctx.expected_area_m2:g} m2"
        if ctx.expected_area_m2 is not None
        else "arquitetonica"
    )
    return (
        f"Voce e revisor critico de plantas baixas extraidas. "
        f"Esta imagem e do tipo '{kind}', extraida de uma planta {area_hint}. "
        f"O modelo de consenso tem walls={walls}, rooms={rooms}, openings={openings}. "
        f"{pdf_hint}\n\n"
        "Aponte EXPLICITAMENTE:\n"
        "1) portas/janelas que parecem fora do lugar ou ausentes (nao basta dizer 'parece ok')\n"
        "2) rooms que tem buraco branco no piso (cobertura incompleta)\n"
        "3) walls duplicadas ou desconectadas visivelmente\n"
        "4) qualquer outra divergencia visual em relacao a uma planta tipica\n\n"
        "Responda em portugues, em ate 6 bullet points objetivos. "
        "Se nao houver problema, responda 'OK' e justifique em 1 linha."
    )


def _ollama_available() -> bool:
    if requests is None:
        return False
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        return r.ok
    except Exception:
        return False


def maybe_vision_critique(entry: dict, ctx: ScorerContext) -> dict[str, Any] | None:
    if not _ollama_available():
        return None
    png = ctx.repo_root / entry["history_path"]
    if not png.exists():
        return None

    try:
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": _build_prompt(entry, ctx),
                "images": [_b64(png)],
                "stream": False,
                "options": {"num_predict": 600, "temperature": 0.2},
            },
            timeout=TIMEOUT_S,
        )
        if not r.ok:
            return {"error": f"ollama {r.status_code}", "model": MODEL}
        data = r.json()
        return {
            "model": MODEL,
            "response": (data.get("response") or "").strip(),
            "eval_duration_ns": data.get("eval_duration"),
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "model": MODEL}
