"""Testes unitários e regressivos do dispatch por cômodo sem SketchUp."""
from unittest.mock import Mock

import pytest

from tools.room_type import BATHROOM, BEDROOM, KITCHEN, LIVING, SERVICE, UNKNOWN
from tools.rooms.dispatch import SUPPORTED_BRAINS, build_brain_registry, get_brain


def _providers():
    return {name: Mock(name=name, return_value=([{"kind": name}], {"result": "OK"}))
            for name in ("bedroom", "kitchen", "living", "bathroom", "service")}


def test_legacy_dispatch_keys_and_identity():
    providers = _providers()
    registry = build_brain_registry(**providers)
    assert tuple(registry) == (BEDROOM, KITCHEN, LIVING, BATHROOM, SERVICE)
    assert tuple(registry) == SUPPORTED_BRAINS
    for key, name in zip(registry, providers):
        assert registry[key] is providers[name]


@pytest.mark.parametrize("unsupported", [UNKNOWN, "BALCONY", "NEW_ROOM", ""])
def test_unsupported_room_is_skipped_without_fallback(unsupported):
    providers = _providers()
    registry = build_brain_registry(**providers)
    assert get_brain(registry, unsupported) is None
    for provider in providers.values():
        provider.assert_not_called()


def test_only_selected_room_brain_is_executed():
    providers = _providers()
    registry = build_brain_registry(**providers)
    chosen = get_brain(registry, KITCHEN)
    boxes, result = chosen({"rooms": []}, "r004")
    assert boxes == [{"kind": "kitchen"}]
    assert result == {"result": "OK"}
    providers["kitchen"].assert_called_once_with({"rooms": []}, "r004")
    for name, provider in providers.items():
        if name != "kitchen":
            provider.assert_not_called()


def test_invalid_brain_fails_closed():
    providers = _providers()
    providers["kitchen"] = None
    with pytest.raises(TypeError, match="ROOM_BRAIN_MUST_BE_CALLABLE"):
        build_brain_registry(**providers)
