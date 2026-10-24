"""FP-055 P4: validacao sobre a geometria CONSTRUIDA (bruta), contrato de referencial e interferencia por PROFUNDIDADE
direcional — negativos que reproduzem o falso PASS e interferencias pequenas mas criticas."""
from __future__ import annotations

import random

from shapely.affinity import translate
from shapely.geometry import Polygon, box

from core import plan_frame as pf
from tools.orchestration import intelligent_pipeline as ip
from tools.validation import built_geometry as bg
from tools.validation import penetration as pn


def _face(poly, z=0.0, z1=None):
    return {"zmin": z, "zmax": z if z1 is None else z1, "outer": [list(p) for p in list(poly.exterior.coords)[:-1]],
            "holes": [[list(p) for p in list(r.coords)[:-1]] for r in poly.interiors]}


def _bbox(polys, z0, z1):
    u = polys[0]
    for q in polys[1:]:
        u = u.union(q)
    x0, y0, x1, y1 = u.bounds
    return {"min": [x0, y0, z0], "max": [x1, y1, z1]}


def _part(poly, z0, z1, path):
    return {"path": path, "zmin": z0, "zmax": z1, "faces": [_face(poly, z0), _face(poly, z1)]}


def _group(name, polys, z0=0.0, z1=0.4, parts=None):
    faces = [_face(p, z0) for p in polys] + [_face(p, z1) for p in polys]
    prts = parts if parts is not None else [_part(p, z0, z1, f"/{name}#{i}") for i, p in enumerate(polys)]
    allp = [q for q in polys]
    zs = [z0, z1] + [x for pt in prts for x in (pt["zmin"], pt["zmax"])]
    return {"name": name, "zmin_m": min(zs), "zmax_m": max(zs), "projected_faces": faces,
            "bbox_world_m": _bbox(allp, min(zs), max(zs)), "parts": prts}


L_FLOOR = Polygon([(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)])     # L: o quadrante (2..4, 2..4) NAO e comodo
WALLS = L_FLOOR.buffer(0.15, join_style=2).difference(L_FLOOR)


def _model(*furniture, floor=L_FLOOR, walls=WALLS, extra=()):
    fl = list(getattr(floor, "geoms", [floor]))
    groups = [{"name": "Floor_Group_r1", "zmin_m": 0, "zmax_m": 0, "projected_faces": [_face(g) for g in fl],
               "bbox_world_m": _bbox(fl, 0, 0)},
              _group("PlanShell_Group", list(getattr(walls, "geoms", [walls])), 0.0, 2.7), *extra] + list(furniture)
    return bg.group_index({"groups": groups})


def _door(hinge=(1.0, 0.0), leaf=0.8):
    """Porta na parede de baixo, dobradica em (1,0), folha ao longo de +x abrindo para dentro (+y)."""
    from shapely.geometry import Point
    swing = Point(hinge).buffer(leaf).intersection(box(hinge[0], hinge[1], hinge[0] + leaf, hinge[1] + leaf))
    return {"d1": {"hinge": hinge, "leaf_len": leaf, "along": (1.0, 0.0), "cross_sign": 1, "swing": swing}}


LEAF = _group("DoorLeaf_Group_d1", [box(1.0, -0.02, 1.8, 0.02)], 0.015, 2.1)   # folha construida: vao inferior 1,5 cm


# --------------------------------------------------------------------------------------------------- contencao
def test_object_inside_the_bbox_but_outside_the_concave_polygon_fails_containment():
    notch = box(2.6, 2.6, 3.2, 3.2)                                       # dentro do bbox do L, fora do L
    rep = bg.validate_room(_model(_group("COMODO · Armario", [notch])), "r1", "COMODO", doors={})
    assert rep["checks"]["CONTAINMENT"] == "FAIL" and bg.status(rep) == "FAIL"
    old = ip.inside_built_shell([{"name": "Floor_Group_r1", "bbox_world_m": {"min": [0, 0, 0], "max": [4, 4, 0]}}],
                                [{"room": "COMODO", "module": "Armario", "z0_in": 0, "h_in": 30,
                                  "corners": [[2.6 / 0.0254, 2.6 / 0.0254], [3.2 / 0.0254, 2.6 / 0.0254],
                                              [3.2 / 0.0254, 3.2 / 0.0254], [2.6 / 0.0254, 3.2 / 0.0254]]}],
                                {"r1": "COMODO"})
    assert old == []                                                      # o cheque antigo (bbox) dava PASS


