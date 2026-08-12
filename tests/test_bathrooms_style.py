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

# Escala real de planta_74 (0.0259) e' setada pelo tests/conftest.py, marcada
# via pytest_collection_modifyitems (este arquivo roda inteiro na invocacao
# `pytest -m planta74_scale`) — nao setar aqui, so no conftest (fonte unica).
pytestmark = pytest.mark.planta74_scale

from tools.bathroom_layout import BASE_THEME, build_boxes, theme_of  # noqa: E402

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
    if theme_of(nm) == BASE_THEME:      # greige só é regra no tema do BANHO 01
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
def test_vanity_has_two_drawer_fronts_with_shadow_gap(nm):
    # Curadoria Felipe 2026-08-08 (kit banho01): gabinete linguagem Celite
    # Elite — 2 frentes limpas + shadow gap entre elas; SAI o nicho de toalhas
    boxes = ROOMS[nm]
    fronts = [b for b in boxes if b["kind"] == "gabinete"
              and b["z0_in"] + b["h_in"] <= 0.79 * M2IN and b["h_in"] >= 0.10 * M2IN]
    assert len(fronts) >= 2, f"{nm}: gabinete sem as 2 frentes de gaveta"
    gaps = [b for b in boxes if b["kind"] == "kb_sombra"
            and 0.55 * M2IN <= b["z0_in"] <= 0.65 * M2IN]
    assert gaps, f"{nm}: sem shadow gap entre as frentes"
    assert not any(b["kind"] == "kb_nicho_fundo" for b in boxes), \
        f"{nm}: nicho de toalhas devia ter saído (curadoria 2026-08-08)"


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
def test_toilet_is_matte_black(nm):  # inclui assento/tampa (kb_tampa, p23)
    boxes = ROOMS[nm]
    vaso = [b for b in boxes if b["kind"] in ("vaso", "kb_tampa")]
    assert vaso and all(sum(b["rgb"]) / 3 <= 80 for b in vaso), \
        f"{nm}: vaso não é preto fosco (referência)"
    assert any(b["kind"] == "kb_tampa" for b in vaso), \
        f"{nm}: assento/tampa precisam de kind próprio (satin separa da caixa)"


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_stone_top_is_greige(nm):
    # STONE_MONOLITH: tampo em pedra greige clara-media (area seca). Nos temas
    # dos outros banhos o tom muda, mas o tampo continua sendo PEDRA lida
    # (nunca branco estourado nem preto absoluto) — ver test_no_pure_white.
    boxes = ROOMS[nm]
    tampo = [b for b in boxes if b["kind"] == "bancada_banho"]
    assert tampo, f"{nm}: sem tampo"
    lo, hi = (110, 175) if theme_of(nm) == BASE_THEME else (45, 205)
    for b in tampo:
        assert lo <= sum(b["rgb"]) / 3 <= hi, f"{nm}: tampo {b['rgb']} fora da faixa do tema"


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_theme_isolates_materials_and_keeps_wood_dry(nm):
    # Tema por cômodo (2026-08-08): cada sala fora do tema-base precisa de
    # mat_name PRÓPRIO (senão pinta por cima do BANHO 01 aprovado), e madeira
    # nunca entra na área molhada do box (regra fixa do Felipe).
    boxes = ROOMS[nm]
    th = theme_of(nm)
    if th != BASE_THEME:
        semt = [b["kind"] for b in boxes if not b.get("mat_name")]
        assert not semt, f"{nm} ({th}): peças sem mat_name próprio: {semt[:5]}"
    molhado = ("kb_piso_box", "kb_parede_pedra", "kb_nicho_box", "box_vidro", "kb_folha")
    for b in boxes:
        if b["kind"] in molhado:
            assert "wood" not in str(b.get("tex_png", "")).lower(), \
                f"{nm}: madeira na área molhada ({b['kind']} = {b.get('tex_png')})"


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


# ---- GEOMETRY_INTEGRITY_GATE (interior-project-audit Gate 1 + Gate 10) ----
# GPT-Docker 2026-08-09: o "ceu vazando nos cantos" so foi descoberto olhando
# render — isso nao pode depender de imagem. add_face(corners) do SketchUp
# retorna nil (peca desaparece em silencio, engolida pelo rescue do .rb) para
# um poligono invalido/self-intersecting; e mesmo com poligono valido, um
# vao vertical entre o topo do painel de parede e a base do teto vaza fundo
# no render. Os dois testes abaixo travam essas duas causas RAIZ do gotcha,
# sem precisar renderizar nada.

@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_ceiling_polygon_is_valid_simple(nm):
    """kb_teto precisa ser um poligono valido/simples — senao add_face(corners)
    do SketchUp retorna nil e a peca desaparece em silencio (rescue do .rb)."""
    from shapely.geometry import Polygon
    teto = [b for b in ROOMS[nm] if b["kind"] == "kb_teto"]
    assert teto, f"{nm}: sem kb_teto — comodo sem fechamento de teto"
    for t in teto:
        poly = Polygon(t["corners"])
        assert poly.is_valid, f"{nm}: kb_teto poligono invalido/self-intersecting ({len(t['corners'])} pts)"
        assert poly.area > 0, f"{nm}: kb_teto com area zero"


@pytest.mark.parametrize("nm", sorted(ROOMS))
def test_wall_panels_reach_ceiling_no_gap(nm):
    """Painel de parede (kb_parede/kb_parede_pedra) precisa encostar na base
    do teto — vao vertical entre os dois vaza fundo/ceu no render (gotcha
    pago 2026-08-09: painel parava em 2.30m, teto comecava em 2.50m)."""
    boxes = ROOMS[nm]
    teto = [b for b in boxes if b["kind"] == "kb_teto"]
    if not teto:
        pytest.skip(f"{nm}: sem kb_teto (coberto por test_ceiling_polygon_is_valid_simple)")
    ceiling_z0_in = min(t["z0_in"] for t in teto)
    panels = [b for b in boxes if b["kind"] in ("kb_parede", "kb_parede_pedra")]
    assert panels, f"{nm}: sem painel de parede nenhum"
    tol_in = 0.20   # ~5mm de folga (arredondamento de escala), nao 20cm do bug
    for p in panels:
        top_in = p["z0_in"] + p["h_in"]
        assert top_in >= ceiling_z0_in - tol_in, (
            f"{nm}: painel {p['kind']} para em {top_in:.1f}in mas o teto comeca "
            f"em {ceiling_z0_in:.1f}in — vao de {ceiling_z0_in - top_in:.1f}in vaza fundo")
