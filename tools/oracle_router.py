#!/usr/bin/env python3
"""Gate framework §6.1 — multi-oracle ROUTING for text decisions.

Pure routing (no I/O, no network, no import of provider OBJECTS — one-way string
dependency, so it unit-tests with zero mocks). Fixes the root limit of the gate:
a peer-Claude shares the asker's blind spots, so it is NOT an independent check.
Route by NEED:

  - an OBJECTIVE/factual question (a deterministic check exists) -> 'deterministic'
    — ground truth WINS over any oracle (the project's constitution applied to the gate).
  - a RISKY decision (or an explicit 'independent' ask) -> a NON-asker-family LLM
    (ChatGPT / local) — a second opinion that does NOT share Claude's bias.
  - otherwise (technical / A-B-C) -> 'claude' (sharpen reasoning, name risks).

`route()` respects an `available` set and degrades gracefully (never raises);
`is_independent()` tells the caller whether the pick is a genuinely independent
signal or just a same-family fallback.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OracleRef:
    id: str            # "claude" | "chatgpt" | "local" | "deterministic"
    family: str        # "claude" | "openai" | "local" | "-"   (independence axis)
    kind: str          # "llm" | "deterministic"
    endpoint: str | None


# Canonical table — strings only; the gate maps id -> a concrete caller.
ORACLES: tuple[OracleRef, ...] = (
    OracleRef("claude", "claude", "llm", "http://localhost:8765"),
    OracleRef("chatgpt", "openai", "llm", "http://localhost:8765"),
    OracleRef("local", "local", "llm", "http://localhost:11434"),
    OracleRef("deterministic", "-", "deterministic", None),
)
_BY_ID = {o.id: o for o in ORACLES}

_FACTUAL = ("factual", "check", "verify", "ground", "deterministic", "objective")
_INDEP = ("independent", "second", "2nd", "non-claude", "cross-check")


def route(*, question_type: str = "technical", risk: str = "normal",
          asker_family: str = "claude", available=None) -> str:
    """Pick an oracle id by need. See module docstring. Never raises."""
    avail = set(available) if available is not None else set(_BY_ID)

    def first(*ids: str) -> str | None:
        return next((i for i in ids if i in avail), None)

    qt = (question_type or "").lower()

    # 1. objective question -> deterministic ground truth beats any oracle.
    if any(k in qt for k in _FACTUAL):
        return first("deterministic", "claude", "chatgpt", "local") or "claude"

    # 2. risky / wants independence -> an LLM whose family != the asker's.
    if risk == "high" or any(k in qt for k in _INDEP):
        indep = first(*[o.id for o in ORACLES
                        if o.kind == "llm" and o.family != asker_family])
        if indep:
            return indep
        return first("claude", "chatgpt", "local") or "claude"  # graceful fallback

    # 3. default: technical / A-B-C -> claude (reasoning + risk-naming).
    return first("claude", "chatgpt", "local") or "claude"


def is_independent(provider_id: str, asker_family: str = "claude") -> bool:
    """True iff `provider_id` gives a signal independent of the asker's model
    family (different family + LLM) — so the caller knows whether its 'second
    opinion' is real or a same-family fallback."""
    o = _BY_ID.get(provider_id)
    return bool(o and o.kind == "llm" and o.family != asker_family)


def describe(provider_id: str) -> OracleRef | None:
    return _BY_ID.get(provider_id)
