"""Monta o `SolverProblem` de um comodo da planta (SOMENTE LEITURA, FP-054 F2A).

Le as caixas do furnish, as interfaces semanticas (F1C) e a politica do especialista do comodo; nao altera nada. Objetos
movimentaveis = pecas registradas em `OBJECT_TYPES`; obstaculos fixos = todo o resto que bloqueia (regra do circulation_gate).
"""
from __future__ import annotations

from importlib import import_module

from shapely.ops import unary_union

from core.frames import RoomFrame
from core.functional_constraints import OBJECT_TYPES
from tools.rooms.shared.spatial_solver.contracts import Portal, SolverObject, SolverProblem

POLICY_MODULE = {"BATHROOM": "tools.rooms.bathroom.solver_policy", "KITCHEN": "tools.rooms.kitchen.solver_policy"}


def room_policy(room_type: str):
    mod = POLICY_MODULE.get(room_type)
    return import_module(mod) if mod else None


def _ring(geom):
    g = geom if geom.geom_type == "Polygon" else max(geom.geoms, key=lambda x: x.area)
    return tuple((round(x, 4), round(y, 4)) for x, y in list(g.exterior.coords)[:-1])


def build_problem(con: dict, boxes: list[dict], room_id: str, room_type: str, interfaces: dict) -> SolverProblem:
    from tools.validation import circulation_gate as cg
    from tools.validation.functional_clearance import M2IN, _room_context
    cell, portals, _dropped, room_boxes = _room_context(con, boxes, room_id)
    policy = room_policy(room_type)
    modules = {m: t for t, spec in OBJECT_TYPES.items() for rt, m in spec["modules"] if rt == room_type}
    objects = []
    for module, otype in sorted(modules.items()):
        parts = [b for b in room_boxes if b.get("module") == module and (b.get("z0_in") or 0) / M2IN < 1.2]
        if not parts or policy is None or otype not in policy.ANCHOR_AND_DOF:
            continue
        fp = unary_union([cg._footprint(b) for b in parts]).intersection(cell)
        anchor, dof = policy.ANCHOR_AND_DOF[otype]
        iface = interfaces.get((room_id, module))
        objects.append(SolverObject(f"{room_id}:{module}", room_id, module, otype, _ring(fp),
                                    (iface,) if iface is not None else (), anchor, dof,
                                    provenance=f"furnish planta_74 + {getattr(policy, 'POLICY_VERSION', '?')}"))
    fixed = [g for b, g in cg._blockers(room_boxes) if b.get("module") not in modules]
    x0, y0, _x1, _y1 = cell.bounds
    return SolverProblem(room_id=room_id, room_type=room_type, frame=RoomFrame(room_id, (round(x0, 4), round(y0, 4))),
                         room_polygon_in=_ring(cell),
                         portals=tuple(Portal(f"{room_id}:p{i}", (round(p.x, 4), round(p.y, 4))) for i, p in enumerate(portals)),
                         objects=tuple(objects), fixed_obstacles_in=tuple(_ring(f) for f in fixed if not f.is_empty),
                         policy_version=getattr(policy, "POLICY_VERSION", ""))
