"""FP-055 P5 / B3 / S1 (#416, #473, #476): a MESMA tecnica de marcenaria (shared.cabinet.parametric) serve a mais de um componente.

Micro-prova L1 PROPOSED: criado-mudo e armario de lavanderia entram como pedidos `cabinet_request.v1` com origem `derived` (das proporcoes de
classe do NightstandSpec e do layout de servico), nao `user_request`. Nada e colocado no apartamento nem substitui movel existente; entrega real
exige `reference_target` aprovado (construction_core_microphases DoD 2.5) e L2 no SketchUp."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from tools.rooms.shared.cabinet.plan import (
    CAPABILITY_ID,
    CAPABILITY_VERSION,
    plan_cabinet,
    require_valid,
)
from tools.rooms.shared.nightstand import nightstand_spec

FIX = Path(__file__).resolve().parents[1] / "fixtures/synthetic_cabinets"
KITCHEN = "valid_a_base_600"
PROPOSED = {"proposed_nightstand": "criado-mudo", "proposed_laundry_cabinet": "armario de lavanderia"}


def load(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text("utf-8"))


def quantities(node):
    if isinstance(node, dict) and {"value", "unit", "origin"} <= set(node):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from quantities(v)


@pytest.mark.parametrize("name", sorted(PROPOSED))
def test_proposed_components_produce_valid_plans_with_the_same_shared_capability_and_version(name):
    plan = plan_cabinet(load(name))
    assert plan["status"] == "OK" and plan["findings"] == [] and plan["execution_authorized"] is False
    assert plan["capability"] == {"id": CAPABILITY_ID, "version": CAPABILITY_VERSION}
    require_valid(plan)
    W, D, H = plan["envelope_m"]
    assert all(-1e-9 <= p["min_m"][k] and p["max_m"][k] <= (W, D, H)[k] + 1e-9 and all(s > 0 and math.isfinite(s) for s in p["size_m"])
               for p in plan["parts"] for k in range(3))


def test_three_components_share_one_capability_with_distinct_signatures_and_the_same_role_vocabulary():
    plans = {n: plan_cabinet(load(n)) for n in (KITCHEN, *PROPOSED)}
    assert {p["capability"]["id"] for p in plans.values()} == {CAPABILITY_ID}
    assert len({p["signature"] for p in plans.values()}) == 3                     # geometrias diferentes, assinaturas diferentes
    roles = {n: {p["id"].split("/")[1] for p in plan["parts"]} for n, plan in plans.items()}
    core = {"back", "bottom", "top", "side_left", "side_right"}
    assert all(core <= r for r in roles.values()), roles                          # a mesma caixaria nos tres componentes
    assert "shelf" in roles["proposed_laundry_cabinet"] and "shelf" not in roles["proposed_nightstand"]    # opcionais so quando pedidos
    assert plans["proposed_laundry_cabinet"]["envelope_m"][2] > plans[KITCHEN]["envelope_m"][2] > plans["proposed_nightstand"]["envelope_m"][2]


def test_proposed_requests_are_honest_about_their_origin_never_user_request():
    for name in PROPOSED:
        origins = {q["origin"] for q in quantities(load(name))}
        assert origins == {"derived"}, (name, origins)


def test_nightstand_proposal_matches_the_class_proportions_it_is_derived_from():
    req, spec = load("proposed_nightstand"), nightstand_spec()
    dims = req["dimensions"]
    assert (dims["width"]["value"] / 1000, dims["depth"]["value"] / 1000, dims["height"]["value"] / 1000) == (spec.width, spec.depth, spec.height)


def test_a_proposal_missing_a_measure_is_refused_not_defaulted():
    req = load("proposed_nightstand")
    del req["panels"]["side"]
    plan = plan_cabinet(req)
    assert plan["status"] == "REFUSED" and plan["findings"][0]["code"] == "MISSING_QUANTITY"
