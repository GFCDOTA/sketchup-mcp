"""Testes da CLASSE poltrona (cycle 001) — template do sofa replicado."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.armchair_class import (ARCHETYPES, _sabotages,            # noqa: E402
                                  armchair_class_gate, derive_armchair_spec)
from tools.sofa_builder import build_sofa                             # noqa: E402

COMBOS = [(a, b) for a in ARCHETYPES for b in ("legs", "plinth")]


@pytest.mark.parametrize("arch,base", COMBOS)
def test_derive_never_fails_class(arch, base):
    spec = derive_armchair_spec(arch, base)
    r = armchair_class_gate(spec)
    assert r["result"] != "FAIL", (arch, base, r["errors"])


@pytest.mark.parametrize("idx", range(6))
def test_class_gate_rejects_sabotages(idx):
    name, mk = _sabotages()[idx]
    r = armchair_class_gate(mk())
    assert r["result"] == "FAIL", f"{name}: veio {r['result']}"


def test_identity_vs_sofa():
    """O DNA: braco presente + footprint quase-quadrado + encosto acima do braco."""
    for arch in ARCHETYPES:
        s = derive_armchair_spec(arch)
        assert 0.22 <= 2 * s.arm_width / s.width <= 0.50, arch
        assert 0.80 <= s.width / s.depth <= 1.30, arch
        assert s.height - s.arm_height >= 0.16, arch
        assert s.seats == 1


def test_builder_reuse_produces_full_anatomy():
    """seats=1 no builder do sofa gera a anatomia completa da poltrona."""
    for arch in ARCHETYPES:
        parts, meta = build_sofa(derive_armchair_spec(arch))
        kinds = {p["kind"] for p in parts}
        assert {"base", "seat_cushion", "back_cushion", "arm", "foot"} <= kinds
        r = armchair_class_gate(derive_armchair_spec(arch), parts)
        assert r["result"] != "FAIL", (arch, r["errors"])


def test_archetype_axis_club_to_lounge():
    c, l = derive_armchair_spec("club"), derive_armchair_spec("lounge")
    assert c.arm_width > l.arm_width            # club gordo, lounge fino
    assert l.backrest_rake > c.backrest_rake    # lounge reclina
    assert l.height > c.height                  # lounge high-back
    assert l.seat_depth > c.seat_depth          # lounge funda


def test_matrix_builds_and_gates(tmp_path):
    pytest.importorskip("matplotlib")
    from tools.armchair_class import build_matrix
    res = build_matrix(tmp_path)
    assert len(res["report"]) == 9
    for r in res["report"]:
        assert r["class_gate"] != "FAIL", r
