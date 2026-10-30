"""R5 (#462): proporcoes do builder e dos satelites da mesa de jantar saem do codigo para o DiningTableSpec com origem declarada; geometria byte a byte identica."""
from __future__ import annotations

import ast
import hashlib
import inspect
import json

import pytest

from tools.rooms.living import dining_table_class as dt
from tools.rooms.living.dining_table_class import (
    DINING_MEASURE_ORIGINS,
    MATRIX,
    DiningTableSpec,
    derive_dining_spec,
)

# SHA-256 de (pecas, meta, cadeiras proxy, ancoras) (floats a 9 casas) gerados ANTES da refatoracao (develop@9bf62e9): a aparencia nao pode mudar.
GOLDEN = {
    "rect_family@4p": "f049e7c411104316ce6b32bbb049d435e1fc31b8c64e554af0a6c219e1e453ad",
    "rect_family@6p": "fad250b2106a6f28c81f1e684baf3847e0ed61024124eab69644623d894353a1",
    "rect_family@8p": "818411afa6403891c38b8cef17517c91b1e120d313a58dc8b6b8ff2fca39cda1",
    "round_compact@2p": "1b60e9f64e25da6055a902a92e44b609907eef4d47f1853b2e1b0977380df6b5",
    "round_compact@4p": "9532f2cddc40f9eeda010ed5fc9d1c57aa8095f9aa3f0a1ed71713dc5c7bc6b3",
    "round_compact@6p": "eb8638943d72cc5ada3e0c942f7514ff7017b9c9d391060fa12f326de109c888",
    "oval_soft@4p": "79191f175561f722d44ebe65507418b8274ef2ca0c25129cb5c5c1fa539f3ea2",
    "oval_soft@6p": "6eab152514e9c296559782bd4a5279e343de1654460377c4f5e5d4bd7ee7ac93",
    "oval_soft@8p": "dccbb745e3ab257d110bdeac4fb56d19718528dbbf421467cc8b3abfde2c1f79",
    "rect_noheads": "9bead4b462c692af112c444e93ce41745df6fee063743589e2b05a1ec5da562b",
    "rect_wide": "d3ce96fdc9d43097818e73b4fd56f2776374f84edf4b46aca6ff6522745295cd",
    "oval_clearance": "36f41f8bb935613fad8acb7f17d7ac133ba71358214925e33a6c5b23057a2341",
    "round_plate": "a4d4078785ef96627ef6e27616dc9482f433300c4bd3931190635723c04274c8",
    "oval_8": "77f60b44894146841f3f216f407d9794fc40de45453061012c7bff973696a952",
}
EXTRA = {
    "rect_noheads": ("rect_family", 6, dict(heads=False)),
    "rect_wide": ("rect_family", 8, dict(width=1.1, apron_inset=0.1, leg_inset=0.07)),
    "oval_clearance": ("oval_soft", 6, dict(clearance_use=1.0, place_w=0.55)),
    "round_plate": ("round_compact", 4, dict(plate_h=0.08, col_r=0.06)),
    "oval_8": ("oval_soft", 8, dict(oval_facets=10)),
}


def _norm(o):
    """Floats a 9 casas: a mesa redonda usa sin/cos e o ultimo bit de libm difere entre Windows e Linux (CI); 1e-9 m e muito abaixo de qualquer medida."""
    if isinstance(o, float):
        return round(o, 9)
    if isinstance(o, (list, tuple)):
        return [_norm(x) for x in o]
    if isinstance(o, dict):
        return {k: _norm(v) for k, v in o.items()}
    return o


def _hash(spec):
    parts, meta = dt.build_dining_table(spec)
    payload = _norm([parts, meta, dt._chair_proxy_parts(spec), dt._seat_anchors(spec)])
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


@pytest.mark.parametrize("name,arch,seats", MATRIX)
def test_matrix_is_byte_identical_to_the_pre_refactor_output(name, arch, seats):
    assert _hash(derive_dining_spec(seats, arch)) == GOLDEN[name]


@pytest.mark.parametrize("name", sorted(EXTRA))
def test_variants_are_byte_identical_to_the_pre_refactor_output(name):
    arch, seats, kw = EXTRA[name]
    assert _hash(derive_dining_spec(seats, arch, **kw)) == GOLDEN[name]


@pytest.mark.parametrize("fn", [dt.build_dining_table, dt._seat_anchors, dt._chair_proxy_parts])
def test_geometry_functions_have_no_embedded_geometric_literal(fn):
    tree = ast.parse(inspect.getsource(fn))
    bad = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and type(n.value) is float and n.value not in (0.0, 0.5, 1.0, 2.0)]
    assert bad == []


def test_every_class_proportion_is_a_declared_field_with_an_origin():
    assert set(DINING_MEASURE_ORIGINS) <= set(DiningTableSpec.__dataclass_fields__)
    assert set(DINING_MEASURE_ORIGINS.values()) == {"default_declared"}


def test_the_proportions_are_overridable_and_change_the_geometry_they_name():
    base, _ = dt.build_dining_table(derive_dining_spec(6, "rect_family"))
    thick, _ = dt.build_dining_table(derive_dining_spec(6, "rect_family", apron_t=0.05))
    a, b = (next(p for p in ps if p["label"] == "apron_f") for ps in (base, thick))
    assert round(a["y1"] - a["y0"], 4) == 0.03 and round(b["y1"] - b["y0"], 4) == 0.05     # a medida vem do spec
    spec = derive_dining_spec(4, "rect_family", ring_t=0.06)
    ring = next(p for p in dt._chair_proxy_parts(spec) if p["label"] == "use_ring_s")
    assert round(ring["y1"] - ring["y0"], 4) == 0.06
