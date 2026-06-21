"""openai_client.py — backend OpenAI OPCIONAL (Fase 7). STUB por enquanto.

Regra: chave SÓ em `OPENAI_API_KEY` (env), nunca no frontend, nunca commitada. NUNCA quebra se a
chave não existir — degrada pro Manual Bridge. O cliente real (chamada à API) é Fase 7 / MT-012;
aqui só existe o contrato de não-quebrar.
"""
from __future__ import annotations

import os


def is_enabled() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def ask(question_contract: dict) -> dict:
    """Retorna sempre um resultado seguro. Se não há chave OU o backend ainda não foi implementado,
    sugere o Manual Bridge — nunca levanta exceção."""
    if not is_enabled():
        return {"ok": False, "error": "OPENAI_API_KEY ausente no ambiente do servidor.",
                "fallback": "manual", "hint": "Copie a pergunta e cole no ChatGPT (Manual Bridge)."}
    return {"ok": False, "error": "Backend OpenAI ainda não implementado (Fase 7 / MT-012).",
            "fallback": "manual", "hint": "Use o Manual Bridge por enquanto."}
