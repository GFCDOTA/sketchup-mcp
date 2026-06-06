"""Prova do bedroom layout brain (tools/bedroom_layout.py) — geometria pura.

Roda em fixtures sinteticas (quarto pequeno/medio/grande) + suites reais da
planta_74 (r000/r003). Verifica: layout valido, cabeceira encostada em parede
NAO-porta, passagem >= 0.60, criados/guarda-roupa conforme tamanho, cama por
area (single/double/queen/king), e degradacao honesta (comodo que nao comporta
cama -> NO_VALID_LAYOUT). Sem shapely-asset / 3DW / SKP.

Dimensoes/regras validadas com ChatGPT (consult "Prioridade Quartos e Layout",
2026-06-05).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.bedroom_layout import _bed_order, run

REPO = Path(__file__).resolve().parents[1]
SYN = REPO / "fixtures" / "synthetic_rooms"
_PLANTA = (REPO / "fixtures" / "planta_74"
           / "consensus_with_human_walls_and_soft_barriers.json")

SYN_CASES = [("bedroom_small_9m2.json", "single"),
             ("bedroom_medium_14m2.json", "double"),
             ("bedroom_large_18m2.json", "queen")]


def _run(path, room):
    con = json.loads(Path(path).read_text("utf-8"))
    return run(con, room)


def _chosen(out):
    wid = out["chosen"]["headboard_wall"]
    return next(c for c in out["candidates"] if c["headboard_wall"] == wid and c["valid"])


@pytest.mark.parametrize("fname,bed", SYN_CASES)
def test_synthetic_bedroom_valid_layout(fname, bed):
    sm, out = _run(SYN / fname, "bedroom")
    assert out["result"] == "OK"
    assert out["bed_size"] == bed
    ch = _chosen(out)
    assert ch["valid"]
    # hard gates do vencedor
    assert ch["hard_gates"]["cabeceira_na_parede"]
    assert ch["hard_gates"]["passagem_min_060"]
    assert ch["hard_gates"]["nao_bloqueia_porta"]
    assert ch["hard_gates"]["nao_bloqueia_circulacao"]
    assert ch["hard_gates"]["dentro_do_comodo"]
    # cabeceira do vencedor NAO e parede de porta (RL: parede limpa > janela > porta)
    hb_rank = {h["wall_id"]: h for h in out["headboard_ranking"]}
    assert hb_rank[ch["headboard_wall"]]["has_door"] is False


@pytest.mark.parametrize("fname,_bed", SYN_CASES)
def test_clearances_meet_minimums(fname, _bed):
    sm, out = _run(SYN / fname, "bedroom")
    ch = _chosen(out)
    assert ch["metrics"]["side_clear_m"] >= 0.60
    assert ch["metrics"]["foot_clear_m"] >= 0.60


def test_medium_and_large_get_wardrobe_and_two_nightstands():
    for fname in ("bedroom_medium_14m2.json", "bedroom_large_18m2.json"):
        sm, out = _run(SYN / fname, "bedroom")
        m = _chosen(out)["metrics"]
        assert m["has_wardrobe"] is True
        assert m["n_nightstands"] == 2


def test_small_room_degrades_gracefully_but_valid():
    """Quarto pequeno: ainda layout VALIDO (cama + criados), mesmo que o
    guarda-roupa nao caiba com folga (omitido, nao forca invalido)."""
    sm, out = _run(SYN / "bedroom_small_9m2.json", "bedroom")
    assert out["result"] == "OK"
    ch = _chosen(out)
    assert ch["valid"]
    assert ch["metrics"]["bed_size"] == "single"


def test_no_wall_fits_bed_is_no_valid_layout():
    """Comodo que nao comporta a cama (raso demais) -> NO_VALID_LAYOUT honesto."""
    from tools.make_synthetic_bedrooms import rect_bedroom
    con = rect_bedroom("QUARTO MINUSCULO", w_m=1.5, d_m=1.5)
    sm, out = run(con, "bedroom")
    assert out["result"] == "NO_VALID_LAYOUT"
    assert not any(c["valid"] for c in out["candidates"])


# ---- planta REAL (canonico): as 2 suites mobiliam ----

@pytest.mark.skipif(not _PLANTA.exists(), reason="planta_74 fixture absent")
@pytest.mark.parametrize("room,bed", [("r003", "queen"), ("r000", "king")])
def test_planta_74_suites_furnish(room, bed):
    sm, out = _run(_PLANTA, room)
    assert out["result"] == "OK"
    assert out["bed_size"] == bed
    ch = _chosen(out)
    assert ch["valid"]
    assert ch["hard_gates"]["cabeceira_na_parede"]
    assert ch["hard_gates"]["nao_bloqueia_porta"]
    assert ch["hard_gates"]["dentro_do_comodo"]


# ---- novos gates + fallback de cama (spec Felipe 2026-06-05) ----

def test_bed_order_fallback_chains():
    assert _bed_order(8, 2.5) == ["single"]
    assert _bed_order(12, 2.8) == ["double", "single"]
    assert _bed_order(16, 3.0) == ["queen", "double", "single"]
    assert _bed_order(25, 3.8) == ["king", "queen", "double"]   # largo -> tenta king
    assert _bed_order(25, 3.0) == ["queen", "double"]           # estreito -> sem king


@pytest.mark.parametrize("fname,_bed", SYN_CASES)
def test_new_hard_gates_present_and_pass(fname, _bed):
    sm, out = _run(SYN / fname, "bedroom")
    hg = _chosen(out)["hard_gates"]
    for g in ("nao_invade_abertura", "nao_bloqueia_janela", "guarda_roupa_frente_livre"):
        assert hg.get(g) is True, f"{g} ausente/falhou em {fname}"


@pytest.mark.skipif(not _PLANTA.exists(), reason="planta_74 fixture absent")
def test_fallback_machinery_recorded():
    """run() registra alvo + tentativas de tamanho de cama (mesmo sem disparar)."""
    sm, out = _run(_PLANTA, "r003")
    assert out["bed_size_target"] == "queen"
    assert isinstance(out.get("bed_tried"), list) and out["bed_tried"]
    order = ["single", "double", "queen", "king"]
    assert order.index(out["bed_size"]) <= order.index(out["bed_size_target"])


def test_wardrobe_when_present_has_front_gate_true():
    """Se ha guarda-roupa no vencedor, o hard gate de frente livre passa."""
    sm, out = _run(SYN / "bedroom_large_18m2.json", "bedroom")
    ch = _chosen(out)
    if ch["metrics"]["has_wardrobe"]:
        assert ch["hard_gates"]["guarda_roupa_frente_livre"] is True
