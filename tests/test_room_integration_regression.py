"""Integração do orquestrador com providers isolados: sem SketchUp e sem SKP."""
from unittest.mock import Mock

import pytest

from tools import furnish_apartment as f
from tools.room_type import BATHROOM, BEDROOM, KITCHEN, LIVING, SERVICE, UNKNOWN


@pytest.fixture
def isolated(monkeypatch):
    # Não executa o materializador nem modifica qualquer fixture.
    from core import spatial_semantics
    monkeypatch.setattr(spatial_semantics, "annotate_all", lambda boxes: None)
    monkeypatch.delenv("FURNISH_STYLE", raising=False)
    providers = {kind: Mock(name=kind) for kind in
                 (BEDROOM, KITCHEN, LIVING, BATHROOM, SERVICE)}
    monkeypatch.setattr(f, "BRAINS", providers)
    return providers, monkeypatch


def _rooms(*kinds):
    return [{"id": "r%03d" % idx, "name": "room_%d" % idx, "room_type": kind}
            for idx, kind in enumerate(kinds)]


def test_every_supported_room_routes_to_its_own_provider(isolated):
    providers, monkeypatch = isolated
    kinds = (BEDROOM, LIVING, BATHROOM, SERVICE)
    monkeypatch.setattr(f, "classify_rooms", lambda _: _rooms(*kinds))
    for kind in kinds:
        providers[kind].return_value = ([{"kind": "part", "rgb": [50, 50, 50]}],
                                         {"result": "OK"})
    boxes, summary = f.collect_boxes({"rooms": []})
    assert len(boxes) == len(kinds)
    assert [row[2] for row in summary] == list(kinds)
    assert all(row[3:] == ("OK", 1) for row in summary)
    assert [b["room"] for b in boxes] == ["room_0", "room_1", "room_2", "room_3"]
    assert all(b["module"] == "part" for b in boxes)
    for idx, kind in enumerate(kinds):
        providers[kind].assert_called_once_with({"rooms": []}, "r%03d" % idx)


def test_unknown_room_skips_without_invoking_any_brain(isolated):
    providers, monkeypatch = isolated
    monkeypatch.setattr(f, "classify_rooms", lambda _: _rooms(UNKNOWN))
    boxes, summary = f.collect_boxes({"rooms": []})
    assert boxes == []
    assert summary == [("r000", "room_0", UNKNOWN, "skip(sem brain)", 0)]
    for brain in providers.values():
        brain.assert_not_called()


def test_kitchen_anchor_failure_prevents_furnishing(isolated):
    providers, monkeypatch = isolated
    from tools import kitchen_validation
    monkeypatch.setattr(f, "classify_rooms", lambda _: _rooms(KITCHEN))
    providers[KITCHEN].return_value = ([{"kind": "pia"}], {"result": "OK"})
    monkeypatch.setattr(kitchen_validation, "validate", lambda *_: {
        "result": "FAIL", "lines": [], "checks": {"sink_wall": "wrong"}
    })
    with pytest.raises(SystemExit, match="BUILD ABORTADO"):
        f.collect_boxes({"rooms": []})
    providers[KITCHEN].assert_called_once_with({"rooms": []}, "r000")


def test_kitchen_anchor_success_keeps_module_identity(isolated):
    providers, monkeypatch = isolated
    from tools import kitchen_validation
    monkeypatch.setattr(f, "classify_rooms", lambda _: _rooms(KITCHEN))
    providers[KITCHEN].return_value = ([{"kind": "cuba", "module": "Cozinha"}],
                                       {"result": "OK"})
    monkeypatch.setattr(kitchen_validation, "validate", lambda *_: {
        "result": "PASS", "lines": [], "checks": {"sink_wall": "W"}
    })
    boxes, summary = f.collect_boxes({"rooms": []})
    assert boxes[0]["room"] == "room_0"
    assert boxes[0]["module"] == "Cozinha"
    assert summary[0][3:] == ("OK", 1)


def test_missing_optional_brain_output_remains_safe(isolated):
    providers, monkeypatch = isolated
    monkeypatch.setattr(f, "classify_rooms", lambda _: _rooms(BEDROOM))
    providers[BEDROOM].return_value = (None, {"result": "NO_VALID_LAYOUT"})
    boxes, summary = f.collect_boxes({"rooms": []})
    assert boxes == []
    assert summary[0][3:] == ("NO_VALID_LAYOUT", 0)
