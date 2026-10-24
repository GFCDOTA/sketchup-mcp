"""Validacao sobre a GEOMETRIA CONSTRUIDA (FP-055 P4): construido x ambiente real, nao construido x pedido.

Entrada: o resultado do job `inspect_geometry.rb` (faces horizontais de cada grupo de topo, em metros, mundo do SketchUp).
Tudo que este modulo afirma vem do modelo reaberto:
  - piso do comodo  = uniao das faces de `Floor_Group_<rid>` (poligono efetivo; concavo e multipoligono preservados);
  - massa de parede = faces horizontais de `PlanShell_Group` acima do piso (topo das paredes, ja com os vaos recortados);
  - folha de porta  = `DoorLeaf_Group_<id>`;
  - pegada do movel = uniao das faces horizontais do grupo "<COMODO> · <modulo>" abaixo de 1,2 m.
Cheques por comodo planejado (cada um PASS / FAIL / BLOCKED — nunca PASS por falta de dado):
  CONTAINMENT  pegada dentro do POLIGONO do piso (nao do bounding box);
  WALL         pegada x massa de parede construida;
  DOOR_SWING   pegada x varredura de porta (consensus pelo contrato de referencial, conferido contra as paredes construidas);
  OBJECTS      pegada x pegada de outro modulo do comodo com sobreposicao em Z (embutidos/hospedados pelo nucleo canonico).
Acabamento de parede (`Pele`/`PeleTeto`) nao e movel: vai para FINISH, com a protusao medida (nunca escondida).
"""
from __future__ import annotations

from typing import Any

from shapely.geometry import Polygon
from shapely.ops import unary_union

FLOOR_LEVEL_M = 1.2
AREA_TOL_M2 = 0.0026          # 4 in2 — o mesmo limiar de interpenetracao do solver
EDGE_TOL_M = 0.01             # pegada pode encostar no contorno do piso com 1 cm de arredondamento
FINISH_MODULES = ("Pele", "PeleTeto")


def _poly(face) -> Polygon | None:
    try:
        p = Polygon(face["outer"], face.get("holes") or [])
        return p if p.is_valid and p.area > 1e-9 else p.buffer(0) if p.area > 1e-9 else None
    except Exception:  # noqa: BLE001 — face degenerada
        return None


def group_index(geom_result: dict) -> dict[str, dict]:
    return {g["name"]: g for g in geom_result.get("groups", [])}


def footprint(group: dict, *, zmax_m: float | None = FLOOR_LEVEL_M, zmin_m: float | None = None):
    polys = [_poly(f) for f in group.get("horizontal_faces", [])
             if (zmax_m is None or f["z"] <= zmax_m) and (zmin_m is None or f["z"] >= zmin_m)]
    polys = [p for p in polys if p is not None]
    return unary_union(polys) if polys else None


def room_floor(idx: dict, room_id: str):
    g = idx.get(f"Floor_Group_{room_id}")
    return footprint(g, zmax_m=None) if g else None


def built_walls(idx: dict):
    g = idx.get("PlanShell_Group")
    return footprint(g, zmax_m=None, zmin_m=0.5) if g else None   # topo das paredes (acima do piso)


def module_groups(idx: dict, room_name: str) -> dict[str, dict]:
    pre = f"{room_name} · "
    return {n[len(pre):]: g for n, g in idx.items() if n.startswith(pre)}


def _z(g):
    return (g.get("zmin_m") or 0.0, g.get("zmax_m") or 0.0)


