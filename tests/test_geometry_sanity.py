"""Regressão do gate geometry_sanity. Hermético (boxes sintéticos em POLEGADAS).
Cobre as 5 classes exigidas: underground, degenerada, off-axis, bbox absurda, fora do cômodo."""
from __future__ import annotations

from tools.geometry_sanity import audit

# caixa "boa": 24x24in no chão, axis-aligned
GOOD = {"kind": "corpo", "label": "ok", "x0": 10, "y0": 10, "x1": 34, "y1": 34,
        "z0_in": 0.0, "h_in": 30.0, "corners": [[10, 10], [34, 10], [34, 34], [10, 34]]}


def test_clean_is_pass():
    r = audit([GOOD], to_m=0.0254)
    assert r["overall"] == "PASS" and r["n_fail"] == 0


def test_underground_fails():
    b = {**GOOD, "label": "afundado", "z0_in": -3.0}
    r = audit([b], to_m=0.0254)
    assert r["overall"] == "FAIL"
    assert any(f["check"] == "underground" for f in r["findings"])


def test_degenerate_footprint_fails():
    b = {**GOOD, "label": "degen", "x0": 10, "y0": 10, "x1": 10.3, "y1": 10.3,
         "corners": [[10, 10], [10.3, 10], [10.3, 10.3], [10, 10.3]]}
    r = audit([b], to_m=0.0254)
    assert r["overall"] == "FAIL"
    assert any(f["check"] == "degenerate_footprint" for f in r["findings"])


def test_off_axis_fails():
    b = {**GOOD, "label": "torto", "corners": [[10, 10], [34, 12], [34, 34], [10, 32]]}
    r = audit([b], to_m=0.0254)
    assert r["overall"] == "FAIL"
    assert any(f["check"] == "off_axis" for f in r["findings"])


def test_absurd_bbox_fails():
    # 300in * 0.0254 = 7.62m > 6m
    b = {**GOOD, "label": "gigante", "x1": 310,
         "corners": [[10, 10], [310, 10], [310, 34], [10, 34]]}
    r = audit([b], to_m=0.0254)
    assert r["overall"] == "FAIL"
    assert any(f["check"] == "absurd_bbox" for f in r["findings"])


def test_outside_room_fails_only_with_rooms():
    room = [[0, 0], [100, 0], [100, 100], [0, 100]]  # caixa GOOD (centro ~22,22) está dentro
    out = {**GOOD, "label": "vazou", "x0": 200, "y0": 200, "x1": 224, "y1": 224,
           "corners": [[200, 200], [224, 200], [224, 224], [200, 224]]}
    r = audit([GOOD, out], rooms=[room], to_m=0.0254)
    assert r["overall"] == "FAIL"
    labels = [f["label"] for f in r["findings"] if f["check"] == "outside_room"]
    assert labels == ["vazou"]
    # sem rooms, o check nao roda
    r2 = audit([out], to_m=0.0254)
    assert not any(f["check"] == "outside_room" for f in r2["findings"])


def test_verdict_blocks_promotion_semantics():
    # FAIL -> exit !=0 (bloqueia); PASS -> 0
    assert audit([GOOD], to_m=0.0254)["overall"] == "PASS"
    assert audit([{**GOOD, "z0_in": -5}], to_m=0.0254)["overall"] == "FAIL"


def test_decorative_clipped_polygon_not_off_axis():
    # tapete decorativo recortado ao comodo (poligono axis-aligned em L, nao-retangular)
    # NAO deve ser off_axis (era falso-positivo). Estrutural rotacionado AINDA e off_axis.
    rug = {"kind": "rug", "label": "tapete", "decorative": True,
           "x0": 10, "y0": 10, "x1": 40, "y1": 40,
           "corners": [[10, 10], [40, 10], [40, 40], [25, 40], [25, 25], [10, 25]]}
    r = audit([rug], to_m=0.0254)
    assert not any(f["check"] == "off_axis" for f in r["findings"])
    # mas um movel ESTRUTURAL torto continua FAIL
    bed = {"kind": "bed", "label": "cama", "x0": 10, "y0": 10, "x1": 40, "y1": 40,
           "corners": [[10, 10], [40, 12], [40, 40], [10, 38]]}
    assert any(f["check"] == "off_axis" for f in audit([bed], to_m=0.0254)["findings"])