def test_object_inside_passes_and_multipolygon_floor_is_respected():
    rep = bg.validate_room(_model(_group("COMODO · Vaso", [box(0.2, 0.2, 0.8, 0.6)])), "r1", "COMODO", doors={})
    assert bg.status(rep) == "PASS", rep["findings"]
    two = box(0, 0, 2, 2).union(box(3, 0, 5, 2))
    gap = _model(_group("COMODO · Banco", [box(2.2, 0.5, 2.8, 1.0)]), floor=two,
                 walls=two.buffer(0.15, join_style=2).difference(two.buffer(0.05)))
    rep2 = bg.validate_room(gap, "r1", "COMODO", doors={})
    assert rep2["floor_parts"] == 2 and rep2["checks"]["CONTAINMENT"] == "FAIL"


# --------------------------------------------------------------------------------------- profundidade x area
def test_long_shallow_wall_penetration_is_caught_although_its_area_is_under_the_old_tolerance():
    # painel de 1 m entrando 2,5 mm na parede de baixo: 25 cm2 (< 4 in2 = 25,8 cm2) — V1 deixava passar
    pnl = _group("COMODO · Painel", [box(0.5, -0.0025, 1.5, 0.30)])
    rep = bg.validate_room(_model(pnl), "r1", "COMODO", doors={})
    w = [f for f in rep["findings"] if f["check"] == "WALL"]
    assert rep["checks"]["WALL"] == "FAIL" and abs(w[0]["depth_m"] - 0.0025) < 0.0002 and w[0]["area_m2"] < 0.0026
    old = bg.validate_room_v1(_model(pnl), "r1", "COMODO", door_swings={})
    assert old["checks"]["WALL"] == "PASS"                                # o falso PASS antigo, reproduzido


def test_tangential_contact_with_rounding_noise_is_not_penetration():
    rng = random.Random(54)
    for _ in range(50):
        o = box(0.5, 0.0, 1.5, 0.6)
        o = Polygon([(x + rng.uniform(-pn.ROUND_M, pn.ROUND_M), y + rng.uniform(-pn.ROUND_M, pn.ROUND_M))
                     for x, y in list(o.exterior.coords)[:-1]])
        rep = bg.validate_room(_model(_group("COMODO · Rack", [o])), "r1", "COMODO", doors={})
        assert rep["checks"]["WALL"] == "PASS", rep["findings"]


def test_penetration_resolution_and_threshold():
    wall = box(0, 0, 3, 0.14)
    for mm, cls in ((0.3, "CONTACT"), (0.6, "PENETRATION"), (1.0, "PENETRATION")):
        o = box(0.5, 0.14 - mm / 1000, 1.5, 0.74)
        d = min(pn.separation(o, wall, (0, 1)), pn.separation(o, wall, (0, -1)))
        assert abs(d - mm / 1000) <= pn.RES_M * 2 and pn.classify(o, wall, depth=d)["class"] == cls


def test_corner_contact_with_two_wall_pieces_is_measured_per_piece_not_summed():
    # armario no canto entrando 1 mm em cada perna: sair exige diagonal -> MTD = sqrt(2) mm (nao 0,55 m de empurrar reto)
    o = _group("COMODO · Armario", [box(-0.001, -0.001, 0.6, 0.4)])
    rep = bg.validate_room(_model(o), "r1", "COMODO", doors={})
    w = [f for f in rep["findings"] if f["check"] == "WALL"][0]
    assert abs(w["depth_m"] - 2 ** 0.5 * 0.001) < 0.0002 and len(w["regions"]) == 1
    # tapete atravessando o vao: encosta nos DOIS batentes -> duas regioes, cada uma rasa, nunca somadas
    floor = box(0, 0, 4, 4)
    walls = box(-0.15, -0.15, 1.0, 0.0).union(box(1.9, -0.15, 4.15, 0.0)).union(box(-0.15, 4.0, 4.15, 4.15))         .union(box(-0.15, -0.15, 0.0, 4.15)).union(box(4.0, -0.15, 4.15, 4.15))
    tap = _group("COMODO · Tapete", [box(0.995, -0.10, 1.905, 0.6)], 0.0, 0.01)
    rep2 = bg.validate_room(_model(tap, floor=floor, walls=walls), "r1", "COMODO", doors={})
    w2 = [f for f in rep2["findings"] if f["check"] == "WALL"][0]
    assert len(w2["regions"]) == 2 and max(r["mtd_m"] for r in w2["regions"]) < 0.0075