def validate_room(idx: dict, room_id: str, room_name: str, *, door_swings=None, walls=None) -> dict[str, Any]:
    from tools.validation.furniture_overlap_gate import EXCLUDE, _is_embedded
    out: dict[str, Any] = {"room_id": room_id, "room": room_name, "checks": {}, "findings": [], "finishes": []}
    floor = room_floor(idx, room_id)
    walls = walls if walls is not None else built_walls(idx)
    mods = module_groups(idx, room_name)
    if floor is None or floor.is_empty:
        out["checks"] = {k: "BLOCKED" for k in ("CONTAINMENT", "WALL", "DOOR_SWING", "OBJECTS")}
        out["findings"].append({"check": "ALL", "reason": f"piso construido Floor_Group_{room_id} ausente"})
        return out
    if not mods:
        out["checks"] = {k: "BLOCKED" for k in ("CONTAINMENT", "WALL", "DOOR_SWING", "OBJECTS")}
        out["findings"].append({"check": "ALL", "reason": f"nenhum grupo '{room_name} · <modulo>' no modelo"})
        return out
    out["floor_area_m2"] = round(floor.area, 4)
    out["floor_parts"] = len(getattr(floor, "geoms", [floor]))
    fps = {}
    for m, g in sorted(mods.items()):
        fp = footprint(g)
        if m in FINISH_MODULES:
            if fp is not None:
                out["finishes"].append({"module": m, "outside_floor_m2": round(fp.difference(floor).area, 5),
                                        "max_protrusion_m": round(fp.difference(floor).hausdorff_distance(floor), 4)
                                        if not fp.difference(floor).is_empty else 0.0})
            continue
        if fp is not None and not fp.is_empty:
            fps[m] = (fp, _z(g))
    # CONTAINMENT: poligono efetivo (com tolerancia de borda), nunca bbox
    allowed = floor.buffer(EDGE_TOL_M)
    bad = [(m, fp.difference(allowed).area) for m, (fp, _z0) in fps.items()]
    bad = [(m, a) for m, a in bad if a > AREA_TOL_M2]
    out["checks"]["CONTAINMENT"] = "FAIL" if bad else "PASS"
    out["findings"] += [{"check": "CONTAINMENT", "module": m, "outside_m2": round(a, 4)} for m, a in bad]
    # WALL
    if walls is None or walls.is_empty:
        out["checks"]["WALL"] = "BLOCKED"
        out["findings"].append({"check": "WALL", "reason": "massa de parede construida ausente"})
    else:
        hits = [(m, fp.intersection(walls).area) for m, (fp, _z0) in fps.items()]
        hits = [(m, a) for m, a in hits if a > AREA_TOL_M2]
        out["checks"]["WALL"] = "FAIL" if hits else "PASS"
        out["findings"] += [{"check": "WALL", "module": m, "inside_wall_m2": round(a, 4)} for m, a in hits]
    # DOOR_SWING
    if door_swings is None:
        out["checks"]["DOOR_SWING"] = "BLOCKED"
        out["findings"].append({"check": "DOOR_SWING", "reason": "varredura de porta indisponivel (contrato nao verificado)"})
    else:
        hits = [(m, d, fp.intersection(sw).area) for m, (fp, _z0) in fps.items() for d, sw in door_swings.items()
                if fp.intersects(sw)]
        hits = [(m, d, a) for m, d, a in hits if a > AREA_TOL_M2]
        out["checks"]["DOOR_SWING"] = "FAIL" if hits else "PASS"
        out["findings"] += [{"check": "DOOR_SWING", "module": m, "door": d, "area_m2": round(a, 4)} for m, d, a in hits]
    # OBJECTS
    names = sorted(fps)
    hits = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if any(e in a.lower() or e in b.lower() for e in EXCLUDE) or _is_embedded(a, b):
                continue
            (pa, (za0, za1)), (pb, (zb0, zb1)) = fps[a], fps[b]
            if min(za1, zb1) - max(za0, zb0) <= 0.02:
                continue
            ar = pa.intersection(pb).area
            if ar > AREA_TOL_M2:
                hits.append({"check": "OBJECTS", "modules": [a, b], "area_m2": round(ar, 4)})
    out["checks"]["OBJECTS"] = "FAIL" if hits else "PASS"
    out["findings"] += hits
    return out


def door_swings_m(con: dict, frame) -> dict:
    """Varreduras de porta do consensus no plano (m), pelo contrato de referencial (core.plan_frame)."""
    from core.plan_frame import to_world_m
    from tools.rooms.shared.clearance import door_swings_pt
    return {str(d): to_world_m(sw, frame) for d, sw in door_swings_pt(con).items()}


def expected_walls_pt(con: dict):
    from tools.rooms.shared.clearance import wall_mass_pt
    return wall_mass_pt(con)


def status(report: dict) -> str:
    vals = list(report["checks"].values())
    return "BLOCKED" if "BLOCKED" in vals else "FAIL" if "FAIL" in vals else "PASS"
