"""room_registry — tradução entre o room_id canônico usado pelo pipeline
(r000..r007, vindo de consensus.json) e um vocabulário amigável de
room_type/alias, para permitir falar de "kitchen"/"suite_01" sem mudar o
que o pipeline já consome.

Não substitui o r0NN em lugar nenhum do código existente — é só um
dicionário de tradução por cima. bedroom_layout.py/bathroom_layout.py/
kitchen_layout.py continuam recebendo r0NN cru.

Fonte da verdade dos room_id + name: fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json::rooms[].
room_type e aliases são override manual (o consensus não tem campo de tipo).
"""
from __future__ import annotations

from dataclasses import dataclass, field

PROJECT_ID = "planta_74"

ROOM_TYPES = frozenset({
    "bedroom", "bathroom", "kitchen", "living_room", "service", "laundry",
})


@dataclass(frozen=True)
class RoomInfo:
    room_id: str
    display_name: str
    room_type: str
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.room_type not in ROOM_TYPES:
            raise ValueError(f"room_type inválido para {self.room_id}: {self.room_type!r}")


# Espelha fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json::rooms[]
# (id, name) confirmado por leitura direta do fixture nesta sessão. room_type/aliases
# são a única parte inferida manualmente (o consensus não carrega tipo semântico).
_PLANTA_74_ROOMS: tuple[RoomInfo, ...] = (
    RoomInfo("r000", "SUITE 01", "bedroom", ("suite_01", "suite1", "bedroom_01")),
    RoomInfo("r001", "A.S. | TERRACO SOCIAL | TERRACO TECNICO", "service", ("area_servico", "terraco")),
    RoomInfo("r002", "SALA DE JANTAR | SALA DE ESTAR", "living_room", ("living_room", "sala")),
    RoomInfo("r003", "SUITE 02", "bedroom", ("suite_02", "suite2", "bedroom_02")),
    RoomInfo("r004", "COZINHA", "kitchen", ("kitchen",)),
    RoomInfo("r005", "BANHO 01", "bathroom", ("bathroom_01", "banho_01", "bathroom")),
    RoomInfo("r006", "BANHO 02", "bathroom", ("bathroom_02", "banho_02")),
    RoomInfo("r007", "LAVABO", "bathroom", ("lavabo", "powder_room")),
)

_REGISTRY: dict[str, dict[str, RoomInfo]] = {
    PROJECT_ID: {room.room_id: room for room in _PLANTA_74_ROOMS},
}

_ALIAS_INDEX: dict[str, dict[str, str]] = {
    project_id: {
        alias: room.room_id
        for room in rooms.values()
        for alias in (*room.aliases, room.room_id)
    }
    for project_id, rooms in _REGISTRY.items()
}


def rooms_for_project(project_id: str = PROJECT_ID) -> tuple[RoomInfo, ...]:
    if project_id not in _REGISTRY:
        raise KeyError(f"projeto desconhecido no room_registry: {project_id!r}")
    return tuple(_REGISTRY[project_id].values())


def resolve_room_id(alias_or_room_id: str, *, project_id: str = PROJECT_ID) -> str:
    """Aceita 'kitchen', 'suite_01' ou 'r004' e devolve sempre o r0NN canônico."""
    if project_id not in _ALIAS_INDEX:
        raise KeyError(f"projeto desconhecido no room_registry: {project_id!r}")
    key = alias_or_room_id.strip().lower()
    try:
        return _ALIAS_INDEX[project_id][key]
    except KeyError:
        raise KeyError(
            f"alias/room_id não reconhecido para {project_id!r}: {alias_or_room_id!r}"
        ) from None


def room_info(alias_or_room_id: str, *, project_id: str = PROJECT_ID) -> RoomInfo:
    room_id = resolve_room_id(alias_or_room_id, project_id=project_id)
    return _REGISTRY[project_id][room_id]