# --------------------------------------------------------------------------------------------- porta (movimento)
def test_small_object_that_blocks_the_door_leaf_fails_although_its_area_is_tiny():
    lixeira = _group("COMODO · Lixeira", [box(1.0, 0.70, 1.10, 0.72)], 0.0, 0.4)      # 2 x 10 cm = 20 cm2
    rep = bg.validate_room(_model(lixeira, extra=[LEAF]), "r1", "COMODO", doors=_door())
    d = [f for f in rep["findings"] if f["check"] == "DOOR"][0]
    assert rep["checks"]["DOOR"] == "FAIL" and d["max_open_deg"] < 90 and d["blocked_by"] == "Lixeira"


def test_low_object_under_the_built_leaf_does_not_block_and_free_swing_passes():
    tapete = _group("COMODO · Tapete", [box(1.0, 0.1, 1.7, 0.7)], 0.0, 0.010)           # 1 cm < vao de 1,5 cm da folha
    rep = bg.validate_room(_model(tapete, extra=[LEAF]), "r1", "COMODO", doors=_door())
    assert rep["checks"]["DOOR"] == "PASS" and rep["door_motion"]["d1"]["max_open_deg"] == 90.0


def test_missing_built_leaf_is_blocked_never_pass():
    rep = bg.validate_room(_model(_group("COMODO · Vaso", [box(1.2, 0.3, 1.5, 0.6)])), "r1", "COMODO", doors=_door())
    assert rep["checks"]["DOOR"] == "BLOCKED" and bg.status(rep) == "BLOCKED"


# ------------------------------------------------------------------------------------------------ objetos
def test_objects_overlapping_in_plan_and_height_fail_but_stacked_parts_are_contact():
    mesa = _group("COMODO · Mesa", [box(0.3, 2.5, 1.2, 3.4)], 0.0, 0.75)
    cadeira = _group("COMODO · Cadeira", [box(1.18, 2.9, 1.6, 3.3)], 0.0, 0.9)          # entra 2 cm na mesa
    rep = bg.validate_room(_model(mesa, cadeira), "r1", "COMODO", doors={})
    o = [f for f in rep["findings"] if f["check"] == "OBJECTS"][0]
    assert abs(o["depth_m"] - 0.02) < 0.0005
    bancada = _group("COMODO · Bancada", [box(0.3, 0.3, 1.0, 0.8)], 0.0, 0.85)
    sabonete = _group("COMODO · Enxoval", [box(0.5, 0.4, 0.6, 0.5)], 0.85, 0.95,          # APOIADO no tampo
                      parts=[_part(box(0.5, 0.4, 0.6, 0.5), 0.85, 0.95, "/s"), _part(box(0.3, 1.0, 0.4, 1.1), 1.6, 1.7, "/t")])
    rep2 = bg.validate_room(_model(bancada, sabonete), "r1", "COMODO", doors={})
    assert rep2["checks"]["OBJECTS"] == "PASS", rep2["findings"]


# ------------------------------------------------------------------------------------------ dado ausente
def test_missing_floor_walls_or_door_data_is_blocked_never_pass():
    idx = bg.group_index({"groups": [_group("COMODO · Vaso", [box(0, 0, 1, 1)])]})
    assert bg.status(bg.validate_room(idx, "r1", "COMODO", doors={})) == "BLOCKED"
    rep = bg.validate_room(_model(_group("COMODO · Vaso", [box(0.2, 0.2, 0.8, 0.6)]), walls=Polygon()), "r1", "COMODO",
                           doors=None)
    assert rep["checks"]["WALL"] == "BLOCKED" and rep["checks"]["DOOR"] == "BLOCKED" and bg.status(rep) == "BLOCKED"


def test_incomplete_extraction_is_blocked_never_pass():
    g = _group("COMODO · Rack", [box(0.2, 0.2, 0.8, 0.6)])
    g["bbox_world_m"] = {"min": [0.2, 0.2, 0], "max": [1.4, 0.6, 0.4]}           # SketchUp ve 0,6 m a mais
    rep = bg.validate_room(_model(g), "r1", "COMODO", doors={})
    assert rep["checks"]["EXTRACTION"] == "BLOCKED" and bg.status(rep) == "BLOCKED"


