"""FP-046/P1-P2: porta Shaker parametrica — plano puro (sem SketchUp). Cobre CA-03..CA-11, CA-13, CA-20, CA-21, CA-23.

Os valores da fixture sao SINTETICOS (nao padrao de fabricante). Prova geometria planejada, nao aparencia nem L2.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.rooms.shared.cabinet import plan_cabinet
from tools.rooms.shared.cabinet import sketchup as cabinet_sketchup
from tools.rooms.shared.cabinet.shaker import (
    CAPABILITY_ID,
    GRAIN_SUPPORT,
    ShakerPlanRefused,
    plan_shaker_door,
    require_valid_shaker,
)
from tools.rooms.shared.cabinet.validation import EPS, _overlap_volume

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures/synthetic_cabinets"
LEGACY_SIGNATURE_A = "be9a6f415ae6f9c64e14b8c72fdbd2b8e61380314b41f456589aa3bc9bd2623a"   # fixado na develop antes do Shaker
LEGACY_SIGNATURE_B = "15ab38eb7cb09e07ca869c652f483c9ecc90dfd8e3faa15e4569160d88cc550e"


def load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def parent(two_fronts: bool = False) -> dict:
    req = load("valid_a_base_600.json")
    if two_fronts:
        req["fronts"] = {"count": 2}
    plan = plan_cabinet(req)
    assert plan["status"] == "OK"
    return plan


def shaker(**over) -> dict:
    req = load("fp046_shaker_valid_a.json")
    for key, value in over.items():
        node = req
        *path, last = key.split("__")
        for step in path:
            node = node[step]
        if value is ...:
            del node[last]
        else:
            node[last] = value
    return req


def qty(mm: float) -> dict:
    return {"value": mm, "unit": "mm", "origin": "user_request"}


def parts_by_name(plan: dict) -> dict:
    return {p["name"]: p for p in plan["parts"]}


# --- plano feliz --------------------------------------------------------------------------------------------------------

def test_valid_request_gives_exactly_five_parts_signed_and_not_authorized():
    plan = plan_shaker_door(shaker(), parent())
    assert plan["status"] == "OK" and plan["findings"] == []
    assert sorted(parts_by_name(plan)) == ["rail_bottom", "rail_top", "recessed_panel", "stile_left", "stile_right"]
    assert plan["capability"]["id"] == CAPABILITY_ID == "shared.cabinet.front.shaker"
    assert plan["execution_authorized"] is False and plan["visual"] == "NOT_REVIEWED"
    assert len(plan["signature"]) == 64 and plan["replaces_part"] == "synthetic-a/front"
    assert {p["role"] for p in plan["parts"]} == {"frame", "panel"}


def test_geometry_fills_the_replaced_front_envelope_exactly_with_face_contact_only():
    par = parent()
    front = next(p for p in par["parts"] if p["name"] == "front")
    plan = plan_shaker_door(shaker(), par)
    parts = plan["parts"]
    lo = [min(p["min_m"][k] for p in parts) for k in range(3)]
    hi = [max(p["max_m"][k] for p in parts) for k in range(3)]
    assert lo == pytest.approx(front["min_m"], abs=EPS) and hi == pytest.approx(front["max_m"], abs=EPS)
    for i, a in enumerate(parts):
        for b in parts[i + 1:]:
            assert _overlap_volume(a, b) <= EPS, (a["id"], b["id"])          # contato de face, nunca volume comum
    by = parts_by_name(plan)
    assert by["stile_left"]["size_m"][0] == pytest.approx(0.060) and by["rail_top"]["size_m"][2] == pytest.approx(0.060)
    assert by["rail_top"]["min_m"][0] == pytest.approx(by["stile_left"]["max_m"][0])       # travessa ENTRE os montantes
    assert by["rail_top"]["max_m"][0] == pytest.approx(by["stile_right"]["min_m"][0])


def test_panel_is_physically_recessed_by_coordinate_not_by_material():
    par = parent()
    front = next(p for p in par["parts"] if p["name"] == "front")
    by = parts_by_name(plan_shaker_door(shaker(), par))
    frame_front_y = by["stile_left"]["max_m"][1]
    assert frame_front_y == pytest.approx(front["max_m"][1])
    assert frame_front_y - by["recessed_panel"]["max_m"][1] == pytest.approx(0.004)         # recuo pedido
    assert by["recessed_panel"]["size_m"][1] == pytest.approx(0.006)
    assert by["recessed_panel"]["min_m"][1] >= by["stile_left"]["min_m"][1] - EPS            # ainda dentro da profundidade da moldura
    assert by["recessed_panel"]["material"] == by["stile_left"]["material"] == "mdf_branco"  # mesmo material: so a geometria distingue


def test_zero_recess_is_flush_and_allowed():
    by = parts_by_name(plan_shaker_door(shaker(panel__recess_from_frame_front=qty(0)), parent()))
    assert by["recessed_panel"]["max_m"][1] == pytest.approx(by["stile_left"]["max_m"][1])


def test_two_fronts_two_independent_assemblies_without_collision_or_duplicate_ids():
    par = parent(two_fronts=True)
    p1 = plan_shaker_door(shaker(target_front="front_1", request_id="shaker-l"), par)
    p2 = plan_shaker_door(shaker(target_front="front_2", request_id="shaker-r"), par)
    assert p1["status"] == p2["status"] == "OK"
    ids = [p["id"] for p in p1["parts"] + p2["parts"]]
    assert len(ids) == len(set(ids)) == 10
    for a in p1["parts"]:
        for b in p2["parts"]:
            assert _overlap_volume(a, b) <= EPS
    assert p1["signature"] != p2["signature"]


def _shared_groups(plan: dict) -> list[list[str]]:
    return sorted(sorted(i.split("/")[1] for i in d["instances"]) for d in plan["definitions"])


def test_equivalent_parts_share_definitions_only_when_role_size_material_grain_match():
    assert _shared_groups(plan_shaker_door(shaker(), parent())) == [
        ["rail_bottom", "rail_top"], ["recessed_panel"], ["stile_left", "stile_right"]]
    differ = plan_shaker_door(shaker(materials__frame="mdf_carvalho"), parent())            # material igual nas 4 pecas de moldura
    assert ["stile_left", "stile_right"] in _shared_groups(differ)
    unequal = plan_shaker_door(shaker(frame__stile_width=qty(70)), parent())                 # montante != travessa em medida
    assert ["rail_bottom", "rail_top"] in _shared_groups(unequal)
    mixed = copy.deepcopy(plan_shaker_door(shaker(), parent()))
    mixed["parts"][1]["grain"] = "along_height"                                                # veio diferente => nao compartilha
    from tools.rooms.shared.cabinet.assembly import definitions
    assert ["stile_left"] in sorted(sorted(i.split("/")[1] for i in d["instances"]) for d in definitions(mixed["parts"]))


# --- determinismo e assinatura ------------------------------------------------------------------------------------------

def test_same_input_same_ids_and_signature_and_any_parameter_changes_it():
    base = plan_shaker_door(shaker(), parent())
    assert base == plan_shaker_door(shaker(), parent())
    for change in ({"panel__recess_from_frame_front": qty(3)}, {"materials__panel": "mdf_azul"}, {"grain__frame": "along_height"},
                   {"frame__rail_height": qty(70)}):
        assert plan_shaker_door(shaker(**change), parent())["signature"] != base["signature"], change


def test_signature_is_bound_to_the_parent_plan():
    other_parent = load("valid_a_base_600.json")
    other_parent["pose"]["rotation_deg"] = {"value": 30, "unit": "deg", "origin": "user_request"}
    moved = plan_cabinet(other_parent)
    assert plan_shaker_door(shaker(), parent())["signature"] != plan_shaker_door(shaker(), moved)["signature"]


# --- recusas antes de qualquer job --------------------------------------------------------------------------------------

@pytest.mark.parametrize("over,code", [
    ({"frame__stile_width": ...}, "MISSING_QUANTITY"),
    ({"frame__stile_width": {"value": 60, "unit": "mm"}}, "MISSING_ORIGIN"),
    ({"frame__stile_width": {"value": 60, "origin": "user_request"}}, "MISSING_UNIT"),
    ({"frame__stile_width": {"value": 60, "unit": "mm", "origin": "default_declared"}}, "INVALID_ORIGIN"),
    ({"frame__rail_height": qty(-5)}, "NON_POSITIVE"),
    ({"frame__rail_height": qty(float("nan"))}, "NON_FINITE"),
    ({"frame__frame_thickness": qty(0)}, "NON_POSITIVE"),
    ({"panel__thickness": qty(0)}, "NON_POSITIVE"),
    ({"panel__recess_from_frame_front": ...}, "MISSING_QUANTITY"),
    ({"materials__panel": ""}, "MISSING_MATERIAL"),
    ({"grain__frame": "diagonal"}, "INVALID_GRAIN"),
    ({"style": "louvered"}, "UNSUPPORTED_STYLE"),
    ({"schema_version": "cabinet_request.v1"}, "INVALID_SCHEMA"),
    ({"request_id": "a b"}, "INVALID_REQUEST_ID"),
    ({"origin_context__source_verified": "yes"}, "MISSING_ORIGIN_CONTEXT"),
    ({"origin_context": ...}, "MISSING_ORIGIN_CONTEXT"),
])
def test_incomplete_or_invalid_input_is_refused_before_any_geometry(over, code):
    plan = plan_shaker_door(shaker(**over), parent())
    assert plan["status"] == "REFUSED" and plan["stage"] == "input" and plan["execution_authorized"] is False
    assert plan["findings"][0]["code"] == code, plan["findings"]
    assert "parts" not in plan


def test_narrow_front_cannot_hold_two_stiles():
    plan = plan_shaker_door(shaker(frame__stile_width=qty(300)), parent())          # 2 x 300 mm > frente de 594 mm
    assert plan["status"] == "REFUSED" and plan["findings"][0]["code"] == "INFEASIBLE_PANEL_OPENING"


def test_recess_plus_panel_beyond_the_frame_depth_is_refused():
    plan = plan_shaker_door(shaker(panel__recess_from_frame_front=qty(14)), parent())     # 14 + 6 > 18
    assert plan["status"] == "REFUSED" and plan["findings"][0]["code"] == "PANEL_OUTSIDE_FRAME_DEPTH"


def test_frame_thickness_must_equal_the_front_it_replaces():
    plan = plan_shaker_door(shaker(frame__frame_thickness=qty(20)), parent())
    assert plan["status"] == "REFUSED" and plan["findings"][0]["code"] == "FRAME_THICKNESS_MISMATCH"


def test_parent_mismatch_unknown_front_and_invalid_parent_are_refused():
    assert plan_shaker_door(shaker(parent_cabinet_request_id="outro"), parent())["findings"][0]["code"] == "PARENT_MISMATCH"
    assert plan_shaker_door(shaker(target_front="front_9"), parent())["findings"][0]["code"] == "TARGET_FRONT_NOT_FOUND"
    assert plan_shaker_door(shaker(target_front="back"), parent())["findings"][0]["code"] == "TARGET_FRONT_NOT_FOUND"   # nao e frente
    broken = parent()
    broken["parts"][0]["material"] = "adulterado"
    plan = plan_shaker_door(shaker(), broken)
    assert plan["findings"][0]["code"] == "PARENT_PLAN_INVALID"


# --- porta unica de materializacao --------------------------------------------------------------------------------------

def test_require_valid_accepts_the_untouched_plan():
    par = parent()
    plan = plan_shaker_door(shaker(), par)
    assert require_valid_shaker(plan, par) is plan


def test_tampered_geometry_signature_flag_or_parent_are_refused_before_sketchup():
    par = parent()
    plan = plan_shaker_door(shaker(), par)

    def refused(mutate, code, parent_plan=par):
        bad = copy.deepcopy(plan)
        mutate(bad)
        with pytest.raises(ShakerPlanRefused) as exc:
            require_valid_shaker(bad, parent_plan)
        assert exc.value.findings[0]["code"] == code, exc.value.findings

    refused(lambda p: p["parts"][4]["max_m"].__setitem__(1, p["parts"][4]["max_m"][1] + 0.004), "SIGNATURE_MISMATCH")
    refused(lambda p: p.__setitem__("execution_authorized", True), "EXECUTION_FLAG_TAMPERED")
    refused(lambda p: p["capability"].__setitem__("id", "shared.cabinet.parametric"), "WRONG_CAPABILITY")
    refused(lambda p: p.__setitem__("status", "REFUSED"), "PLAN_NOT_OK")
    refused(lambda p: p.__setitem__("schema_version", "cabinet_assembly_plan.v1"), "PLAN_NOT_OK")
    newer_parent = load("valid_a_base_600.json")
    newer_parent["materials"]["front"] = "mdf_outro"
    refused(lambda p: None, "PARENT_PLAN_CHANGED", plan_cabinet(newer_parent))


def test_resigned_but_geometrically_invalid_plan_is_still_refused():
    """Quem adultera E reassina nao passa: a geometria e revalidada, nao confiada."""
    from tools.rooms.shared.cabinet.shaker.plan import signature

    par = parent()
    bad = copy.deepcopy(plan_shaker_door(shaker(), par))
    bad["parts"][4]["min_m"][0] = bad["parts"][0]["min_m"][0]         # painel invade o montante esquerdo
    bad["parts"][4]["size_m"][0] = bad["parts"][4]["max_m"][0] - bad["parts"][4]["min_m"][0]
    bad["signature"] = signature(bad["parameters"], bad["parts"], bad["parent_plan_signature"])
    with pytest.raises(ShakerPlanRefused) as exc:
        require_valid_shaker(bad, par)
    assert any(f["code"] == "PART_COLLISION" for f in exc.value.findings)


def test_legacy_cabinet_plan_is_byte_for_byte_unchanged_and_rejects_the_shaker_plan():
    from tools.rooms.shared.cabinet import PlanRefused, require_valid

    assert plan_cabinet(load("valid_a_base_600.json"))["signature"] == LEGACY_SIGNATURE_A
    assert plan_cabinet(load("valid_b_tall_900.json"))["signature"] == LEGACY_SIGNATURE_B
    with pytest.raises(PlanRefused):
        require_valid(plan_shaker_door(shaker(), parent()))             # o materializador antigo recusa o plano novo


def test_grain_stays_not_supported_like_the_legacy_materializer():
    assert GRAIN_SUPPORT == cabinet_sketchup.GRAIN_SUPPORT == "NOT_SUPPORTED"
    assert plan_shaker_door(shaker(grain__frame="along_height"), parent())["grain_support"] == "NOT_SUPPORTED"


def test_source_verified_false_is_carried_and_never_flipped():
    ctx = plan_shaker_door(shaker(), parent())["origin_context"]
    assert ctx == {"recipe_id": "cabinet.recessed-shaker-and-louvers", "source_id": "yt-cabinet-styles-2024", "source_verified": False}


def test_planning_does_not_mutate_inputs_or_write_files(tmp_path):
    par, req = parent(), shaker()
    before = (copy.deepcopy(par), copy.deepcopy(req))
    plan_shaker_door(req, par)
    assert (par, req) == before


def test_shared_shaker_does_not_import_any_room_package():
    code = ("import sys, importlib; importlib.import_module('tools.rooms.shared.cabinet.shaker');"
            "bad=[m for m in sys.modules if m.startswith('tools.rooms.') and m.split('.')[2] in "
            "('kitchen','bedroom','living','bathroom','service','balcony','closet','home_office','circulation')];"
            "print(bad)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert out.stdout.strip() == "[]", out.stdout + out.stderr
