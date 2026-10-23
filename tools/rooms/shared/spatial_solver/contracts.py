"""Contratos do solver espacial compartilhado (FP-054 F2A). Generico: nada aqui sabe o que e banheiro ou cozinha.

Unidade: polegadas do plano (`unit="in"`) para geometria; metros (`*_m`) para graus de liberdade e limiares. Conversao so por
`core.units`. Interfaces funcionais: `core.functional_constraints.FunctionalInterface` (F1C) — obrigatorias e SEMANTICAS;
interface heuristica ou ausente => problema invalido (o solver nunca adivinha face, porta ou largura de entrada).

Estados do solver: FEASIBLE (ha alternativa sem violacao hard, demonstrada), INFEASIBLE (todas as alternativas do espaco
DECLARADO de graus de liberdade, na discretizacao declarada, violam hard), UNKNOWN (limite de exploracao atingido sem prova),
INVALID_INPUT (entrada falha no contrato — veja `issues`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely.geometry import LineString, Polygon

from core.frames import RoomFrame
from core.functional_constraints import OBJECT_TYPES, FunctionalInterface

SOLVER_STATUSES = ("FEASIBLE", "INFEASIBLE", "UNKNOWN", "INVALID_INPUT")
ANCHORS = ("WALL_BACKED", "HYDRAULIC_PDF", "CORNER", "FREE")
ALGORITHM_VERSION = "fp054-f2.v1"
INSIDE_ROOM_MIN_FRACTION = 0.98      # pegada pode passar 2% da celula (revestimento/arredondamento); acima disso e invalida
INTERFACE_ON_FOOTPRINT_TOL_IN = 1.0


@dataclass(frozen=True)
class SolverIssue:
    code: str
    field: str
    detail: str
    severity: str = "ERROR"

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass(frozen=True)
class DegreesOfFreedom:
    """O que o especialista do comodo PERMITE mexer. Discretizacao explicita (passo) — e o espaco que o solver enumera."""
    slide_along_wall_m: tuple[float, float] = (0.0, 0.0)    # deslocamento ao longo da parede de apoio (min, max)
    step_m: float = 0.02
    allow_mirror_entry: bool = False                         # box: trocar o lado da frente (porta) dentro do mesmo volume
    provenance: str = "PROJECT_POLICY"
    source: str = ""

    def errors(self) -> list[str]:
        lo, hi = self.slide_along_wall_m
        out = []
        if not (math.isfinite(lo) and math.isfinite(hi)) or lo > hi:
            out.append("intervalo de deslizamento invalido")
        if not self.step_m > 0:
            out.append("passo precisa ser positivo")
        if not self.source:
            out.append("grau de liberdade sem fonte/decisao")
        return out

    def slide_values(self) -> list[float]:
        """Valores enumerados (m), ordenados; inclui 0 (posicao atual) quando esta no intervalo."""
        lo, hi = self.slide_along_wall_m
        n = int(round((hi - lo) / self.step_m))
        vals = {round(lo + i * self.step_m, 6) for i in range(n + 1)}
        if lo <= 0 <= hi:
            vals.add(0.0)
        return sorted(vals)


@dataclass(frozen=True)
class SolverObject:
    object_id: str
    room_id: str
    module: str
    object_type: str
    footprint_in: tuple[tuple[float, float], ...]
    interfaces: tuple[FunctionalInterface, ...]
    anchor: str
    dof: DegreesOfFreedom
    unit: str = "in"
    provenance: str = ""


@dataclass(frozen=True)
class Portal:
    portal_id: str
    point_in: tuple[float, float]


@dataclass(frozen=True)
class SolverProblem:
    room_id: str
    room_type: str
    frame: RoomFrame
    room_polygon_in: tuple[tuple[float, float], ...]
    portals: tuple[Portal, ...]
    objects: tuple[SolverObject, ...]
    fixed_obstacles_in: tuple[tuple[tuple[float, float], ...], ...] = ()
    unit: str = "in"
    policy_version: str = ""
    algorithm_version: str = ALGORITHM_VERSION
    seed: int = 0                                            # o algoritmo e deterministico; registrado para reproducao
    notes: tuple[str, ...] = field(default_factory=tuple)


def _poly(coords) -> Polygon | None:
    try:
        p = Polygon(coords)
    except (ValueError, TypeError):
        return None
    return p if p.is_valid and not p.is_empty and p.area > 0 else None


def validate_problem(p: SolverProblem) -> list[SolverIssue]:
    """Contrato de entrada. Lista vazia = entrada aceita. Nunca corrige nem completa nada."""
    issues: list[SolverIssue] = []
    if p.unit != "in":
        issues.append(SolverIssue("UNIT_INVALID", "unit", f"esperado 'in', veio {p.unit!r}"))
    room = _poly(p.room_polygon_in)
    if room is None:
        issues.append(SolverIssue("ROOM_GEOMETRY_INVALID", "room_polygon_in", "poligono do comodo invalido, vazio ou degenerado"))
    if not p.portals:
        issues.append(SolverIssue("NO_PORTAL", "portals", "comodo sem portal: alcance nao pode ser provado"))
    ids = [o.object_id for o in p.objects]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        issues.append(SolverIssue("OBJECT_ID_DUPLICATED", "objects", dup))
    for o in p.objects:
        f = f"objects[{o.object_id}]"
        if o.unit != "in":
            issues.append(SolverIssue("UNIT_INVALID", f + ".unit", o.unit))
        if o.object_type not in OBJECT_TYPES:
            issues.append(SolverIssue("OBJECT_TYPE_UNKNOWN", f + ".object_type", o.object_type))
            continue
        if o.anchor not in ANCHORS:
            issues.append(SolverIssue("ANCHOR_UNKNOWN", f + ".anchor", o.anchor))
        for e in o.dof.errors():
            issues.append(SolverIssue("DOF_INVALID", f + ".dof", e))
        fp = _poly(o.footprint_in)
        if fp is None:
            issues.append(SolverIssue("FOOTPRINT_INVALID", f + ".footprint_in", "pegada invalida ou degenerada"))
            continue
        if room is not None and fp.intersection(room).area < INSIDE_ROOM_MIN_FRACTION * fp.area:
            issues.append(SolverIssue("OUTSIDE_ROOM", f + ".footprint_in",
                                      f"{fp.intersection(room).area / fp.area:.1%} dentro do comodo"))
        need = OBJECT_TYPES[o.object_type]["interface"]
        found = [i for i in o.interfaces if i.interface == need]
        if not found:
            issues.append(SolverIssue("MISSING_SEMANTIC_INTERFACE", f + ".interfaces", f"falta {need}"))
            continue
        for i in found:
            if not i.semantic:
                issues.append(SolverIssue("HEURISTIC_INTERFACE_REJECTED", f + ".interfaces",
                                          f"{need} com base {i.basis}: solver exige semantica explicita"))
            elif fp.boundary.distance(LineString(i.segment_in).interpolate(0.5, normalized=True)) > INTERFACE_ON_FOOTPRINT_TOL_IN:
                issues.append(SolverIssue("INTERFACE_GEOMETRY_MISMATCH", f + ".interfaces", "interface fora da borda da peca"))
    return issues
