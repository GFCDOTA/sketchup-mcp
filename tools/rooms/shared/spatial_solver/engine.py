"""Motor de restricoes RIGIDAS do solver (FP-054 F2B). Avalia um layout (caixas + interfaces semanticas) de um comodo.

Fonte unica das medidas: `tools.validation.functional_clearance` (modo SOLVER: sem interface semantica => entrada invalida) e a
geometria compartilhada. Acrescenta as verificacoes que nao sao "folga": colisao entre pecas, peca fora do comodo, invasao de
parede e de giro de porta (`room_collisions`, o mesmo da regressao FP-047) e circulacao do comodo (`circulation_gate`).
Cada violacao traz o CULPADO (parede, outra peca, o proprio modelo de porta) e a medida — evidencia, nao opiniao.

Rigido = qualquer INVALID funcional, entrada invalida, colisao, fora do comodo, parede, giro de porta, corredor do comodo
reprovado. Preferencias (margens) ficam em `metrics` e nunca compensam uma violacao rigida.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from shapely.geometry import LineString
from shapely.ops import unary_union

from core.functional_constraints import FUNCTIONAL_CONSTRAINTS, OBJECT_TYPES
from tools.rooms.shared.spatial_solver.geometry import M2IN, _front_rect

COLLISION_TOL_IN2 = 4.0          # ~26 cm2: abaixo disso e encosto/arredondamento de pecas vizinhas


@dataclass(frozen=True)
class Violation:
    code: str
    object_id: str
    detail: str
    measured: float | None = None
    threshold: float | None = None
    unit: str | None = None
    culprit: str | None = None
    constraint: str | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class LayoutEvaluation:
    room_id: str
    hard_violations: list[Violation]
    rows: list[dict]
    metrics: dict
    witnesses: dict = field(default_factory=dict)

    @property
    def feasible(self) -> bool:
        return not self.hard_violations

    def to_dict(self) -> dict:
        return {"room_id": self.room_id, "feasible": self.feasible,
                "hard_violations": [v.to_dict() for v in self.hard_violations], "metrics": self.metrics, "rows": self.rows}


def _registered_modules(room_type: str) -> dict[str, str]:
    return {m: t for t, spec in OBJECT_TYPES.items() for rt, m in spec["modules"] if rt == room_type}


def _culprit_front(row, cell, room_boxes, module) -> str | None:
    """Quem limita a profundidade livre: estende o retangulo medido em 2 cm e ve o que ele toca (parede ou peca)."""
    from tools.validation import circulation_gate as cg
    w = row.get("witness") or {}
    seg = w.get("usable_segment") or w.get("segment")
    if not seg:
        return None
    n = w["normal"]
    d = (row["measured"] or 0.0) + 0.02
    probe = _front_rect(LineString(seg), n, d * M2IN)
    if probe.difference(cell.buffer(1e-6)).area > 1e-6:
        return "WALL"
    best, area = None, 0.0
    for b, g in cg._blockers([b for b in room_boxes if b.get("module") != module]):
        a = g.buffer(0.5).intersection(probe).area
        if a > area:
            best, area = ("WALL" if b.get("geometry_intent") == "STRUCTURAL" else str(b.get("module"))), a
    return best


def _culprit_entry(row, cell, room_boxes, module) -> str:
    """Quem corta o vao declarado: sonda a linha de entrada 1 in a frente contra parede e pecas."""
    from tools.validation import circulation_gate as cg
    w = row.get("witness") or {}
    n = w["normal"]
    probe = LineString([(x + n[0] * 1.0, y + n[1] * 1.0) for x, y in w["segment"]])
    if probe.difference(cell.buffer(1e-6)).length > 1e-6:
        return "WALL"
    best, length = "OBSTRUCTION", 0.0
    for b, g in cg._blockers([b for b in room_boxes if b.get("module") != module]):
        L = probe.intersection(g.buffer(0.5)).length
        if L > length:
            best, length = ("WALL" if b.get("geometry_intent") == "STRUCTURAL" else str(b.get("module"))), L
    return best


def evaluate_layout(con, boxes, room_id, room_type, interfaces, room_name=None) -> LayoutEvaluation:
    from tools.validation import circulation_gate as cg
    from tools.validation import functional_clearance as fc
    from tools.validation import room_collisions
    rows = [e.to_dict(FUNCTIONAL_CONSTRAINTS.get(e.constraint_id))
            for e in fc.evaluate_room(con, boxes, room_id, room_type, room_name, interfaces, "SOLVER")]
    cell, _portals, _dropped, room_boxes = fc._room_context(con, boxes, room_id)
    modules = _registered_modules(room_type)
    out: list[Violation] = []
    margins = []
    for r in rows:
        oid = f"{room_id}:{r['object_id']}"
        ref = (r.get("reference_minimum") or {}).get("value")
        if r["verdict"] == "BLOCKED_MISSING_INPUT":
            out.append(Violation("INPUT_" + r["reason_code"], oid, ", ".join(r["missing_input"]), constraint=r["constraint"]))
        elif r["verdict"] == "INVALID":
            culprit, detail = None, r["reason_code"]
            if r["constraint"].endswith("entry_width"):
                seg = (r.get("witness") or {}).get("segment")
                nominal = LineString(seg).length / M2IN if seg else None
                culprit = "DECLARED_ENTRY" if nominal is not None and r["measured"] >= nominal - 0.01 else \
                    _culprit_entry(r, cell, room_boxes, r["object_id"])
                detail = f"vao livre {r['measured']:.3f} m de {nominal:.3f} m declarados" if nominal else detail
            elif r["constraint"].endswith("front_clearance"):
                culprit = _culprit_front(r, cell, room_boxes, r["object_id"])
            elif r["constraint"].endswith("reach_path"):
                g = (r.get("witness") or {}).get("bottleneck")
                culprit = ("INTERFACE_OBSTRUCTED" if r["reason_code"] == "INTERFACE_OBSTRUCTED" else
                           "PATH_DISCONNECTED" if r["measured"] == 0 else "BOTTLENECK")
                if g:
                    detail = f"{r['reason_code']}; gargalo em {g['point']}"
            out.append(Violation("FUNCTIONAL_" + r["constraint"].upper().replace(".", "_"), oid, detail, r["measured"], ref,
                                 "m", culprit, r["constraint"]))
        if r["verdict"] in ("INVALID", "VALID_BELOW_TARGET", "VALID", "PREFERRED") and ref is not None:
            margins.append(round(r["measured"] - ref, 4))
    # colisao: nucleo CANONICO de sobreposicao (Z, embutido/hospedado, limiares do furniture_overlap_gate); so pares com uma
    # peca registrada e so no nivel FAIL do gate. Fora do comodo: centro da pegada fora da celula (invasao parcial de parede
    # e do gate de parede abaixo).
    from tools.validation.circulation_gate import _footprint
    from tools.validation.furniture_overlap_gate import _module_geom, iter_overlap_pairs
    # limiar estrito para as pecas do solver: qualquer interpenetracao 3D acima de COLLISION_TOL_IN2 (o nivel FAIL do gate
    # deixava passar o vaso deslizado entrando no gabinete do Banho 02: 0,067 m2, 29% da menor pegada)
    strict = COLLISION_TOL_IN2 / (M2IN * M2IN)
    for a, b, inter, frac in iter_overlap_pairs(_module_geom(room_boxes), area_min_m2=strict, frac_min=0.0):
        if a in modules or b in modules:
            mine, other = (a, b) if a in modules else (b, a)
            out.append(Violation("COLLISION", f"{room_id}:{mine}", f"sobreposicao com {other} ({frac:.0%} da menor)",
                                 round(inter, 4), 0.0, "m2", other))
    for m in sorted(modules):
        parts = [b for b in room_boxes if b.get("module") == m and (b.get("z0_in") or 0) / M2IN < 1.2]
        if parts and not cell.contains(unary_union([_footprint(b) for b in parts]).centroid):
            out.append(Violation("OUTSIDE_ROOM", f"{room_id}:{m}", "centro da pegada fora do comodo", culprit="WALL"))
    # parede e giro de porta (mesmo nucleo da regressao FP-047), so para as pecas registradas
    import copy
    audit = room_collisions.audit(con, copy.deepcopy(room_boxes))
    for _room, data in sorted(audit.items()):
        for hit in data.get("wall_penetration", []):
            if hit["module"] in modules:
                out.append(Violation("WALL_PENETRATION", f"{room_id}:{hit['module']}", hit.get("label", ""),
                                     hit["area_cm2"], 0.0, "cm2", "WALL"))
        for hit in data.get("door_swing_hits", []):
            if hit["module"] in modules:
                out.append(Violation("DOOR_SWING_OBSTRUCTED", f"{room_id}:{hit['module']}", hit.get("label", ""),
                                     hit["area_cm2"], 0.0, "cm2", hit["door"]))
    # corredor do comodo (portas obrigatorias com passagem)
    g = cg.gate(con, boxes, room_id)
    corr = g["checks"]["corredor_principal"]
    if corr["result"] in ("FAIL", "BLOCKED_MISSING_INPUT"):
        out.append(Violation("ROOM_CIRCULATION_" + corr["result"], f"{room_id}:*", corr.get("reason_code", ""),
                             culprit="LAYOUT"))
    out.sort(key=lambda v: (v.object_id, v.code, v.constraint or ""))
    metrics = {"hard_violations": len(out), "min_margin_m": min(margins) if margins else None,
               "sum_margin_m": round(sum(margins), 4) if margins else None, "measured_rules": len(margins)}
    return LayoutEvaluation(room_id, out, rows, metrics)
