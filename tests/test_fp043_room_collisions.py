"""FP-043/P3a-03 — mobilia (FURNITURE/FIXTURE) nao pode entrar na parede nem ficar no giro de porta, na planta_74 real.

Reproduz em L1 (planner, sem SketchUp) os achados do L2 FP-042. Os comodos de controle (SUITE 02, cozinha, servico) seguem sem achado.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONSENSUS = ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"


@pytest.fixture(scope="module")
def planned():
    os.environ["PT_TO_M"] = "0.0259"
    from core import scale
    if abs(scale.PT_TO_M - 0.0259) > 1e-9:
        pytest.skip("escala da planta_74 (PT_TO_M=0.0259) nao ativa")
    from tools.furnish_apartment import collect_boxes
    from tools.validation.room_collisions import audit
    con = json.loads(CONSENSUS.read_text("utf-8"))
    boxes, _ = collect_boxes(con)
    return audit(con, boxes)


def _hits(planned, key):
    return {room: d[key] for room, d in planned.items() if d[key]}


KNOWN_OPEN_D008 = {"SUITE 01": {"Criado-mudo 2"}}   # decisao de produto do Felipe: ver docs/specs/FP-043_open_decisions.md


def test_nenhum_movel_ou_fixture_penetra_parede(planned):
    """So o criado-mudo 2 da SUITE 01 (D-008) segue aberto: sem posicao livre que respeite parede e faixa da porta."""
    got = {r: {x["module"] for x in v} for r, v in _hits(planned, "wall_penetration").items()}
    assert got == KNOWN_OPEN_D008, got


def test_nenhum_movel_ou_fixture_no_giro_de_porta(planned):
    got = {r: [(x["door"], x["module"], x["area_cm2"]) for x in v] for r, v in _hits(planned, "door_swing_hits").items()}
    assert got == {}, got
