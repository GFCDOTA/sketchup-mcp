#!/usr/bin/env python3
"""Gate framework §6.4 — structured Verdict parser + canonical answer format.

The oracle answers in a fixed bullet format (ANSWER_FORMAT). `parse_verdict`
extracts the fields so the asker can act programmatically — crucially the §6.4
additions `confidence` and `assumptions` (what the oracle ASSUMED / could NOT
verify), so the asker knows which parts to re-check deterministically vs accept
on faith.
"""
from __future__ import annotations

import re

VERDICT_ENUM = ("GO", "NO-GO", "MORE-INFO", "VISUAL_REVIEW")
CONFIDENCE_ENUM = ("high", "medium", "low")

# Single source of the answer contract — referenced by the bridge SYSTEM prompt
# and the asker's prompt builder so the two can't drift.
ANSWER_FORMAT = "\n".join([
    "- Verdict: GO / NO-GO / MORE-INFO / VISUAL_REVIEW",
    "- Confidence: high / medium / low",
    "- Reasoning: 2-4 sentences, technical, critical",
    "- Assumptions: bullets — what you ASSUMED or could NOT verify from the prompt",
    "- Risks: bullets",
    "- Suggested next action: 1-2 lines, highest-leverage first",
])

_HEADERS = r"verdict|confidence|reasoning|assumptions?|risks?|suggested|next\s+action"
_VMAP = {"VISUAL-REVIEW": "VISUAL_REVIEW", "NO-GO": "NO-GO",
         "MORE-INFO": "MORE-INFO", "GO": "GO"}


def _line_value(raw: str, name: str) -> str | None:
    m = re.search(rf"(?im)^[ \t>*\-\d.\)]*\**\s*{name}\**\s*[:\-]\s*(.+?)\s*$", raw)
    return m.group(1).strip() if m else None


def _bullets(raw: str, name: str) -> list[str]:
    """Text after a `Name:` header, up to the next known header → bullet list."""
    m = re.search(
        rf"(?ims)^[ \t>*\-\d.\)]*\**\s*{name}\**\s*[:\-]\s*(.*?)"
        rf"(?=^[ \t>*\-\d.\)]*\**\s*(?:{_HEADERS})\**\s*[:\-]|\Z)",
        raw)
    if not m:
        return []
    out: list[str] = []
    for ln in m.group(1).splitlines():
        ln = ln.strip().lstrip("-*•").strip()
        if ln:
            out.append(ln)
    return out


def _parse_verdict_token(raw: str) -> str | None:
    line = (_line_value(raw, "verdict") or "").upper().replace("_", "-")
    for v in ("VISUAL-REVIEW", "NO-GO", "MORE-INFO", "GO"):  # specific first
        if v in line:
            return _VMAP[v]
    return None


def _parse_confidence(raw: str) -> str | None:
    line = (_line_value(raw, "confidence") or "").lower()
    for c in CONFIDENCE_ENUM:
        if c in line:
            return c
    return None


def parse_verdict(raw: str) -> dict:
    """Parse the oracle's answer. Missing fields -> None / []. Tolerant of
    bullet style (-/*/numbered), **bold**, and case."""
    raw = raw or ""
    return {
        "verdict": _parse_verdict_token(raw),
        "confidence": _parse_confidence(raw),
        "reasoning": _line_value(raw, "reasoning"),
        "assumptions": _bullets(raw, "assumptions?"),
        "risks": _bullets(raw, "risks?"),
        "next_action": _line_value(raw, r"(?:suggested\s+)?next\s+action"),
    }
