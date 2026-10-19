"""Registro de providers de cômodos; nenhuma dependência circular com os brains.

O executor permanece tools.furnish_apartment. Este módulo somente monta o
dispatch a partir de funções explicitamente injetadas, sem executar SketchUp.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping

from tools.room_type import BATHROOM, BEDROOM, KITCHEN, LIVING, SERVICE

SUPPORTED_BRAINS = (BEDROOM, KITCHEN, LIVING, BATHROOM, SERVICE)


def build_brain_registry(
    *,
    bedroom: Callable,
    kitchen: Callable,
    living: Callable,
    bathroom: Callable,
    service: Callable,
) -> dict[str, Callable]:
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


def get_brain(registry: Mapping[str, Callable], room_type: str) -> Callable | None:
    """UNKNOWN e categorias sem brain mantêm o comportamento skip(sem brain)."""
    return registry.get(room_type)
