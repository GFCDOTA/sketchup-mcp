"""Testes da CLASSE sofa (programa arquiteto-de-classe, FASE 1-3):
teoria executavel (faixas/relacoes/anti-regressao), derivacao por arquetipo,
prova de generalizacao e contrato bbox com rake. SU-free, deterministico.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.furniture_anatomy_spec import SofaSpec                       # noqa: E402
from tools.sofa_builder import build_sofa                               # noqa: E402
from tools.sofa_class import (ARCHETYPES, ARM_STYLES, BASE_STYLES,      # noqa: E402
                              _sabotages, derive_spec, sofa_class_gate)
from tools.sofa_gate import gate as anatomy_gate                        # noqa: E402

ALL_COMBOS = [(a, s, arm, b) for a in ARCHETYPES for s in (2, 3, 4)
              for arm in ARM_STYLES for b in BASE_STYLES]


@pytest.mark.parametrize("arch,seats,arm,base", ALL_COMBOS)
def test_derive_never_fails_class(arch, seats, arm, base):
    """TODO derivado pela classe valida na classe (54 combos)."""
    spec = derive_spec(seats, arch, arm, base)
    r = sofa_class_gate(spec)
    assert r["result"] != "FAIL", (arch, seats, arm, base, r["errors"])


@pytest.mark.parametrize("idx", range(6))
def test_class_gate_rejects_sabotages(idx):
    """Aberracoes que o validate() raso aceita DEVEM falhar na classe."""
    name, mk = _sabotages()[idx]
    r = sofa_class_gate(mk())
    assert r["result"] == "FAIL", f"{name}: esperava FAIL, veio {r['result']}"


def test_scaling_only_width_grows():
    """Escala 2->3->4: SO a largura cresce; corpo humano e' constante."""
    s2, s3, s4 = (derive_spec(n, "standard") for n in (2, 3, 4))
    assert s2.width < s3.width < s4.width
    per_seat = ARCHETYPES["standard"]["per_seat"]
    assert s3.width - s2.width == pytest.approx(per_seat, abs=1e-6)
    for attr in ("seat_height", "seat_depth", "depth", "height", "arm_height",
                 "arm_width", "cushion_thickness", "backrest_rake"):
        assert getattr(s2, attr) == getattr(s3, attr) == getattr(s4, attr), attr


def test_archetype_axis_formal_to_lounge():
    """O eixo de intencao: lounge e' mais baixo, mais fundo, mais reclinado."""
    f, l = derive_spec(3, "formal"), derive_spec(3, "lounge")
    assert l.height < f.height
    assert l.seat_depth > f.seat_depth
    assert l.backrest_rake > f.backrest_rake
    assert l.cushion_thickness > f.cushion_thickness


def test_bbox_contract_includes_rake_overhang():
    """Furo de classe da FASE 0: bbox_m() ignorava o cisalhamento do rake e
    todo sofa com rake dava WARN falso no gate de anatomia."""
    spec = derive_spec(3, "standard")
    parts, meta = build_sofa(spec)
    exp = spec.bbox_m()
    assert all(abs(meta["bbox_m"][i] - exp[i]) <= 0.05 for i in range(3)), \
        (meta["bbox_m"], exp)
    assert anatomy_gate(spec, parts)["result"] == "PASS"


def test_default_exemplar_still_in_class():
    """O exemplar PASS dos cycles 1-4 (defaults do SofaSpec) pertence a classe
    (anti-regressao: a teoria nao pode expulsar o que o juiz aprovou)."""
    r = sofa_class_gate(SofaSpec())
    assert r["result"] != "FAIL", r["errors"]


def test_matrix_builds_and_gates(tmp_path):
    pytest.importorskip("matplotlib")
    from tools.sofa_class_matrix import build_matrix
    res = build_matrix(tmp_path)
    assert len(res["report"]) == 9
    for r in res["report"]:
        assert r["class_gate"] != "FAIL", r
        assert r["anatomy_gate"] != "FAIL", r
    assert Path(res["sheet"]).exists()
