"""Contrato do detector de vão planejado-vs-parede. Hermético: geometria sintética,
sem dados reais nem coordenadas de consensus."""
from __future__ import annotations

from tools.furniture_wall_gap import audit, is_planned, perp_gap

WALL_V = (0.0, 0.0, 0.0, 3.0)  # parede vertical em x=0, y 0..3


def test_perp_gap_flush_is_zero():
    flush = {"x0": 0.0, "y0": 0.5, "x1": 0.6, "y1": 2.5}
    assert perp_gap(flush, WALL_V) == 0.0


def test_perp_gap_measures_gap():
    gapped = {"x0": 0.03, "y0": 0.5, "x1": 0.63, "y1": 2.5}
    assert abs(perp_gap(gapped, WALL_V) - 0.03) < 1e-9


def test_perp_gap_none_without_overlap():
    away = {"x0": 0.03, "y0": 5.0, "x1": 0.6, "y1": 6.0}  # fora do span Y da parede
    assert perp_gap(away, WALL_V) is None


def test_is_planned_disambiguates_corpo_by_height():
    assert is_planned({"kind": "corpo", "h_in": 83.0}) is True    # guarda-roupa (alto)
    assert is_planned({"kind": "corpo", "h_in": 17.0}) is False   # criado-mudo (baixo)
    assert is_planned({"kind": "bancada"}) is True
    assert is_planned({"kind": "headboard"}) is True
    assert is_planned({"kind": "sofa"}) is False
    assert is_planned({"kind": "seat_cushion"}) is False


def test_audit_flags_only_gapped_planned():
    boxes = [
        {"kind": "corpo", "h_in": 83.0, "label": "guarda-roupa", "x0": 0.03, "y0": 0.5, "x1": 0.63, "y1": 2.5},
        {"kind": "corpo", "h_in": 83.0, "label": "gr-flush", "x0": 0.0, "y0": 0.5, "x1": 0.6, "y1": 2.5},
        {"kind": "corpo", "h_in": 17.0, "label": "criado-mudo", "x0": 0.10, "y0": 0.5, "x1": 0.5, "y1": 0.9},
        {"kind": "sofa", "label": "sofa", "x0": 0.03, "y0": 0.5, "x1": 1.0, "y1": 2.5},
    ]
    f = audit(boxes, [WALL_V], tol=0.02)
    labels = [x["label"] for x in f]
    assert labels == ["guarda-roupa"]          # só o planejado com vão; flush/criado/sofa fora
    assert f[0]["gap_m"] == 0.03
