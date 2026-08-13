"""Regressão do collision_envelope_gate — visual_bbox != collision_footprint
(achado 2026-08-12: tapete de banho inflando footprint de colisão do módulo
que o hospedava). Hermético (boxes sintéticos)."""
from __future__ import annotations

from tools.collision_envelope_gate import audit, resolve_envelope

RECT = [[0, 0], [10, 0], [10, 10], [0, 10]]


def test_normal_furniture_is_pass():
    b = {"kind": "sofa", "module": "Sofa", "label": "s1", "corners": RECT,
         "x0": 0, "y0": 0, "x1": 10, "y1": 10}
    r = audit([b])
    assert r["overall"] == "PASS" and r["n_fail"] == 0


def test_soft_item_marked_solid_fails():
    # regressao direta do bug real: um item SOFT (tapete) com interaction_policy
    # dizendo que e' solido (bbox visual virou colisao sem a politica mandar).
    b = {"kind": "rug", "module": "Tapete", "label": "tapete malicioso",
         "x0": 0, "y0": 0, "x1": 10, "y1": 10, "corners": RECT,
         "geometry_intent": "SOFT",
         "interaction_policy": {"circulation": "BLOCK", "furniture_overlap": "EXCLUSIVE"}}
    r = audit([b])
    assert r["overall"] == "FAIL"
    assert any(f["check"] == "soft_items_never_solid" for f in r["findings"])


def test_decorative_item_marked_solid_fails():
    b = {"kind": "almofada", "module": "Sofa", "label": "cushion",
         "x0": 0, "y0": 0, "x1": 5, "y1": 5, "corners": RECT,
         "geometry_intent": "DECORATIVE",
         "interaction_policy": {"circulation": "BLOCK", "furniture_overlap": "IGNORE"}}
    r = audit([b])
    assert r["overall"] == "FAIL"


def test_soft_item_correctly_walkable_passes():
    b = {"kind": "rug", "module": "Tapete", "label": "tapete ok",
         "x0": 0, "y0": 0, "x1": 10, "y1": 10, "corners": RECT,
         "geometry_intent": "SOFT",
         "interaction_policy": {"circulation": "WALKABLE", "furniture_overlap": "ALLOW"}}
    r = audit([b])
    assert r["overall"] == "PASS"


def test_missing_geometry_fails():
    b = {"kind": "misterioso", "label": "sem geometria"}
    r = audit([b])
    assert r["overall"] == "FAIL"
    assert any(f["check"] == "envelope_resolves" for f in r["findings"])


def test_resolve_envelope_derives_not_persists_by_default():
    b = {"kind": "sofa", "module": "Sofa", "corners": RECT, "x0": 0, "y0": 0, "x1": 10, "y1": 10}
    env = resolve_envelope(b)
    assert env["visual_bbox_exists"] is True
    assert env["collision_footprint"] == "visual_bbox"   # FURNITURE default: EXCLUSIVE
    assert env["circulation_blocks"] is True
