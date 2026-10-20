"""P2 shared material tokens and legacy compatibility without render side-effects."""
from tools.rooms.shared import materials


def test_style_symbols_live_in_the_single_shared_owner():
    # a fachada style_spec saiu na FP-044/F6; o dono unico continua sendo tools.rooms.shared.materials
    assert isinstance(materials.STYLE_TOKENS, dict)
    for name in ("StyleSpec", "apply_style", "get_style",
                 "resolve_material", "attach_materials", "module_family",
                 "texture_map_for", "finish_map_for", "tile_map_for", "texture_env"):
        assert getattr(materials, name).__module__ == materials.__name__


def test_styles_preserve_cross_room_material_separation():
    for style in ("industrial", "modern_warm", "black_wood_gold"):
        if style not in materials.STYLE_TOKENS:
            continue
        sofa = materials.resolve_material(style, "sofa", "base")
        rack = materials.resolve_material(style, "rack", "base")
        assert isinstance(sofa, dict)
        assert isinstance(rack, dict)
        assert materials.resolve_material(style, "sofa", "base") == sofa


def test_materials_owner_holds_the_style_tables():
    from pathlib import Path
    src = Path(materials.__file__).read_text(encoding="utf-8")
    assert src.count("class StyleSpec") == 1
    assert "_INDUSTRIAL_RGB = {" in src
