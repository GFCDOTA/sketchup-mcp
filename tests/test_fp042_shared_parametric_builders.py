"""FP-042 P2: parametric primitives used across room domains have one owner."""
import ast
from pathlib import Path

import pytest

from tools import (furniture_anatomy_spec as old_specs,
                   sofa_builder as old_sofa,
                   bed_builder as old_bed,
                   wardrobe_builder as old_wardrobe,
                   nightstand_builder as old_nightstand)
from tools.rooms.shared import anatomy, sofa, bed, wardrobe, nightstand


@pytest.mark.parametrize("legacy,canonical,symbols", [
    (old_specs, anatomy, ("SofaSpec", "BedSpec", "WardrobeSpec", "NightstandSpec",
                          "sofa_spec", "bed_spec", "wardrobe_spec", "nightstand_spec")),
    (old_sofa, sofa, ("build_sofa", "place_sofa_boxes", "parts_to_boxes", "_p", "_darker")),
    (old_bed, bed, ("build_bed", "place_bed_boxes")),
    (old_wardrobe, wardrobe, ("build_wardrobe", "place_wardrobe_boxes")),
    (old_nightstand, nightstand, ("build_nightstand", "place_nightstand_boxes")),
])
def test_public_symbols_are_identity_preserving_reexports(legacy, canonical, symbols):
    for name in symbols:
        assert getattr(legacy, name) is getattr(canonical, name)


@pytest.mark.parametrize("legacy,module", [
    (old_specs, "anatomy"), (old_sofa, "sofa"), (old_bed, "bed"),
    (old_wardrobe, "wardrobe"), (old_nightstand, "nightstand"),
])
def test_legacy_module_has_no_duplicate_builder(legacy, module):
    content = Path(legacy.__file__).read_text(encoding="utf-8")
    assert f"from tools.rooms.shared import {module} as _impl" in content
    tree = ast.parse(content)
    defs = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert defs <= {"__getattr__", "__dir__"}
    assert 'if __name__ == "__main__":' in content


def test_parametric_builders_still_create_distinct_parts():
    spec = anatomy.sofa_spec(variant="straight", seats=2)
    parts, _ = sofa.build_sofa(spec)
    assert parts and len(parts) > 2
    assert any(p["kind"] != parts[0]["kind"] for p in parts)
