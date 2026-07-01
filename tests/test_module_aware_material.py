"""FP-037 Module-aware Material Attribution — resolve material por (familia_de_modulo, kind), nao
so por kind. Destrava madeira no rack/mesa SEM contaminar o sofa (kinds base/foot sobrecarregados).
Python puro + contrato-texto do .rb (sem SketchUp)."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.style_spec import STYLE_TOKENS, attach_materials, module_family, resolve_material

ROOT = Path(__file__).resolve().parents[1]
TEX_DIR = ROOT / "assets/textures/procedural"


def test_module_family_normalizes_known_labels():
    cases = {
        "Rack TV": "rack", "Mesa de centro": "coffee_table", "Mesa de jantar": "dining_table",
        "Cadeira jantar": "dining_chair", "Sofa": "sofa", "Cama": "bed",
        "Criado-mudo 2": "nightstand", "Guarda-roupa": "wardrobe", "Tapete": "rug",
        "Parede concreto": "wall_panel", "base_cabinet_01": "kitchen_cabinet",
        "Bancada": "bathroom_vanity", "Quadro": "decor",
    }
    for label, fam in cases.items():
        assert module_family(label) == fam, f"{label} -> {module_family(label)} != {fam}"
    assert module_family("coisa desconhecida") == ""   # fallback por kind
    assert module_family(None) == ""


def test_cadeira_jantar_is_chair_not_table():
    # 'Cadeira jantar' contem 'jantar' -> a ordem das regras nao pode classificar como dining_table
    assert module_family("Cadeira jantar") == "dining_chair"


@pytest.mark.parametrize("style", list(STYLE_TOKENS))
def test_rack_base_resolves_wood_not_sofa(style):
    r = resolve_material(style, "rack", "base")
    assert r["tex_png"] is not None and "wood" in r["tex_png"]
    assert r["mat_name"] == "ph_rack_base"


@pytest.mark.parametrize("style", list(STYLE_TOKENS))
def test_sofa_base_never_gets_wood(style):
    r = resolve_material(style, "sofa", "base")
    assert r["tex_png"] is None, "sofa.base NAO pode receber madeira (kind sobrecarregado)"
    assert r["mat_name"] == "ph_base"        # nome kind-level, distinto de ph_rack_base


@pytest.mark.parametrize("style", list(STYLE_TOKENS))
def test_same_kind_different_module_distinct_materials(style):
    rack = resolve_material(style, "rack", "base")
    sofa = resolve_material(style, "sofa", "base")
    assert rack["mat_name"] != sofa["mat_name"], "rack.base e sofa.base nao podem colidir em ph_base"


def test_fallback_chain_module_then_kind_then_flat():
    # NIVEL 1: override por modulo
    assert resolve_material("industrial", "coffee_table", "top")["tex_png"] == "wood_dark.png"
    # NIVEL 2: mapa por kind (FP-036) — o sofa de tecido continua resolvendo
    r2 = resolve_material("industrial", "sofa", "seat_cushion")
    assert r2["tex_png"] == "fabric_charcoal.png" and r2["mat_name"] == "ph_seat_cushion"
    # NIVEL 3: flat — kind sem entrada em lugar nenhum
    r3 = resolve_material("industrial", "sofa", "foot")
    assert r3["tex_png"] is None and r3["mat_name"] == "ph_foot"


def test_no_paint_all_across_families():
    # os pes/pernas/saia (apoio) NUNCA viram madeira, em nenhuma familia
    for fam in ("rack", "coffee_table", "dining_table", "sofa"):
        for kind in ("foot", "leg", "saia"):
            assert resolve_material("industrial", fam, kind)["tex_png"] is None, f"{fam}.{kind} virou madeira"


@pytest.mark.parametrize("style", list(STYLE_TOKENS))
def test_resolved_pngs_exist(style):
    st = STYLE_TOKENS[style]
    for png in st.module_kind_texture.values():
        assert (TEX_DIR / png).exists(), f"{style}: png de modulo inexistente {png}"


def test_module_finish_tuple_keys_never_serialized():
    # chave-tupla vive so no Python; garantir que ninguem tente json.dumps do mapa por engano
    import json
    st = STYLE_TOKENS["industrial"]
    with pytest.raises(TypeError):
        json.dumps(st.module_kind_texture)   # tuple keys -> nao serializavel (esperado)


# ---------------------------------------------------------------- Fatia 2: attach por box
def _boxes():
    return [
        {"module": "Sofa", "kind": "base", "rgb": [34, 35, 38]},
        {"module": "Sofa", "kind": "seat_cushion", "rgb": [64, 66, 70]},
        {"module": "Rack TV", "kind": "base", "rgb": [60, 47, 36]},
        {"module": "Rack TV", "kind": "front", "rgb": [80, 62, 46]},
        {"module": "Mesa de centro", "kind": "top", "rgb": [80, 62, 46]},
        {"module": "Mesa de centro", "kind": "leg", "rgb": [30, 30, 33]},
    ]


def test_attach_materials_mutates_boxes():
    boxes = _boxes()
    n = attach_materials(boxes, "industrial")
    by = {(b["module"], b["kind"]): b for b in boxes}
    # todos ganharam os campos
    assert all("mat_name" in b and "tex_png" in b and "tile_in" in b for b in boxes)
    # rack.base e front -> madeira; sofa.base -> flat; sofa.cushion -> fabric (kind-level)
    assert by[("Rack TV", "base")]["tex_png"] == "wood_dark.png"
    assert by[("Rack TV", "base")]["mat_name"] == "ph_rack_base"
    assert by[("Sofa", "base")]["tex_png"] is None
    assert by[("Sofa", "base")]["mat_name"] == "ph_base"
    assert by[("Sofa", "seat_cushion")]["tex_png"] == "fabric_charcoal.png"
    assert by[("Mesa de centro", "top")]["tex_png"] == "wood_dark.png"
    assert by[("Mesa de centro", "leg")]["tex_png"] is None
    assert n == 4        # rack.base, rack.front, mesa.top, sofa.cushion


def test_attach_materials_noop_without_style():
    boxes = _boxes()
    assert attach_materials(boxes, None) == 0
    assert all("mat_name" not in b for b in boxes)   # sem estilo -> nao mexe (fallback FP-036)


# ---------------------------------------------------------------- Fatia 3: contrato-texto do .rb
def test_pl_run_prefers_resolved_material():
    """.rb nao roda headless -> contrato-TEXTO. FLAG: confirmar madeira no rack em build SU real."""
    rb = (ROOT / "tools/place_layout_skp.rb").read_text("utf-8")
    assert "b['mat_name']" in rb, "o .rb precisa preferir o material resolvido (mat_name)"
    assert "b.key?('tex_png')" in rb, "o .rb precisa preferir o tex_png por box (com fallback FP-036)"
    assert "b['tile_in']" in rb, "o .rb precisa usar o tile_in resolvido"
    assert "tex_map[kind]" in rb, "o fallback FP-036 (tex_map por kind) deve continuar existindo"
    assert "pl_material(model, mat_name" in rb, "o material deve ser criado pelo nome resolvido"


def test_furnish_calls_attach_materials():
    src = (ROOT / "tools/furnish_apartment.py").read_text("utf-8")
    assert "attach_materials" in src, "furnish deve resolver material por modulo antes do dump"
