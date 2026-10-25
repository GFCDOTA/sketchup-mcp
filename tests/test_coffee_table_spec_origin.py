"""R5 (#462): proporcoes do builder da mesa de centro saem de build_coffee_table_v2 para o CoffeeTableClassSpec com origem declarada; geometria byte a byte identica."""
from __future__ import annotations

import ast
import hashlib
import inspect
import json

import pytest

from tools.rooms.living import coffee_table_class as ct
from tools.rooms.living.coffee_table_class import (
    COFFEE_MEASURE_ORIGINS,
    SOFAS_REF,
    CoffeeTableClassSpec,
    build_coffee_table_v2,
    derive_coffee_spec,
)

# SHA-256 de (pecas, meta) gerados ANTES da refatoracao (develop@14f94eb): a aparencia nao pode mudar.
GOLDEN = {
    "low_slab@sofa-formal-2l": "03dde8c856c3f28fca9149515de0762c627f4d6f47adc2669e740d56741201aa",
    "low_slab@sofa-std-3l": "1fa65cd5d9e65fab9990bca453a631ecf21cb8d3ec1ed6c9a404051dcde530bb",
    "low_slab@sofa-lounge-4l": "2492097f8de15be3ed97dfcf8def1d8265b7820e6177afc57d290043e9e0ac63",
    "two_tier@sofa-formal-2l": "df1e5632630f96b9518ae903efa7ff713989e1a0c22322fd42e608dd71967882",
    "two_tier@sofa-std-3l": "f80bbdf559a9ec2e64647467bfb22a8d4dda3664032f984382c42a0864a6835a",
    "two_tier@sofa-lounge-4l": "89690a8b2641966033baf47cef7aff7260cf44fc7f641b05b846b07e9a922510",
    "organic@sofa-formal-2l": "3a77cd255eba83c7a7279418595c16360d42e0f4cdf6cda1a7f8ff68e6a228a0",
    "organic@sofa-std-3l": "273d4a826c0bcb29f20ed293ffae690f81425f941d8e2a1ae8b1acceaedeb0af",
    "organic@sofa-lounge-4l": "be4f1f19c4be6bd4b750dacd896203f408e306db9474b7d054a2576416242b59",
    "slab_reveal": "15490cbe90cc0bc7c1ce1ec0a45eb1296db6fd84585831ff66ed277f126477d5",
    "slab_default": "1c72a42818ac5058099b02de74d5f098d227674b4e65e1612418049f7de77852",
    "tier_shelf_gap": "1a329059567c7753e24da727ed57478156c56bf4234e20e35de48df3351a3611",
    "tier_noshelf": "5138e02f2b3422ca6b789b40498b5ba57cc614c0044b01d91d23dedfa17d6668",
    "tier_taper": "0f814df33188c892960982ec69a2844e3972342ebd39dee1c41dc5bf4be9218e",
    "organic_round": "94fee09ae068f67b850c20cb143a3c5a66bde0d7cb66748b96b6442c6d20c6b3",
    "organic_flat": "080f72ba508d10c1bcba1cb328628ada6dc1357d6fc7465b69277f1e677b650d",
}
EXTRA = {
    "slab_reveal": dict(style="low_slab", top_t=0.08, slab_reveal=0.09, leg_inset=0.15, length=1.5, width=0.8),
    "slab_default": dict(style="low_slab", top_t=0.08),
    "tier_shelf_gap": dict(style="two_tier", shelf=True, shelf_gap_floor=0.10, height=0.45),
    "tier_noshelf": dict(style="two_tier", shelf=False),
    "tier_taper": dict(style="two_tier", shelf=True, leg_taper=0.5, leg_t=0.06),
    "organic_round": dict(style="organic", round_corners=True, corner_ear_frac=0.2, corner_soft_frac=0.3, leg_taper=0.55),
    "organic_flat": dict(style="organic", round_corners=False),
}


def _hash(spec):
    parts, meta = build_coffee_table_v2(spec)
    return hashlib.sha256(json.dumps([parts, meta], sort_keys=True, default=str).encode()).hexdigest()


@pytest.mark.parametrize("name", sorted(k for k in GOLDEN if "@" in k))
def test_derived_archetypes_are_byte_identical_to_the_pre_refactor_output(name):
    arch, sofa = name.split("@")
    sw, ssh = next((w, h) for n, w, h in SOFAS_REF if n == sofa)
    assert _hash(derive_coffee_spec(sw, ssh, arch)) == GOLDEN[name]


@pytest.mark.parametrize("name", sorted(EXTRA))
def test_style_variants_are_byte_identical_to_the_pre_refactor_output(name):
    assert _hash(CoffeeTableClassSpec(**EXTRA[name])) == GOLDEN[name]


def test_builder_has_no_embedded_geometric_literal():
    tree = ast.parse(inspect.getsource(ct.build_coffee_table_v2))
    bad = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and type(n.value) is float and n.value not in (0.0, 0.5, 1.0, 2.0)]
    assert bad == []


def test_every_class_proportion_is_a_declared_field_with_an_origin():
    assert set(COFFEE_MEASURE_ORIGINS) <= set(CoffeeTableClassSpec.__dataclass_fields__)
    assert set(COFFEE_MEASURE_ORIGINS.values()) == {"default_declared"}


def test_the_proportions_are_overridable_and_change_the_geometry_they_name():
    base, _ = build_coffee_table_v2(CoffeeTableClassSpec(style="two_tier", shelf=True))
    thick, _ = build_coffee_table_v2(CoffeeTableClassSpec(style="two_tier", shelf=True, shelf_t=0.05))
    a = next(p for p in base if p["label"] == "shelf")
    b = next(p for p in thick if p["label"] == "shelf")
    assert round(a["z1"] - a["z0"], 4) == 0.03 and round(b["z1"] - b["z0"], 4) == 0.05      # a medida vem do spec
    slab, _ = build_coffee_table_v2(CoffeeTableClassSpec(style="low_slab", top_t=0.08, slab_inset_y=0.5))
    ref, _ = build_coffee_table_v2(CoffeeTableClassSpec(style="low_slab", top_t=0.08))
    assert next(p for p in slab if p["label"] == "base_panel")["y0"] != next(p for p in ref if p["label"] == "base_panel")["y0"]


def test_validate_uses_the_declared_shelf_thickness():
    with pytest.raises(AssertionError):
        CoffeeTableClassSpec(style="two_tier", shelf=True, height=0.40, shelf_gap_floor=0.12, shelf_t=0.20).validate()
