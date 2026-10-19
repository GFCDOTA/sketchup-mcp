"""FP-042/P3: adapter de quarto tem ownership no quarto; API legacy preservada.

Usa doubles controlados, sem SketchUp ou mutação de fixtures.
"""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools.room_type import BEDROOM
from tools.rooms.bedroom import furnishing


def test_public_adapter_and_dispatch_are_same_callable():
    from tools import furnish_apartment as orchestrator

    assert orchestrator.bedroom_designer_boxes is furnishing.bedroom_designer_boxes
    assert orchestrator.BRAINS[BEDROOM] is furnishing.bedroom_designer_boxes
    assert furnishing._chair_parts is orchestrator._chair_parts
    assert furnishing._oriented_box is orchestrator._oriented_box


@pytest.mark.parametrize("result", ["NO_VALID_LAYOUT", "FAIL", "SKIPPED"])
def test_non_ok_designer_result_early_returns_without_building(monkeypatch, result):
    con = {"rooms": []}
    expected = {"result": result, "reason": "unchanged"}
    run = Mock(return_value=(None, expected))
    convert = Mock()
    monkeypatch.setattr(furnishing.bedroom_designer, "run", run)
    monkeypatch.setattr(furnishing.bedroom_designer, "_items_to_boxes", convert)
    assert furnishing.bedroom_designer_boxes(con, "r000") == (None, expected)
    run.assert_called_once_with(con, "r000", minimalist=True)
    convert.assert_not_called()


def test_empty_ok_designer_preserves_contract(monkeypatch):
    out = {"result": "OK", "_winner_items": []}
    monkeypatch.setattr(furnishing.bedroom_designer, "run", lambda *_args, **_kw: ({}, out))
    monkeypatch.setattr(furnishing.bedroom_designer, "_items_to_boxes", lambda _items: [])
    boxes, result = furnishing.bedroom_designer_boxes({}, "r003")
    assert boxes == []
    assert result is out


def test_desk_chair_uses_shared_assembly_and_module(monkeypatch):
    from tools import sofa_builder

    chair = {"type": "desk_chair", "box": SimpleNamespace(bounds=(0, 0, 60, 45)),
             "facing": (0, 1)}
    out = {"result": "OK", "_winner_items": [chair]}
    monkeypatch.setattr(furnishing.bedroom_designer, "run", lambda *_args, **_kw: ({}, out))
    monkeypatch.setattr(
        furnishing.bedroom_designer, "_items_to_boxes",
        lambda _items: [{"kind": "desk_chair", "module": "placeholder"}],
    )
    def fake_place(parts, center, facing):
        assert parts == furnishing._chair_parts()
        assert facing == (0.0, -1.0)
        return [{"kind": p["kind"]} for p in parts]
    monkeypatch.setattr(sofa_builder, "place_sofa_boxes", fake_place)
    boxes, result = furnishing.bedroom_designer_boxes({}, "r003")
    assert len(boxes) == 8
    assert all(b["module"] == "Cadeira escrivaninha" for b in boxes)
    assert all(b["kind"] != "desk_chair" for b in boxes)
    assert result is out


def test_fp043_nightstand_materialization_matches_planned_body_and_top(monkeypatch):
    """Regressao: reduzir para 72% nao pode esconder inflacao na materializacao."""
    from shapely.geometry import box
    from core.scale import M, PT_TO_IN
    from tools.rooms.bedroom import designer

    approved_w, approved_d = designer.nightstand_real_dimensions(0.45 * 0.72, 0.40 * 0.72)[:2]
    approved = box(0, 0, M(approved_w), M(approved_d))
    out = {"result": "OK", "_winner_items": [{"type": "nightstand", "box": approved}]}
    monkeypatch.setattr(furnishing.bedroom_designer, "run", lambda *_a, **_kw: ({}, out))
    monkeypatch.setattr(furnishing.bedroom_designer, "_items_to_boxes", lambda _items: [])
    boxes, res = furnishing.bedroom_designer_boxes({}, "r000")
    top = next(b for b in boxes if b["kind"] == "ks_criado_tampo")
    body = next(b for b in boxes if b["kind"] == "ks_criado_corpo")
    xs = [p[0] for p in top["corners"]]
    ys = [p[1] for p in top["corners"]]
    bx = [p[0] for p in body["corners"]]
    by = [p[1] for p in body["corners"]]
    _, _, top_w, top_d = designer.nightstand_real_dimensions(approved_w, approved_d)
    assert (max(xs) - min(xs)) * 0.0254 == pytest.approx(top_w, abs=0.0003)
    assert (max(ys) - min(ys)) * 0.0254 == pytest.approx(top_d, abs=0.0003)
    assert (max(bx) - min(bx)) * 0.0254 == pytest.approx(approved_w, abs=0.0003)
    assert (max(by) - min(by)) * 0.0254 == pytest.approx(approved_d, abs=0.0003)
    assert res["nightstand_parametric"]["floating"] is True
