"""R5 (#462): medidas do guarda-roupa saem do builder para o WardrobeSpec com origem declarada; geometria byte a byte identica."""
from __future__ import annotations

import hashlib
import inspect
import json

from tools.rooms.shared import anatomy, wardrobe
from tools.rooms.shared.wardrobe import build_wardrobe, wardrobe_spec

# SHA-256 das pecas+meta geradas ANTES da refatoracao (develop@a9f0e5c6): a aparencia nao pode mudar.
GOLDEN = {
    "0.6": "cb55d948bfb1d0eb7f8070734330fc802d0f0a660a782166cc96a28b06ec5bcc",
    "0.9": "a9ed28c80232abcd4711bc733d53c0945b83c780698206eb4000f19daf1898ad",
    "1.2": "32a95b7dbc370a4571fb29080444248d65086ed68a6565df47fbb41ee959d280",
    "1.8": "b7db812c285cb09132e58062182f3b6964464fb82c82804069a796d874cfa2e3",
    "2.4": "88ecc8c2322b9d16f658a2423e708b09890401a1570dc83206c5f0c1834abc46",
}


def digest(width: float) -> str:
    parts, meta = build_wardrobe(wardrobe_spec(width=width))
    return hashlib.sha256(json.dumps([parts, meta], sort_keys=True, default=str).encode()).hexdigest()


def test_default_wardrobe_geometry_is_byte_identical_to_the_pre_refactor_output():
    assert {str(w): digest(w) for w in (0.6, 0.9, 1.2, 1.8, 2.4)} == GOLDEN


def test_builder_has_no_embedded_geometric_literal_every_measure_comes_from_the_spec():
    import ast
    tree = ast.parse(inspect.getsource(wardrobe))
    bad = [n.value for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) for n in ast.walk(fn)
           if isinstance(n, ast.Constant) and isinstance(n.value, float) and n.value not in (0.0, 0.5, 1.0, 2.0)]
    assert bad == [] and not hasattr(wardrobe, "MARGIN")


def test_each_proportion_is_a_declared_spec_field_with_an_origin_and_overridable():
    spec = anatomy.WardrobeSpec()
    for name in ("plinth_setback", "door_margin", "door_bottom_offset", "door_top_offset", "handle_w", "handle_proud",
                 "handle_inset_far", "handle_inset_near"):
        assert isinstance(getattr(spec, name), float)
        assert anatomy.WARDROBE_MEASURE_ORIGINS[name] == "default_declared"
    parts, _ = build_wardrobe(wardrobe_spec(width=1.8, door_margin=0.05))
    first_door = next(p for p in parts if p["label"] == "porta_1")
    assert first_door["x0"] == 0.05                                   # a medida vem do spec, nao do builder
    assert digest(1.8) == GOLDEN["1.8"]                                # default continua o mesmo
