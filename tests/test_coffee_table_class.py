"""Testes da CLASSE mesa de centro (cycle 001) — satelite DO SOFA por construcao."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.coffee_table_class import (ARCHETYPES, SOFAS_REF, _apply_sab,  # noqa: E402
                                      _sabotages, build_coffee_table_v2,
                                      coffee_table_class_gate,
                                      derive_coffee_spec, sofa_satellite_gate)

COMBOS = [(a, sw, ssh) for a in ARCHETYPES for _, sw, ssh in SOFAS_REF]


@pytest.mark.parametrize("arch,sw,ssh", COMBOS)
def test_derive_never_fails(arch, sw, ssh):
    spec = derive_coffee_spec(sw, ssh, arch)
    assert coffee_table_class_gate(spec)["result"] != "FAIL"
    assert sofa_satellite_gate(spec, sw, ssh)["result"] == "PASS"


@pytest.mark.parametrize("idx", range(8))
def test_sabotages_fail(idx):
    name, mk = _sabotages()[idx]
    assert _apply_sab(mk), name


def test_satellite_by_construction():
    """a mesa nao tem tamanho proprio: muda o sofa, muda a mesa."""
    small = derive_coffee_spec(1.48, 0.45)
    big = derive_coffee_spec(3.00, 0.40)
    assert small.length < big.length
    assert small.height > big.height          # segue o assento
    # tampo NUNCA acima do assento, em qualquer derivacao
    for _, sw, ssh in SOFAS_REF:
        s = derive_coffee_spec(sw, ssh)
        assert s.height <= ssh


def test_saturation_rule_for_xl_sofas():
    """tensao de teoria resolvida: alcance humano nao escala — frac relaxa em XL."""
    s = derive_coffee_spec(3.00, 0.40)
    assert s.length <= 1.40
    assert sofa_satellite_gate(s, 3.00, 0.40)["result"] == "PASS"
    # mas em sofa normal a regra cheia vale
    s2 = derive_coffee_spec(2.16, 0.43, length=0.90)
    assert sofa_satellite_gate(s2, 2.16, 0.43)["result"] == "FAIL"


def test_archetype_grammar_in_geometry():
    slab, _ = build_coffee_table_v2(derive_coffee_spec(2.16, 0.43, "low_slab"))
    tier, _ = build_coffee_table_v2(derive_coffee_spec(2.16, 0.43, "two_tier"))
    org, _ = build_coffee_table_v2(derive_coffee_spec(2.16, 0.43, "organic"))
    assert any(p["label"] == "base_panel" for p in slab)
    assert any(p["label"] == "shelf" for p in tier)
    assert any(p.get("verts8") for p in org)            # pernas conicas
    # cycle002: alas TRAPEZOIDAIS (octogono real) + reveal no slab
    ala = next(p for p in org if p["label"] == "top_l")
    assert ala.get("verts8"), "ala organica deve ser trapezoidal (verts8)"
    assert any(p["label"] == "base_shadow" for p in slab)


def test_matrix_builds(tmp_path):
    pytest.importorskip("matplotlib")
    from tools.coffee_table_class import build_matrix
    res = build_matrix(tmp_path)
    assert len(res["report"]) == 9
    for r in res["report"]:
        assert r["class_gate"] != "FAIL" and r["satellite"] != "FAIL", r
