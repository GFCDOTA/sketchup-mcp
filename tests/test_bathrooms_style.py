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
def test_vanity_is_floating_nogueira_with_black_sink(nm):
    boxes = ROOMS[nm]
    gab = [b for b in boxes if b["kind"] == "gabinete"]
    assert gab, f"{nm}: sem gabinete"
    assert min(b["z0_in"] for b in gab) >= 0.24 * M2IN, f"{nm}: gabinete no chão — pediu suspenso"
    assert any(80 <= b["rgb"][0] <= 130 for b in gab), f"{nm}: gabinete não é nogueira"
    cuba = [b for b in boxes if b["kind"] == "cuba"]
    assert cuba and all(sum(b["rgb"]) / 3 <= 60 for b in cuba), f"{nm}: cuba não é preta (D5)"
    assert any(b["kind"] == "kb_gola" for b in boxes), f"{nm}: gabinete sem gola handleless"
    assert any(b["kind"] == "kb_led" for b in boxes), f"{nm}: espelho sem retroiluminação"
    assert any(b["kind"] == "kb_torneira" for b in boxes), f"{nm}: bancada sem torneira"


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_metals_black_with_single_gold_ring(nm):
    # ESTÚDIO BANHEIRO (referência oficial 2026-08-05, loop GPT 4.4→8.0):
    # metais PRETO fosco; ouro em UM ponto só — o kb_anel da torneira. Bronze ZERO
    # (substitui a referência de 2026-08-04 que pedia torneira de parede bronze).
    boxes = ROOMS[nm]
    bronze = [b for b in boxes if list(b["rgb"]) == BRONZE]
    assert not bronze, f"{nm}: bronze sobrou em {[b['kind'] for b in bronze]}"
    torneira = [b for b in boxes if b["kind"] == "kb_torneira"]
    assert torneira and all(sum(b["rgb"]) / 3 <= 60 for b in torneira), \
        f"{nm}: torneira não é preto fosco"
    anel = [b for b in boxes if b["kind"] == "kb_anel"]
    assert len(anel) == 1, f"{nm}: anel dourado deve ser ÚNICO (tem {len(anel)})"


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_mirror_frame_is_champagne(nm):
    # moldura champagne fina do espelho (identidade da referência)
    boxes = ROOMS[nm]
    mold = [b for b in boxes if b["kind"] == "kb_moldura"]
    assert mold, f"{nm}: espelho sem moldura"
    for b in mold:
        assert b["rgb"][0] > b["rgb"][2] and b["rgb"][0] >= 150, \
            f"{nm}: moldura {b['rgb']} não é champagne"


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
    anel = [b for b in boxes if b["kind"] == "kb_anel"]
    assert anel and abs(anel[0]["z0_in"] / M2IN - min(zs)) < 0.02, \
        f"{nm}: anel dourado deve estar na BASE da torneira"


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_toilet_is_matte_black(nm):
    boxes = ROOMS[nm]
    vaso = [b for b in boxes if b["kind"] == "vaso"]
    assert vaso and all(sum(b["rgb"]) / 3 <= 80 for b in vaso), \
        f"{nm}: vaso não é preto fosco (referência)"


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_stone_top_is_quiet_dark(nm):
    boxes = ROOMS[nm]
    tampo = [b for b in boxes if b["kind"] == "bancada_banho"]
    assert tampo, f"{nm}: sem tampo"
    for b in tampo:
        assert sum(b["rgb"]) / 3 <= 70, f"{nm}: tampo claro {b['rgb']} — pedra quieta escura"


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
