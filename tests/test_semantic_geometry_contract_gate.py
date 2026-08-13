"""Regressão do semantic_geometry_contract_gate — contrato semântico central
(core/spatial_semantics.py). Hermético (boxes sintéticos)."""
from __future__ import annotations

from tools.semantic_geometry_contract_gate import audit

RECT = [[10, 10], [34, 10], [34, 34], [10, 34]]
ROTATED_RECT = [[10, 10], [30, 12], [28, 32], [8, 30]]   # retangulo real, so girado
NON_RECT = [[10, 10], [34, 12], [34, 34], [10, 32]]      # paralelogramo (nao 90deg)


def test_known_kind_is_pass():
    b = {"kind": "parede", "label": "p1", "corners": RECT}
    r = audit([b])
    assert r["overall"] == "PASS" and r["n_fail"] == 0 and r["n_warn"] == 0


def test_known_module_fallback_is_pass():
    # kind sem entrada propria (ex. parte "seat" de uma cadeira), mas module
    # bate no MODULE_REGISTRY -> ainda e' declaracao explicita, nao chute.
    b = {"kind": "seat", "module": "Cadeira jantar", "label": "assento", "corners": RECT}
    r = audit([b])
    assert r["overall"] == "PASS"


def test_unknown_simple_kind_is_warn_legacy():
    b = {"kind": "totally_unregistered_kind_xyz", "label": "x", "corners": RECT}
    r = audit([b])
    assert r["overall"] == "WARN" and r["n_warn"] == 1
    assert r["findings"][0]["status"] == "WARN_LEGACY_SEMANTICS"


def test_unknown_complex_kind_is_fail():
    b = {"kind": "totally_unregistered_kind_xyz", "label": "torto", "corners": NON_RECT}
    r = audit([b])
    assert r["overall"] == "FAIL" and r["n_fail"] == 1
    assert r["findings"][0]["status"] == "FAIL_MISSING_SEMANTICS"


def test_unknown_rotated_rect_is_fail():
    # retangulo GIRADO sem contrato declarado tambem e' "complexo" o
    # suficiente pra exigir declaracao (nao sabemos se a rotacao e' de
    # proposito sem geometry_intent/shape_policy explicito).
    b = {"kind": "totally_unregistered_kind_xyz", "label": "girado", "corners": ROTATED_RECT}
    r = audit([b])
    assert r["overall"] == "FAIL"


def test_explicit_geometry_intent_overrides_kind():
    # builder que seta geometry_intent direto no box e' declaracao explicita
    # mesmo com kind desconhecido.
    b = {"kind": "totally_unregistered_kind_xyz", "label": "x", "corners": RECT,
         "geometry_intent": "DECORATIVE", "_semantics_provenance": "explicit"}
    r = audit([b])
    assert r["overall"] == "PASS"
