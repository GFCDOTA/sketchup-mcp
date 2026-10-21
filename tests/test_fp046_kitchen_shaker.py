"""FP-046/P4 — adapter e fluxo opt-in da porta Shaker na cozinha, com SketchUp DUBLE.

Prova ORDEM, bloqueios e a ausencia de promocao implicita (D46-09). A prova real (SKP salvo/reaberto na cozinha da planta_74) e o
L2 em artifacts/review/fp046/p4_kitchen_shaker_l2/. Escala da planta_74 -> marcador `planta74_scale`.
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
        "origin_context": {"recipe_id": "cabinet.recessed-shaker-and-louvers", "source_id": "yt-cabinet-styles-2024",
                           "source_verified": False},
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


# --- catalogo/perfil: nada foi promovido (D46-09) ----------------------------------------------------------------------

def test_binding_stays_blocked_and_nothing_was_promoted():
    catalog = cc.load_catalog()
    binding = next(b for b in catalog["bindings"] if b["id"] == "bind.kitchen.shaker")
    assert binding["capability_id"] is None and binding["gap"]
    assert "shared.cabinet.front.shaker" not in {c["id"] for c in catalog["capabilities"]}
    profile = sp.load_profile("kitchen")
    assert not set(flow.PREPROMOTION_TOOLS) & set(profile["tool_allowlist"])
    plan = sp.plan({"text": SHAKER_TEXT, "room": "kitchen"})
    assert plan["state"] == "BLOCKED_CAPABILITY_MISSING"


# --- fluxo opt-in com SketchUp duble -----------------------------------------------------------------------------------------

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


def _run(world, req=None, *, ack=True, su=None, **kw):
    return flow.run_prepromotion_request(req or request(), out_dir=world.out, base_skp=world.base, su=su or world.su,
                                         mode="interactive", close_pids=False, prepromotion_ack=ack, **kw)


def test_default_stops_at_the_specialist_verdict_without_touching_sketchup(tmp_path, consensus):
    w = World(tmp_path)
    req = request()
    snap = copy.deepcopy(req)
    t = _run(w, req, ack=False, su=Boom())
    assert t["state"] == "BLOCKED_CAPABILITY_MISSING" and t["promotion"] == "NOT_PROMOTED"
    assert w.state["launches"] == [] and not w.out.exists() and req == snap and t["input_unchanged"] is True
    k = next(s for s in t["steps"] if s["step"] == "knowledge")
    assert k["binding"] == "bind.kitchen.shaker" and k["capability_id"] is None
    assert k["source_evidence"] == {"yt-cabinet-styles-2024": "TRANSCRIPT_AND_DESCRIPTION_ONLY"}
    assert "evidence" not in t and t["execution_authorized"] is False


def test_ack_runs_the_whole_chain_in_order_and_never_promotes(tmp_path, consensus):
    w = World(tmp_path)
    req = request()
    snap = copy.deepcopy(req)
    t = _run(w, req)
    assert t["state"] == "PREPROMOTION_L2_VERIFIED", t["steps"][-3:]
    assert [s["step"] for s in t["steps"]] == ["request", "project_room", "consensus_requirements", "knowledge", "specialist_plan",
                                                "prepromotion", "plan_validation", "allowlist", "baseline_inspect", "job_parent",
                                                "job_shaker", "reopen_inspection", "kitchen_anchor_after", "evidence"]
    assert w.state["launches"] == ["shaker_inspect.rb", "cabinet_build.rb", "shaker_build.rb", "shaker_inspect.rb"]
    ev = t["evidence"]
    assert t["promotion"] == ev["promotion"] == "NOT_PROMOTED" and ev["source_verified"] is False
    assert ev["non_cabinet_fingerprint_before"] == ev["non_cabinet_fingerprint_after"] == "fp0"
    assert "PENDING_HUMAN" in ev["visual_review"] and t["visual_review"] == "PENDING_HUMAN"
    assert [g["result"] for g in ev["gates"]["parent"] + ev["gates"]["composition"]] == ["PASS"] * 8
    assert t["execution_authorized"] is False and t["input_unchanged"] is True and req == snap
    assert w.base.read_bytes() == b"SKP-FURNISHED"
    assert next(s for s in t["steps"] if s["step"] == "allowlist")["status"] == "PREPROMOTION"


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
])
def test_ack_bypasses_only_the_missing_capability_not_other_blocks(tmp_path, consensus, mutate, state):
    w = World(tmp_path)
    req = request()
    mutate(req)
    t = _run(w, req, su=Boom())
    assert t["state"] == state and w.state["launches"] == [] and not w.out.exists()


def test_ack_with_a_refused_plan_does_not_boot_sketchup(tmp_path, consensus):
    w = World(tmp_path)
    req = request()
    req["inputs"]["pose.x"] = {"value": 0.5, "unit": "m", "origin": "user_request"}
    t = _run(w, req, su=Boom())
    assert t["state"] == "BLOCKED_PLAN_REFUSED" and w.state["launches"] == [] and "evidence" not in t
    no_block = request()
    del no_block["shaker"]
    t2 = _run(w, no_block, su=Boom())
    assert t2["state"] == "BLOCKED_INPUT_INCOMPLETE" and w.state["launches"] == []


def test_job_failure_and_geometry_mismatch_leave_no_positive_proof(tmp_path, consensus):
    w = World(tmp_path / "a", die_on="shaker_build.rb")
    t = _run(w)
    assert t["state"] == "JOB_FAILED" and "evidence" not in t and not list(w.out.rglob("manifest.json"))
    w2 = World(tmp_path / "b", tamper=True)
    t2 = _run(w2)
    assert t2["state"] == "VERIFY_FAILED" and not list(w2.out.rglob("manifest.json"))
    assert next(s for s in t2["steps"] if s["step"] == "reopen_inspection")["failed"]


def test_if_the_binding_is_ever_promoted_the_same_flow_needs_no_ack(tmp_path, consensus, monkeypatch):
    real = sp.plan
    monkeypatch.setattr(sp, "plan", lambda r, root=sp.ROOT: {"state": sp.PLAN_READY, "binding": "bind.kitchen.shaker",
                                                              "capability": {"id": "x"}, "steps": []} if r.get("room") else real(r))
    w = World(tmp_path)
    t = _run(w, ack=False)
    assert t["state"] == "DONE_L2_VERIFIED" and t["promotion"] == "PROMOTED"


def test_the_plain_front_flow_is_untouched_by_this_phase():
    from tools.rooms.kitchen.capabilities import cabinet, cabinet_flow
    for module in (cabinet, cabinet_flow):
        text = Path(module.__file__).read_text("utf-8")
        assert "shaker" not in text.lower(), module.__name__
