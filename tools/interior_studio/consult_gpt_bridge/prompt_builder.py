"""prompt_builder.py — monta o ARCHITECT_QUESTION_CONTRACT a partir do estado do Arquiteto.

Lógica PURA (sem IO). O clock entra só por `now` injetável (handler passa real; teste passa fixo).
"""
from __future__ import annotations

import time

from tools.interior_studio.consult_gpt_bridge import contracts as C

_FROZEN_KITCHEN = [
    "Layout linear da cozinha congelado.",
    "Posição da pia fixa pelo PDF.",
    "Geladeira fixa na lateral.",
    "Circulação mínima não pode piorar.",
    "Não alterar paredes, portas ou janelas.",
]
_MUTABLE_KITCHEN = [
    "Pele / material.", "Intensidade da madeira.", "Tipo de pedra.", "Metais.",
    "Iluminação.", "Decoração leve.", "Cor de eletros.",
]


def _now_iso(now: str | None) -> str:
    return now or time.strftime("%Y-%m-%dT%H:%M:%S")


def build_question(*, mode: str, room: str, phase: str, theme: str, context: str, decision_goal: str,
                   architect_hypothesis: str, frozen_constraints=None, mutable=None, questions=None,
                   visual_inputs=None, priority: str = "medium", project: str = "planta_74",
                   references=None, question_id: str | None = None, now: str | None = None) -> dict:
    """Constrói + valida um question_contract. Levanta ValueError se inválido."""
    created = _now_iso(now)
    qid = question_id or f"{room}_{phase}_{created.replace(':', '').replace('-', '')[-6:]}"
    contract = {
        "question_id": qid,
        "created_at": created,
        "agent": "architect",
        "mode": mode,
        "project": project,
        "room": room,
        "phase": phase,
        "theme": theme,
        "priority": priority,
        "context": (context or "").strip(),
        "decision_goal": (decision_goal or "").strip(),
        "visual_inputs": visual_inputs or {"main": None, "aux": [], "compare": {}},
        "frozen_constraints": list(frozen_constraints) if frozen_constraints is not None
        else (_FROZEN_KITCHEN if room == "kitchen" else []),
        "mutable": list(mutable) if mutable is not None
        else (_MUTABLE_KITCHEN if room == "kitchen" else []),
        "architect_hypothesis": (architect_hypothesis or "").strip(),
        "references": list(references) if references else [],
        "questions": questions or [dict(q) for q in C.DEFAULT_QUESTIONS],
        "answer_format": C.ANSWER_FORMAT,
    }
    errs = C.validate_question(contract)
    if errs:
        raise ValueError("question_contract inválido: " + "; ".join(errs))
    return contract


def build_judge(*, render: str, theme: str, room: str = "kitchen", context: str | None = None,
                architect_hypothesis: str | None = None, now: str | None = None,
                question_id: str | None = None) -> dict:
    """Atalho MODE=JUDGE para validar um render existente (caso canônico do brief: kitchen_skin_001)."""
    return build_question(
        mode="JUDGE", room=room, phase="skin", theme=theme, priority="high",
        question_id=question_id,
        context=context or (f"Validando a pele da {room} compacta do apê 74m² do Felipe. Geometria "
                            "congelada. Avaliar se está alinhada ao gosto dark premium do Felipe."),
        decision_goal="Decidir se a pele atual pode ir pra render final ou precisa de ajuste antes do próximo ciclo.",
        architect_hypothesis=architect_hypothesis or (
            "Armários preto fosco, madeira quente, pedra escura com veio dourado sutil, metais bronze "
            "discretos e LED 2700K pra uma cozinha industrial boutique premium."),
        visual_inputs={"main": render, "aux": [], "compare": {}},
        now=now)
