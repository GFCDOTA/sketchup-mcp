"""Registro de providers de cômodos; nenhuma dependência circular com os brains.

O executor permanece tools.furnish_apartment. Este módulo somente monta o
dispatch a partir de funções explicitamente injetadas, sem executar SketchUp.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from tools.room_type import BATHROOM, BEDROOM, KITCHEN, LIVING, SERVICE

SUPPORTED_BRAINS = (BEDROOM, KITCHEN, LIVING, BATHROOM, SERVICE)


class RoomBrain(Protocol):
    """Porta do brain de um comodo: `(consensus, room_id) -> (caixas, resultado)`.

    `caixas`: lista de dicts com `kind`/`corners`/... (o executor acrescenta `room` e `module`); `resultado`: dict com `result`
    e, opcionalmente, `downgrades`, `dropped` e `functional_interfaces` (nunca descartados em silencio por quem consome).
    Cinco implementacoes reais (quarto, cozinha, sala, banheiro, servico) justificam a porta; o tipo nao muda comportamento."""

    def __call__(self, con: dict, room_id: str) -> tuple[list[dict], dict]: ...


def build_brain_registry(
    *,
    bedroom: RoomBrain,
    kitchen: RoomBrain,
    living: RoomBrain,
    bathroom: RoomBrain,
    service: RoomBrain,
) -> dict[str, RoomBrain]:
    """Mesmo contrato legado BRAINS; nenhuma importação de builders ao chamar."""
    result = {
        BEDROOM: bedroom,
        KITCHEN: kitchen,
        LIVING: living,
        BATHROOM: bathroom,
        SERVICE: service,
    }
    if set(result) != set(SUPPORTED_BRAINS):
        raise ValueError("ROOM_DISPATCH_INCOMPLETE")
    if any(not callable(provider) for provider in result.values()):
        raise TypeError("ROOM_BRAIN_MUST_BE_CALLABLE")
    return result


def get_brain(registry: Mapping[str, RoomBrain], room_type: str) -> RoomBrain | None:
    """UNKNOWN e categorias sem brain mantêm o comportamento skip(sem brain)."""
    return registry.get(room_type)
