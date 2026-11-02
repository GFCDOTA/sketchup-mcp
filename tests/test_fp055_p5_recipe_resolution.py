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


# ------------------------------------------------------------------ ligacao ao orquestrador (plan_room): a receita nao e mais so "selecionada"
def _plan_room_bathroom():
    from core.pipeline_contracts import CapabilityLedger
    from tests.test_fp054_f2c_candidates import ROOM, _scene
    from tools.orchestration import intelligent_pipeline as ip
    con, boxes, ifaces = _scene()
    led = CapabilityLedger()
    return ip.plan_room(con, boxes, ifaces, "r_syn", "BATHROOM", ROOM, "tools.rooms.bathroom.layout.build_boxes", led), led


def test_plan_room_carries_the_recipe_resolution_and_records_it_in_the_ledger_trail():
    out, led = _plan_room_bathroom()
    res = out["recipe_resolution"]
    assert {r["recipe_id"] for r in res} == {"cabinet.materials-and-texture-direction", "cabinet.sink-and-wet-channel-cutouts"}
    assert {r["state"] for r in res} == {"BLOCKED_CAPABILITY_MISSING"}   # banheiro: lacunas DECLARADAS (W1), nunca sucesso nem UNBOUND
    trail = led.to_dict()["recipe.cabinet.sink-and-wet-channel-cutouts"]["trail"]
    assert "BLOCKED_CAPABILITY_MISSING" in next(e["evidence"] for e in trail if e["state"] == "SELECTED")


def test_recipe_resolution_never_executes_anything_nor_promotes_a_recipe_to_consumed():
    out, led = _plan_room_bathroom()
    assert led.state("recipe.cabinet.sink-and-wet-channel-cutouts") == "SELECTED"          # resolver nao e consumir
    assert all(r.get("capability") is None or r["state"].startswith("RESOLVED") for r in out["recipe_resolution"])


# ------------------------------------------------------------------ banheiro: receitas do gabinete da pia (W1) sao lacunas DECLARADAS (#416)
_BATH_GAPS = {"cabinet.sink-and-wet-channel-cutouts": "bind.bathroom.sink-cutout",
              "cabinet.materials-and-texture-direction": "bind.bathroom.vanity-materials"}


def test_bathroom_vanity_recipes_are_declared_gaps_with_the_reason_never_unbound():
    res = {r["recipe_id"]: r for r in rr.resolve_room("bathroom")["constructive_recipes"]}
    assert set(res) == set(_BATH_GAPS)
    for rid, bid in _BATH_GAPS.items():
        r = res[rid]
        assert r["state"] == "BLOCKED_CAPABILITY_MISSING" and r["capability"] is None and r["bindings"] == [bid]
        assert "W1" in r["reason"]                                    # o motivo aponta a microfase que falta (gabinete da pia)


def test_bathroom_gaps_do_not_borrow_a_shared_capability_to_fake_a_two_component_technique():
    # ligar o banheiro ao shared.cabinet sem consumidor real faria a P5 "passar" no papel: integracao nominal (FP-055)
    from tools.rooms import capability_catalog as cc
    cat = cc.load_catalog(rr.ROOT / "tools/rooms/capability_catalog.v1.json")
    assert {b["id"]: b["capability_id"] for b in cat["bindings"] if b["id"] in _BATH_GAPS.values()} == dict.fromkeys(_BATH_GAPS.values())
    assert not any("bathroom" in rooms for rooms in rr.shared_techniques().values())


def test_bathroom_cutout_or_grain_request_is_refused_with_the_gap_not_planned_by_the_layout_binding():
    # antes: "banheiro"/"cuba" casavam so o layout e o plano saia PLAN_READY para uma tecnica sem capacidade (falso PASS)
    from tools.rooms import specialists as sp
    for text, bid in (("recorte da cuba no gabinete do banheiro", "bind.bathroom.sink-cutout"),
                      ("orientacao do veio da textura no gabinete do banheiro", "bind.bathroom.vanity-materials")):
        out = sp.plan({"text": text, "room": "bathroom"})
        assert (out["state"], out.get("binding")) == ("BLOCKED_CAPABILITY_MISSING", bid), text
        assert out["knowledge_only"] is True and out["execution_authorized"] is False


def test_bathroom_layout_request_with_a_sink_still_routes_to_the_layout_binding():
    from tools.rooms import specialists as sp
    out = sp.plan({"text": "layout do banheiro com cuba e box", "room": "bathroom"})
    assert out["binding"] == "bind.bathroom.layout" and out["state"] != "BLOCKED_CAPABILITY_MISSING"