def test_overhang_and_inclined_faces_count_in_the_footprint():
    base, overhang = box(0.2, 0.2, 0.6, 0.6), box(0.2, 0.2, 1.0, 0.6)
    slope = {"zmin": 0.3, "zmax": 0.5, "inclined": True, "outer": [[0.2, 0.6], [0.6, 0.6], [0.6, 0.9], [0.2, 0.9]], "holes": []}
    g = {"name": "COMODO · Bancada", "zmin_m": 0, "zmax_m": 0.8, "bbox_world_m": {"min": [0.2, 0.2, 0], "max": [1.0, 0.9, 0.8]},
         "projected_faces": [_face(base, 0.0), _face(overhang, 0.75), slope]}
    assert abs(bg.footprint(g).area - (0.8 * 0.4 + 0.4 * 0.3)) < 1e-9 and bg.extraction_gap_m(g) == 0.0


def test_wall_finish_is_reported_separately_with_its_protrusion():
    pele = _group("COMODO · Pele", [box(-0.02, 0.0, 0.0, 4.0)], 0.0, 2.6)
    rep = bg.validate_room(_model(pele), "r1", "COMODO", doors={})
    assert rep["finishes"][0]["module"] == "Pele" and abs(rep["finishes"][0]["max_protrusion_m"] - 0.02) < 1e-6


# ------------------------------------------------------------------------------------- contrato de referencial
def test_scale_chain_mismatch_is_blocked_before_building():
    planta = "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"
    other = "runs/fp055/x/consensus_synthetic.json"
    shell_p, shell_o = pf.frame_for_consensus(planta), pf.frame_for_consensus(other)
    assert abs(shell_p.pt_to_m - 0.0259) < 1e-9 and abs(shell_o.pt_to_m - 0.19 / 5.4) < 1e-9
    proc = pf.process_frame().pt_to_m
    for path, fr in ((planta, shell_p), (other, shell_o)):
        r = pf.check_chain(path)
        assert r["status"] == ("OK" if abs(fr.pt_to_m - proc) < 1e-9 else "BLOCKED_SCALE_MISMATCH")
        assert len(r["transforms"]) == 4


def test_frame_contract_is_checked_against_built_walls():
    walls = [{"id": "h", "start": [100, 102.5], "end": [300, 102.5], "thickness": 5},
             {"id": "v", "start": [102.5, 100], "end": [102.5, 300], "thickness": 5}]
    walls_pt = box(100, 100, 300, 105).union(box(100, 100, 105, 300))
    right = pf.PlanFrame(0.0259)
    built = pf.to_world_m(walls_pt, right)
    ok = pf.verify_against_built(walls_pt, right, built, walls)
    assert ok["status"] == "OK" and ok["walls_checked"] == 2 and not ok["walls_failed"]
    r = pf.verify_against_built(walls_pt, pf.PlanFrame(0.19 / 5.4), built, walls)
    assert r["status"] == "BLOCKED_FRAME_MISMATCH" and r["wall_iou"] < 0.95
    assert pf.verify_against_built(walls_pt, right, None, walls)["status"] == "BLOCKED"
    assert pf.verify_against_built(walls_pt, right, built, None)["status"] == "BLOCKED"


def test_one_wrong_wall_cannot_hide_behind_a_good_global_overlap():
    walls, pieces = [], []
    for i in range(12):
        y = 100 + i * 40
        walls.append({"id": f"w{i}", "start": [100, y], "end": [700, y], "thickness": 5})
        pieces.append(box(100, y - 2.5, 700, y + 2.5))
    walls.append({"id": "short", "start": [900, 100], "end": [900, 140], "thickness": 5})
    pieces.append(box(897.5, 100, 902.5, 140))
    exp_pt = pieces[0]
    for q in pieces[1:]:
        exp_pt = exp_pt.union(q)
    fr = pf.PlanFrame(0.0259)
    built = pf.to_world_m(exp_pt.difference(pieces[-1]).union(translate(pieces[-1], xoff=3.0)), fr)
    r = pf.verify_against_built(exp_pt, fr, built, walls)
    assert r["wall_iou"] >= 0.95 and r["status"] == "BLOCKED_FRAME_MISMATCH" and r["walls_failed"] == ["short"]


