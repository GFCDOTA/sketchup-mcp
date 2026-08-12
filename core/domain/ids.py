"""ids — geração/validação de IDs compartilhados entre projeto, cômodo,
iteração e trace de retrieval. Funções puras, sem I/O e sem dependência de
wall-clock/random (iteration_id é sequencial explícito; trace_id usa
uuid4, que não é determinístico por natureza mas não quebra resume/replay
de nada nesta camada — é gerado uma vez por chamada real, não em script).
"""
from __future__ import annotations

import re
import uuid

from core.domain.room_registry import resolve_room_id

_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_ITERATION_ID_RE = re.compile(r"^(?P<project_id>[a-z][a-z0-9_]*)\.(?P<room_id>r\d{3})\.(?P<seq>\d{3})$")


def validate_project_id(project_id: str) -> str:
    if not _PROJECT_ID_RE.match(project_id):
        raise ValueError(f"project_id inválido: {project_id!r}")
    return project_id


def make_room_id(alias_or_room_id: str, *, project_id: str) -> str:
    """Resolve um alias/room_id cru para o r0NN canônico do projeto."""
    return resolve_room_id(alias_or_room_id, project_id=project_id)


def make_iteration_id(project_id: str, room_id: str, seq: int) -> str:
    """Formato estável e ordenável: '<project_id>.<r0NN>.<seq:03d>'."""
    validate_project_id(project_id)
    if not re.match(r"^r\d{3}$", room_id):
        raise ValueError(f"room_id deve ser canônico (r0NN) para compor iteration_id, recebeu: {room_id!r}")
    if seq < 0:
        raise ValueError(f"seq deve ser >= 0, recebeu: {seq}")
    return f"{project_id}.{room_id}.{seq:03d}"


def parse_iteration_id(iteration_id: str) -> dict[str, str | int]:
    m = _ITERATION_ID_RE.match(iteration_id)
    if not m:
        raise ValueError(f"iteration_id malformado: {iteration_id!r}")
    return {
        "project_id": m.group("project_id"),
        "room_id": m.group("room_id"),
        "seq": int(m.group("seq")),
    }


def make_trace_id() -> str:
    """trace_id de observabilidade — só identidade, não precisa ser reproduzível."""
    return uuid.uuid4().hex
