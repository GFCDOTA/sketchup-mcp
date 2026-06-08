#!/usr/bin/env python3
"""Roteamento de TIER do oraculo (:8765) por PROPOSITO da consulta.

Camada CLIENTE: decide QUAL tier pedir. O server
(`tools/claude_bridge/server.py`, `resolve_tier`) e quem mapeia o nome do
tier -> (model, effort). Esta funcao e PURA e testavel, sem I/O.

Dois tiers (ver server.TIERS):

- **fast** = Sonnet + effort baixo (segundos). Consultas BARATAS e
  REPETITIVAS, principalmente ANTES de gerar o `.skp` no ciclo de mobiliario:
  design-intent, referencia->checklist, rascunho de regra de layout, triagem,
  preparacao de prompt, exploracao.
- **deep** = Opus + xhigh (~minuto, o JUIZ). Decisao de peso: veredito visual
  FINAL que aprova/reprova o `.skp`, merge, aprovacao de artifact, decisao
  arquitetural, conflito entre gates.

Hard rule (negative-dogfood): o veredito visual FINAL fica PINADO em `deep`
mesmo que alguem peca `fast` — so um override EXPLICITO do usuario troca.

Default = `deep` (seguranca + back-compat: proposito desconhecido/vazio NAO
vira fast por acidente; os 9 triggers canonicos de decisao caem aqui -> deep).
"""
from __future__ import annotations

VALID_TIERS = ("fast", "deep")
DEFAULT_TIER = "deep"

# Propositos BARATOS/repetitivos do ciclo de mobiliario (pre-.skp) -> fast.
FAST_PURPOSES = frozenset({
    "design_intent",           # gerar/extrair DesignIntentSpec pre-movel
    "reference_to_checklist",  # transformar referencia visual em checklist
    "layout_rule_draft",       # rascunhar regra de layout / furniture anatomy
    "triage",                  # triagem inicial de problemas
    "prompt_prep",             # preparar prompt p/ referencia GPT
    "exploration",             # perguntas exploratorias / baratas
})

# Propositos de PESO (o juiz) -> deep.
DEEP_PURPOSES = frozenset({
    "final_visual_verdict",    # GPT que aprova/reprova o .skp (PINADO, ver abaixo)
    "merge_decision",          # mergear PR
    "artifact_approval",       # promover .skp/render a artifact canonico
    "architectural_decision",  # decisao arquitetural
    "gate_conflict",           # conflito entre gates / vereditos
})

# Pinados em deep mesmo se pedirem fast (salvo override explicito do usuario).
PINNED_DEEP_PURPOSES = frozenset({"final_visual_verdict"})


def choose_gate_tier(purpose: str = "", *, explicit_tier: str = "",
                     user_override: bool = False) -> str:
    """Decide o tier ('fast'|'deep') de uma consulta ao oraculo pelo proposito.

    - `purpose`: rotulo do proposito da consulta (ver FAST_PURPOSES / DEEP_PURPOSES).
    - `explicit_tier`: se 'fast'/'deep', vence o roteamento por proposito —
      EXCETO num proposito pinado em deep, que so cede com `user_override=True`.
    - `user_override`: True = o usuario escolheu o tier explicitamente; libera
      trocar o tier de um proposito pinado (ex.: "modo rapido no veredito final").

    Proposito desconhecido/vazio -> DEFAULT_TIER ('deep'). Pura, sem I/O.
    """
    p = (purpose or "").strip().lower()
    et = (explicit_tier or "").strip().lower()
    et = et if et in VALID_TIERS else ""

    # 1. Hard rule: proposito pinado em deep (veredito visual final).
    if p in PINNED_DEEP_PURPOSES:
        if user_override and et:
            return et          # usuario pediu explicitamente -> respeita
        return "deep"

    # 2. Override explicito de tier vence o roteamento por proposito.
    if et:
        return et

    # 3. Roteamento por proposito.
    if p in FAST_PURPOSES:
        return "fast"
    if p in DEEP_PURPOSES:
        return "deep"

    # 4. Desconhecido/vazio -> deep (compat + seguranca).
    return DEFAULT_TIER
