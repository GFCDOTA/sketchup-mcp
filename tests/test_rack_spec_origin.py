"""R5 (#462): proporcoes do rack saem de build_rack/_tv_proxy_parts para o RackSpec com origem declarada; geometria byte a byte identica."""
from __future__ import annotations

import ast
import hashlib
import inspect
import json

import pytest

from tools.rooms.living import rack_class as rc
from tools.rooms.living.rack_class import (
    RACK_MEASURE_ORIGINS,
    RackSpec,
    build_rack,
    derive_rack_spec,
)

# SHA-256 de (pecas, meta, proxy da TV) gerados ANTES da refatoracao (develop@ed26558): a aparencia nao pode mudar.
GOLDEN = {
    "floating_minimal@55": "830863a50a0f8101eea0370123cee53c55a61ae800ebefe81cdad9f8889c5d87",
    "floating_minimal@65": "f60da060f5101e21ea69822b6614364d6ba3280ce6aa02a42a78c15e3106844d",
    "floating_minimal@75": "a4865f0fd2d79aa056b28fbb2649a25fd13ac77267b165ea7f2b0ebf865913fd",
    "low_credenza@55": "0b7ac7a3e0ce1c1da634a86b36ff4605746f959a5edaff783bab24a3ac4a54f5",
    "low_credenza@65": "8a8453bfbce1bfbff21e16d583fe13a7ba9ebf725667851debc0103da305394a",
    "low_credenza@75": "8c5ea3be86772f1c71effe5c7262a1ba9b8de537e169d442ea68b4da1a07018c",
    "storage_media@55": "5f11dce7020cc2dfa61acf23a3b2fd33a79121e77b3ee99c67a224dd331f4126",
    "storage_media@65": "bbca1b5de0058dea2b702fab99b6651a470cbdf5d304c8e86e8f6cd1ad968700",
    "storage_media@75": "35b4e82ee115fdd1e170e513c1208f5cfd5668ace0c10bea1e616b2c8049c8eb",
    "legs_noFacade": "cb49369b3d619758f336728f08165f608c1f9cac0544fb2870c1b40047ac7cde",
    "legs_longer": "2237c4518f64ad3874a81af59008f1f3a281581affeaf59dd7ab9823c1607f98",
    "floating_wall": "7cf29f14dcc3180842bb7987688418680b65c063cae0caf2a8e951af038f5956",
    "floating_nowall": "a71ad301a47994773802a6bc58c71b55cefccb0b22cb8ec23ebda0e33363f870",
    "base_wide": "b95c629cb58f67129599cdbcbbc02cb2c04bd003dfbdbb6d21a965546be43703",
    "top_proud": "53e1a6aac34eee79d15973de16c19617d3592054bea1511c739eb88303c6591a",
    "one_module": "8f9c5f531824e0b843aee877a37da01ab01ed19895853fc4099652766dce515f",
}
EXTRA = {
    "legs_noFacade": dict(support="legs", n_niches=2, n_drawers=3, facade_pattern=()),
    "legs_longer": dict(support="legs", length=2.4, depth=0.45, leg_height=0.2, leg_section=0.06),
    "floating_wall": dict(support="floating", wall_back=True, gap_floor=0.4),
    "floating_nowall": dict(support="floating", wall_back=False),
    "base_wide": dict(support="base", toe_recess=0.08, length=2.6, body_h=0.5),
    "top_proud": dict(support="legs", top_proud=0.05),
    "one_module": dict(support="base", n_niches=1, n_drawers=0, facade_pattern=()),
}


def _hash(spec, tv):
    parts, meta = build_rack(spec)
    return hashlib.sha256(json.dumps([parts, meta, rc._tv_proxy_parts(spec, tv)], sort_keys=True, default=str).encode()).hexdigest()


@pytest.mark.parametrize("name", sorted(k for k in GOLDEN if "@" in k))
def test_derived_archetypes_are_byte_identical_to_the_pre_refactor_output(name):
    arch, tv = name.split("@")
    assert _hash(derive_rack_spec(tv, arch), tv) == GOLDEN[name]


@pytest.mark.parametrize("name", sorted(EXTRA))
def test_support_and_facade_variants_are_byte_identical_to_the_pre_refactor_output(name):
    assert _hash(RackSpec(**EXTRA[name]), "65") == GOLDEN[name]


@pytest.mark.parametrize("fn", [rc.build_rack, rc._tv_proxy_parts])
def test_geometry_builders_have_no_embedded_geometric_literal(fn):
    tree = ast.parse(inspect.getsource(fn).lstrip())
    bad = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and type(n.value) is float and n.value not in (0.0, 0.5, 1.0, 2.0)]
    assert bad == []


def test_every_class_proportion_is_a_declared_field_with_an_origin():
    assert set(RACK_MEASURE_ORIGINS) <= set(RackSpec.__dataclass_fields__)
    assert set(RACK_MEASURE_ORIGINS.values()) == {"default_declared"}


def test_the_proportions_are_overridable_and_change_the_geometry_they_name():
    base, _ = build_rack(RackSpec(support="legs"))
    moved, _ = build_rack(RackSpec(support="legs", leg_inset_x=0.10))
    assert next(p for p in base if p["label"] == "leg_fl")["x0"] == 0.06
    assert next(p for p in moved if p["label"] == "leg_fl")["x0"] == 0.1                  # a medida vem do spec, nao do builder
    toe, _ = build_rack(RackSpec(support="base", toe_h=0.09))
    assert next(p for p in toe if p["label"] == "toe_base")["z1"] == 0.09
    eye = [p for p in rc._tv_proxy_parts(RackSpec(eye_z0=1.0, eye_z1=1.02), "65") if p["label"] == "eye_line"][0]
    assert (eye["z0"], eye["z1"]) == (1.0, 1.02)
