"""FP-055 P4: validacao sobre a geometria CONSTRUIDA e contrato de referencial — negativos que reproduzem o falso PASS."""
from __future__ import annotations

from shapely.geometry import Polygon, box

from core import plan_frame as pf
from tools.orchestration import intelligent_pipeline as ip
from tools.validation import built_geometry as bg


def _face(poly, z=0.0):
    return {"z": z, "outer": [list(p) for p in list(poly.exterior.coords)[:-1]],
            "holes": [[list(p) for p in list(r.coords)[:-1]] for r in poly.interiors]}


def _group(name, polys, z0=0.0, z1=0.4):
    faces = [_face(p, z0) for p in polys] + [_face(p, z1) for p in polys]
    return {"name": name, "zmin_m": z0, "zmax_m": z1, "horizontal_faces": faces}


L_FLOOR = Polygon([(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)])     # L: o quadrante (2..4, 2..4) NAO e comodo
WALLS = L_FLOOR.buffer(0.15, join_style=2).difference(L_FLOOR)


def _model(*furniture, floor=L_FLOOR, walls=WALLS):
    groups = [{"name": "Floor_Group_r1", "zmin_m": 0, "zmax_m": 0, "horizontal_faces": [_face(g) for g in
                                                                                        getattr(floor, "geoms", [floor])]},
              _group("PlanShell_Group", list(getattr(walls, "geoms", [walls])), 0.0, 2.7)] + list(furniture)
    return bg.group_index({"groups": groups})


def test_object_inside_the_bbox_but_outside_the_concave_polygon_fails_containment():
    notch = box(2.6, 2.6, 3.2, 3.2)                                       # dentro do bbox do L, fora do L
    idx = _model(_group("COMODO · Armario", [notch]))
    rep = bg.validate_room(idx, "r1", "COMODO", door_swings={})
    assert rep["checks"]["CONTAINMENT"] == "FAIL" and bg.status(rep) == "FAIL"
    # o cheque anterior (bounding box do piso) dava PASS para o mesmo caso — por isso foi substituido
    old = ip.inside_built_shell([{"name": "Floor_Group_r1", "bbox_world_m": {"min": [0, 0, 0], "max": [4, 4, 0]}}],
                                [{"room": "COMODO", "module": "Armario", "z0_in": 0, "h_in": 30,
                                  "corners": [[2.6 / 0.0254, 2.6 / 0.0254], [3.2 / 0.0254, 2.6 / 0.0254],
                                              [3.2 / 0.0254, 3.2 / 0.0254], [2.6 / 0.0254, 3.2 / 0.0254]]}],
                                {"r1": "COMODO"})
    assert old == []


def test_object_inside_the_polygon_passes_and_multipolygon_floor_is_respected():
    idx = _model(_group("COMODO · Vaso", [box(0.2, 0.2, 0.8, 0.6)]))
    rep = bg.validate_room(idx, "r1", "COMODO", door_swings={})
    assert bg.status(rep) == "PASS", rep["findings"]
    two = box(0, 0, 2, 2).union(box(3, 0, 5, 2))                          # piso em duas partes (multipoligono)
    gap = _model(_group("COMODO · Banco", [box(2.2, 0.5, 2.8, 1.0)]), floor=two,
                 walls=two.buffer(0.15, join_style=2).difference(two.buffer(0.05)))
    rep2 = bg.validate_room(gap, "r1", "COMODO", door_swings={})
    assert rep2["floor_parts"] == 2 and rep2["checks"]["CONTAINMENT"] == "FAIL"


def test_object_in_wall_door_swing_and_other_object_each_fail_their_own_check():
    in_wall = _group("COMODO · Rack", [box(-0.10, 1.0, 0.30, 1.6)])
    swing = {"d1": box(1.0, 0.0, 1.8, 0.8)}
    in_swing = _group("COMODO · Banco", [box(1.1, 0.1, 1.5, 0.5)])
    a = _group("COMODO · Mesa", [box(0.3, 2.5, 1.2, 3.4)], 0.0, 0.75)
    b = _group("COMODO · Cadeira", [box(0.8, 2.9, 1.5, 3.6)], 0.0, 0.9)
    rep = bg.validate_room(_model(in_wall, in_swing, a, b), "r1", "COMODO", door_swings=swing)
    assert rep["checks"] == {"CONTAINMENT": "FAIL", "WALL": "FAIL", "DOOR_SWING": "FAIL", "OBJECTS": "FAIL"}
    assert {f["check"] for f in rep["findings"]} == {"CONTAINMENT", "WALL", "DOOR_SWING", "OBJECTS"}


def test_missing_floor_walls_or_door_data_is_blocked_never_pass():
    idx = bg.group_index({"groups": [_group("COMODO · Vaso", [box(0, 0, 1, 1)])]})
    assert bg.status(bg.validate_room(idx, "r1", "COMODO", door_swings={})) == "BLOCKED"
    rep = bg.validate_room(_model(_group("COMODO · Vaso", [box(0.2, 0.2, 0.8, 0.6)]), walls=Polygon()), "r1", "COMODO",
                           door_swings=None)
    assert rep["checks"]["WALL"] == "BLOCKED" and rep["checks"]["DOOR_SWING"] == "BLOCKED" and bg.status(rep) == "BLOCKED"


def test_wall_finish_is_reported_separately_with_its_protrusion():
    pele = _group("COMODO · Pele", [box(-0.02, 0.0, 0.0, 4.0)], 0.0, 2.6)
    rep = bg.validate_room(_model(pele), "r1", "COMODO", door_swings={})
    assert rep["finishes"] and rep["finishes"][0]["module"] == "Pele" and rep["finishes"][0]["outside_floor_m2"] > 0


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
    walls_pt = box(100, 100, 300, 105).union(box(100, 100, 105, 300))
    right = pf.PlanFrame(0.0259)
    built = pf.to_world_m(walls_pt, right)
    assert pf.verify_against_built(walls_pt, right, built)["status"] == "OK"
    wrong = pf.PlanFrame(0.19 / 5.4)                                        # o erro da 1a execucao da P4
    r = pf.verify_against_built(walls_pt, wrong, built)
    assert r["status"] == "BLOCKED_FRAME_MISMATCH" and r["wall_iou"] < 0.95
    assert pf.verify_against_built(walls_pt, right, None)["status"] == "BLOCKED"
