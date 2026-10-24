"""FP-056 P0: causas-raiz dos defeitos da planta_74, travadas como xfail(strict) ate a correcao NA ORIGEM.

Cada teste mede a causa no gerador (nao no validador). Quando a correcao entrar, o teste passa e o xfail(strict) quebra a
suite de proposito: a correcao tem de remover o xfail no mesmo PR (nunca relaxar a medida).
"""
from __future__ import annotations

import json

import pytest
from shapely.geometry import Polygon

from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS


def _con():
    return json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))


@pytest.mark.planta74_scale
@pytest.mark.xfail(strict=True, reason="FP-056 RC-B: tools/rooms/service/layout.py _cell_m/_circ_m tratam o cell (pontos do PDF) "
                                       "como polegadas (x0,0254 em vez de x PT_TO_M): a zona da A.S. sai 1,9% menor, puxada "
                                       "para a origem — pecas saem 3 a 29 cm do comodo (maquina, varal, bancada gourmet)")
def test_service_planner_cell_is_in_the_plants_metres():
    from core.scale import PT_TO_M
    from tools.rooms.service.layout import _cell_m
    from tools.rooms.shared.spatial_model import build_spatial_model
    con = _con()
    sm = build_spatial_model(con, "r001")
    true_m = Polygon([(x * PT_TO_M, y * PT_TO_M) for x, y in sm["_geom"]["cell"].exterior.coords])
    got = _cell_m(sm)
    assert max(abs(a - b) for a, b in zip(got.bounds, true_m.bounds)) < 0.005


@pytest.mark.planta74_scale
@pytest.mark.xfail(strict=True, reason="FP-056 RC-A (FP-043 D-007): o cell que os planejadores recebem e a LAJE construtiva, que "
                                       "entra FLOOR_UNDER_FRAC (0,4) x espessura sob a parede; mobiliar o cell poe pecas dentro "
                                       "da parede (11 ocorrencias R1 no registro da FP-055 P4)")
def test_planner_cell_does_not_overlap_the_wall_mass():
    from core.scale import PT_TO_M
    from tools.rooms.shared.clearance import wall_mass_pt
    from tools.rooms.shared.spatial_model import build_spatial_model
    con = _con()
    walls = wall_mass_pt(con)
    worst = max(build_spatial_model(con, r["id"])["_geom"]["cell"].intersection(walls).area for r in con["rooms"])
    assert worst * PT_TO_M ** 2 < 1e-4                                   # < 1 cm2 de laje dentro da parede, em qualquer comodo
