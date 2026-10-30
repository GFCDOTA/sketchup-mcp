"""R5 (#462): proporcoes dos builders de decor saem do codigo para os Specs com origem declarada; geometria byte a byte identica."""
from __future__ import annotations

import ast
import hashlib
import inspect
import json

import pytest

from tools.rooms.shared import decor_builders as db
from tools.rooms.shared.decor_anatomy_spec import (
    DECOR_MEASURE_ORIGINS,
    PlantSpec,
    ShelfSpec,
    WallArtSpec,
)
from tools.rooms.shared.decor_builders import build_decor

# SHA-256 de (pecas, meta) gerados ANTES da refatoracao (develop@ae1b12c): a aparencia nao pode mudar.
VARIANTS = {
    "rug#0": ({}, "d4b41203a11ecf06c888441aceb0f1aacde6832e7ff3a1f13544df392e5fff73"),
    "rug#1": ({"width": 4.0, "depth": 2.6}, "61c8386b6beb980215fcfd00e436003b80b364c8edfc4c70ec921c2f31ffbd1e"),
    "coffee_table#0": ({}, "c89124f26b58d7d23239f0b38105c28a88a874f15a44d88cf08d0d9025007792"),
    "coffee_table#1": ({"width": 1.4, "depth": 0.8, "height": 0.4}, "b2a8ca011ef75e69b6dda1072beb78fccbe1705d8df6ec82ed3ff34ef1b04d2c"),
    "side_table#0": ({}, "0090c9128b1e5fbfd84cdd098a7ddfc2a91d5958dd5e7491c8a766ea2d909ab2"),
    "side_table#1": ({"diameter": 0.55, "height": 0.6}, "74ec9c593c56a9d8315b5e68ebb19c51c419b925e24aaaa3378190d6664f5c47"),
    "floor_lamp#0": ({}, "8923e3f19e6bb5fd8eaea8f3e0ca3b03d9d0f304a3be4bf920f5c88377d89f13"),
    "floor_lamp#1": ({"height": 1.7}, "6f156ff40d584be335cc7e358ef77d1061d4ceb7d80afb42fba3809538d5d1f9"),
    "wall_art#0": ({}, "2f26f85b893b39f6e3dc84fc345f816f8ed6c7186e92d3b8580e59cf18e4da16"),
    "wall_art#1": ({"width": 1.8, "height": 1.2}, "4153bc947e4a64aa41f74f781243a84cb3792e4b21ac559880f9eb1c6bf19a2c"),
    "wall_art#2": ({"width": 0.8, "height": 0.6}, "7f9b3258aaf97f77ecd1913c1e2f392a93ce742a89bec7f6990282a2e1a514d6"),
    "curtain#0": ({}, "78f5ae8e44ada922d5b77f5e841946f0a1a149b73ff4f700cfcd0c3233e0c037"),
    "curtain#1": ({"panel_split": 2, "width": 3.0}, "f8a0eb7ae6f77b3900eb2468865921fe324ddca6152c4812d8a992488fccf8c6"),
    "curtain#2": ({"width": 2.0}, "8c91ed676241b04b28f0a49eb537aeab97252a82f7f5e4a1694c4ccca1634ef2"),
    "plant_placeholder#0": ({}, "f2e5964ca33ffd4861397373b6fd14e60acf36399ce8756498070107bd3f4458"),
    "plant_placeholder#1": ({"height": 1.6, "foliage_w": 0.7}, "96161e11e425c484a048b516011b2f4a1cf31851515aa6871810e28e3c2e361e"),
    "plant_placeholder#2": ({"height": 1.0}, "c6ce842f041457fb8d1465c80f94160b1eb3b8768ac3990bbc3bdea27a340a85"),
    "accent_seat#0": ({}, "bed4c92b5f263cb50bc546b6ab8a585af92cf7d4357b2afd48fd8bcedeb71a65"),
    "accent_seat#1": ({"width": 0.9, "depth": 0.9}, "34e925dcd03f15ec8be4c005596bee9beeef7546008fb8ee4863bff62e83caf2"),
    "shelf#0": ({}, "d996f719ce315e3eab0a543e93dd35c209fd02226a60bcf6a57806a0909ad3eb"),
    "shelf#1": ({"n_planks": 1}, "b94421092eab0ee76a5bbc27f72b66171a87f7c93aa3ae7007bce9638680a5da"),
    "shelf#2": ({"n_planks": 3, "width": 1.5}, "136c0fdb133ebe74d1a2dae6b6a3f88fb10f055d305b77c7e4705707cf836f78"),
    "track_light#0": ({}, "ef468c2f6eb01145f35656af574d98633411736ef79f25aaf1866df37c5bef57"),
    "track_light#1": ({"n_spots": 4, "length": 2.0}, "220a35907d7f431386a05f6dbebbd38bde1452f1ab95f38b367754790f8ca163"),
}


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_decor_geometry_is_byte_identical_to_the_pre_refactor_output(name):
    overrides, golden = VARIANTS[name]
    parts, meta = build_decor(name.split("#")[0], **overrides)
    assert hashlib.sha256(json.dumps([parts, meta], sort_keys=True, default=str).encode()).hexdigest() == golden


def test_builders_have_no_embedded_geometric_literal_every_measure_comes_from_the_spec():
    tree = ast.parse(inspect.getsource(db))
    bad = [n.value for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) for n in ast.walk(fn)
           if isinstance(n, ast.Constant) and type(n.value) is float and n.value not in (0.0, 0.5, 1.0, 2.0)]
    assert bad == []


def test_every_new_proportion_is_a_declared_spec_field_with_an_origin():
    fields = {*WallArtSpec.__dataclass_fields__, *PlantSpec.__dataclass_fields__, *ShelfSpec.__dataclass_fields__,
              *build_decor.__globals__["AccentSeatSpec"].__dataclass_fields__}
    assert set(DECOR_MEASURE_ORIGINS) <= fields
    assert set(DECOR_MEASURE_ORIGINS.values()) == {"default_declared"}


def test_the_proportions_are_overridable_and_change_the_geometry_they_name():
    base, _ = build_decor("shelf")
    moved, _ = build_decor("shelf", bracket_inset=0.10)
    b1 = next(p for p in base if p["label"] == "bracket_1l")
    b2 = next(p for p in moved if p["label"] == "bracket_1l")
    assert (b1["x0"], b2["x0"]) == (0.06, 0.1)                         # a medida vem do spec, nao do builder
    art, _ = build_decor("wall_art", accent_proud=0.01)
    ref, _ = build_decor("wall_art")
    a = next(p for p in art if p["kind"] == "art_accent")
    r = next(p for p in ref if p["kind"] == "art_accent")
    assert round(r["y0"] - a["y0"], 4) == 0.005
    seat, _ = build_decor("accent_seat", back_shade=0.5)
    ref_seat, _ = build_decor("accent_seat")
    assert next(p for p in seat if p["label"] == "back")["rgb"] != next(p for p in ref_seat if p["label"] == "back")["rgb"]
