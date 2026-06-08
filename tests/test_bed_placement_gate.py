"""Testes deterministicos do bed_placement_gate (Fase 2 placement: cama/guarda-roupa/criado).
Sem SketchUp/V-Ray. Prova: quarto valido PASS; cama (hard) FAIL; guarda-roupa/criado (soft)
WARN com a dimensao certa em FAIL/WARN; e o sofa (living_room_planner) sem regressao.

Reusa as fixtures do proprio gate (_fixtures), que mutam o layout REAL do bedroom_designer
em casos de erro — nada hardcoded de geometria."""
import json
from pathlib import Path

import pytest

from interior.validators.bed_placement_gate import _fixtures, bed_placement_gate
from interior.planners.living_room_planner import plan_living

ROOM = "r000"
SOFA_ROOM = "r002"
CON_PATH = (Path(__file__).resolve().parents[1]
            / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")


@pytest.fixture(scope="module")
def con():
    return json.loads(CON_PATH.read_text("utf-8"))


@pytest.fixture(scope="module")
def fixtures(con):
    return _fixtures(con, ROOM)


@pytest.fixture(scope="module")
def graded(con, fixtures):
    # roda o gate uma vez por fixture (designer roda 1x dentro de _fixtures)
    return [(name, expect, bed_placement_gate(con, ROOM, lay)) for name, lay, expect in fixtures]


def _find(graded, key):
    return next(r for name, _e, r in graded if key in name)


def test_fixtures_cover_all_branches(fixtures):
    names = " | ".join(n for n, _l, _e in fixtures)
    assert len(fixtures) >= 6, names
    assert "valido" in names
    assert "cama" in names           # ramo cama (hard)
    assert "guarda-roupa" in names   # ramo guarda-roupa (soft)
    assert "criado" in names         # ramo criado/nightstand


def test_all_fixtures_match_expected(graded):
    for name, expect, r in graded:
        assert r["verdict"] == expect, f"{name}: {r['verdict']} != {expect} ({r.get('issues')})"


def test_valid_room_passes(graded):
    r = _find(graded, "valido")
    assert r["verdict"] == "PASS"
    assert r["BED_PLACEMENT"] == "PASS"
    assert r["CIRCULATION"] == "PASS"
    assert r["ORIENTATION"] == "PASS"


def test_bed_rotated_is_hard_fail(graded):
    r = _find(graded, "rotacionada")
    assert r["verdict"] == "FAIL"
    assert r["BED_PLACEMENT"] == "FAIL"
    assert r["ORIENTATION"] == "FAIL"


def test_bed_floating_is_hard_fail(graded):
    r = _find(graded, "flutuando")
    assert r["verdict"] == "FAIL"
    assert r["BED_PLACEMENT"] == "FAIL"


def test_wardrobe_no_free_front_is_soft(graded):
    # guarda-roupa sem frente livre: dimensao FAIL, mas verdict WARN (guarda-roupa e soft)
    r = _find(graded, "sem frente livre")
    assert r["WARDROBE_PLACEMENT"] == "FAIL"
    assert r["verdict"] == "WARN"


def test_nightstand_loose_warns(graded):
    r = _find(graded, "criado solto")
    assert r["NIGHTSTANDS"] == "WARN"
    assert r["verdict"] == "WARN"


def test_sofa_no_regression(con):
    # o SofaBrain (marco GPT-validado) continua colocando sofa de frente p/ TV
    r = plan_living(con, SOFA_ROOM)
    assert r["result"] == "OK", r.get("result")
    assert r.get("plan", {}).get("sofa", {}).get("wall_id"), "sofa sem parede no plano"


def test_gate_is_deterministic(con, fixtures):
    # mesmo layout -> mesmo verdict (sem aleatoriedade)
    name, lay, _e = fixtures[0]
    a = bed_placement_gate(con, ROOM, lay)
    b = bed_placement_gate(con, ROOM, lay)
    assert a["verdict"] == b["verdict"] and a["issues"] == b["issues"]
