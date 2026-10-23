"""units.py — conversao de comprimento EXPLICITA e centralizada (FP-054 F2A).

Regra: nenhuma conversao implicita. Todo valor que cruza fronteira do solver carrega a unidade; `to_unit` converte entre
m/cm/mm/in. Pontos de PDF (`pt`) dependem da escala DA PLANTA, entao exigem `pt_to_m` explicito (nunca o global de
`core.scale`): `pt_to(value, unit, pt_to_m=...)`. Tolerancias numericas do solver ficam aqui, documentadas.
"""
from __future__ import annotations

import math

METERS_PER: dict[str, float] = {"m": 1.0, "cm": 0.01, "mm": 0.001, "in": 0.0254}

# Tolerancias (unidade declarada no nome): comparacoes geometricas do solver usam estes valores, nada de epsilons soltos.
GEOM_TOL_IN = 1e-6             # igualdade/contencao de coordenadas em polegadas (escala do plano ~1e3 in)
MEASURE_RESOLUTION_M = 0.005   # resolucao das bissecoes de folga (metade de 1 cm)
REACH_RESOLUTION_M = 0.01      # resolucao da largura de passagem


def _check(unit: str) -> None:
    if unit not in METERS_PER:
        raise ValueError(f"unidade desconhecida: {unit!r} (use {sorted(METERS_PER)}; pt exige pt_to_m explicito)")


def to_unit(value: float, from_unit: str, to_unit_: str) -> float:
    _check(from_unit)
    _check(to_unit_)
    if not math.isfinite(value):
        raise ValueError("valor nao finito")
    return value * METERS_PER[from_unit] / METERS_PER[to_unit_]


def pt_to(value: float, to_unit_: str, *, pt_to_m: float) -> float:
    if not (pt_to_m > 0 and math.isfinite(pt_to_m)):
        raise ValueError("pt_to_m precisa ser positivo e finito (escala da planta)")
    return to_unit(value * pt_to_m, "m", to_unit_)


def to_pt(value: float, from_unit: str, *, pt_to_m: float) -> float:
    return to_unit(value, from_unit, "m") / pt_to_m if pt_to_m > 0 else math.nan
