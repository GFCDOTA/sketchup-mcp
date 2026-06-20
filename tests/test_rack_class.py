"""Testes da CLASSE rack (cycle 001) — builder 100% novo; satelites TV+sofa."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.rack_class import (ARCHETYPES, TVS, _apply_sab, _sabotages,  # noqa: E402
                              build_rack, derive_rack_spec, rack_class_gate,
                              sofa_satellite_gate, tv_satellite_gate)

COMBOS = [(a, tv) for a in ARCHETYPES for tv in TVS]


@pytest.mark.parametrize("arch,tv", COMBOS)
def test_derive_never_fails(arch, tv):
    spec = derive_rack_spec(tv, arch)
    assert rack_class_gate(spec)["result"] != "FAIL"
    assert tv_satellite_gate(spec, tv)["result"] == "PASS"


@pytest.mark.parametrize("idx", range(9))
def test_sabotages_fail(idx):
    name, mk = _sabotages()[idx]
    assert _apply_sab(mk), name


def test_tv_scales_length_not_height():
    """DNA: TV maior ALARGA o rack, nao sobe."""
    s55 = derive_rack_spec("55", "low_credenza")
    s75 = derive_rack_spec("75", "low_credenza")
    assert s75.length > s55.length
    assert s75.total_height() == s55.total_height()


def test_one_support_mode_with_levity():
    for arch in ARCHETYPES:
        spec = derive_rack_spec("65", arch)
        parts, _ = build_rack(spec)
        if spec.support == "legs":
            assert any(p["kind"] == "foot" for p in parts)
        if spec.support == "base":
            assert any(p["label"] == "toe_base" for p in parts)
        if spec.support == "floating":
            body = next(p for p in parts if p["label"] == "body")
            assert body["z0"] >= 0.25                    # respiro real do corpo


def test_facade_rhythm_and_technical_void():
    parts, _ = build_rack(derive_rack_spec("65", "storage_media"))
    assert any(p["kind"] == "niche" for p in parts)    # vazio tecnico
    assert any(p["kind"] == "front" for p in parts)    # gaveta


def test_cycle002_floating_context_and_facades():
    """flutuacao REAL (wall_back + shadow gap + cleat) e fachadas simetricas."""
    pf, _ = build_rack(derive_rack_spec("65", "floating_minimal"))
    labels = {p["label"] for p in pf}
    assert {"wall_back", "shadow_gap", "cleat"} <= labels
    for arch in ("floating_minimal", "low_credenza", "storage_media"):
        s = derive_rack_spec("65", arch)
        assert s.facade_pattern == tuple(reversed(s.facade_pattern)), arch
    # credenza: nicho CENTRAL (nao na ponta)
    assert derive_rack_spec("65", "low_credenza").facade_pattern[1] == "niche"


def test_tv_proxy_parts():
    from tools.rack_class import _tv_proxy_parts
    spec = derive_rack_spec("65", "low_credenza")
    proxy = _tv_proxy_parts(spec, "65")
    assert any(p["label"] == "eye_line" for p in proxy)
    tw = 1.45
    tl = next(p for p in proxy if p["label"] == "tv_l")
    tr = next(p for p in proxy if p["label"] == "tv_r")
    assert abs((tr["x1"] - tl["x0"]) - tw) < 0.01


def test_floating_body_scales_with_length():
    """com wall_back (ancora) o corpo fino e' ok ate 7.2; sem, engrossa."""
    s = derive_rack_spec("75", "floating_minimal")
    assert s.length / s.body_h <= 7.2 and s.wall_back


def test_sofa_satellite():
    spec = derive_rack_spec("75", "low_credenza")
    assert sofa_satellite_gate(spec, "75", sofa_dist=3.0)["result"] == "PASS"
    assert sofa_satellite_gate(spec, "75", sofa_dist=1.8)["result"] == "FAIL"


def test_matrix_builds(tmp_path):
    pytest.importorskip("matplotlib")
    from tools.rack_class import build_matrix
    res = build_matrix(tmp_path)
    assert len(res["report"]) == 9
    for r in res["report"]:
        assert "FAIL" not in (r["class_gate"], r["tv_sat"], r["sofa_sat"]), r
