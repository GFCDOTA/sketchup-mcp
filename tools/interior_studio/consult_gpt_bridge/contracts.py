"""contracts.py — vocabulário + validação (hand-rolled, stdlib only) dos contratos Consult GPT.

Sem jsonschema (o container é python:3.12-slim, stdlib only). A validação aqui é leve: chaves
obrigatórias + enums + tipos, espelhando os JSON Schemas em contracts/schemas/. Lógica PURA e
determinística (sem clock/IO) — testável direto.
"""
from __future__ import annotations

MODES = ("SPEC", "JUDGE", "REPAIR", "LEARN", "COMPARE")
ROOMS = ("kitchen", "living", "bedroom", "bathroom", "laundry", "full_apartment")
PHASES = ("layout", "form", "skin", "lighting", "render", "final_validation")
PRIORITIES = ("low", "medium", "high", "blocker")
VERDICTS = ("PASS", "WARN", "FAIL")
ANSWER_FORMAT = "ARCHITECT_ANSWER_CONTRACT v1"

# Os 7 checks canônicos do Felipe (mesma ordem do template v1).
DEFAULT_QUESTIONS = [
    {"id": "cave_check", "text": "ficou escuro demais ou se segura?"},
    {"id": "fake_luxury_check", "text": "parece elegante ou virou luxo fake?"},
    {"id": "compact_premium_check", "text": "tem impacto sem perder uso real?"},
    {"id": "warmth_balance_check", "text": "tem madeira/luz suficiente?"},
    {"id": "material_hierarchy_check", "text": "os materiais competem entre si?"},
    {"id": "felipe_taste_match", "text": "parece o gosto do Felipe?"},
    {"id": "ajuste_1", "text": "qual é o ajuste número 1 antes do próximo ciclo?"},
]


def validate_question(c: dict) -> list[str]:
    """Devolve lista de erros (vazia = válido). Espelha question_contract.schema.json."""
    errs: list[str] = []
    if not isinstance(c, dict):
        return ["question não é objeto"]
    req = ("question_id", "created_at", "agent", "mode", "room", "phase", "theme", "priority",
           "context", "decision_goal", "frozen_constraints", "mutable", "architect_hypothesis",
           "questions", "answer_format")
    for k in req:
        if not c.get(k) and c.get(k) != []:
            errs.append(f"falta: {k}")
    _enum(errs, c, "mode", MODES)
    _enum(errs, c, "room", ROOMS)
    _enum(errs, c, "phase", PHASES)
    _enum(errs, c, "priority", PRIORITIES)
    if c.get("agent") not in (None, "architect"):
        errs.append("agent deve ser 'architect'")
    for k in ("frozen_constraints", "mutable"):
        if k in c and not isinstance(c[k], list):
            errs.append(f"{k} deve ser lista")
    qs = c.get("questions")
    if not isinstance(qs, list) or not qs:
        errs.append("questions deve ser lista não-vazia")
    else:
        for i, q in enumerate(qs):
            if not isinstance(q, dict) or not q.get("id") or not q.get("text"):
                errs.append(f"questions[{i}] precisa de id+text")
    if c.get("mode") == "COMPARE":
        vi = c.get("visual_inputs") or {}
        if not (vi.get("compare")):
            errs.append("mode COMPARE exige visual_inputs.compare")
    if c.get("answer_format") not in (None, ANSWER_FORMAT):
        errs.append(f"answer_format deve ser '{ANSWER_FORMAT}'")
    return errs


def validate_answer(c: dict) -> list[str]:
    """Devolve lista de erros (vazia = válido). Espelha answer_contract.schema.json. Lenient:
    usado para AVISAR, não para barrar a ingestão (o GPT às vezes esquece um campo)."""
    errs: list[str] = []
    if not isinstance(c, dict):
        return ["answer não é objeto"]
    for k in ("question_id", "verdict", "summary", "question_answers", "top_fix", "next_microtask"):
        if not c.get(k) and c.get(k) != []:
            errs.append(f"falta: {k}")
    _enum(errs, c, "verdict", VERDICTS)
    nm = c.get("next_microtask")
    if nm is not None and not (isinstance(nm, dict) and nm.get("title")):
        errs.append("next_microtask precisa de title")
    return errs


def _enum(errs: list[str], c: dict, key: str, allowed: tuple) -> None:
    v = c.get(key)
    if v is not None and v not in allowed:
        errs.append(f"{key}='{v}' inválido (use {'|'.join(allowed)})")


def render_question_md(c: dict) -> str:
    """Renderiza o contrato de pergunta como markdown limpo (pronto pro Felipe colar no ChatGPT)."""
    vi = c.get("visual_inputs") or {}
    lines = [
        "# ARCHITECT_QUESTION_CONTRACT v1", "",
        "## Metadata",
        f"- question_id: `{c.get('question_id','')}`",
        f"- created_at: `{c.get('created_at','')}`",
        "- agent: `architect`",
        f"- mode: `{c.get('mode','')}`",
        f"- project: `{c.get('project','')}`",
        f"- room: `{c.get('room','')}`",
        f"- phase: `{c.get('phase','')}`",
        f"- theme: `{c.get('theme','')}`",
        f"- priority: `{c.get('priority','')}`", "",
        "## Contexto", (c.get("context") or "").strip(), "",
        "## Objetivo da decisão", (c.get("decision_goal") or "").strip(), "",
        "## Inputs visuais",
        f"- Imagem principal: `{vi.get('main') or '(sem imagem — decisão de direção)'}`",
    ]
    for i, a in enumerate(vi.get("aux") or [], 1):
        lines.append(f"  {i}. `{a}`")
    if vi.get("compare"):
        for k in sorted(vi["compare"]):
            lines.append(f"- Versão {k}: `{vi['compare'][k]}`")
    lines += ["", "## Restrições congeladas (NÃO pode mudar)"]
    lines += [f"- {x}" for x in (c.get("frozen_constraints") or [])] or ["- (declarar a geometria congelada)"]
    lines += ["", "## O que pode mudar"]
    lines += [f"- {x}" for x in (c.get("mutable") or [])] or ["- (declarar o espaço de decisão)"]
    lines += ["", "## Hipótese do Arquiteto", (c.get("architect_hypothesis") or "").strip(),
              "", "## Dúvidas específicas"]
    for i, q in enumerate(c.get("questions") or [], 1):
        lines.append(f"{i}. {q.get('id','')}: {q.get('text','')}")
    lines += ["", "## Formato obrigatório da resposta",
              f"Responder usando **`{c.get('answer_format', ANSWER_FORMAT)}`**. Obrigatório: VEREDITO "
              "PASS/WARN/FAIL · resposta para cada dúvida · correção prioritária nº1 · regras novas pro "
              "Felipe Style DNA · anti-patterns · próxima microtarefa executável.", ""]
    return "\n".join(lines)