def test_sliver_opening_does_not_hide_a_one_centimetre_wall_offset():
    walls = [{"id": "w", "start": [100, 102.7], "end": [400, 102.7], "thickness": 5.4}]
    exp_pt = box(100, 100, 400, 105.4)
    fr = pf.PlanFrame(0.0259)
    sliver = pf.to_world_m(box(100, 107.0, 400, 107.05), fr)    # DENTRO do corredor da parede, 4,3 cm da face
    ok = pf.verify_against_built(exp_pt, fr, pf.to_world_m(exp_pt, fr).union(sliver), walls)
    assert ok["status"] == "OK", ok["per_wall"]
    bad = pf.verify_against_built(exp_pt, fr, pf.to_world_m(translate(exp_pt, yoff=0.01 / 0.0259), fr), walls)
    assert bad["status"] == "BLOCKED_FRAME_MISMATCH" and bad["walls_failed"] == ["w"]


def test_wall_joint_intersections_with_lines_and_points_keep_only_the_area():
    from shapely.geometry import GeometryCollection, LineString, Point
    g = GeometryCollection([box(0, 0, 1, 1), LineString([(2, 2), (3, 3)]), Point(5, 5)])
    assert abs(pf.polygonal(g).area - 1.0) < 1e-12 and pf.polygonal(None).is_empty


def test_normalization_is_recorded_per_wall_and_never_reaches_the_safety_checks():
    walls = [{"id": "w", "start": [100, 102.7], "end": [400, 102.7], "thickness": 5.4}]
    exp_pt = box(100, 100, 400, 105.4)
    fr = pf.PlanFrame(0.0259)
    sliver = pf.to_world_m(box(100, 107.0, 400, 107.05), fr)    # DENTRO do corredor da parede, 4,3 cm da face
    r = pf.verify_against_built(exp_pt, fr, pf.to_world_m(exp_pt, fr).union(sliver), walls)["per_wall"][0]
    n = r["normalization"]
    assert n["radius_m"] == pf.SLIVER_OPEN_M and n["removed_built_m2"] > 0 and n["removed_max_extent_m"] > 7.0
    # um painel INTENCIONAL de 3 mm (a abertura de 2 mm o apagaria) entrando 2 mm na parede: a seguranca usa o bruto
    painel = _group("COMODO · Painel", [box(1.0, -0.002, 1.003, 0.8)], 0.0, 2.0)
    rep = bg.validate_room(_model(painel), "r1", "COMODO", doors={})
    w = [f for f in rep["findings"] if f["check"] == "WALL"]
    assert rep["checks"]["WALL"] == "FAIL" and abs(w[0]["depth_m"] - 0.002) < 0.0003
    # e uma haste de 3 mm no caminho da folha bloqueia a porta
    haste = _group("COMODO · Haste", [box(1.3, 0.5, 1.303, 0.503)], 0.0, 1.0)
    rep2 = bg.validate_room(_model(haste, extra=[LEAF]), "r1", "COMODO", doors=_door())
    assert rep2["checks"]["DOOR"] == "FAIL"


def test_slab_tucked_under_the_wall_is_not_room_and_does_not_hide_a_piece_inside_the_wall():
    # a laje do shell entra 0,4 x espessura sob a parede (D-007): um movel 5 cm DENTRO da parede ficaria "na laje"
    t = 0.15
    slab = box(-0.4 * t, -0.4 * t, 4.0, 4.0)
    walls = box(-t, -t, 4.0 + t, 0.0).union(box(-t, -t, 0.0, 4.0 + t))
    idx = bg.group_index({"groups": [
        {"name": "Floor_Group_r1", "zmin_m": 0, "zmax_m": 0, "projected_faces": [_face(slab)], "bbox_world_m": _bbox([slab], 0, 0)},
        _group("PlanShell_Group", [walls], 0.0, 2.7), _group("COMODO · Armario", [box(1.0, -0.05, 1.6, 0.55)], 0.0, 2.0)]})
    eff = bg.room_floor(idx, "r1")
    assert eff.bounds[1] >= -1e-9 and bg.room_slab(idx, "r1").bounds[1] < -0.05
    rep = bg.validate_room(idx, "r1", "COMODO", doors={})
    c = [f for f in rep["findings"] if f["check"] == "CONTAINMENT"]
    assert rep["checks"]["CONTAINMENT"] == "FAIL" and abs(c[0]["outside_depth_m"] - 0.05) < 1e-3
    assert rep["checks"]["WALL"] == "FAIL"
