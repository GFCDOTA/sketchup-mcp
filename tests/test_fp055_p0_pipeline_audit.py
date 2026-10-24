"""FP-055 P0: o audit de pipeline mede execucao real (nao import) e nunca marca CONSUMED sem INVOKED."""
from __future__ import annotations

import pytest

from tools.navigation import pipeline_audit as pa


@pytest.fixture(scope="module")
def audit():
    trace = pa.trace_generation()
    return trace, pa.capability_inventory(trace), pa.watched_modules(trace)


@pytest.mark.planta74_scale
def test_generation_trace_covers_every_room_and_is_deterministic(audit):
    trace, _caps, _w = audit
    assert {r["id"] for r in trace["rooms"]} == {f"r00{i}" for i in range(8)}
    assert trace["n_boxes"] == 390                       # FP-056 P1: A.S. sem bancada gourmet/cuba/mesa (circulacao)
    again = pa.trace_generation()          # mesmo processo: imports e caches ja feitos -> chamadas sao subconjunto
    assert again["rooms"] == trace["rooms"] and set(again["calls"]) <= set(trace["calls"])


@pytest.mark.planta74_scale
def test_consumed_requires_invoked_and_an_explicit_rule(audit):
    _t, caps, _w = audit
    for c in caps:
        if c["CONSUMED"]:
            assert c["INVOKED"] and c["consumed_basis"], c["id"]
        assert c["REFLECTED_IN_MODEL"] == "NOT_EVALUATED" and c["VALIDATED"] == "NOT_EVALUATED"


@pytest.mark.planta74_scale
def test_baseline_gaps_are_detected_not_assumed(audit):
    trace, caps, watched = audit
    by = {c["id"]: c for c in caps}
    assert not by["shared.cabinet.parametric"]["INVOKED"]              # L2_PASS fora da geracao do apartamento
    assert by["bathroom.wet-room.guard"]["CONSUMED"]                   # FP-055 #427: o guard agora bloqueia a geracao
    w = {m["component"]: m["EXECUTED_IN_GENERATION"] for m in watched}
    assert not w["F2 solver: engine"] and not w["specialists.plan (perfil+allowlist+binding)"]
    # F1C do banheiro: chamado, e mesmo assim nao consumido (descartado por collect_boxes)
    assert "tools/rooms/bathroom/layout.py::_functional_interfaces" in trace["calls"]
    assert "tools.rooms.bathroom.layout._functional_interfaces" not in pa._CONSUMED_RULES
