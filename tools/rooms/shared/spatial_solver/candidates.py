"""Geracao de alternativas (FP-054 F2C). So o que o especialista do comodo declarou em `DegreesOfFreedom`.

Movimentos (transformacoes rigidas aplicadas a TODAS as pecas do modulo e a sua interface):
  - `slide_m`: translacao ao longo da parede de apoio (direcao do segmento da interface), em metros;
  - `mirrored`: reflexao do volume pela linha central paralela a frente (box: a frente/porta passa para o lado oposto, dentro
    do mesmo volume; a normal da interface inverte).
Espaco de busca = produto dos valores declarados por objeto, enumerado em ordem DETERMINISTICA: menos objetos movidos primeiro,
depois menor deslocamento total, depois o identificador. Exato SOBRE a discretizacao declarada — nao prova nada fora dela.
"""
from __future__ import annotations

import copy
import itertools
import math
from dataclasses import dataclass

from shapely.ops import unary_union

from core.functional_constraints import FunctionalInterface
from tools.rooms.shared.spatial_solver.contracts import SolverObject, SolverProblem
from tools.rooms.shared.spatial_solver.geometry import M2IN


@dataclass(frozen=True)
class Move:
    object_id: str
    slide_m: float = 0.0
    mirrored: bool = False
    rotation_deg: int = 0

    @property
    def is_identity(self) -> bool:
        return abs(self.slide_m) < 1e-12 and not self.mirrored and self.rotation_deg % 360 == 0


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    moves: tuple[Move, ...]

    @property
    def moved(self) -> tuple[Move, ...]:
        return tuple(m for m in self.moves if not m.is_identity)

    @property
    def displacement_m(self) -> float:
        return round(sum(abs(m.slide_m) for m in self.moves), 6)

    def to_dict(self) -> dict:
        return {"candidate_id": self.candidate_id, "moves": [m.__dict__ for m in self.moved],
                "displacement_m": self.displacement_m, "mirrors": sum(m.mirrored for m in self.moves)}


def _options(o: SolverObject) -> list[tuple[float, bool, int]]:
    mirrors = (False, True) if o.dof.allow_mirror_entry else (False,)
    return [(s, mi, r) for s in o.dof.slide_values() for mi in mirrors for r in sorted(set(o.dof.rotations_deg))]


def enumerate_candidates(problem: SolverProblem) -> list[Candidate]:
    objs = sorted(problem.objects, key=lambda o: o.object_id)
    combos = itertools.product(*[_options(o) for o in objs]) if objs else [()]
    out = []
    for combo in combos:
        moves = tuple(Move(o.object_id, s, mi, r) for o, (s, mi, r) in zip(objs, combo))
        cid = "|".join(f"{m.object_id}:{m.slide_m:+.2f}{'M' if m.mirrored else ''}{f'R{m.rotation_deg}' if m.rotation_deg else ''}"
                       for m in moves if not m.is_identity) or "ORIGINAL"
        out.append(Candidate(cid, moves))
    out.sort(key=lambda c: (len(c.moved), c.displacement_m, sum(m.mirrored for m in c.moves),
                            sum(m.rotation_deg != 0 for m in c.moves), c.candidate_id))
    return out


def _unit(seg):
    (x0, y0), (x1, y1) = seg
    L = math.hypot(x1 - x0, y1 - y0) or 1.0
    return (x1 - x0) / L, (y1 - y0) / L


def _point_map(move: Move, iface: FunctionalInterface, fp_centroid):
    tx, ty = _unit(iface.segment_in)
    dx, dy = tx * move.slide_m * M2IN, ty * move.slide_m * M2IN
    nx, ny = iface.normal
    cx, cy = fp_centroid

    rad = math.radians(move.rotation_deg)
    cr, sr = round(math.cos(rad), 12), round(math.sin(rad), 12)

    def f(p):
        x, y = p
        if move.rotation_deg % 360:               # giro rigido em torno do centroide da pegada
            vx, vy = x - cx, y - cy
            x, y = cx + cr * vx - sr * vy, cy + sr * vx + cr * vy
        if move.mirrored:                       # reflexao pela reta (centroide, direcao t): componente normal troca de sinal
            vx, vy = x - cx, y - cy
            dn = vx * nx + vy * ny
            x, y = x - 2 * dn * nx, y - 2 * dn * ny
        return (x + dx, y + dy)
    return f


def _transform_box(box: dict, f) -> dict:
    if box.get("profile_world") is not None:     # perfil 3D (sofa) nao e transformado aqui: recusar, nunca mover pela metade
        raise ValueError(f"peca com profile_world nao suportada pelo solver: {box.get('module')}/{box.get('kind')}")
    b = copy.deepcopy(box)
    if b.get("corners"):
        b["corners"] = [[round(c, 4) for c in f(tuple(p))] for p in b["corners"]]
        xs, ys = [p[0] for p in b["corners"]], [p[1] for p in b["corners"]]
        b["x0"], b["x1"], b["y0"], b["y1"] = min(xs), max(xs), min(ys), max(ys)
    return b


def apply_candidate(problem: SolverProblem, boxes: list[dict], interfaces: dict, cand: Candidate,
                    room_name: str) -> tuple[list[dict], dict]:
    """(caixas, interfaces) com o candidato aplicado. Nao muta as entradas. So pecas do comodo `room_name` sao movidas."""
    from tools.validation.circulation_gate import _footprint
    by_id = {o.object_id: o for o in problem.objects}
    new_boxes, new_ifaces = list(boxes), dict(interfaces)
    for mv in cand.moved:
        o = by_id[mv.object_id]
        iface = interfaces[(o.room_id, o.module)]
        parts_idx = [i for i, b in enumerate(boxes) if b.get("module") == o.module and b.get("room") == room_name]
        cen = unary_union([_footprint(boxes[i]) for i in parts_idx if boxes[i].get("corners")]).centroid
        f = _point_map(mv, iface, (cen.x, cen.y))
        for i in parts_idx:
            new_boxes[i] = _transform_box(boxes[i], f)
        seg = tuple(tuple(round(c, 4) for c in f(p)) for p in iface.segment_in)
        rad = math.radians(mv.rotation_deg)
        nx, ny = iface.normal
        nx, ny = (round(math.cos(rad) * nx - math.sin(rad) * ny, 12), round(math.sin(rad) * nx + math.cos(rad) * ny, 12))
        normal = (-nx, -ny) if mv.mirrored else (nx, ny)
        new_ifaces[(o.room_id, o.module)] = FunctionalInterface(
            iface.room_id, iface.module, iface.object_type, iface.interface, seg, normal, iface.basis,
            iface.source + f" + candidato {cand.candidate_id}", iface.note)
    return new_boxes, new_ifaces
