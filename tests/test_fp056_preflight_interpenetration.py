"""#502: o pre-voo ve a interpenetracao NOVA/PIOR entre modulos (baseline-aware), que o limiar por modulo nao enxerga."""
from __future__ import annotations

import contextlib
import copy
import io
import json

import pytest

from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
from tools.validation import layout_preflight as lp

pytestmark = pytest.mark.planta74_scale


@pytest.fixture(scope="module")
def apt():
    from tools.furnish_apartment import collect_boxes
    con = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, summary = collect_boxes(con)
    return con, boxes, summary


def rows(pre, gate="module_interpenetration"):
    return [r for r in pre["rooms"] if r["gate"] == gate]


def test_without_a_baseline_the_gate_measures_nothing_and_says_so(apt):
    con, boxes, summary = apt
    assert {r["status"] for r in rows(lp.preflight(con, copy.deepcopy(boxes), summary))} == {"NOT_APPLICABLE"}


def test_current_apartment_has_no_new_or_worse_interpenetration_against_the_registry(apt):
    con, boxes, summary = apt
    pre = lp.preflight(con, copy.deepcopy(boxes), summary, lp.planta74_twin(PLANTA_74_CONSENSUS))
    assert {r["status"] for r in rows(pre)} == {"PASS"}, rows(pre)


def test_a_module_pair_missing_from_the_registry_fails_the_preflight(apt):
    con, boxes, summary = apt
    twin = lp.planta74_twin(PLANTA_74_CONSENSUS)
    objs = [d for d in twin["baseline"] if "|OBJECTS|" in d["key"]]
    assert objs, "o baseline precisa ter ao menos um defeito OBJECTS para este teste"
    twin["baseline"] = [d for d in twin["baseline"] if d is not objs[0]]            # simula defeito que o registro nao conhece
    pre = lp.preflight(con, copy.deepcopy(boxes), summary, twin)
    bad = [r for r in rows(pre) if r["status"] == "FAIL"]
    assert bad and objs[0]["key"] in sum((r["reasons"]["new"] for r in bad), [])
    assert not lp.allows_materialization(pre)


def test_a_worse_measure_than_the_registry_fails(apt):
    con, boxes, summary = apt
    twin = lp.planta74_twin(PLANTA_74_CONSENSUS)
    obj = next(d for d in twin["baseline"] if "|OBJECTS|" in d["key"] and d["measure"] > 0.01)
    obj["measure"] = 0.0
    pre = lp.preflight(con, copy.deepcopy(boxes), summary, twin)
    assert any(obj["key"] in r["reasons"].get("worse", []) for r in rows(pre) if r["status"] == "FAIL")


def test_another_consensus_has_no_twin_context():
    assert lp.planta74_twin("/tmp/outra/consensus_model.json") is None
