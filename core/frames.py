"""frames.py — sistema de coordenadas do comodo x sistema global da planta (FP-054 F2A).

Global = coordenadas do plano em POLEGADAS (as das caixas do pipeline; y cresce como no consensus). Local do comodo = origem num
ponto escolhido do comodo, eixo x local girado `rotation_rad` em relacao ao x global. Transformacao rigida:

    p_global = origin + R(rotation) * p_local         p_local = R(-rotation) * (p_global - origin)

Rigida (preserva distancias e areas); o solver mede no local e devolve no global. Testado por ida-e-volta e invariancias.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RoomFrame:
    room_id: str
    origin_in: tuple[float, float]
    rotation_rad: float = 0.0
    unit: str = "in"

    def __post_init__(self) -> None:
        if self.unit != "in":
            raise ValueError("RoomFrame trabalha em polegadas (unidade das caixas do pipeline)")
        if not all(math.isfinite(v) for v in (*self.origin_in, self.rotation_rad)):
            raise ValueError("frame com valor nao finito")

    def to_plant(self, p):
        c, s = math.cos(self.rotation_rad), math.sin(self.rotation_rad)
        return (self.origin_in[0] + c * p[0] - s * p[1], self.origin_in[1] + s * p[0] + c * p[1])

    def to_local(self, p):
        c, s = math.cos(-self.rotation_rad), math.sin(-self.rotation_rad)
        x, y = p[0] - self.origin_in[0], p[1] - self.origin_in[1]
        return (c * x - s * y, s * x + c * y)

    def vector_to_plant(self, v):
        c, s = math.cos(self.rotation_rad), math.sin(self.rotation_rad)
        return (c * v[0] - s * v[1], s * v[0] + c * v[1])

    def polygon_to_plant(self, pts):
        return [self.to_plant(p) for p in pts]

    def polygon_to_local(self, pts):
        return [self.to_local(p) for p in pts]
