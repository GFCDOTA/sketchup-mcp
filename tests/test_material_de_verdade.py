"""FP-036 Material de Verdade — testes do path interativo texturizado + finish token +
flat_white gate. Micro-fixtures deterministicas (sem SketchUp). O comportamento no .skp REAL
(m.texture no SU) e verificado por CONTRATO-TEXTO aqui + FLAG de confirmacao em build SU real.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from tools.flat_white_gate import flat_white_check
from tools.interior_studio.render_fingerprint import fingerprint, texture_frac
from tools.style_spec import (
    STYLE_TOKENS,
    finish_map_for,
    texture_env,
    texture_map_for,
    tile_map_for,
)

ROOT = Path(__file__).resolve().parents[1]
TEX_DIR = ROOT / "assets/textures/procedural"

# ---------------------------------------------------------------- micro-fixtures (deterministicas)
_W, _H = 800, 600
_BG = (176, 174, 170)
_BOXES = {"wall": (100, 60, 700, 200), "sofa": (150, 320, 450, 500),
          "rack": (500, 360, 700, 470), "rug": (140, 500, 470, 590)}
_FLAT_RGB = {"wall": (165, 162, 158), "sofa": (60, 62, 66), "rack": (74, 56, 42), "rug": (54, 54, 58)}
_TEX_PNG = {"wall": "concrete.png", "sofa": "fabric_charcoal.png",
            "rack": "wood_dark.png", "rug": "fabric_charcoal.png"}


def _flat_png(path):
    img = np.full((_H, _W, 3), _BG, dtype=np.uint8)
    for k, (x0, y0, x1, y1) in _BOXES.items():
        img[y0:y1, x0:x1] = _FLAT_RGB[k]
    Image.fromarray(img).save(path)
    return path


def _textured_png(path):
    img = np.full((_H, _W, 3), _BG, dtype=np.uint8)
    for k, (x0, y0, x1, y1) in _BOXES.items():
        t = np.asarray(Image.open(TEX_DIR / _TEX_PNG[k]).convert("RGB"))
        th, tw = t.shape[:2]
        h, w = y1 - y0, x1 - x0
        img[y0:y1, x0:x1] = np.tile(t, (h // th + 1, w // tw + 1, 1))[:h, :w]
    Image.fromarray(img).save(path)
    return path


def _white_png(path):
    img = np.full((_H, _W, 3), (247, 247, 245), dtype=np.uint8)
    img[320:500, 150:450] = (238, 236, 232)
    Image.fromarray(img).save(path)
    return path


def _fabric_only_png(path):
    """Sofa de TECIDO (fabric_charcoal, o must_style primario) enchendo a maior parte do frame,
    SEM parede de concreto de alta amplitude. Guarda o finding #1: o gate NAO pode falso-FALHAR o
    proprio sofa texturizado que o FP-036 entrega so porque a trama e sutil."""
    img = np.full((_H, _W, 3), (150, 148, 146), dtype=np.uint8)   # shell cinza medio (da contraste)
    t = np.asarray(Image.open(TEX_DIR / "fabric_charcoal.png").convert("RGB"))
    th, tw = t.shape[:2]
    x0, y0, x1, y1 = 90, 90, 710, 510
    h, w = y1 - y0, x1 - x0
    img[y0:y1, x0:x1] = np.tile(t, (h // th + 1, w // tw + 1, 1))[:h, :w]
    Image.fromarray(img).save(path)
    return path


def _blank_png(path):
    Image.fromarray(np.full((_H, _W, 3), (60, 61, 63), dtype=np.uint8)).save(path)
    return path


# ---------------------------------------------------------------- texture map / invariante kind
def test_texture_map_for_industrial_covers_must_style():
    st = STYLE_TOKENS["industrial"]
    tm = texture_map_for("industrial")
    for k in st.must_style:
        # sofa (seat/back/arm) e tapete SAO os kinds que o Felipe julga texturizados
        if k == "tapete" or "cushion" in k or k == "arm":
            assert k in tm, f"must_style '{k}' sem textura no mapa industrial"
    # e todo png referenciado existe (guarda a regressao wood.png/fabric.png inexistentes)
    for png in tm.values():
        assert (TEX_DIR / png).exists(), f"png ausente: {png}"


@pytest.mark.parametrize("style", list(STYLE_TOKENS))
def test_all_texture_maps_reference_existing_pngs(style):
    for png in texture_map_for(style).values():
        assert (TEX_DIR / png).exists(), f"{style}: png inexistente {png}"


def test_apply_style_does_not_paint_all_with_first():
    """Invariante FP-036: cada kind mapeia a SUA textura, nunca a 1a peca em todos.
    Materiais de familia diferente (madeira vs tecido vs metal) -> pngs diferentes."""
    tm = texture_map_for("industrial")
    assert tm["rack_tv"] != tm["seat_cushion"], "madeira e tecido nao podem compartilhar png"
    assert tm["frame"] != tm["rack_tv"], "metal e madeira nao podem compartilhar png"
    assert len(set(tm.values())) >= 3, "mapa colapsou numa unica textura (paint-all)"
    # cada kind aponta pra si mesmo (dict keyed por kind = fonte unica)
    assert all(isinstance(k, str) and v.endswith(".png") for k, v in tm.items())


# ---------------------------------------------------------------- finish / BRDF token (.md-citado)
def _band(cite: str):
    """(rough_lo, rough_hi, metal_lo, metal_hi) da faixa CITADA na .md. Ordem importa
    (grafite/preto/inox antes do generico)."""
    c = cite.lower()
    if "grafite" in c:
        return (0.6, 0.8, 0.2, 0.6)          # metal.md grafite fosco
    if "preto fosco" in c:
        return (0.6, 1.0, 0.0, 0.5)          # metal.md preto fosco (roughness alta)
    if "inox" in c:
        return (0.3, 0.5, 0.7, 1.0)          # metal.md inox escovado
    if "laca" in c or "lacquer" in c:
        return (0.5, 0.85, 0.0, 0.0)         # lacquer.md laca fosca (metalness 0)
    if "wood.md" in c:
        return (0.5, 0.85, 0.0, 0.0)         # wood.md fosco/acetinado
    if "stone.md" in c or "mineral" in c:
        return (0.5, 0.95, 0.0, 0.0)         # stone.md quartzo/mineral fosco
    return (0.0, 1.0, 0.0, 1.0)              # sem cite reconhecida -> so range fisico


@pytest.mark.parametrize("style", list(STYLE_TOKENS))
def test_finish_map_values_within_reference_bands(style):
    fm = finish_map_for(style)
    assert fm, f"{style} sem finish token"
    for kind, fin in fm.items():
        cite = fin.get("cite", "")
        assert cite, f"{style}/{kind}: sem citacao da .md (valor nao pode ser inventado)"
        rlo, rhi, mlo, mhi = _band(cite)
        r, m = fin["roughness"], fin["metalness"]
        assert 0.0 <= r <= 1.0 and 0.0 <= m <= 1.0, f"{style}/{kind}: fora do range fisico"
        assert rlo <= r <= rhi, f"{style}/{kind}: roughness {r} fora da faixa {rlo}-{rhi} ({cite})"
        assert mlo <= m <= mhi, f"{style}/{kind}: metalness {m} fora da faixa {mlo}-{mhi} ({cite})"
        assert fin["tile_in"] in (40, 80)


def test_tile_map_mirrors_finish_tile_in():
    for style in STYLE_TOKENS:
        tiles = tile_map_for(style)
        fm = finish_map_for(style)
        assert tiles == {k: v["tile_in"] for k, v in fm.items()}
        # parede pede tile grande (~2m); movel tile default
        if "parede_concreto" in tiles:
            assert tiles["parede_concreto"] == 80


# ---------------------------------------------------------------- flat_white gate (micro-fixture)
# VEREDITO = near_white_frac (sinal confiavel). texture_frac e ADVISORY (nao decide), pois a revisao
# adversarial provou que ele falso-FALHA tecido sutil e falso-PASSA arestas AA num render de linha.
def test_flat_white_fails_on_synthetic_white_png(tmp_path):
    r = flat_white_check(_white_png(tmp_path / "white.png"), "industrial")
    assert r["result"] == "FAIL", r
    assert r["metrics"]["near_white_frac"] > 0.55


def test_flat_white_passes_on_textured_png(tmp_path):
    r = flat_white_check(_textured_png(tmp_path / "tex.png"), "industrial")
    assert r["result"] == "PASS", r
    assert r["metrics"]["near_white_frac"] < 0.30


def test_flat_white_does_not_false_fail_fabric_sofa(tmp_path):
    """Finding #1: um sofa de TECIDO texturizado (must_style primario) enchendo o frame NAO pode
    ser FALHADO como 'chapado'. O veredito nao depende do texture_frac (que e cego a trama sutil)."""
    r = flat_white_check(_fabric_only_png(tmp_path / "fab.png"), "industrial")
    assert r["result"] != "FAIL", r


def test_flat_white_warns_on_blank_render(tmp_path):
    """Render quase-VAZIO/uniforme (SU nao desenhou / uma cor so) -> WARN (contraste minusculo).
    (FP-039: veredito por flag de vocabulario fixo 'quase_vazio'.)"""
    r = flat_white_check(_blank_png(tmp_path / "blank.png"), "industrial")
    assert r["result"] == "WARN", r
    assert "quase_vazio" in r["flags"]


def test_gate_verdict_is_texture_frac_independent(tmp_path):
    """Contrato honesto: texture_frac e ADVISORY, nunca veredito. Uma cena FACETADA de cor chapada
    (nao-branca) NAO e FALHADA por 'sem textura' — a prova de textura e o log per-kind do .rb."""
    r = flat_white_check(_flat_png(tmp_path / "flat.png"), "industrial")
    assert r["result"] == "PASS", r                       # nao-branco, com contraste -> PASS honesto
    assert "texture_frac_advisory" in r["metrics"]        # reportado, nao no veredito


def test_texture_frac_is_advisory_and_registers_texture(tmp_path):
    """Sanidade do advisory: textura de veio/concreto eleva texture_frac acima do chapado solido."""
    flat = np.asarray(Image.open(_flat_png(tmp_path / "f.png")).convert("RGB")).astype(float)
    tex = np.asarray(Image.open(_textured_png(tmp_path / "t.png")).convert("RGB")).astype(float)
    assert texture_frac(tex) > texture_frac(flat)


def test_flat_white_gate_deterministic(tmp_path):
    p = _textured_png(tmp_path / "det.png")
    assert flat_white_check(p)["metrics"] == flat_white_check(p)["metrics"]


# ---------------------------------------------------------------- env injection (furnish + slice)
def test_furnish_injects_tex_map_when_style_set():
    env = texture_env("industrial", TEX_DIR)
    assert env, "estilo valido deve injetar env"
    import json
    assert env["LAYOUT_TEX_MAP"] != "{}"
    assert json.loads(env["LAYOUT_TEX_MAP"]) == texture_map_for("industrial")
    assert json.loads(env["LAYOUT_TILE_MAP"]) == tile_map_for("industrial")
    assert Path(env["LAYOUT_TEX_DIR"]).is_dir()


def test_texture_env_empty_for_unknown_style():
    # sem estilo -> {} -> o .rb cai no default '{}' = cor chapada (fallback preservado)
    assert texture_env("nope", TEX_DIR) == {}
    assert texture_env(None, TEX_DIR) == {}


# ---------------------------------------------------------------- CONTRATO-TEXTO do .rb (nao-headless)
def test_pl_material_sets_texture_when_png_present():
    """O .rb nao roda headless aqui -> contrato-TEXTO: o path interativo aplica m.texture por kind
    lendo LAYOUT_TEX_MAP/LAYOUT_TILE_MAP. FLAG: confirmar visualmente em build SU real (Felipe)."""
    rb = (ROOT / "tools/place_layout_skp.rb").read_text("utf-8")
    assert "m.texture = tex_path" in rb, "pl_material nao seta m.texture (o BUG do FP-036)"
    assert "LAYOUT_TEX_MAP" in rb and "LAYOUT_TILE_MAP" in rb, ".rb nao le os mapas injetados"
    assert "tex_path = (png && tex_dir)" in rb, "kind != fonte unica (deveria resolver png por kind)"
    assert "File.exist?(tex_path)" in rb, "sem fallback: png ausente deve cair na cor chapada"
    # sanity: pl_material assinatura estendida
    assert "def pl_material(model, name, rgb, tex_path = nil, tile = 40)" in rb


def test_furnish_and_slice_call_texture_env():
    """Ambos os callers do path interativo injetam via style_spec.texture_env (fonte unica)."""
    for f in ("tools/furnish_apartment.py", "tools/place_layout_skp.py"):
        src = (ROOT / f).read_text("utf-8")
        assert "texture_env" in src, f"{f} nao injeta LAYOUT_TEX_MAP via texture_env"
