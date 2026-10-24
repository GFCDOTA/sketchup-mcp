"""R5 (#462): proporcoes da cama saem do builder para o BedSpec com origem declarada; geometria byte a byte identica."""
from __future__ import annotations

import ast
import hashlib
import inspect
import itertools
import json

import pytest

from tools.rooms.shared import anatomy, bed
from tools.rooms.shared.bed import bed_spec, build_bed

# SHA-256 de pecas+meta de TODA a matriz estilo de base x estilo de cabeceira x saia x travesseiros x overhang, por tamanho,
# gerado ANTES da refatoracao: a aparencia nao pode mudar.
GOLDEN = {
    "king": "56d856f36b2d732adb7524f966207b8f710db994a709a1d0bc9c4e7b41d55ccc",
    "queen": "4e2f58abb17544abf37a580a095c521021d13437565de559ef8cca620724fd66",
    "casal": "e0647b8a61fc20423a8e04aabcb968d4ebade763ac512a4b50387ab29bea7150",
    "solteiro": "c675351881486af85d95b027fc0e8ea60d63f0a58daaebd030338e7829103597",
}
FIELDS = ["plinth_shade",
          "rail_shade",
          "leg_inset",
          "leg_rail_max",
          "leg_rail_frac",
          "box_shadow_h",
          "box_shadow_inset",
          "box_shadow_shade",
          "skirt_shade",
          "skirt_overhang",
          "skirt_t",
          "skirt_back_cut",
          "plinth_rail_max",
          "plinth_rail_frac",
          "ledge_over",
          "ledge_depth",
          "ledge_h",
          "ledge_shade",
          "bolster_inset",
          "bolster_proud",
          "bolster_above_mattress",
          "bolster_tint",
          "mattress_edge",
          "pillow_gap",
          "pillow_back_gap",
          "blanket_side_inset",
          "blanket_foot_offset"]


def matrix_digest(size: str) -> str:
    h = hashlib.sha256()
    for bs, hs, sk, npil, ov in itertools.product(("plinth", "legs", "box"), ("plain", "panel", "upholstered", "contained"),
                                                  (False, True), (1, 2, 3), (0.0, 0.1)):
        spec = bed_spec(size, base_style=bs, headboard_style=hs, skirt=sk, n_pillows=npil, headboard_overhang=ov)
        h.update(json.dumps(build_bed(spec), sort_keys=True, default=str).encode())
    return h.hexdigest()


@pytest.mark.parametrize("size", sorted(GOLDEN))
def test_bed_geometry_is_byte_identical_to_the_pre_refactor_output_for_every_style(size):
    assert matrix_digest(size) == GOLDEN[size]


def test_builder_has_no_embedded_geometric_literal_every_measure_comes_from_the_spec():
    tree = ast.parse(inspect.getsource(bed))
    bad = [n.value for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) for n in ast.walk(fn)
           if isinstance(n, ast.Constant) and isinstance(n.value, float) and n.value not in (0.0, 0.5, 1.0, 2.0)]
    assert bad == []


def test_each_proportion_is_a_declared_spec_field_with_an_origin_and_overridable():
    spec = anatomy.BedSpec()
    for name in FIELDS:
        assert isinstance(getattr(spec, name), float)
        assert anatomy.BED_MEASURE_ORIGINS[name] == "default_declared"
    default, _ = build_bed(bed_spec("queen", base_style="legs"))
    moved, _ = build_bed(bed_spec("queen", base_style="legs", leg_inset=0.09))
    f1 = next(p for p in default if p["label"] == "pe_1")
    f2 = next(p for p in moved if p["label"] == "pe_1")
    assert (f1["x0"], f2["x0"]) == (0.05, 0.09)                         # a medida vem do spec, nao do builder
