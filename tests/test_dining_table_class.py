"""Testes da CLASSE mesa de jantar (cycle 001) — derivada de LUGARES;
cadeira/envelope/circulacao = satelites VISIVEIS (padrao institucional)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.dining_table_class import (CHAIR, MATRIX, PLACE_W_MIN,  # noqa: E402
                                      _apply_sab, _chair_proxy_parts,
                                      _sabotages, _seat_anchors,
                                      build_dining_table, chair_satellite_gate,
                                      circulation_gate, derive_dining_spec,
                                      dining_class_gate)


@pytest.mark.parametrize("name,arch,seats", MATRIX)
def test_derive_never_fails(name, arch, seats):
    spec = derive_dining_spec(seats, arch)
    parts, _ = build_dining_table(spec)
    assert dining_class_gate(spec, parts)["result"] != "FAIL", name
    assert chair_satellite_gate(spec)["result"] == "PASS", name
    vis = parts + _chair_proxy_parts(spec)
    assert circulation_gate(spec, parts_vis=vis)["result"] == "PASS", name


@pytest.mark.parametrize("idx", range(10))
def test_sabotages_fail(idx):
    name, mk = _sabotages()[idx]
    assert _apply_sab(mk), name


def test_satellite_by_construction():
    """a mesa nao tem tamanho proprio: mudam os lugares, muda a mesa."""
    assert (derive_dining_spec(8, "rect_family").length
            > derive_dining_spec(4, "rect_family").length)
    assert (derive_dining_spec(6, "round_compact").length
            > derive_dining_spec(2, "round_compact").length)
    # altura NUNCA deriva dos lugares (corpo humano governa)
    for _, arch, seats in MATRIX:
        s = derive_dining_spec(seats, arch)
        assert s.height == 0.75
        assert 0.27 <= s.height - CHAIR["seat_h"] <= 0.33


def test_saturation_and_place_floor():
    """saturacao 2.60: comprime a frente ate 0.55, nunca abaixo."""
    for _, arch, seats in MATRIX:
        s = derive_dining_spec(seats, arch)
        assert s.length <= 2.60 + 1e-9
        assert s.place_w >= PLACE_W_MIN - 1e-9
    # mas prancha forcada via override reprova (saturacao e regra, nao clamp)
    s = derive_dining_spec(8, "rect_family", length=3.2)
    assert dining_class_gate(s)["result"] == "FAIL"


def test_knee_clearance_all_cells():
    for name, arch, seats in MATRIX:
        s = derive_dining_spec(seats, arch)
        assert s.knee_clearance() >= 0.60 - 1e-9, name


def test_archetype_grammar_in_geometry():
    rect, _ = build_dining_table(derive_dining_spec(6, "rect_family"))
    rnd, _ = build_dining_table(derive_dining_spec(4, "round_compact"))
    oval, _ = build_dining_table(derive_dining_spec(6, "oval_soft"))
    # familia: 4 pernas + saia nos 4 lados
    assert sum(1 for p in rect if p["kind"] == "foot") == 4
    assert sum(1 for p in rect if p["label"].startswith("apron")) == 4
    # redonda: tampo DISCO + pedestal redondos por BANDAS (le circulo, nao octogono)
    rlabels = [p["label"] for p in rnd]
    assert sum(1 for p in rnd if p["label"].startswith("top_")
               and p.get("verts8")) >= 8          # disco curvo, nao 2 alas
    assert any(l.startswith("column") for l in rlabels)  # coluna fina redonda
    assert any(l.startswith("foot") for l in rlabels)    # prato baixo redondo
    assert {"top", "foot"} <= {p["kind"] for p in rnd}
    # oval: pontas trapezoidais verts8 + pernas conicas verts8
    assert any(p.get("verts8") for p in oval if p["label"] in ("top_w", "top_e"))
    assert all(p.get("verts8") for p in oval if p["kind"] == "foot")


def test_chair_proxies_visible_per_seat():
    """padrao institucional: 1 cadeira + 1 envelope POR lugar + anel de uso."""
    for _, arch, seats in MATRIX:
        spec = derive_dining_spec(seats, arch)
        anchors = _seat_anchors(spec)
        assert len(anchors) == seats
        prox = _chair_proxy_parts(spec)
        assert sum(1 for p in prox if p["kind"] == "chair"
                   and "seat" in p["label"]) == seats
        assert sum(1 for p in prox if "env" in p["label"]) == seats
        assert sum(1 for p in prox if p["label"].startswith("use_ring")) == 4


def test_visibility_gate_is_institutional():
    spec = derive_dining_spec(6, "rect_family")
    parts, _ = build_dining_table(spec)
    assert circulation_gate(spec, parts_vis=parts)["result"] == "FAIL"
    vis = parts + _chair_proxy_parts(spec)
    assert circulation_gate(spec, parts_vis=vis)["result"] == "PASS"


def test_matrix_builds(tmp_path):
    pytest.importorskip("matplotlib")
    from tools.dining_table_class import build_matrix
    res = build_matrix(tmp_path)
    assert len(res["report"]) == 9
    for r in res["report"]:
        assert r["class_gate"] != "FAIL" and r["chair_sat"] != "FAIL", r
        assert r["use_sat"] != "FAIL", r
