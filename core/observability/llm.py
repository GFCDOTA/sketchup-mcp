"""llm — contrato normalizado de uma chamada de modelo + decomposição do contexto.

DUAS DECISÕES
-------------
1. **Normalizar, não repassar.** O Ollama devolve `prompt_eval_count` e
   `eval_count` — que HOJE são descartados em `_ollama()` e em
   `ollama_bridge.ask()` (ambos fazem `.get("response")` e jogam o resto fora).
   Ler isso sai de graça. Mas `prompt_eval_count` é semântica do Ollama: outro
   provider chama de outra coisa e às vezes conta de outro jeito. Então o
   contrato é nosso (`prompt_tokens` / `completion_tokens`), o adapter é por
   provider, e o metadado cru só é preservado quando acrescenta algo.

2. **Chars são medidos, tokens não são estimados.** A decomposição do contexto
   por origem é medida em CARACTERES, que é o que dá pra contar olhando as
   strings que já são concatenadas. Tokens por origem exigiriam tokenizer no
   caminho quente — então o campo existe e diz `NOT_INSTRUMENTED`. Nunca uma
   estimativa travestida de medição.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

NOT_INSTRUMENTED = "NOT_INSTRUMENTED"


# ---------------------------------------------------------------------------
# origens de contexto
# ---------------------------------------------------------------------------


class ContextSource(str, Enum):
    """De onde cada pedaço do prompt veio."""

    SYSTEM_STATIC = "system/static"
    PROJECT_STATE = "project state"
    RETRIEVED_KNOWLEDGE = "retrieved knowledge"
    RETRIEVED_PREFERENCES = "retrieved preferences"
    STYLE_STATIC = "style/static context"
    CONVERSATION = "conversation"
    TOOL_DEFINITIONS = "tool definitions"
    OTHER = "other"


@dataclass(frozen=True)
class ContextSection:
    source: ContextSource
    chars: int
    label: str | None = None


@dataclass
class ContextComposition:
    """Quanto do prompt veio de cada origem.

    Uso: o call-site mede as MESMAS strings que já monta, sem mudar a montagem.

        comp = ContextComposition()
        comp.add(ContextSource.SYSTEM_STATIC, PROMPT_TEMPLATE)
        comp.add(ContextSource.STYLE_STATIC, dna)
        comp.add(ContextSource.RETRIEVED_KNOWLEDGE, design_spec)
        comp.add(ContextSource.PROJECT_STATE, existing_str)
    """

    sections: list[ContextSection] = field(default_factory=list)

    def add(self, source: ContextSource, text: str | None,
            label: str | None = None) -> "ContextComposition":
        if text:
            self.sections.append(
                ContextSection(source=source, chars=len(text), label=label))
        return self

    @property
    def total_chars(self) -> int:
        return sum(s.chars for s in self.sections)

    def by_source(self) -> dict[ContextSource, int]:
        out: dict[ContextSource, int] = {}
        for s in self.sections:
            out[s.source] = out.get(s.source, 0) + s.chars
        return out

    def coverage(self, prompt: str) -> float | None:
        """Fração do prompt real que as seções declaradas explicam.

        Honestidade: se o call-site mediu 4 pedaços mas o prompt tem 20% a mais
        (separadores, formatação do template), a UI precisa saber que a soma
        NÃO fecha, em vez de mostrar percentuais que somam 100% por
        normalização. < 1.0 significa "há contexto não atribuído".
        """
        if not prompt:
            return None
        return round(self.total_chars / len(prompt), 4)

    def to_meta(self, prompt: str | None = None) -> dict[str, Any]:
        total = self.total_chars or 1
        by = self.by_source()
        meta: dict[str, Any] = {
            "sections": [
                {"source": src.value, "chars": chars,
                 "pct": round(100.0 * chars / total, 1)}
                for src, chars in sorted(by.items(), key=lambda kv: -kv[1])
            ],
            "totalChars": self.total_chars,
            # medir tokens por origem exigiria tokenizer no caminho quente;
            # estimar seria inventar. O campo existe e é honesto.
            "totalTokens": NOT_INSTRUMENTED,
        }
        if prompt is not None:
            cov = self.coverage(prompt)
            meta["promptChars"] = len(prompt)
            if cov is not None:
                meta["attributedFraction"] = cov
        return meta


# ---------------------------------------------------------------------------
# chamada de modelo
# ---------------------------------------------------------------------------


@dataclass
class LLMCall:
    """Uma chamada, no NOSSO contrato — não no do provider."""

    provider: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float | None = None
    stream: bool = False
    finish_reason: str | None = None
    provider_raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int | None:
        if self.prompt_tokens is None and self.completion_tokens is None:
            return None
        return (self.prompt_tokens or 0) + (self.completion_tokens or 0)

    def to_meta(self) -> dict[str, Any]:
        meta: dict[str, Any] = {"model": self.model, "stream": self.stream}
        for key, value in (("promptTokens", self.prompt_tokens),
                           ("completionTokens", self.completion_tokens),
                           ("totalTokens", self.total_tokens)):
            meta[key] = value if value is not None else NOT_INSTRUMENTED
        if self.latency_ms is not None:
            meta["latencyMs"] = round(self.latency_ms, 3)
        if self.provider_raw:
            meta["providerRaw"] = dict(self.provider_raw)
        return meta


# Campos do Ollama que valem preservar como metadado cru: são nanossegundos de
# fase (carga do modelo, avaliação do prompt, geração) que o nosso contrato não
# tem e que explicam latência alta. O resto do body é descartado.
_OLLAMA_RAW_KEYS = ("total_duration", "load_duration",
                    "prompt_eval_duration", "eval_duration")


def from_ollama(body: dict[str, Any], *, model: str,
                latency_ms: float | None = None,
                stream: bool = False,
                keep_raw: bool = True) -> LLMCall:
    """Adapter Ollama -> LLMCall.

    `prompt_eval_count` = tokens de entrada, `eval_count` = tokens gerados.
    Ausentes em resposta truncada/erro -> None (nunca 0: "não sei" != "zero").
    NÃO assuma esta semântica em outro provider — escreva outro adapter.
    """
    raw = {k: body[k] for k in _OLLAMA_RAW_KEYS if k in body} if keep_raw else {}
    return LLMCall(
        provider="ollama",
        model=body.get("model") or model,
        prompt_tokens=body.get("prompt_eval_count"),
        completion_tokens=body.get("eval_count"),
        latency_ms=latency_ms,
        stream=stream,
        finish_reason=body.get("done_reason"),
        provider_raw=raw,
    )
