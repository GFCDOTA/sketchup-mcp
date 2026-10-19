"""P2 shared material tokens and legacy compatibility without render side-effects."""
from tools import style_spec as legacy
from tools.rooms.shared import materials


def test_legacy_style_symbols_reference_single_shared_owner():
    for name in ("StyleSpec", "STYLE_TOKENS", "apply_style", "get_style",
                 "resolve_material", "attach_materials", "module_family",
                 "texture_map_for", "finish_map_for", "tile_map_for", "texture_env"):
        assert getattr(legacy, name) is getattr(materials, name)


def test_styles_preserve_cross_room_material_separation():
    for style in ("industrial", "modern_warm", "black_wood_gold"):
        if style not in materials.STYLE_TOKENS:
            continue
        sofa = materials.resolve_material(style, "sofa", "base")
        rack = materials.resolve_material(style, "rack", "base")
        assert isinstance(sofa, dict)
        assert isinstance(rack, dict)
        assert legacy.resolve_material(style, "sofa", "base") == sofa


def test_legacy_materials_file_is_facade():
    from pathlib import Path
    src = Path(legacy.__file__).read_text(encoding="utf-8")
    assert "class StyleSpec:" not in src
    assert "_INDUSTRIAL_RGB = {" not in src
    assert "from tools.rooms.shared import materials as _shared" in src
