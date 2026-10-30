"""R5 (#462): proporcoes da poltrona saem do builder para o ArmchairSpec com origem declarada; geometria byte a byte identica."""
from __future__ import annotations

import ast
import hashlib
import inspect
import json

import pytest

from tools.rooms.shared import armchair_builder as ab
from tools.rooms.shared.armchair_builder import ArmchairSpec, build_armchair

# SHA-256 de pecas+meta geradas ANTES da refatoracao: a aparencia nao pode mudar.
VARIANTS = {
    "default": ({}, "ecf6bf499a5fa01b65af3eab6b827f13f21cf26498f0643084863483b8c2daca"),
    "wide": ({"width": 1.1, "depth": 0.95}, "876c158e926e667c2b6b0f48f5730f1e7f22322a730417d8b351c45d02a5ce9f"),
    "cap": ({"arm_cap": True, "backrest_rake": 0.0}, "1fb46678b02584edab3145feef28ce933e7acbc1f9dbc32dacf406f0434cc33c"),
    "club": ({"wrap_frac": 0.8, "shell_back_h": 1.05, "height": 1.1}, "6460a52ad22fba07e5d2016cfaa091a3d9c8d7a0605f425c400d5fe352cf69ab"),
    "low": ({"seat_height": 0.38, "height": 0.8, "foot_height": 0.1}, "a17053e1c30af52d1cf04da7293062c2ae6b80ad8bef8f89597bca77e1c1da8b"),
}
FIELDS = ("cushion_tint", "base_shade", "pivot_offset", "foot_side", "foot_inset", "arm_cap_t", "arm_cap_over", "shoulder_min_rise",
          "back_cushion_inset", "min_cavity_width")


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_armchair_geometry_is_byte_identical_to_the_pre_refactor_output(name):
    kwargs, golden = VARIANTS[name]
    assert hashlib.sha256(json.dumps(build_armchair(ArmchairSpec(**kwargs)), sort_keys=True, default=str).encode()).hexdigest() == golden


def test_builder_has_no_embedded_geometric_literal_every_measure_comes_from_the_spec():
    tree = ast.parse(inspect.getsource(ab))
    bad = [n.value for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) for n in ast.walk(fn)
           if isinstance(n, ast.Constant) and isinstance(n.value, float) and n.value not in (0.0, 0.5, 1.0, 2.0)]
    assert bad == []


def test_each_proportion_is_a_declared_spec_field_with_an_origin_and_overridable():
    spec = ArmchairSpec()
    for name in FIELDS:
        assert isinstance(getattr(spec, name), float)
        assert ab.ARMCHAIR_MEASURE_ORIGINS[name] == "default_declared"
    default, _ = build_armchair(ArmchairSpec())
    moved, _ = build_armchair(ArmchairSpec(foot_inset=0.06))
    f1 = next(p for p in default if p["label"] == "foot_1")
    f2 = next(p for p in moved if p["label"] == "foot_1")
    assert (f1["x0"], f2["x0"]) == (0.04, 0.06)                         # a medida vem do spec, nao do builder
