"""FP-051/P1: safe DAG planning, absent skills, honest proofs and no execution."""
import copy
import json
from pathlib import Path

import pytest

from tools.rooms import furniture_goals as fg

ROOT = Path(__file__).resolve().parents[1]
TARGET = "artifacts/reference_lab/targets/planta_74/r004/kitchen_base_001.target.v1.json"


def _goal(*parts):
    return {"schema_version": "furniture_goal.v1", "goal_id": "kitchen_base_001",
            "room": "kitchen", "target_id": "planta_74.r004.kitchen_base_001",
            "target_ref": TARGET, "parts": list(parts), "execution_authorized": False}


def _part(id, binding, depends=()):
    return {"id": id, "binding_id": binding, "depends_on": list(depends)}


def test_draft_target_blocks_even_when_capability_has_l2():
    result = fg.plan_furniture_goal(_goal(_part("carcass", "bind.kitchen.cabinet")))
    assert result["state"] == "BLOCKED_TARGET_UNDEFINED"
    assert result["target_ready"] is False
    assert result["capability_dag"][0]["state"] == "L2_PASS"
    assert result["capability_dag"][0]["decision"] == "REUSE_CAPABILITY"
    assert result["execution_authorized"] is False
    assert "steps" not in result


def test_reused_capability_is_only_advice_when_target_approved(monkeypatch):
    monkeypatch.setattr(fg, "_target_result", lambda *a, **k: {"ready": True, "codes": []})
    result = fg.plan_furniture_goal(_goal(_part("carcass", "bind.kitchen.cabinet")))
    assert result["state"] == "PLAN_READY_NOT_EXECUTED"
    assert result["missing_capabilities"] == [] and result["execution_authorized"] is False
    assert result["next_step"] == "CHECK_PARAMETERS_AND_PLACEMENT"


def test_missing_skill_reported_without_fake_builder(monkeypatch):
    monkeypatch.setattr(fg, "_target_result", lambda *a, **k: {"ready": True, "codes": []})
    request = _goal(_part("front", "bind.kitchen.shaker"),
                    _part("carcass", "bind.kitchen.cabinet"),
                    _part("shelf", "bind.kitchen.countertop", ("carcass",)))
    result = fg.plan_furniture_goal(request)
    assert result["state"] == "BLOCKED_KNOWLEDGE_EVIDENCE"
    assert [p["part_id"] for p in result["capability_dag"]] == ["carcass", "front", "shelf"]
    assert result["next_gap"]["part_id"] == "shelf"
    assert result["next_gap"]["decision"] == "BLOCKED_MISSING_EVIDENCE"
    assert "steps" not in result and result["execution_authorized"] is False


def test_unreviewed_recipe_cannot_borrow_human_review_of_same_video():
    catalog = json.loads((ROOT / "tools/rooms/capability_catalog.v1.json").read_text())
    assert "cabinet.countertop-separate-and-bevel" not in fg._reviewed_recipe(
        ["cabinet.countertop-separate-and-bevel"], catalog, ROOT)
    assert "cabinet.front-gaps-and-profiles" in fg._reviewed_recipe(
        ["cabinet.front-gaps-and-profiles"], catalog, ROOT)


@pytest.mark.parametrize("parts", [
    [_part("front", "bind.kitchen.shaker", ("front",))],
    [_part("front", "bind.kitchen.shaker", ("shelf",)),
     _part("shelf", "bind.kitchen.countertop", ("front",))],
    [_part("front", "bind.kitchen.shaker", ("missing",))],
    [_part("front", "bind.kitchen.shaker"), _part("front", "bind.kitchen.shaker")],
])
def test_dag_cycles_or_invalid_edges_fail_closed(parts):
    r = fg.plan_furniture_goal(_goal(*parts))
    assert r["state"] == "BLOCKED_DEPENDENCY_CYCLE"
    assert r["execution_authorized"] is False


def test_unknown_binding_cross_room_and_path_traversal():
    wrong = fg.plan_furniture_goal(_goal(_part("carcass", "bind.bedroom.wardrobe")))
    assert wrong["state"] == "BLOCKED_CAPABILITY_NOT_IN_PROFILE"
    req = _goal(_part("carcass", "bind.kitchen.cabinet"))
    req["target_ref"] = "../outside.json"
    assert fg.plan_furniture_goal(req)["state"] == "BLOCKED_GOAL_SCHEMA"
    req = _goal(_part("carcass", "bind.kitchen.cabinet"))
    req["execution_authorized"] = True
    assert fg.plan_furniture_goal(req)["state"] == "BLOCKED_GOAL_SCHEMA"


def test_stale_evidence_not_promoted_to_reuse(monkeypatch):
    monkeypatch.setattr(fg, "_target_result", lambda *a, **k: {"ready": True, "codes": []})
    monkeypatch.setattr(fg, "_evidence_current", lambda *a: False)
    r = fg.plan_furniture_goal(_goal(_part("carcass", "bind.kitchen.cabinet")))
    assert r["state"] == "BLOCKED_EVIDENCE_STALE"
    assert r["next_gap"]["decision"] == "REVALIDATE_L2"


def test_target_scope_does_not_inherit_room_style():
    goal = _goal(_part("carcass", "bind.kitchen.cabinet"))
    goal["target_id"] = "wrong_target"
    r = fg.plan_furniture_goal(goal)
    assert not r["target_ready"] and r["state"] == "BLOCKED_TARGET_UNDEFINED"


def test_second_room_cannot_reuse_kitchen_binding_implicitly():
    goal = _goal(_part("carcass", "bind.kitchen.cabinet"))
    goal["room"] = "bathroom"
    r = fg.plan_furniture_goal(goal)
    assert r["state"] == "BLOCKED_CAPABILITY_NOT_IN_PROFILE"


def test_schemas_reject_extra_unknown_steps_and_duplicate_dependencies():
    goal = _goal(_part("carcass", "bind.kitchen.cabinet", ("front", "front")))
    assert fg.plan_furniture_goal(goal)["state"] == "BLOCKED_GOAL_SCHEMA"
    goal = _goal(_part("carcass", "bind.kitchen.cabinet"))
    goal["steps"] = ["run sketchup"]
    assert fg.plan_furniture_goal(goal)["state"] == "BLOCKED_GOAL_SCHEMA"
