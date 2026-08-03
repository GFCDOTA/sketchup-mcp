"""Suítes 01/02 na gramática BLACK_WOOD_GOLD — programa apê-inteiro (2026-08-03).

Contratos: cama QUEEN real (1.58x1.98) nas duas suítes, painel ripado de
cabeceira, criados SUSPENSOS handleless (sem pé, sem knob) com tampo nogueira
e LED, guarda-roupa até o teto sem barra de puxador, bronze contido (1-2 peças
por suíte), teto de claridade (fronha 222, nunca branco puro).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.furnish_apartment import bedroom_designer_boxes

M2IN = 39.3700787402
BRONZE = [171, 119, 63]


@pytest.fixture(scope="module")
def suites():
    con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    out = {}
    for rid in ("r000", "r003"):
        boxes, meta = bedroom_designer_boxes(con, rid)
        assert boxes, f"suíte {rid} não montou: {meta}"
        out[rid] = (boxes, meta)
    return out


def test_bed_master_is_real_queen(suites):
    # r000 (15.9m² REAL): queen 1.58x1.98 — king engolia criados+circulação.
    bp = suites["r000"][1].get("bed_parametric") or {}
    assert abs(bp.get("W_m", 0) - 1.58) <= 0.05, f"largura {bp} != queen 1.58"
    assert abs(bp.get("L_m", 0) - 1.98) <= 0.06, f"comprimento {bp} != queen 1.98"


def test_bed_suite02_fits_room_honestly(suites):
    # r003 tem 8.0m² REAL (medida manda): casal 1.38x1.88 lê como suíte sem
    # engolir o quarto; queen aqui seria fabricar espaço que não existe.
    bp = suites["r003"][1].get("bed_parametric") or {}
    assert abs(bp.get("W_m", 0) - 1.38) <= 0.05, f"largura {bp} != casal 1.38"


@pytest.mark.parametrize("rid", ["r000", "r003"])
def test_headboard_panel_with_ripas(suites, rid):
    boxes, _ = suites[rid]
    painel = [b for b in boxes if b.get("module") == "Painel cabeceira"]
    assert painel, f"{rid}: painel de cabeceira ausente"
    ripas = [b for b in painel if b["kind"] == "ks_ripa"]
    assert len(ripas) >= 8, f"{rid}: painel sem ripas ({len(ripas)})"


@pytest.mark.parametrize("rid", ["r000", "r003"])
def test_nightstands_are_floating_handleless(suites, rid):
    boxes, _ = suites[rid]
    ns = [b for b in boxes if str(b.get("module", "")).startswith("Criado-mudo")]
    assert ns, f"{rid}: sem criados"
    kinds = {b["kind"] for b in ns}
    assert "pe" not in kinds and "puxador" not in kinds, \
        f"{rid}: criado com pé/knob — diretriz pede suspenso handleless"
    corpo = [b for b in ns if b["kind"] == "ks_criado_corpo"]
    assert corpo and min(b["z0_in"] for b in corpo) >= 0.28 * M2IN, f"{rid}: criado não flutua"
    assert any(b["kind"] == "ks_led" for b in ns), f"{rid}: criado sem LED"


@pytest.mark.parametrize("rid", ["r000", "r003"])
def test_wardrobe_to_ceiling_handleless(suites, rid):
    boxes, _ = suites[rid]
    wd = [b for b in boxes if b.get("module") == "Guarda-roupa"]
    if not wd:
        pytest.skip(f"{rid} sem guarda-roupa (cômodo não comportou)")
    assert not any(b["kind"] == "puxador" for b in wd), f"{rid}: barra de puxador viva"
    top_m = max(b["z0_in"] + b["h_in"] for b in wd) / M2IN
    assert top_m >= 2.60, f"{rid}: guarda-roupa para em {top_m:.2f}m — pediu até o teto"


@pytest.mark.parametrize("rid", ["r000", "r003"])
def test_bronze_is_contained(suites, rid):
    boxes, _ = suites[rid]
    bronze = [b for b in boxes if list(b["rgb"]) == BRONZE]
    assert 1 <= len(bronze) <= 2, f"{rid}: {len(bronze)} peças bronze (regra: 1 ponto)"


@pytest.mark.parametrize("rid", ["r000", "r003"])
def test_no_pure_white(suites, rid):
    boxes, _ = suites[rid]
    for b in boxes:
        if "led" in str(b["kind"]).lower():
            continue
        assert sum(b["rgb"]) / 3 <= 225, \
            f"{rid}: branco em {b.get('module')}/{b['kind']} {b['rgb']}"
