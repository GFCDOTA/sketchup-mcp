"""Regressão da regra de wet-room extraída do orquestrador."""
from tools.rooms.bathroom.validation import unexpected_wet_room_kinds


def test_wet_room_allowed_kinds_and_details():
    boxes = [{"kind": kind} for kind in (
        "gabinete", "bancada_banho", "cuba", "espelho",
        "vaso", "box_vidro", "box", "kb_led", "kb_torneira"
    )]
    assert unexpected_wet_room_kinds(boxes) == []


def test_unexpected_kinds_sorted_deduplicated_without_mutation():
    boxes = [{"kind": "sofa"}, {"kind": "cama"}, {"kind": "sofa"}]
    original = [dict(b) for b in boxes]
    assert unexpected_wet_room_kinds(boxes) == ["cama", "sofa"]
    assert boxes == original


def test_missing_kind_and_empty_are_legacy_compatible():
    assert unexpected_wet_room_kinds([]) == []
    assert unexpected_wet_room_kinds(None) == []
    assert unexpected_wet_room_kinds([{}]) == ["None"]
