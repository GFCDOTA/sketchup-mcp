"""Trava regressiva do core de construcao: medida embutida em builder so pode DIMINUIR (mapa de microfases, T1/T2)."""
from __future__ import annotations

import json
from pathlib import Path

from tools.navigation import builder_detail_audit as audit

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/reports/construction_core/builder_detail_baseline.v1.json"


def test_request_driven_builders_have_no_embedded_geometry():
    rows = audit.audit()["builders"]
    gen2 = {k: v for k, v in rows.items() if v["generation"] == "gen2_request_driven"}
    assert gen2 and all(v["embedded_float_literals"] == 0 for v in gen2.values()), gen2


def test_embedded_geometry_never_grows_against_the_versioned_baseline():
    base = json.loads(BASELINE.read_text(encoding="utf-8"))["builders"]
    now = audit.audit()["builders"]
    assert set(now) == set(base), "builder novo/removido: atualizar GEN1/GEN2 e o baseline no mesmo PR"
    grew = {k: (base[k], now[k]) for k in now
            if now[k]["embedded_float_literals"] > base[k]["embedded_float_literals"]
            or now[k]["module_float_constants"] > base[k]["module_float_constants"]}
    assert not grew, f"medida embutida cresceu (migrar para pedido {{value,unit,origin}} em vez disso): {grew}"


def test_counter_ignores_arithmetic_and_counts_nested_functions_once():
    src = "X = 0.03\ndef f(a):\n    def g():\n        return a * 0.5 + 0.12\n    return g() + 2.0 + 0.12 + 0.0\n"
    assert sorted(audit.embedded_floats(src)) == [0.12, 0.12] and audit.module_constants(src) == [0.03]


def test_baseline_file_matches_the_generator_schema():
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert data["schema_version"] == "builder_detail_audit.v1" and data["total_gen1"] >= 0
