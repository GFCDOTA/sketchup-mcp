"""redact — saneamento aplicado NO SINK, não no consumidor.

A regra de segurança do workspace ("redatar segredos em log/ledger/handoff") só
vale se o segredo nunca TOCA o disco. Redigir na UI seria teatro: o `.jsonl` já
estaria no repo. Então a barreira é uma só, e é na escrita.

Três camadas, nesta ordem:

1. **Allowlist de chaves** — `meta` só passa com chave conhecida. É o oposto de
   uma denylist: chave nova nasce bloqueada, e ninguém vaza um campo por ter
   esquecido de proibi-lo.
2. **Scrub de valor** — o que sobra ainda passa por regex de segredo, porque um
   campo legítimo (`reason`, `note`) pode conter um token colado numa mensagem
   de erro. É exatamente o caso do `InfraUnavailable(f"... falhou: {e!r}")`, que
   serializa a URL inteira.
3. **Caminho relativo** — path absoluto vira relativo à raiz do repo. Não é
   segredo, é privacidade: `C:\\Users\\felip_local\\...` não precisa viajar.

O prompt montado NUNCA entra no evento: vai `{sha12, chars}`. O texto só é
servido por rota local com `INSPECTOR_SHOW_PROMPTS=1`.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

REDACTED = "«redacted»"
_MAX_STR = 512          # nenhum valor de meta passa disso
_MAX_LIST = 64          # nenhuma lista de meta passa disso

# ---------------------------------------------------------------------------
# 1. allowlist
# ---------------------------------------------------------------------------

ALLOWED_META_KEYS: frozenset[str] = frozenset({
    # identidade / classificação
    "retrievalKind", "harnessKind", "indexKind", "isRag", "ragCycleComplete",
    "resultingTaxonomy", "intentMatchedExecution",
    # RAG — intenção vs execução (ver core/observability/retrieval.py)
    "retriever", "backendRequested", "backendActual", "fallbackTriggered",
    "fallbackReason", "degradedTo",
    "collection", "corpusVersion", "topK", "threshold", "queryChars", "queryHash",
    "embedModel", "embedDim", "prefix", "retrieversFused",
    "fusionStrategy", "fusionK", "inputs", "provenance",
    "candidatesCount", "nRetrieved", "nSelected", "nRejected", "nStale", "nKept",
    "chunkId", "score", "rank", "source", "sourceType", "sourceKind",
    "chars", "selected", "reason", "documentId", "documentVersion",
    "latencyMs",
    # contexto
    "sections", "totalChars", "totalTokens", "attributedFraction",
    "promptSha12", "promptChars", "systemPromptSha12",
    # LLM
    "model", "promptTokens", "completionTokens", "stream", "finishReason",
    "providerRaw", "temperature", "numPredict",
    # tools / sketchup
    "tool", "args", "argKeys", "exitCode", "script", "entityRef", "entitiesDelta",
    "artifact", "plant", "room", "roomId",
    # gates
    "gate", "verdict", "metric", "measured", "required", "unit", "nFail",
    "nTotal", "nPass", "measurements", "counts",
    # harness
    "cycle", "maxCycles", "terminal", "fix", "findingType", "reverted",
    "signature", "badness",
    # evidência de decisão (taxonomy.DecisionEvidence.to_meta)
    "triggerEvent", "gateResult", "contextRefs", "toolCalled", "effect",
    # diagnóstico
    "error", "errorType", "truncated", "note", "stage",
})

# ---------------------------------------------------------------------------
# 2. scrub de valor
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"), "«redacted:api_key»"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"), "«redacted:github_token»"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"), "«redacted:slack_token»"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"), "«redacted:bearer»"),
    (re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|pwd)"
                r"\s*[=:]\s*[^\s,;&'\"]{4,}"), r"\1=«redacted»"),
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "«redacted:email»"),
    # credencial embutida em URL: scheme://user:pass@host
    (re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^/\s:@]+:[^/\s@]+@"), r"\1«redacted»@"),
)


def scrub_text(text: str) -> str:
    """Aplica todos os padrões de segredo a uma string."""
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


# ---------------------------------------------------------------------------
# 3. caminho relativo
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]


def relativize(text: str, root: Path | None = None) -> str:
    """Path absoluto sob a raiz do repo vira relativo. Fora dela, vira basename."""
    r = str(root or _REPO_ROOT)
    out = text.replace(r + "\\", "").replace(r + "/", "").replace(r, "")
    # caminho absoluto de OUTRA árvore (home do usuário, temp) perde o prefixo
    out = re.sub(r"(?i)\b[a-z]:[\\/](?:[^\\/\s\"']+[\\/]){2,}", "…/", out)
    out = re.sub(r"(?<![\w.])/(?:[^/\s\"']+/){2,}", "…/", out)
    return out


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def sha12(text: str) -> str:
    """Hash curto — a forma segura de referenciar um prompt sem carregá-lo."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _clean_value(value: Any, depth: int = 0) -> Any:
    if depth > 3:
        return REDACTED
    if isinstance(value, str):
        out = relativize(scrub_text(value))
        return out[:_MAX_STR] + "…" if len(out) > _MAX_STR else out
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [_clean_value(v, depth + 1) for v in list(value)[:_MAX_LIST]]
    if isinstance(value, dict):
        return {str(k): _clean_value(v, depth + 1) for k, v in value.items()}
    return _clean_value(str(value), depth)


def redact_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    """Allowlist + scrub. Chave desconhecida some (e não vira `«redacted»`:
    marcar cada chave bloqueada só encheria o trace de ruído)."""
    if not meta:
        return {}
    return {k: _clean_value(v) for k, v in meta.items() if k in ALLOWED_META_KEYS}


def dropped_keys(meta: dict[str, Any] | None) -> list[str]:
    """Chaves que a allowlist barrou — para diagnóstico e teste, não para o trace."""
    if not meta:
        return []
    return sorted(k for k in meta if k not in ALLOWED_META_KEYS)
