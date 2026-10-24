"""Gemeo em caixas da geometria construida (FP-056): valida uma PROPOSTA antes do SketchUp com o MESMO validador do construido.

Monta, a partir dos dados que vao para o builder, um resultado no formato do `inspect_geometry.rb` e entrega a
`built_geometry.validate_room` (v2). Cada elo foi medido contra o SketchUp real na FP-055 P4 / FP-056 P0:
  - caixas do planejador = grupos construidos (0 mm, conferencia proposta x construido);
  - laje do comodo = `compute_room_floors` do shell (diferenca de cm2 contra o `Floor_Group` construido);
  - massa de parede = `wall_mass_pt` (o poligono que o shell extruda; 20/20 paredes conferidas por parede);
  - folha de porta = dobradica/vao do consensus, altura `DOOR_HEIGHT_M` lida do proprio `build_plan_shell_skp.rb`.
Nao substitui a prova no SketchUp (L2): e o gate de proposta e a medida rapida das correcoes. Escala: o referencial do
contrato (`core.plan_frame`), o mesmo do shell.
"""
from __future__ import annotations

import re
from pathlib import Path

from shapely.geometry import LineString, Polygon

ROOT = Path(__file__).resolve().parents[2]
_RB = ROOT / "tools/sketchup/shell/build_plan_shell_skp.rb"
IN2M = 0.0254


def door_height_m() -> float:
    m = re.search(r"^DOOR_HEIGHT_M\s*=\s*([0-9.]+)", _RB.read_text("utf-8"), re.M)
    if not m:
        raise RuntimeError("DOOR_HEIGHT_M nao encontrado no shell builder")
    return float(m.group(1))


def _face(poly, z):
    return {"zmin": z, "zmax": z, "outer": [list(p) for p in list(poly.exterior.coords)[:-1]],
            "holes": [[list(p) for p in list(r.coords)[:-1]] for r in poly.interiors]}


def _group(name, parts):
    """parts: [(poligono_m, z0, z1, caminho)]."""
    faces, prts, zs, polys = [], [], [], []
    for poly, z0, z1, path in parts:
        for g in getattr(poly, "geoms", [poly]):
            if g.is_empty or g.area <= 0:
                continue
            f0, f1 = _face(g, z0), _face(g, z1)
            faces += [f0, f1]
            prts.append({"path": path, "zmin": z0, "zmax": z1, "faces": [f0, f1]})
            zs += [z0, z1]
            polys.append(g)
    if not polys:
        return None
    x0 = min(p.bounds[0] for p in polys)
    y0 = min(p.bounds[1] for p in polys)
    x1 = max(p.bounds[2] for p in polys)
    y1 = max(p.bounds[3] for p in polys)
    return {"name": name, "zmin_m": min(zs), "zmax_m": max(zs), "projected_faces": faces, "parts": prts,
            "bbox_world_m": {"min": [x0, y0, min(zs)], "max": [x1, y1, max(zs)]}}


def build_result(con: dict, boxes: list[dict], frame) -> dict:
    from core.plan_frame import to_world_m
    from tools.rooms.shared.clearance import wall_mass_pt
    from tools.sketchup.shell.build_plan_shell_skp import compute_room_floors
    groups = []
    for rid, e in compute_room_floors(con).items():
        slab = to_world_m(Polygon(e["outer"], holes=e.get("holes") or []), frame)
        g = _group(f"Floor_Group_{rid}", [(slab, 0.0, 0.0, f"/floor_{rid}")])
        if g:
            groups.append(g)
    walls = to_world_m(wall_mass_pt(con), frame)
    g = _group("PlanShell_Group", [(walls, 0.0, 2.7, "/walls")])
    if g:
        groups.append(g)
    h = door_height_m()
    from tools.validation.built_geometry import door_kinematics_m
    for did, k in door_kinematics_m(con, frame).items():
        hx, hy = k["hinge"]
        ax, ay = k["along"]
        leaf = LineString([(hx, hy), (hx + ax * k["leaf_len"], hy + ay * k["leaf_len"])]).buffer(0.02, cap_style=2)
        g = _group(f"DoorLeaf_Group_{did}", [(leaf, 0.0, h, f"/leaf_{did}")])
        if g:
            groups.append(g)
    by_group: dict[str, list] = {}
    for i, b in enumerate(boxes):
        if not b.get("corners") or not b.get("room"):
            continue
        poly = Polygon([(x * IN2M, y * IN2M) for x, y in b["corners"]])
        if not poly.is_valid:
            poly = poly.buffer(0)
        z0 = float(b.get("z0_in") or 0.0) * IN2M
        z1 = z0 + float(b.get("h_in") or 0.0) * IN2M
        by_group.setdefault(f"{b['room']} · {b.get('module')}", []).append((poly, z0, z1, f"/{b.get('kind')}#{i}"))
    for name, parts in sorted(by_group.items()):
        g = _group(name, parts)
        if g:
            groups.append(g)
    return {"ok": True, "unit": "m", "frame": "box_twin", "groups": groups}


def validate_boxes(con: dict, boxes: list[dict], consensus_path, rooms: dict[str, str] | None = None) -> dict[str, dict]:
    """{room_id: relatorio v2} sobre o gemeo em caixas, no referencial do contrato para `consensus_path`."""
    from core.plan_frame import frame_for_consensus
    from tools.validation import built_geometry as bg
    frame = frame_for_consensus(consensus_path)
    idx = bg.group_index(build_result(con, boxes, frame))
    rooms = rooms or {r["id"]: str(r.get("name") or r["id"]) for r in con["rooms"]}
    doors = bg.door_kinematics_m(con, frame)
    return {rid: bg.validate_room(idx, rid, name, doors=doors) for rid, name in rooms.items()}
