"""Banheiros + lavabo na gramática BLACK_WOOD_GOLD — programa apê-inteiro.

Contratos: gabinete SUSPENSO nogueira com gola, tampo pedra quieta sem veio,
cuba preta, torneira preta PVD, espelho retroiluminado (LED), box com perfil
preto + ducha, metais 100% pretos nos banhos (bronze ZERO) e o lavabo como joia
(o ÚNICO bronze mora na torneira dele).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.bathroom_layout import build_boxes

M2IN = 39.3700787402
BRONZE = [171, 119, 63]


def _rooms():
    con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    out = {}
    for r in con.get("rooms", []):
        nm = str(r.get("name", "")).upper()
        if "BANHO" in nm or "LAVABO" in nm:
            boxes, meta = build_boxes(con, r["id"])
            if boxes:
                out[nm] = boxes
    return out


ROOMS = _rooms()


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_vanity_is_floating_stone_monolith(nm):
    # STONE_MONOLITH: gabinete suspenso em PEDRA greige (sem madeira protagonista)
    boxes = ROOMS[nm]
    gab = [b for b in boxes if b["kind"] == "gabinete"]
    assert gab, f"{nm}: sem gabinete"
    assert min(b["z0_in"] for b in gab) >= 0.24 * M2IN, f"{nm}: gabinete no chão — pediu suspenso"
    assert any(130 <= b["rgb"][0] <= 170 for b in gab), f"{nm}: gabinete não é pedra greige"
    cuba = [b for b in boxes if b["kind"] == "cuba"]
    assert cuba and all(b["z0_in"] / M2IN < 0.88 for b in cuba), \
        f"{nm}: cuba deve ser under-mount (abaixo do tampo)"
    assert any(b["kind"] == "kb_gola" for b in boxes), f"{nm}: gabinete sem gola handleless"
    assert any(b["kind"] == "kb_led" for b in boxes), f"{nm}: espelho sem retroiluminação"
    assert any(b["kind"] == "kb_torneira" for b in boxes), f"{nm}: bancada sem torneira"


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_metals_black_gold_zero(nm):
    # STONE_MONOLITH (Felipe 2026-08-05): metais 100% preto fosco; dourado ZERO
    # (sai o anel da torneira); bronze zero.
    boxes = ROOMS[nm]
    bronze = [b for b in boxes if list(b["rgb"]) == BRONZE]
    assert not bronze, f"{nm}: bronze sobrou em {[b['kind'] for b in bronze]}"
    torneira = [b for b in boxes if b["kind"] == "kb_torneira"]
    assert torneira and all(sum(b["rgb"]) / 3 <= 60 for b in torneira), \
        f"{nm}: torneira não é preto fosco"
    assert not [b for b in boxes if b["kind"] == "kb_anel"], \
        f"{nm}: dourado deve ser ZERO nesta linguagem"


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_mirror_frame_is_thin_black(nm):
    # STONE_MONOLITH: moldura muito discreta PRETA (espelho protagonista)
    boxes = ROOMS[nm]
    mold = [b for b in boxes if b["kind"] == "kb_moldura"]
    assert mold, f"{nm}: espelho sem moldura"
    for b in mold:
        assert sum(b["rgb"]) / 3 <= 60, f"{nm}: moldura {b['rgb']} não é preta discreta"


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_vanity_has_towel_niche_signature(nm):
    # A assinatura da referência: nicho aberto nogueira com TOALHAS + LED sob o tampo
    boxes = ROOMS[nm]
    assert any(b["kind"] == "kb_nicho_fundo" for b in boxes), f"{nm}: sem nicho de toalhas"
    toalhas = [b for b in boxes if b["kind"] == "kb_toalha"]
    assert len(toalhas) >= 2, f"{nm}: nicho sem toalhas ({len(toalhas)})"


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_faucet_is_deck_mounted_from_countertop(nm):
    # ESTÚDIO BANHEIRO: torneira DE BANCADA (corpo nasce no tampo ~0.88m, bica
    # ~1.03-1.06m) com anel dourado na base — não mais de parede
    boxes = ROOMS[nm]
    t = [b for b in boxes if b["kind"] == "kb_torneira"]
    assert t, f"{nm}: sem torneira"
    zs = [b["z0_in"] / M2IN for b in t]
    assert 0.85 <= min(zs) <= 0.92, \
        f"{nm}: corpo da torneira deve nascer do tampo (z {min(zs):.2f})"


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_toilet_is_matte_black(nm):
    boxes = ROOMS[nm]
    vaso = [b for b in boxes if b["kind"] == "vaso"]
    assert vaso and all(sum(b["rgb"]) / 3 <= 80 for b in vaso), \
        f"{nm}: vaso não é preto fosco (referência)"


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_stone_top_is_greige(nm):
    # STONE_MONOLITH: tampo em pedra greige clara-media (area seca)
    boxes = ROOMS[nm]
    tampo = [b for b in boxes if b["kind"] == "bancada_banho"]
    assert tampo, f"{nm}: sem tampo"
    for b in tampo:
        assert 110 <= sum(b["rgb"]) / 3 <= 175, f"{nm}: tampo {b['rgb']} fora do greige"


def test_shower_box_has_black_profile_and_shower():
    with_box = {nm: bx for nm, bx in ROOMS.items()
                if any(b["kind"] == "box_vidro" for b in bx)}
    if not with_box:
        pytest.skip("nenhum banho comportou box (área)")
    for nm, boxes in with_box.items():
        assert any(b["kind"] == "kb_perfil" for b in boxes), f"{nm}: box sem perfil preto"
        assert any(b["kind"] == "kb_ducha" for b in boxes), f"{nm}: box sem ducha"


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_no_pure_white(nm):
    for b in ROOMS[nm]:
        if "led" in str(b["kind"]).lower():
            continue
        assert sum(b["rgb"]) / 3 <= 228, f"{nm}: branco em {b['kind']} {b['rgb']}"
