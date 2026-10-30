"""FP-055 P5 (#416): receita -> operacao -> implementacao -> prova, com regra funcional / receita / referencia estetica separadas."""
from __future__ import annotations

from tools.rooms import recipe_resolution as rr


def states(room):
    return {(r["recipe_id"], r["capability"]["id"] if r["capability"] else None): r["state"] for r in rr.resolve_room(room)["constructive_recipes"]}


def test_kitchen_recipes_resolve_to_proven_capabilities_with_operation_and_symbols():
    res = rr.resolve_room("kitchen")
    r = next(x for x in res["constructive_recipes"] if x["capability"] and x["capability"]["id"] == "kitchen.cabinet.shaker-door")
    assert r["state"] == "RESOLVED_PROVEN" and r["operation"] and r["implementation_symbols"]
    assert r["capability"]["validation"] == "L2_PASS" and r["capability"]["visual"] == "NOT_REVIEWED"        # visual nunca vira APPROVED aqui


def test_recipes_without_a_capability_are_refused_with_the_declared_gap_not_invented():
    s = states("kitchen")
    for rid in ("cabinet.drawer-box-and-hardware", "cabinet.countertop-separate-and-bevel", "cabinet.sink-and-wet-channel-cutouts"):
        assert s[(rid, None)] == "BLOCKED_CAPABILITY_MISSING"
    gap = next(x for x in rr.resolve_room("kitchen")["constructive_recipes"] if x["recipe_id"] == "cabinet.drawer-box-and-hardware")
    assert gap["reason"] and gap["capability"] is None


def test_recipe_listed_by_the_specialist_but_cited_by_no_binding_is_unbound_never_selected_silently():
    assert set(states("bedroom").values()) == {"UNBOUND"}


def test_the_three_concepts_come_from_different_stores_and_resolution_never_authorizes_execution():
    res = rr.resolve_room("kitchen", room_ids=("r004",))
    assert res["functional_rules"] and all(isinstance(x, str) for x in res["functional_rules"])      # constraints do perfil
    assert res["aesthetic_references"] and res["aesthetic_references"][0]["state"] == "DRAFT_BLOCKED"   # alvo FP-052, nao autoriza
    assert res["execution_authorized"] is False
    assert rr.resolve_room("kitchen")["aesthetic_references"] == []                                    # sem room_ids nao ha ligacao


def test_shared_techniques_count_is_measured_not_assumed():
    shared = rr.shared_techniques()
    assert all(len(rooms) >= 2 for rooms in shared.values())
