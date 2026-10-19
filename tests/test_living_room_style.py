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


def test_dining_table_is_rectangular_4_seats(sala):
    # Era 6 lugares (VERDICT 6.5 original) — rebaixado pra 4 em 2026-08-12
    # depois de circulation_gate.py provar (varredura EXAUSTIVA: grade
    # completa do cômodo, overlap real contra sofá/rack, exigindo os 5
    # portais conectados E folga atrás/puxada de toda cadeira) que NENHUMA
    # mesa retangular de 6 lugares tem posição válida nessa sala combinada —
    # sofá (ajustado ao nicho) + rack já ocupam a parede-TV inteira. P1 do
    # VERDICT 6.5 (circulação) tem prioridade sobre contagem de lugares.
    # Ver tools/furnish_apartment.py (bloco "ZONA DE JANTAR").
    mods = _mods(sala)
    assert "Mesa de jantar" in mods
    xs0 = min(p["x0"] for p in mods["Mesa de jantar"])
    xs1 = max(p["x1"] for p in mods["Mesa de jantar"])
    ys0 = min(p["y0"] for p in mods["Mesa de jantar"])
    ys1 = max(p["y1"] for p in mods["Mesa de jantar"])
    lados = sorted([xs1 - xs0, ys1 - ys0])
    assert lados[1] / lados[0] >= 1.4, "mesa quadrada — diretriz pede retangular"
    seats = [p for p in mods.get("Cadeira jantar", []) if p["kind"] == "seat"]
    assert len(seats) == 2, f"esperava 2 cadeiras (teto real da sala, ver comentário), veio {len(seats)}"


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


def test_fp043_tv_panel_is_outside_shell_wall_return(sala):
    """P3a-03: testa o painel construido contra a massa real da parede."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from core.scale import PT_TO_IN, PT_TO_M
    from tools.rooms.shared.spatial_model import build_spatial_model, wall_footprint

    con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    sm = build_spatial_model(con, "r002")
    walls = unary_union([wall_footprint(sm["_geom"]["walls"][wid], extend_endpoints=True)
                         for wid in sm["_geom"]["room_walls"]])
    for b in sala:
        if b["kind"] != "painel_tv":
            continue
        p = Polygon([(x / PT_TO_IN, y / PT_TO_IN) for x, y in b["corners"]])
        collision_cm2 = p.intersection(walls).area * PT_TO_M ** 2 * 10000
        assert collision_cm2 < 0.1, f"painel TV entra no retorno de parede: {collision_cm2:.2f}cm2"


def test_fp043_dining_table_avoids_real_door_swing(sala):
    """P3a-03: h_o000 tinha ~36cm2 de colisao no tampo da mesa."""
    from shapely.geometry import Polygon
    from core.scale import PT_TO_IN, PT_TO_M
    from tools.rooms.shared.geometry import door_swing_polygons

    con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    swings = door_swing_polygons(con, strict=True)
    table = [b for b in sala if b.get("module") == "Mesa de jantar"]
    assert table
    for b in table:
        poly = Polygon([(x / PT_TO_IN, y / PT_TO_IN) for x, y in b["corners"]])
        for oid, door in swings.items():
            overlap_cm2 = poly.intersection(door).area * PT_TO_M ** 2 * 10000
            assert overlap_cm2 < 0.1, f"mesa de jantar invade {oid}: {overlap_cm2:.2f}cm2"
