"""R6 (#463): os provedores de render vivem em tools.rendering.providers; o caminho antigo interior.renderers e fachada de mesma identidade."""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULES = ("render_provider", "sketchup_basic_provider", "enscape_preview_provider", "vray_final_provider")


@pytest.mark.parametrize("name", MODULES)
def test_legacy_module_is_the_very_same_module_as_the_new_owner(name):
    assert importlib.import_module(f"interior.renderers.{name}") is importlib.import_module(f"tools.rendering.providers.{name}")


def test_package_facade_reexports_the_same_symbols():
    old, new = importlib.import_module("interior.renderers"), importlib.import_module("tools.rendering.providers")
    for sym in ("RENDER_TYPES", "RenderProvider", "RenderRequest", "RenderResult", "get_provider", "available_providers"):
        assert getattr(old, sym) is getattr(new, sym)


def test_root_still_points_at_the_repository_after_the_move():
    from tools.rendering.providers.render_provider import ROOT
    assert ROOT == REPO and (ROOT / "tools/sketchup/furnish/place_layout_skp.rb").exists()


def test_provider_lookup_returns_the_owner_class_and_refuses_unknown_names():
    from tools.rendering.providers import get_provider
    from tools.rendering.providers.sketchup_basic_provider import SketchUpBasicProvider
    assert isinstance(get_provider("sketchup_basic"), SketchUpBasicProvider)
    with pytest.raises(ValueError):
        get_provider("inexistente")


def test_facades_hold_no_logic_and_no_consumer_in_production_still_imports_the_old_path():
    for name in MODULES:
        text = (REPO / "interior/renderers" / f"{name}.py").read_text("utf-8")
        assert "importlib.import_module(_TARGET)" in text and len(text.splitlines()) < 30
    for rel in ("tools/rendering/render_scene_views.py", "tools/rendering/render_scene_vray.py",
                "tools/rooms/living/capabilities/sofa_class_matrix.py"):
        assert "interior.renderers" not in (REPO / rel).read_text("utf-8")
