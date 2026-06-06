"""Prova que as fixtures sinteticas de QUARTO sao inputs validos pro bedroom
brain (tools/make_synthetic_bedrooms.py). Testa a LOGICA do gerador em memoria
(sem I/O de arquivo): cada quarto e um consensus bem-formado, com 1 porta + 1
janela, classifica como BEDROOM, e sempre oferece >=1 parede LIMPA (sem abertura)
como candidata a cabeceira. Sem shapely / 3DW / SKP.

Regras validadas com ChatGPT (consult "Prioridade Quartos e Layout", 2026-06-05).
"""
from __future__ import annotations

import pytest

from tools.make_synthetic_bedrooms import SPECS, rect_bedroom
from tools.room_type import BEDROOM, classify_room_type

_CASES = [(fname, room_name, kw) for fname, (room_name, kw) in SPECS.items()]


@pytest.fixture(params=_CASES, ids=[c[0] for c in _CASES])
def bedroom(request):
    fname, room_name, kw = request.param
    return fname, room_name, rect_bedroom(room_name, **kw)


def test_is_wellformed_consensus(bedroom):
    _, _, con = bedroom
    assert con["wall_thickness_pts"] == 5.4
    assert len(con["walls"]) == 4
    assert {w["id"] for w in con["walls"]} == {"wB", "wR", "wT", "wL"}
    room = con["rooms"][0]
    poly = room["polygon_pts"]
    assert poly[0] == poly[-1]          # poligono fechado
    assert len(poly) == 5               # retangulo (4 cantos + fecho)


def test_has_exactly_one_door_and_one_window(bedroom):
    _, _, con = bedroom
    kinds = sorted(o["kind_v5"] for o in con["openings"])
    assert kinds == ["interior_door", "window"]
    # toda abertura ancorada numa parede existente do quarto
    wall_ids = {w["id"] for w in con["walls"]}
    assert all(o["wall_id"] in wall_ids for o in con["openings"])


def test_room_name_classifies_as_bedroom(bedroom):
    _, room_name, _ = bedroom
    assert classify_room_type(room_name) == BEDROOM


def test_has_at_least_one_clean_headboard_wall(bedroom):
    """Parede sem porta nem janela -> candidata a cabeceira (hard gate do brain:
    cabeceira encostada em parede limpa). Cada fixture precisa oferecer >=1."""
    _, _, con = bedroom
    walls_with_opening = {o["wall_id"] for o in con["openings"]}
    clean = {w["id"] for w in con["walls"]} - walls_with_opening
    assert len(clean) >= 1, f"sem parede limpa p/ cabeceira (aberturas em {walls_with_opening})"


def test_door_and_window_on_different_walls(bedroom):
    """Por design: porta e janela em paredes distintas -> mais paredes limpas e
    o caso 'cabeceira forcada sob janela' nao aparece nas fixtures basicas."""
    _, _, con = bedroom
    by_wall = {o["kind_v5"]: o["wall_id"] for o in con["openings"]}
    assert by_wall["interior_door"] != by_wall["window"]
