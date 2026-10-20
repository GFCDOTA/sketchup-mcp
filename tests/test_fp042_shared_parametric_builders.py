"""FP-042 P2: parametric primitives used across room domains have one owner."""
import ast
from pathlib import Path

import pytest

from tools.rooms.shared import anatomy, sofa, bed, wardrobe, nightstand

# as fachadas sofa_builder/bed_builder/wardrobe_builder/nightstand_builder/furniture_anatomy_spec sairam na FP-044/F6;
# o contrato que sobra e o do dono unico em tools/rooms/shared/.
OWNERS = [
    (anatomy, ("SofaSpec", "BedSpec", "WardrobeSpec", "NightstandSpec",
               "sofa_spec", "bed_spec", "wardrobe_spec", "nightstand_spec")),
    (sofa, ("build_sofa", "place_sofa_boxes", "parts_to_boxes", "_p", "_darker")),
    (bed, ("build_bed", "place_bed_boxes")),
    (wardrobe, ("build_wardrobe", "place_wardrobe_boxes")),
    (nightstand, ("build_nightstand", "place_nightstand_boxes")),
]


@pytest.mark.parametrize("canonical,symbols", OWNERS)
def test_public_symbols_are_defined_in_the_single_owner(canonical, symbols):
    tree = ast.parse(Path(canonical.__file__).read_text(encoding="utf-8"))
    defined = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    for name in symbols:
        assert name in defined or getattr(canonical, name).__module__.startswith("tools.rooms.shared"), name


@pytest.mark.parametrize("canonical,symbols", OWNERS)
def test_owner_keeps_the_cli(canonical, symbols):
    assert 'if __name__ == "__main__":' in Path(canonical.__file__).read_text(encoding="utf-8")


def test_parametric_builders_still_create_distinct_parts():
    spec = anatomy.sofa_spec(variant="straight", seats=2)
    parts, _ = sofa.build_sofa(spec)
    assert parts and len(parts) > 2
    assert any(p["kind"] != parts[0]["kind"] for p in parts)
