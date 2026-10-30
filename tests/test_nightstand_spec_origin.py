"""R5 (#462): medidas do criado-mudo saem do builder para o NightstandSpec com origem declarada; geometria byte a byte identica."""
from __future__ import annotations

import ast
import hashlib
import inspect
import json

from tools.rooms.shared import anatomy, nightstand
from tools.rooms.shared.nightstand import build_nightstand, nightstand_spec

# SHA-256 das pecas+meta geradas ANTES da refatoracao: a aparencia nao pode mudar.
GOLDEN = {
    (0.45, 0.40, 0.55): "8837e5c1538c757339ad450302cd98b9fc4f8fb0153b9528e3915ab3e5175651",
    (0.40, 0.35, 0.50): "70b39295f1a0a94b4ee9595381f70469458f306c002edc22ca13576af44fd4f0",
    (0.55, 0.45, 0.60): "84cc91aa5e2a1abc40c3d76aba0ae656a1a86d2d7bbf556359159586e59411fb",
    (0.35, 0.30, 0.45): "f5e287bd0aa4076ae953cb18bdb6c51bf0d41434c469fa6bc1811a7baec4eadf",
}
FIELDS = ("foot_size", "edge_inset", "drawer_bottom_gap", "drawer_top_gap", "drawer_side_inset", "knob_half_w", "knob_proud",
          "knob_half_h")


def digest(spec) -> str:
    return hashlib.sha256(json.dumps(build_nightstand(spec), sort_keys=True, default=str).encode()).hexdigest()


def test_default_nightstand_geometry_is_byte_identical_to_the_pre_refactor_output():
    assert {k: digest(nightstand_spec(*k)) for k in GOLDEN} == GOLDEN


def test_builder_has_no_embedded_geometric_literal_every_measure_comes_from_the_spec():
    tree = ast.parse(inspect.getsource(nightstand))
    bad = [n.value for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) for n in ast.walk(fn)
           if isinstance(n, ast.Constant) and isinstance(n.value, float) and n.value not in (0.0, 0.5, 1.0, 2.0)]
    assert bad == []


def test_each_proportion_is_a_declared_spec_field_with_an_origin_and_overridable():
    spec = anatomy.NightstandSpec()
    for name in FIELDS:
        assert isinstance(getattr(spec, name), float)
        assert anatomy.NIGHTSTAND_MEASURE_ORIGINS[name] == "default_declared"
    parts, _ = build_nightstand(nightstand_spec(edge_inset=0.03))
    corpo = next(p for p in parts if p["label"] == "corpo")
    assert corpo["x0"] == 0.03                                        # a medida vem do spec, nao do builder
    assert digest(nightstand_spec(0.45, 0.40, 0.55)) == GOLDEN[(0.45, 0.40, 0.55)]
