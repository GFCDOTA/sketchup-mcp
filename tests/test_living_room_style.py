"""Sala (r002) na gramática BLACK_WOOD_GOLD — contratos do programa
"mobiliar o apê inteiro" (Felipe 2026-08-03).

Pina o que faz a sala LER como sala no caminho de PRODUÇÃO (sem FURNISH_STYLE):
TV de verdade sobre o rack, painel de TV em nogueira, pendente sobre o jantar
com o ÚNICO bronze do ambiente, mesa retangular de 6 lugares, tapete com borda,
zero branco puro. Veredito visual segue humano.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.furnish_apartment import living_room_boxes

BRONZE = [171, 119, 63]


@pytest.fixture(scope="module")
def sala():
    con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    boxes, out = living_room_boxes(con, "r002")
    assert out.get("result") == "OK", f"sala não montou: {out}"
    return boxes


def _mods(boxes):
    out = {}
    for b in boxes:
        out.setdefault(b.get("module", ""), []).append(b)
    return out


def test_tv_exists_in_production(sala):
    mods = _mods(sala)
    assert "TV" in mods, "TV não existe em produção — rack sem TV não lê como sala"
    glass = [p for p in mods["TV"] if max(p["rgb"]) <= 30]
    assert glass, "TV sem o vidro preto profundo"


def test_tv_panel_is_nogueira_and_wide(sala):
    mods = _mods(sala)
    assert "Painel TV" in mods, "painel de TV (nogueira) ausente — era proxy gated"
    pan = mods["Painel TV"]
    w_in = max(max(p["x1"] - p["x0"], p["y1"] - p["y0"]) for p in pan)
    assert w_in >= 2.0 * 39.37, "painel estreito demais"
    assert any(80 <= p["rgb"][0] <= 130 and p["rgb"][1] < p["rgb"][0] for p in pan), \
        "painel não é madeira nogueira"


def test_dining_table_is_rectangular_6_seats(sala):
    mods = _mods(sala)
    assert "Mesa de jantar" in mods
    xs0 = min(p["x0"] for p in mods["Mesa de jantar"])
    xs1 = max(p["x1"] for p in mods["Mesa de jantar"])
    ys0 = min(p["y0"] for p in mods["Mesa de jantar"])
    ys1 = max(p["y1"] for p in mods["Mesa de jantar"])
    lados = sorted([xs1 - xs0, ys1 - ys0])
    assert lados[1] / lados[0] >= 1.4, "mesa quadrada — diretriz pede retangular 6 lugares"
    seats = [p for p in mods.get("Cadeira jantar", []) if p["kind"] == "seat"]
    assert len(seats) == 6, f"esperava 6 cadeiras, veio {len(seats)}"


def test_pendente_holds_the_single_bronze(sala):
    bronze = [p for p in sala if list(p["rgb"]) == BRONZE]
    assert len(bronze) == 1, f"a sala tem {len(bronze)} pontos de bronze — a regra é UM (pendente)"
    assert "Pendente" in str(bronze[0].get("module", "")), "o bronze não está no pendente"


def test_rug_has_border(sala):
    mods = _mods(sala)
    rug = mods.get("Tapete", [])
    assert len(rug) >= 2, "tapete-laje: precisa campo + borda"


def test_no_pure_white_surfaces(sala):
    for p in sala:
        if "led" in str(p.get("kind", "")).lower() or "spot" in str(p.get("kind", "")).lower():
            continue
        assert sum(p["rgb"]) / 3 <= 200, \
            f"branco puro na sala: {p.get('module')}/{p.get('kind')} {p['rgb']}"
