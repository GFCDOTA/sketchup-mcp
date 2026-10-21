"""FP-046/P4+P5 — adapter e fluxo da porta Shaker na cozinha, com SketchUp DUBLE.

Prova ORDEM, bloqueios e que nao ha contorno (o fluxo so roda se o catalogo/perfil liberarem a Shaker). A prova real (SKP
salvo/reaberto na cozinha da planta_74) e o L2 em artifacts/review/fp046/promotion_l2/. Escala da planta_74 -> `planta74_scale`.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.test_fp046_shaker_sketchup import Boom, inspected_from
from tests.test_sketchup_specialist import FakeSystem
from tools.rooms import capability_catalog as cc
from tools.rooms import specialists as sp
from tools.rooms.kitchen.capabilities import shaker as kshaker
from tools.rooms.kitchen.capabilities import shaker_flow as flow
from tools.rooms.shared.cabinet.shaker import ShakerPlanRefused, require_valid_shaker
from tools.sketchup.process import Locations, SketchUp

pytestmark = pytest.mark.planta74_scale

ROOT = Path(__file__).resolve().parents[1]
EXE = Path("C:/SU/SketchUp.exe")
P7 = json.loads((ROOT / "artifacts/review/fp043/p7_kitchen_cabinet/request.json").read_text("utf-8"))
SHAKER_TEXT = "porta shaker na cozinha com painel rebaixado"


def shaker_block(parent_id="shaker-kitchen-parent", **over):
    block = {
        "schema_version": "shaker_door_request.v1", "request_id": "shaker-kitchen-001", "parent_cabinet_request_id": parent_id,
        "target_front": "front", "style": "recessed_shaker",
        "frame": {"stile_width": {"value": 50, "unit": "mm", "origin": "user_request"},
                  "rail_height": {"value": 50, "unit": "mm", "origin": "user_request"},
                  "frame_thickness": {"value": 16, "unit": "mm", "origin": "user_request"}},       # = panels.front do pai
        "panel": {"thickness": {"value": 6, "unit": "mm", "origin": "user_request"},
                  "recess_from_frame_front": {"value": 4, "unit": "mm", "origin": "user_request"}},
        "materials": {"frame": "mdf_nogueira", "panel": "mdf_nogueira"}, "grain": {"frame": "none", "panel": "none"},
        "origin_context": {"recipe_id": "cabinet.front-gaps-and-profiles", "source_id": "yt-cabinet-tips-2021",
                           "source_verified": True},
    }
    block.update(over)
    return block


def request(**kw):
    req = copy.deepcopy(P7)
    req["request_id"] = "shaker-kitchen-parent"
    req["text"] = SHAKER_TEXT
    req["shaker"] = shaker_block()
    req.update(kw)
    return req


@pytest.fixture(scope="module")
def consensus():
    from core import scale
    if abs(scale.PT_TO_M - 0.0259) > 1e-9:
        pytest.skip("escala da planta_74 (PT_TO_M=0.0259) nao ativa")
    from tools.rooms.kitchen.capabilities.cabinet_flow import CONSENSUS_DEFAULT
    return json.loads(Path(CONSENSUS_DEFAULT).read_text("utf-8"))


def _plan(consensus, req=None, shaker=None):
    from tools.rooms.kitchen.capabilities.cabinet_flow import inputs_to_cabinet_request
    req = req or request()
    cab = inputs_to_cabinet_request(req["request_id"], req["inputs"], req["materials"], req.get("grain"))
    return kshaker.plan_kitchen_shaker(consensus, "r004", cab, shaker or req["shaker"])


# --- adapter: gates ------------------------------------------------------------------------------------------------------

def test_parent_and_composition_gates_all_pass_in_order(consensus):
    out = _plan(consensus)
    assert out["status"] == "OK" and out["execution_authorized"] is False
    assert [g["gate"] for g in out["parent_plan"]["gates"]] == ["hydraulic_anchor", "architecture", "furniture_overlap", "circulation"]
    assert [g["gate"] for g in out["gates"]] == ["hydraulic_anchor", "architecture", "furniture_overlap", "circulation"]
    assert all(g["result"] == "PASS" for g in out["parent_plan"]["gates"] + out["gates"])
    shaker = out["shaker_plan"]
    assert require_valid_shaker(shaker, out["parent_plan"]) is shaker and shaker["adapter"]["room"] == "kitchen"


def test_planning_does_not_mutate_consensus_or_request(consensus):
    snap_c, req = copy.deepcopy(consensus), request()
    snap_r = copy.deepcopy(req)
    _plan(consensus, req)
    assert consensus == snap_c and req == snap_r


def test_parent_outside_the_kitchen_is_refused_before_any_shaker_plan(consensus):
    req = request()
    req["inputs"]["pose.x"] = {"value": 0.5, "unit": "m", "origin": "user_request"}
    out = _plan(consensus, req)
    assert out["status"] == "REFUSED" and out["stage"] == "parent_cabinet:kitchen_gate:architecture" and out["shaker_plan"] is None


def test_invalid_shaker_geometry_is_refused_at_the_shaker_stage(consensus):
    bad = shaker_block(frame={**shaker_block()["frame"], "frame_thickness": {"value": 20, "unit": "mm", "origin": "user_request"}})
    out = _plan(consensus, shaker=bad)
    assert out["status"] == "REFUSED" and out["stage"] == "shaker_plan:geometry"
    assert out["shaker_plan"]["findings"][0]["code"] == "FRAME_THICKNESS_MISMATCH"


def test_composition_circulation_sees_the_five_shaker_parts_and_not_the_replaced_front(consensus, monkeypatch):
    from tools.validation import circulation_gate

    real, seen = circulation_gate.gate, []

    def spy(con, boxes, room_id):
        seen.append([b["label"] for b in boxes if b.get("kind") == "cabinet"])
        return real(con, boxes, room_id)

    monkeypatch.setattr(circulation_gate, "gate", spy)
    out = _plan(consensus)
    assert out["status"] == "OK" and len(seen) == 2
    assert "front" in seen[0] and "stile_left" not in seen[0]                      # pai: frente lisa
    comp = seen[1]
    assert "front" not in comp and {"stile_left", "stile_right", "rail_top", "rail_bottom", "recessed_panel"} <= set(comp)


def test_composition_circulation_failure_refuses_before_any_job(consensus, monkeypatch):
    from tools.validation import circulation_gate

    real = circulation_gate.gate

    def fail_on_composition(con, boxes, room_id):
        if any(b.get("label") == "stile_left" for b in boxes):
            return {"result": "FAIL", "room": "COZINHA", "checks": {}}
        return real(con, boxes, room_id)

    monkeypatch.setattr(circulation_gate, "gate", fail_on_composition)
    out = _plan(consensus)
    assert out["status"] == "REFUSED" and out["stage"] == "kitchen_gate:circulation"
    assert [g["result"] for g in out["gates"]] == ["PASS", "PASS", "PASS", "FAIL"]
    with pytest.raises(ShakerPlanRefused) as exc:
        require_valid_shaker(out["shaker_plan"], out["parent_plan"])
    assert exc.value.findings[0]["code"] in ("KITCHEN_GATE_FAILED", "PLAN_NOT_OK") or any(
        f["code"] == "KITCHEN_GATE_FAILED" for f in exc.value.findings)


def test_composition_overlap_failure_refuses_even_though_the_parent_passed(consensus, monkeypatch):
    from tools.rooms.kitchen import layout
    from tools.rooms.kitchen.capabilities.cabinet import _boxes_for_plan
    from tools.rooms.kitchen.capabilities.cabinet_flow import inputs_to_cabinet_request
    from tools.rooms.shared.cabinet import plan_cabinet

    r = request()
    footprint_box = _boxes_for_plan(plan_cabinet(inputs_to_cabinet_request(r["request_id"], r["inputs"], r["materials"], r.get("grain"))))[-1]       # a frente (ultima peca): e onde a Shaker entra
    real_boxes, real_plan, state = layout.build_boxes, kshaker.plan_shaker_door, {"after_parent": False, "clashes": 0}

    def shaker_planned(*a, **k):                                       # marca o instante em que o PAI ja passou todos os gates
        state["after_parent"] = True
        return real_plan(*a, **k)

    def clash_only_in_the_composition(con, room_id, *a, **k):
        boxes, meta = real_boxes(con, room_id, *a, **k)
        if state["after_parent"]:
            state["clashes"] += 1
            boxes = list(boxes) + [dict(footprint_box, label="intruso", decorative=False)]
        return boxes, meta

    monkeypatch.setattr(kshaker, "plan_shaker_door", shaker_planned)
    monkeypatch.setattr(layout, "build_boxes", clash_only_in_the_composition)
    out = _plan(consensus)
    assert state["clashes"] >= 1 and out["status"] == "REFUSED" and out["stage"] == "kitchen_gate:furniture_overlap"
    assert [g["result"] for g in out["parent_plan"]["gates"]] == ["PASS"] * 4                  # o pai passou sozinho
    assert [g["gate"] for g in out["gates"]][-1] == "furniture_overlap" and out["gates"][-1]["result"] == "FAIL"


# --- catalogo/perfil: promovida, mas a aparencia segue com o Felipe ---------------------------------------------------------

def test_binding_is_registered_with_an_inspected_reviewed_source_and_the_tools_are_allowlisted():
    catalog = cc.load_catalog()
    binding = next(b for b in catalog["bindings"] if b["id"] == "bind.kitchen.shaker")
    assert binding["capability_id"] == "kitchen.cabinet.shaker-door" and not binding.get("gap")
    caps = {c["id"]: c for c in catalog["capabilities"]}
    assert {"kitchen.cabinet.shaker-door", "shared.cabinet.front.shaker"} <= set(caps)
    assert all(caps[i]["visual"]["state"] == "NOT_REVIEWED" for i in ("kitchen.cabinet.shaker-door", "shared.cabinet.front.shaker"))
    profile = sp.load_profile("kitchen")
    assert set(flow.FLOW_TOOLS) <= set(profile["tool_allowlist"])
    assert {"kitchen.cabinet.shaker-door", "shared.cabinet.front.shaker"} <= set(profile["capability_ids"])
    assert profile["execution_authorized"] is False


def test_the_flow_has_no_bypass_argument():
    import inspect
    assert not [p for p in inspect.signature(flow.run_request).parameters if "ack" in p or "promotion" in p or "bypass" in p]
    assert not hasattr(flow, "run_prepromotion_request") and not hasattr(flow, "BYPASSABLE")


# --- fluxo com SketchUp duble ------------------------------------------------------------------------------------------------

class World:
    def __init__(self, tmp_path, *, tamper=False, die_on=None):
        self.state = {"parent": None, "shaker": None, "launches": []}
        self.tamper, self.die_on = tamper, die_on
        st = self.state

        def job(cmd, env, handle):
            script = Path(cmd[3]).name
            st["launches"].append(script)
            params = json.loads(Path(env["SKMCP_PARAMS"]).read_text("utf-8"))
            if script == self.die_on:
                handle.returncode = 1
                return
            if script == "cabinet_build.rb":
                st["parent"] = params["plan"]
                Path(cmd[1]).write_bytes(b"SKP-PARENT")
                res = {"ok": True, "saved": True, "built": True, "sketchup_version": "26.0.429", "replaced_previous": 0}
            elif script == "shaker_build.rb":
                st["shaker"] = params["plan"]
                Path(cmd[1]).write_bytes(b"SKP-SHAKER")
                res = {"ok": True, "saved": True, "built": True, "sketchup_version": "26.0.429", "removed_front": params["plan"]["replaces_part"],
                       "grain_support": "NOT_SUPPORTED"}
            else:
                if st["shaker"] is None:
                    res = {"ok": True, "cabinets": [], "non_cabinet": {"count": 1, "fingerprint": "fp0", "items": 1}}
                else:
                    res = {"ok": True, **inspected_from(st["parent"], st["shaker"])}
                    if self.tamper:
                        res["cabinets"][0]["shakers"][0]["parts"][4]["world_corners_m"][0][0] += 0.01
            Path(env["SKMCP_RESULT"]).write_text(json.dumps(res), "utf-8")

        self.su = SketchUp(FakeSystem(job=job, virtual=(EXE,)),
                           Locations(exe=EXE, plugins_dir=Path("C:/SU/Plugins"), vray_exe=Path("C:/SU/vray.exe")))
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.base = tmp_path / "base.skp"
        self.base.write_bytes(b"SKP-FURNISHED")
        self.out = tmp_path / "out"


def _run(world, req=None, *, su=None, **kw):
    return flow.run_request(req or request(), out_dir=world.out, base_skp=world.base, su=su or world.su, mode="interactive",
                            close_pids=False, **kw)


def test_whole_chain_runs_in_order_with_the_specialist_verdict_and_never_authorizes_or_approves(tmp_path, consensus):
    w = World(tmp_path)
    req = request()
    snap = copy.deepcopy(req)
    t = _run(w, req)
    assert t["state"] == "DONE_L2_VERIFIED", t["steps"][-3:]
    assert [s["step"] for s in t["steps"]] == ["request", "project_room", "consensus_requirements", "knowledge", "specialist_plan",
                                                "capability", "plan_validation", "allowlist", "baseline_inspect", "job_parent",
                                                "job_shaker", "reopen_inspection", "kitchen_anchor_after", "evidence"]
    assert w.state["launches"] == ["shaker_inspect.rb", "cabinet_build.rb", "shaker_build.rb", "shaker_inspect.rb"]
    k = next(s for s in t["steps"] if s["step"] == "knowledge")
    assert k["capability_id"] == "kitchen.cabinet.shaker-door"
    assert k["source_evidence"]["yt-cabinet-tips-2021"] == "TRANSCRIPT_AND_VISUAL_WALKTHROUGH"
    assert k["human_review"]["yt-cabinet-tips-2021"]["reviewer"] == "Felipe"
    assert next(s for s in t["steps"] if s["step"] == "specialist_plan")["state"] == "PLAN_READY_NOT_EXECUTED"
    ev = t["evidence"]
    assert ev["non_cabinet_fingerprint_before"] == ev["non_cabinet_fingerprint_after"] == "fp0" and ev["source_verified"] is True
    assert "PENDING_HUMAN" in ev["visual_review"] and t["visual_review"] == "PENDING_HUMAN"
    assert [g["result"] for g in ev["gates"]["parent"] + ev["gates"]["composition"]] == ["PASS"] * 8
    assert t["execution_authorized"] is False and t["input_unchanged"] is True and req == snap
    assert w.base.read_bytes() == b"SKP-FURNISHED"


def test_same_key_is_not_redone_and_other_request_gets_another_key(tmp_path, consensus):
    w = World(tmp_path)
    first = _run(w)
    n = len(w.state["launches"])
    again = _run(w)
    assert again["state"] == "ALREADY_DONE" and len(w.state["launches"]) == n and again["skp_sha256"] == first["evidence"]["skp_sha256"]
    other = request()
    other["shaker"]["panel"]["recess_from_frame_front"]["value"] = 3
    assert _run(w, other)["idempotency_key"] != first["idempotency_key"]


@pytest.mark.parametrize("mutate,state", [
    (lambda r: r.update(touches=["walls"]), "BLOCKED_ARCHITECTURE_CHANGE"),
    (lambda r: r.update(text=SHAKER_TEXT + " e remover a parede oeste"), "BLOCKED_ARCHITECTURE_CHANGE"),
    (lambda r: r.update(tool="mcp:su_apply_edits"), "BLOCKED_TOOL_NOT_ALLOWED"),
    (lambda r: r["shaker"]["frame"].pop("stile_width"), "BLOCKED_INPUT_INCOMPLETE"),
    (lambda r: r["shaker"]["panel"]["thickness"].pop("origin"), "BLOCKED_INPUT_INCOMPLETE"),
    (lambda r: r.pop("shaker"), "BLOCKED_INPUT_INCOMPLETE"),
])
def test_blocks_before_any_sketchup(tmp_path, consensus, mutate, state):
    w = World(tmp_path)
    req = request()
    mutate(req)
    t = _run(w, req, su=Boom())
    assert t["state"] == state and w.state["launches"] == [] and not w.out.exists() and "evidence" not in t


def test_refused_plans_do_not_boot_sketchup(tmp_path, consensus):
    w = World(tmp_path)
    outside = request()
    outside["inputs"]["pose.x"] = {"value": 0.5, "unit": "m", "origin": "user_request"}
    thick = request()
    thick["shaker"]["frame"]["frame_thickness"] = {"value": 20, "unit": "mm", "origin": "user_request"}
    for req in (outside, thick):
        t = _run(w, req, su=Boom())
        assert t["state"] == "BLOCKED_PLAN_REFUSED" and w.state["launches"] == [] and "evidence" not in t


def test_a_shaker_block_in_a_request_that_does_not_ask_for_shaker_is_refused(tmp_path, consensus):
    w = World(tmp_path)
    req = request(text="Quero um gabinete baixo de frentes lisas na cozinha")
    t = _run(w, req, su=Boom())
    assert t["state"] == "BLOCKED_TECHNIQUE_UNRESOLVED" and "nao pede porta Shaker" in t["reason"] and w.state["launches"] == []


def test_source_verified_true_needs_a_recorded_human_review(tmp_path, consensus):
    w = World(tmp_path)
    req = request()
    req["shaker"]["origin_context"]["source_id"] = "yt-cabinet-styles-2024"             # fonte so descritiva: sem revisao humana
    t = _run(w, req, su=Boom())
    assert t["state"] == "BLOCKED_KNOWLEDGE_EVIDENCE" and w.state["launches"] == []
    req["shaker"]["origin_context"]["source_verified"] = False                          # declarar honestamente nao e bloqueado
    assert _run(w, req)["state"] == "DONE_L2_VERIFIED"


def test_if_the_specialist_stops_releasing_the_capability_the_flow_stops_with_no_way_around(tmp_path, consensus, monkeypatch):
    real = sp.plan
    monkeypatch.setattr(sp, "plan", lambda r, root=sp.ROOT: {"state": "BLOCKED_CAPABILITY_MISSING", "reason": "retirada", "next_step": "x",
                                                              "binding": "bind.kitchen.shaker"} if r.get("room") else real(r))
    w = World(tmp_path)
    t = _run(w, su=Boom())
    assert t["state"] == "BLOCKED_CAPABILITY_MISSING" and w.state["launches"] == [] and not w.out.exists()


def test_job_failure_and_geometry_mismatch_leave_no_positive_proof(tmp_path, consensus):
    w = World(tmp_path / "a", die_on="shaker_build.rb")
    t = _run(w)
    assert t["state"] == "JOB_FAILED" and "evidence" not in t and not list(w.out.rglob("manifest.json"))
    w2 = World(tmp_path / "b", tamper=True)
    t2 = _run(w2)
    assert t2["state"] == "VERIFY_FAILED" and not list(w2.out.rglob("manifest.json"))
    assert next(s for s in t2["steps"] if s["step"] == "reopen_inspection")["failed"]


def test_the_plain_front_flow_refuses_shaker_instead_of_building_a_plain_cabinet(tmp_path, consensus):
    """R-19: um pedido de Shaker no fluxo de frentes lisas nao pode virar gabinete liso em silencio."""
    from tools.rooms.kitchen.capabilities.cabinet_flow import run_request as plain_run
    w = World(tmp_path)
    req = request()
    req["inputs"].update(flow.shaker_inputs(req["shaker"]))
    t = plain_run({k: v for k, v in req.items() if k != "shaker"}, out_dir=w.out, base_skp=w.base, su=Boom(), mode="interactive", close_pids=False)
    assert t["state"] == "BLOCKED_CAPABILITY_MISMATCH" and w.state["launches"] == []
