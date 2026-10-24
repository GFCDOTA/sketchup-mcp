"""Validacao sobre a GEOMETRIA CONSTRUIDA (FP-055 P4): construido x ambiente real, nao construido x pedido.

Entrada: o resultado do job `inspect_geometry.rb` — toda face NAO vertical (horizontal ou inclinada) de cada grupo de topo,
projetada no plano, com a faixa de Z, em metros no mundo do SketchUp, percorrendo grupos/componentes aninhados.
Tudo que este modulo afirma vem do modelo reaberto:
  - piso do comodo  = uniao das faces de `Floor_Group_<rid>` (poligono efetivo; concavo e multipoligono preservados);
  - massa de parede = faces horizontais de `PlanShell_Group` acima do piso (topo das paredes, ja com os vaos recortados);
  - folha de porta  = `DoorLeaf_Group_<id>`;
  - pegada do movel = uniao das projecoes das faces do grupo "<COMODO> · <modulo>" que comecam abaixo de 1,2 m (saliencias
    e beirais entram pela face de baixo; faces inclinadas pela projecao).
EXTRACTION (antes de tudo): a pegada extraida precisa cobrir o bounding box que o PROPRIO SketchUp calcula para o grupo
(diferenca <= 1 cm por lado). Se nao cobre, a extracao perdeu ocupacao fisica: BLOCKED, nunca PASS.
Limites: entidade oculta e ignorada (contada); superficie curva vem facetada; peca so com faces verticais sem tampa teria
pegada nula — cai na EXTRACTION.
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

from tools.validation.penetration import (
    EPS_DEPTH,
    classify,
    door_open_angle,
    mtd,
    outside_depth,
    separation,
)

FLOOR_LEVEL_M = 1.2
EXTRACTION_TOL_M = 0.01       # pegada extraida x bbox do SketchUp: diferenca maxima por lado
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
    """Uniao das projecoes das faces nao verticais. `zmax_m`: so faces que COMECAM abaixo (ocupam ate aquela altura);
    `zmin_m`: so faces inteiramente acima (topo das paredes)."""
    polys = [_poly(f) for f in group.get("projected_faces", [])
             if (zmax_m is None or f["zmin"] <= zmax_m) and (zmin_m is None or f["zmin"] >= zmin_m)]
    polys = [p for p in polys if p is not None]
    return unary_union(polys) if polys else None


def extraction_gap_m(group: dict) -> float | None:
    """Maior diferenca por lado entre a pegada extraida (todas as faces) e o bbox de mundo do SketchUp. None = sem dado."""
    fp, bb = footprint(group, zmax_m=None), group.get("bbox_world_m")
    if fp is None or fp.is_empty or not bb:
        return None
    x0, y0, x1, y1 = fp.bounds
    return round(max(abs(x0 - bb["min"][0]), abs(y0 - bb["min"][1]), abs(bb["max"][0] - x1), abs(bb["max"][1] - y1)), 4)


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


def validate_room_v1(idx: dict, room_id: str, room_name: str, *, door_swings=None, walls=None) -> dict[str, Any]:
    """V1 (substituida, mantida SO para a comparacao de regressao FP-055 P4): decide por AREA de intersecao (4 in2) e por
    piso alargado de 1 cm. Deixa passar o longo-e-raso e o pequeno-que-bloqueia — ver validate_room."""
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
    gaps = {m: extraction_gap_m(g) for m, g in mods.items()}
    incomplete = {m: v for m, v in gaps.items() if v is None or v > EXTRACTION_TOL_M}
    out["extraction_gap_m"] = gaps
    if incomplete:
        out["checks"] = {k: "BLOCKED" for k in ("EXTRACTION", "CONTAINMENT", "WALL", "DOOR_SWING", "OBJECTS")}
        out["findings"].append({"check": "EXTRACTION", "reason": "pegada extraida nao cobre o bbox do SketchUp",
                                "modules": incomplete})
        return out
    out["checks"]["EXTRACTION"] = "PASS"
    out["floor_area_m2"] = round(floor.area, 4)
    out["floor_parts"] = len(getattr(floor, "geoms", [floor]))
    fps = {}
    for m, g in sorted(mods.items()):
        fp = footprint(g)
        if m in FINISH_MODULES:
            if fp is not None:
                out["finishes"].append({"module": m, "outside_floor_m2": round(fp.difference(floor).area, 5),
                                        "max_protrusion_m": round(outside_depth(fp, floor), 4)})
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


Z_EPS_M = 0.0005               # sobreposicao vertical minima para duas partes ocuparem o mesmo espaco (= EPS_DEPTH)


def parts(group: dict, *, zmax_m: float | None = None) -> list[tuple[Any, float, float, str]]:
    """Solidos do grupo: (pegada, zmin, zmax, caminho) por PARTE exportada (container com faces proprias). Sem `parts` no
    resultado (exportacao antiga) a parte e o grupo inteiro — mais grosseiro, nunca mais permissivo para colisao com parede."""
    raw = group.get("parts")
    if not raw:
        fp = footprint(group, zmax_m=None)
        return [(fp, group.get("zmin_m") or 0.0, group.get("zmax_m") or 0.0, "<grupo>")] if fp is not None else []
    out = []
    for pt in raw:
        polys = [q for q in (_poly(f) for f in pt.get("faces", [])) if q is not None]
        if not polys or pt.get("zmin") is None:
            continue
        if zmax_m is not None and pt["zmin"] > zmax_m:
            continue
        out.append((unary_union(polys), pt["zmin"], pt["zmax"], pt.get("path", "")))
    return out


def _components(g):
    return [x for x in getattr(g, "geoms", [g]) if not x.is_empty and getattr(x, "area", 0) > 0]


def _wall_normals(walls, fp, pad: float = 0.05) -> list[tuple[float, float]]:
    """Normais das arestas da massa de parede que tocam a pegada: as direcoes em que se sai da parede."""
    import math

    from shapely.geometry import LineString
    out = set()
    for g in getattr(walls, "geoms", [walls]):
        rings = [g.exterior, *g.interiors] if hasattr(g, "exterior") else []
        for r in rings:
            c = list(r.coords)
            for (x0, y0), (x1, y1) in zip(c, c[1:]):
                L = math.hypot(x1 - x0, y1 - y0)
                if L < 1e-9:
                    continue
                if LineString([(x0, y0), (x1, y1)]).distance(fp) <= pad:
                    out.add((round(-(y1 - y0) / L, 6), round((x1 - x0) / L, 6)))
    return sorted(out)


CONTACT_PAD_M = 0.02            # parede considerada em volta de cada regiao de contato (so a peca local)


def wall_depth(fp, walls) -> dict:
    """Profundidade de penetracao na parede, por REGIAO DE CONTATO (cada componente conexa de pegada ∩ parede), contra SO a
    parede em volta dessa regiao: MTD (menor translacao em qualquer direcao que separa). Num canto o objeto precisa sair na
    diagonal (2 pernas, 1 mm cada -> ~1,41 mm); atravessando um vao (dois batentes) sao duas regioes medidas separadas,
    nunca somadas. Tambem devolve a separacao perpendicular a aresta tocada (metrica direcional complementar).
    Retorna {"depth_m": max das regioes, "regions": [...]}."""
    from tools.validation.penetration import valid
    inter = valid(fp.intersection(walls))
    regions = []
    for reg in _components(inter):
        local = valid(walls.intersection(reg.buffer(CONTACT_PAD_M)))
        d, direc = mtd(fp, local)
        normals = _wall_normals(local, reg, pad=1e-6)
        perp = min((min(separation(fp, local, n), separation(fp, local, (-n[0], -n[1]))) for n in normals), default=None)
        regions.append({"area_m2": round(reg.area, 8), "mtd_m": round(d, 5), "mtd_dir": [round(direc[0], 3), round(direc[1], 3)],
                        "perpendicular_m": None if perp is None else round(perp, 5)})
    return {"depth_m": max((r["mtd_m"] for r in regions), default=0.0), "regions": regions}


def validate_room(idx: dict, room_id: str, room_name: str, *, doors=None, walls=None, others=None) -> dict[str, Any]:
    """V2 (FP-055 P4): cada interferencia e medida por AREA, CONTATO e PROFUNDIDADE DIRECIONAL separadas
    (`tools.validation.penetration`); a regra depende da natureza da restricao:
      CONTAINMENT  profundidade para fora do poligono do piso (outside_depth) > EPS_DEPTH reprova;
      WALL         profundidade perpendicular a parede (wall_depth) > EPS_DEPTH reprova — qualquer area;
      DOOR         movimento funcional: a folha gira de fechada a 90 graus em volta da dobradica (consensus pelo contrato);
                   abrir menos que 90 graus porque um objeto PENETRA o caminho reprova — qualquer area;
      OBJECTS      MTD entre pegadas com sobreposicao em Z > EPS_DEPTH reprova, exceto hospedados/embutidos.
    Contato tangencial (profundidade <= EPS_DEPTH) nunca e penetracao. Geometria BRUTA do SketchUp; nada normalizado aqui.
    `doors`: {id: cinematica de door_kinematics_m}; None = DOOR BLOCKED. `others`: pegadas de outros comodos (porta)."""
    from tools.validation.furniture_overlap_gate import EXCLUDE, _is_embedded
    out: dict[str, Any] = {"room_id": room_id, "room": room_name, "checks": {}, "findings": [], "finishes": [],
                           "version": "v2", "eps_depth_m": EPS_DEPTH}
    keys = ("EXTRACTION", "CONTAINMENT", "WALL", "DOOR", "OBJECTS")
    floor = room_floor(idx, room_id)
    walls = walls if walls is not None else built_walls(idx)
    mods = module_groups(idx, room_name)
    if floor is None or floor.is_empty or not mods:
        out["checks"] = {k: "BLOCKED" for k in keys}
        out["findings"].append({"check": "ALL", "reason": "piso construido ausente" if floor is None or floor.is_empty
                                else f"nenhum grupo '{room_name} · <modulo>' no modelo"})
        return out
    gaps = {m: extraction_gap_m(g) for m, g in mods.items()}
    out["extraction_gap_m"] = gaps
    incomplete = {m: v for m, v in gaps.items() if v is None or v > EXTRACTION_TOL_M}
    if incomplete:
        out["checks"] = {k: "BLOCKED" for k in keys}
        out["findings"].append({"check": "EXTRACTION", "reason": "pegada extraida nao cobre o bbox do SketchUp",
                                "modules": incomplete})
        return out
    out["checks"]["EXTRACTION"] = "PASS"
    out["floor_area_m2"], out["floor_parts"] = round(floor.area, 4), len(getattr(floor, "geoms", [floor]))
    fps = {}
    for m, g in sorted(mods.items()):
        fp = footprint(g)
        if m in FINISH_MODULES:
            if fp is not None:
                out["finishes"].append({"module": m, "outside_floor_m2": round(fp.difference(floor).area, 5),
                                        "max_protrusion_m": round(outside_depth(fp, floor), 4)})
            continue
        if fp is not None and not fp.is_empty:
            fps[m] = (fp, _z(g))
    prts = {m: parts(mods[m], zmax_m=None) for m in fps}
    low = {m: [x for x in ps if x[1] < FLOOR_LEVEL_M] for m, ps in prts.items()}
    # CONTAINMENT: cada parte que comeca abaixo de 1,2 m, para fora do poligono do piso
    rows = []
    for m, ps in low.items():
        d = max((outside_depth(fp, floor) for fp, *_r in ps), default=0.0)
        if d > EPS_DEPTH:
            rows.append({"check": "CONTAINMENT", "module": m, "outside_depth_m": round(d, 5),
                         "outside_m2": round(fps[m][0].difference(floor).area, 6)})
    out["checks"]["CONTAINMENT"] = "FAIL" if rows else "PASS"
    out["findings"] += rows
    # WALL: cada parte x cada peca de parede tocada
    if walls is None or walls.is_empty:
        out["checks"]["WALL"] = "BLOCKED"
        out["findings"].append({"check": "WALL", "reason": "massa de parede construida ausente"})
    else:
        rows = []
        for m, ps in prts.items():
            worst, wc = 0.0, None
            for fp, _z0, _z1, path in ps:
                if not fp.intersects(walls):
                    continue
                wd = wall_depth(fp, walls)
                if wd["depth_m"] > worst:
                    worst = wd["depth_m"]
                    wc = classify(fp, walls.intersection(fp.buffer(0.5)), depth=wd["depth_m"]) | {
                        "part": path, "regions": wd["regions"]}
            if wc is not None and wc["class"] == "PENETRATION":
                rows.append({"check": "WALL", "module": m, **wc})
        out["checks"]["WALL"] = "FAIL" if rows else "PASS"
        out["findings"] += rows
    # DOOR: movimento da folha CONSTRUIDA (faixa de Z do DoorLeaf_Group_<id> do modelo); so partes nessa faixa obstruem
    if doors is None:
        out["checks"]["DOOR"] = "BLOCKED"
        out["findings"].append({"check": "DOOR", "reason": "cinematica de porta indisponivel (contrato nao verificado)"})
    else:
        rows, measured, blocked = [], {}, []
        for did, k in doors.items():
            if not k["swing"].intersects(floor):
                continue
            leaf = idx.get(f"DoorLeaf_Group_{did}")
            if leaf is None or leaf.get("zmin_m") is None:
                blocked.append({"check": "DOOR", "door": did, "reason": f"folha DoorLeaf_Group_{did} ausente no modelo"})
                continue
            lz0, lz1 = leaf["zmin_m"], leaf["zmax_m"]
            near = {}
            for m, ps in prts.items():
                band = [fp for fp, z0, z1, _p in ps if min(z1, lz1) - max(z0, lz0) > Z_EPS_M and fp.intersects(k["swing"])]
                if band:
                    near[m] = unary_union(band)
            r = (door_open_angle(k["hinge"], k["leaf_len"], k["along"], k["cross_sign"], near) if near
                 else {"max_open_deg": 90.0, "blocked_by": None, "required_deg": 90.0, "ok": True})
            r["leaf_z_m"] = [lz0, lz1]
            measured[did] = r
            if not r["ok"]:
                rows.append({"check": "DOOR", "door": did, **r})
        out["door_motion"] = measured
        out["checks"]["DOOR"] = "FAIL" if rows else ("BLOCKED" if blocked else "PASS")
        out["findings"] += rows + blocked
    # OBJECTS: partes de modulos diferentes que se sobrepoem em planta E em altura
    names, rows = sorted(prts), []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if any(e in a.lower() or e in b.lower() for e in EXCLUDE) or _is_embedded(a, b):
                continue
            worst = None
            for pa, za0, za1, qa in prts[a]:
                for pb, zb0, zb1, qb in prts[b]:
                    if min(za1, zb1) - max(za0, zb0) <= Z_EPS_M or not pa.intersects(pb):
                        continue
                    c = classify(pa, pb)
                    if c["class"] == "PENETRATION" and (worst is None or c["depth_m"] > worst["depth_m"]):
                        worst = c | {"parts": [qa, qb], "z_overlap_m": round(min(za1, zb1) - max(za0, zb0), 5)}
            if worst is not None:
                rows.append({"check": "OBJECTS", "modules": [a, b], **worst})
    out["checks"]["OBJECTS"] = "FAIL" if rows else "PASS"
    out["findings"] += rows
    return out


def door_kinematics_m(con: dict, frame) -> dict:
    """Dobradica, folha e sentido de abertura de cada porta interior no plano (m), pelo contrato de referencial.
    Mesma geometria de `tools.rooms.shared.clearance.door_swings_pt` (raio = largura do vao, a partir da dobradica)."""
    from core.plan_frame import to_world_m
    from tools.rooms.shared.clearance import DOOR_KINDS, door_swings_pt
    swings = door_swings_pt(con)
    walls = {w["id"]: w for w in con["walls"]}
    out = {}
    for o in con.get("openings", []):
        if o["id"] not in swings or (o.get("kind") != "door" and o.get("kind_v5") not in DOOR_KINDS):
            continue
        w = walls[o["wall_id"]]
        horiz = abs(w["start"][1] - w["end"][1]) < 1e-6
        cx, cy = o["center"]
        hw = float(o["opening_width_pts"]) / 2
        t = float(w.get("thickness", 5.4)) / 2
        sgn = 1 if o.get("swing_side") == "pos" else -1
        along, cross = (cx, cy) if horiz else (cy, cx)
        h_al = along - hw if o.get("hinge_side") == "left" else along + hw
        u = 1 if o.get("hinge_side") == "left" else -1
        h_cr = cross + sgn * t
        hinge_pt = (h_al, h_cr) if horiz else (h_cr, h_al)
        a_dir = (float(u), 0.0) if horiz else (0.0, float(u))
        n_dir = (0.0, float(sgn)) if horiz else (float(sgn), 0.0)
        cross_sign = 1 if (a_dir[0] * n_dir[1] - a_dir[1] * n_dir[0]) > 0 else -1
        out[str(o["id"])] = {"hinge": frame.pt_to_world_m(hinge_pt), "leaf_len": 2 * hw * frame.pt_to_m, "along": a_dir,
                             "cross_sign": cross_sign, "swing": to_world_m(swings[o["id"]], frame)}
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
