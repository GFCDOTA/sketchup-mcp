"""FP-055 P7 (#418): integracao nominal nao volta a passar — regressao E melhoria nao registrada reprovam."""
from __future__ import annotations

import copy
import json

import pytest

from tools.validation import consumption_baseline as cb

BASE = {"schema_version": "consumption_baseline.v1",
        "capabilities": {"a": {"INVOKED": True, "CONSUMED": True}, "b": {"INVOKED": True, "CONSUMED": False},
                         "c": {"INVOKED": False, "CONSUMED": False}},
        "watched_executed": {"solver": False, "gate": True}, "specialists_invoked": 0, "specialists_total": 9,
        "recipes_consumed": 0, "recipes_total": 19}


def test_identical_state_has_no_divergence():
    assert cb.compare(BASE, copy.deepcopy(BASE)) == []


def test_a_dropped_call_is_a_regression_in_capability_and_in_watched_module():
    now = copy.deepcopy(BASE)
    now["capabilities"]["a"]["CONSUMED"] = False         # alguem passou a descartar a saida
    now["capabilities"]["b"]["INVOKED"] = False          # alguem removeu a chamada
    now["watched_executed"]["gate"] = False
    got = cb.compare(BASE, now)
    assert "REGRESSAO a: CONSUMED era true e agora e false" in got
    assert "REGRESSAO b: INVOKED era true e agora e false" in got
    assert "REGRESSAO modulo vigiado gate: deixou de ser executado" in got


def test_an_unrecorded_improvement_also_fails_so_the_baseline_never_goes_stale():
    now = copy.deepcopy(BASE)
    now["capabilities"]["c"]["INVOKED"] = True
    now["watched_executed"]["solver"] = True
    now["specialists_invoked"] = 2
    got = cb.compare(BASE, now)
    assert any(x.startswith("MELHORIA c: INVOKED") for x in got)
    assert any("MELHORIA modulo vigiado solver" in x for x in got)
    assert any("MELHORIA specialists_invoked: 0 -> 2" in x for x in got)


def test_new_and_removed_capabilities_are_reported():
    now = copy.deepcopy(BASE)
    now["capabilities"]["novo"] = {"INVOKED": False, "CONSUMED": False}
    del now["capabilities"]["c"]
    got = cb.compare(BASE, now)
    assert any(x.startswith("NOVA capacidade fora do retrato: novo") for x in got) and "REMOVIDA do catalogo: c" in got


def test_not_consumed_report_lists_what_the_generation_does_not_use():
    rows = cb.not_consumed(BASE)
    assert "capacidade b: INVOKED=True CONSUMED=False" in rows and "modulo vigiado solver: nao executado" in rows
    assert not any("capacidade a:" in r for r in rows)


@pytest.mark.planta74_scale
def test_real_generation_matches_the_committed_consumption_baseline():
    now = cb.capture()
    diffs = cb.compare(json.loads(cb.BASELINE.read_text("utf-8")), now)
    assert diffs == [], "divergencia de consumo (veja `python -m tools.validation.consumption_baseline`):\n" + "\n".join(diffs)
    assert now["capabilities"]["bathroom.wet-room.guard"]["CONSUMED"]          # FP-055 #427: guard bloqueia
    assert not now["capabilities"]["shared.cabinet.parametric"]["INVOKED"]      # lacuna conhecida #426, nao escondida
