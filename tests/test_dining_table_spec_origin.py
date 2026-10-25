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

# SHA-256 de (pecas, meta, cadeiras proxy, ancoras) gerados ANTES da refatoracao (develop@9bf62e9): a aparencia nao pode mudar.
GOLDEN = {
    "rect_family@4p": "67008493105fd71fc1bc55d55eb14ad5c11616d6eaf9af8efe8800c4e7a3091d",
    "rect_family@6p": "26ac4d6430784d5b4c456064da5dcfc619cd6f2f6d771a98ff6c3bf55584f7ea",
    "rect_family@8p": "f980cfee5e1ebd261696caf10019df714eb8c2bcdc47306f16dd434106ee66ed",
    "round_compact@2p": "b3b86360cbb7f2ed8cd909a8310f561e055d547bc9c4c27b4889283c7d17ad04",
    "round_compact@4p": "4598523d2c87d3a9c4a63e89ad78524f2a28c9e4ad0bc3910af608082e100dc9",
    "round_compact@6p": "9e4d5f8d55e33fea1c59604bbdbf6c9f498ce44e053888e5f40f2cf22f712157",
    "oval_soft@4p": "532e28452009be79e64e9ea79e8f3ed878025170e0b77027b3c8e0d7530b375d",
    "oval_soft@6p": "6a6345ae336da0f5ce14daabdce04950289cef941dd4f150d9bdd4e60bd318cf",
    "oval_soft@8p": "634bf45251a1bfa0ec18f09bb14da1f612794b3643b361e2e9c77e5fa7a84962",
    "rect_noheads": "78cfc77cb83f1d3c60a8d82b4a250029eadb701bd66468f5471fc3468b2e94aa",
    "rect_wide": "4cd853f365b1950f42022e37adcc0b444b1c9f107580df8adef32a0e5906cf14",
    "oval_clearance": "52d4df1799840d5d5eb679dfe06d201cb948dbbede9d7793a7d3d69419b46784",
    "round_plate": "1783a231f3a91432d6a71f263035069a4c727c078be97a4efeab5044bdfd0eba",
    "oval_8": "c5a4a950201a9fb3c2f54efff09e049fcb984fb325c2619686d4de4523ef0c6f",
}
EXTRA = {
    "rect_noheads": ("rect_family", 6, dict(heads=False)),
    "rect_wide": ("rect_family", 8, dict(width=1.1, apron_inset=0.1, leg_inset=0.07)),
    "oval_clearance": ("oval_soft", 6, dict(clearance_use=1.0, place_w=0.55)),
    "round_plate": ("round_compact", 4, dict(plate_h=0.08, col_r=0.06)),
    "oval_8": ("oval_soft", 8, dict(oval_facets=10)),
}


def _hash(spec):
    parts, meta = dt.build_dining_table(spec)
    return hashlib.sha256(json.dumps([parts, meta, dt._chair_proxy_parts(spec), dt._seat_anchors(spec)], sort_keys=True,
                                     default=str).encode()).hexdigest()


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
