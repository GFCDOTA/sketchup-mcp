"""FP-042/P3/P4: SERVICE implementation owned by module, legacy API and CLI retained."""
from pathlib import Path

from shapely.geometry import box

from tools.rooms.service import layout


def test_service_provider_is_owned_by_the_room_module():
    # a fachada service_layout saiu na FP-044/F6; o contrato do dono continua
    for fn in (layout.build_boxes, layout.main, layout._split_zones, layout._programa):
        assert fn.__module__ == layout.__name__
    assert {layout.AS, layout.SOCIAL, layout.TECNICO}


def test_root_resolves_to_repository_not_service_package():
    root = Path(__file__).resolve().parents[1]
    assert layout.ROOT == root


def test_invalid_seed_never_builds_3_invented_rooms(monkeypatch):
    sm = {"room_name": "A.S. | TERRACO SOCIAL | TERRACO TECNICO",
          "_geom": {"cell": box(0, 0, 120, 180), "circ": []}}
    monkeypatch.setattr(layout, "build_spatial_model", lambda _con, _room: sm)
    monkeypatch.setattr(layout, "_split_zones",
                        lambda _con, _room, _cell: (None, "SEED_ZONE_MISMATCH"))
    boxes, result = layout.build_boxes({}, "r001")
    assert boxes == []
    assert result == {
        "result": "NO_VALID_LAYOUT",
        "room_name": "A.S. | TERRACO SOCIAL | TERRACO TECNICO",
        "reason": "SEED_ZONE_MISMATCH",
        "placement": "service_layout",
    }


def test_owner_has_a_single_builder_and_the_cli():
    source = Path(layout.__file__).read_text(encoding="utf-8")
    assert source.count("def build_boxes(") == 1
    assert source.count("def _split_zones(") == 1
    assert "if __name__ == \"__main__\":" in source
