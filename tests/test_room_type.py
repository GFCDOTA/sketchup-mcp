"""Prova do classificador de tipo de comodo por nome (tools/room_type.py).

Cobre: cada tipo casa pelo nome; nomes combinados resolvem pela precedencia
(molhado > quarto); nome vazio/desconhecido -> UNKNOWN (degrada honesto, nao
chuta); e a planta REAL (planta_74) classifica os 8 comodos como esperado, com
so as 2 suites mobiliaveis no v1. Sem shapely / 3DW / SKP.

Spec validada com ChatGPT (consult "Prioridade Quartos e Layout", 2026-06-05).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.room_type import (BALCONY, BATHROOM, BEDROOM, FURNISHABLE_V1, KITCHEN,
                             LIVING, ROOM_TYPE_SOURCE, SERVICE, UNKNOWN,
                             classify_room_type, classify_rooms, is_furnishable)

REPO = Path(__file__).resolve().parents[1]
_PLANTA = (REPO / "fixtures" / "planta_74"
           / "consensus_with_human_walls_and_soft_barriers.json")


@pytest.mark.parametrize("name,expected", [
    ("SUITE 01", BEDROOM),
    ("SUÍTE MASTER", BEDROOM),
    ("QUARTO 02", BEDROOM),
    ("DORMITÓRIO", BEDROOM),
    ("SALA DE JANTAR | SALA DE ESTAR", LIVING),
    ("ESTAR", LIVING),
    ("COZINHA", KITCHEN),
    ("BANHO 01", BATHROOM),
    ("BANHEIRO SOCIAL", BATHROOM),
    ("LAVABO", BATHROOM),
    ("A.S. | TERRACO SOCIAL | TERRACO TECNICO", SERVICE),
    ("AREA DE SERVIÇO", SERVICE),
    ("TERRAÇO", BALCONY),
    ("VARANDA GOURMET", BALCONY),
])
def test_classify_known_names(name, expected):
    assert classify_room_type(name) == expected


@pytest.mark.parametrize("name", ["", None, "   ", "HOBBY ROOM", "XYZ", "MEZANINO"])
def test_unmapped_or_empty_is_unknown(name):
    assert classify_room_type(name) == UNKNOWN


def test_wet_room_beats_bedroom_in_combined_name():
    """'BANHO DA SUITE' e um BANHEIRO, nao um quarto (precedencia molhado > quarto)."""
    assert classify_room_type("BANHO DA SUITE") == BATHROOM


def test_living_beats_balcony_in_combined_name():
    """'SALA COM TERRACO' e uma SALA (LIVING vence BALCONY)."""
    assert classify_room_type("SALA COM TERRACO") == LIVING


def test_only_bedroom_is_furnishable_v1():
    assert is_furnishable(BEDROOM) is True
    for t in (LIVING, KITCHEN, BATHROOM, SERVICE, BALCONY, UNKNOWN):
        assert is_furnishable(t) is False
    assert FURNISHABLE_V1 == frozenset({BEDROOM})


def test_unknown_degrades_honest_not_guessed():
    """UNKNOWN nao e mobiliado e carrega reason auditavel (nao chuta tipo)."""
    con = {"rooms": [{"id": "rX", "name": "ESPACO MISTERIOSO"}]}
    rows = classify_rooms(con)
    assert rows[0]["room_type"] == UNKNOWN
    assert rows[0]["furnishable"] is False
    assert rows[0]["reason"] == "room_type_unknown_missing_or_unmapped_name"
    assert rows[0]["room_type_source"] == ROOM_TYPE_SOURCE


def test_classify_rooms_marks_source_on_every_room():
    con = {"rooms": [{"id": "a", "name": "SUITE 01"}, {"id": "b", "name": "COZINHA"}]}
    rows = classify_rooms(con)
    assert [r["room_type"] for r in rows] == [BEDROOM, KITCHEN]
    assert all(r["room_type_source"] == ROOM_TYPE_SOURCE for r in rows)
    assert "reason" not in rows[0]  # so UNKNOWN carrega reason


# ---- planta REAL (canonico): os 8 comodos classificam como esperado ----

@pytest.mark.skipif(not _PLANTA.exists(), reason="planta_74 fixture absent")
def test_planta_74_rooms_classified():
    con = json.loads(_PLANTA.read_text("utf-8"))
    got = {r["id"]: r["room_type"] for r in classify_rooms(con)}
    expected = {
        "r000": BEDROOM,   # SUITE 01
        "r001": SERVICE,   # A.S. | TERRACO SOCIAL | TERRACO TECNICO
        "r002": LIVING,    # SALA DE JANTAR | SALA DE ESTAR
        "r003": BEDROOM,   # SUITE 02
        "r004": KITCHEN,   # COZINHA
        "r005": BATHROOM,  # BANHO 01
        "r006": BATHROOM,  # BANHO 02
        "r007": BATHROOM,  # LAVABO
    }
    assert got == expected


@pytest.mark.skipif(not _PLANTA.exists(), reason="planta_74 fixture absent")
def test_planta_74_furnishable_are_the_two_suites():
    con = json.loads(_PLANTA.read_text("utf-8"))
    rows = classify_rooms(con)
    furn = sorted(r["id"] for r in rows if r["furnishable"])
    assert furn == ["r000", "r003"]   # so as 2 suites entram no mobiliar v1
    assert all(r["room_type_source"] == ROOM_TYPE_SOURCE for r in rows)
