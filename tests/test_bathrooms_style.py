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
def test_metals_are_bronze_per_felipe_reference(nm):
    # Referência ChatGPT do Felipe (2026-08-04, "tipo isso"): torneira de PAREDE
    # e ducha em BRONZE em todos os banhos (sobrepõe o veto antigo de manutenção;
    # PVD bronze resiste — trade-off registrado). Perfis do box seguem PRETOS.
    boxes = ROOMS[nm]
    bronze = [b for b in boxes if list(b["rgb"]) == BRONZE]
    assert bronze, f"{nm}: sem bronze — a referência pede metais bronze"
    torneira_bronze = [b for b in bronze if "torneira" in b["kind"]]
    assert torneira_bronze, f"{nm}: torneira não é bronze"


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_vanity_has_towel_niche_signature(nm):
    # A assinatura da referência: nicho aberto nogueira com TOALHAS + LED sob o tampo
    boxes = ROOMS[nm]
    assert any(b["kind"] == "kb_nicho_fundo" for b in boxes), f"{nm}: sem nicho de toalhas"
    toalhas = [b for b in boxes if b["kind"] == "kb_toalha"]
    assert len(toalhas) >= 2, f"{nm}: nicho sem toalhas ({len(toalhas)})"


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_faucet_is_wall_mounted(nm):
    # torneira de PAREDE (bica horizontal ~1.05m) — não montante de bancada
    boxes = ROOMS[nm]
    t = [b for b in boxes if b["kind"] == "kb_torneira"]
    assert t, f"{nm}: sem torneira"
    zs = [b["z0_in"] / M2IN for b in t]
    assert min(zs) >= 0.95, f"{nm}: torneira nasce da bancada (z {min(zs):.2f}) — referência é de parede"


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
