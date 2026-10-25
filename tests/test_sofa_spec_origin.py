"""R5 (#462): proporcoes do sofa saem do builder para o SofaSpec com origem declarada; geometria byte a byte identica."""
from __future__ import annotations

import ast
import hashlib
import inspect
import itertools
import json

import pytest

from tools.rooms.shared import anatomy, sofa
from tools.rooms.shared.sofa import build_sofa, sofa_spec

# SHA-256 de pecas+meta de 1152 combinacoes (variante x lugares x base x braco x assento/encosto x travessa x terminacao x rake), por variante,
# gerado ANTES da refatoracao: a aparencia nao pode mudar.
GOLDEN = {
    "straight": "33167a6dd68c5ba1107ae53e3e76a840acd920287708bc9de73c5ec8a7825a13",
    "chaise_left": "7a9a56198b1029a1af75be554e8fddd2b224f2671c92020265aadbc515aa7ea7",
    "chaise_right": "a29aed3989cd061dbe56b407c0234630f78f6fd951b0b694939fd3f621fa178b",
}
FIELDS = ("base_shade", "back_shade", "back_pivot_offset", "foot_side", "foot_inset", "arm_cap_t", "arm_cap_over", "shoe_inset",
          "riser_inset_min", "riser_shade", "taper_split", "chaise_seat_overlap")
ARM = [{}, {"arm_relief": 0.05, "arm_cap": True}, {"arm_taper": 0.03},
       {"arm_profile": "rounded", "arm_edge_radius": 0.03, "arm_front_recess": 0.02}]
SURF = [{}, {"seat_style": "single_crowned", "back_style": "single_crowned"},
        {"seat_style": "single_crowned", "seat_overhang": 0.03, "cushion_bevel": 0.0}]


def digest(variant: str) -> str:
    h = hashlib.sha256()
    for seats, base, a, s, rail, term, rake in itertools.product((2, 3), ("feet", "plinth"), range(len(ARM)), range(len(SURF)),
                                                                 ("box", "recessed_rounded"), ("panel", "open"), (10.0, 0.0)):
        spec = sofa_spec(variant, seats, base_style=base, base_rail=rail, chaise_termination=term, backrest_rake=rake, **ARM[a], **SURF[s])
        h.update(json.dumps(build_sofa(spec), sort_keys=True, default=str).encode())
    return h.hexdigest()


@pytest.mark.parametrize("variant", sorted(GOLDEN))
def test_sofa_geometry_is_byte_identical_to_the_pre_refactor_output_for_every_style(variant):
    assert digest(variant) == GOLDEN[variant]


def test_builder_has_no_embedded_geometric_literal_every_class_measure_comes_from_the_spec():
    tree = ast.parse(inspect.getsource(sofa))
    bad = [n.value for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) for n in ast.walk(fn)
           if isinstance(n, ast.Constant) and isinstance(n.value, float) and n.value not in (0.0, 0.5, 1.0, 2.0)]
    assert bad == []


def test_each_proportion_is_a_declared_spec_field_with_an_origin_and_overridable():
    spec = anatomy.SofaSpec()
    for name in FIELDS:
        assert isinstance(getattr(spec, name), float)
        assert anatomy.SOFA_MEASURE_ORIGINS[name] == "default_declared"
    default, _ = build_sofa(sofa_spec("straight", 3))
    moved, _ = build_sofa(sofa_spec("straight", 3, foot_inset=0.07))
    f1 = next(p for p in default if p["label"] == "foot_1")
    f2 = next(p for p in moved if p["label"] == "foot_1")
    assert (f1["x0"], f2["x0"]) == (0.04, 0.07)                       # a medida vem do spec, nao do builder


def test_bbox_contract_follows_the_same_pivot_offset_as_the_builder():
    a, b = sofa_spec("straight", 3), sofa_spec("straight", 3, back_pivot_offset=0.10)
    assert a.bbox_m()[1] != b.bbox_m()[1]
