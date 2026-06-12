"""Testes da CLASSE cama (cycle 001) + constraint satelite do criado-mudo."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.bed_builder import build_bed                                # noqa: E402
from tools.bed_class import (ARCHETYPES, BED_SKUS, _sabotages,         # noqa: E402
                             bed_class_gate, derive_bed_spec,
                             nightstand_satellite_gate)

COMBOS = [(s, a) for s in BED_SKUS for a in ARCHETYPES]


@pytest.mark.parametrize("size,arch", COMBOS)
def test_derive_never_fails_class(size, arch):
    r = bed_class_gate(derive_bed_spec(size, arch))
    assert r["result"] != "FAIL", (size, arch, r["errors"])


@pytest.mark.parametrize("idx", range(6))
def test_class_gate_rejects_sabotages(idx):
    name, mk = _sabotages()[idx]
    r = bed_class_gate(mk())
    assert r["result"] == "FAIL", f"{name}: veio {r['result']}"


def test_skus_are_discrete():
    """colchao nao se interpola: width fora dos SKUs BR = FAIL."""
    s = derive_bed_spec("queen", "upholstered")
    s.width = 1.20
    assert bed_class_gate(s)["result"] == "FAIL"


def test_headboard_respects_width():
    """derivacao anti-trono: solteiro clampa a cabeceira a 0.52*W."""
    s = derive_bed_spec("solteiro", "upholstered", headboard="high")
    above = s.headboard_h - s.mattress_top
    assert above / s.width <= 0.55
    assert bed_class_gate(s)["result"] != "FAIL"


def test_base_styles_build_anatomy():
    for base in ("plinth", "legs", "box"):
        spec = derive_bed_spec("queen", "box" if base == "box" else "upholstered",
                               base_style=base)
        parts, meta = build_bed(spec)
        kinds = {p["kind"] for p in parts}
        assert {"estrado", "colchao", "cabeceira", "travesseiro", "manta"} <= kinds
        if base == "legs":
            assert any(p["label"].startswith("pe_") for p in parts)
        if base == "box" and spec.skirt:
            assert any(p["label"].startswith("saia") for p in parts)
        assert bed_class_gate(spec, parts)["result"] != "FAIL"


def test_archetype_axis_platform_to_box():
    p, u, b = (derive_bed_spec("queen", a) for a in ("platform", "upholstered", "box"))
    assert p.mattress_top < u.mattress_top < b.mattress_top   # sobe no eixo
    assert p.headboard_t < u.headboard_t                      # madeira fina vs estofada
    assert u.headboard_overhang > 0                           # wings so estofada


def test_nightstand_satellite_relation():
    """1a constraint ENTRE classes: o alvo do criado e' DERIVADO da cama."""
    plat = derive_bed_spec("queen", "platform")
    uphol = derive_bed_spec("queen", "upholstered")
    # criado padrao 0.55: serve a estofada, FALHA na platform baixa
    assert nightstand_satellite_gate(uphol, ns_height=0.55)["result"] == "PASS"
    assert nightstand_satellite_gate(plat, ns_height=0.55)["result"] == "FAIL"
    # criado derivado do alvo serve sempre
    for bed in (plat, uphol):
        target = nightstand_satellite_gate(bed)["metrics"]["ns_target_h_m"]
        assert nightstand_satellite_gate(bed, ns_height=target)["result"] == "PASS"
    # profundidade que invade circulacao
    assert nightstand_satellite_gate(uphol, ns_height=0.57, ns_depth=0.55)["result"] == "FAIL"


def test_matrix_builds_and_gates(tmp_path):
    pytest.importorskip("matplotlib")
    from tools.bed_class import build_matrix
    res = build_matrix(tmp_path)
    assert len(res["report"]) == 9
    for r in res["report"]:
        assert r["class_gate"] != "FAIL", r
