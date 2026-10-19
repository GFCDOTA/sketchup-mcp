"""FP-042/P3/P4: SERVICE implementation owned by module, legacy API and CLI retained."""
from pathlib import Path

from shapely.geometry import box

from tools import service_layout as legacy
from tools.rooms.service import layout


def test_legacy_public_provider_points_to_room_module():
    assert legacy.build_boxes is layout.build_boxes
    assert legacy.main is layout.main
    assert legacy._split_zones is layout._split_zones
    assert legacy._programa is layout._programa
    assert legacy.AS == layout.AS
    assert legacy.SOCIAL == layout.SOCIAL
    assert legacy.TECNICO == layout.TECNICO


def test_root_resolves_to_repository_not_service_package():
    root = Path(__file__).resolve().parents[1]
    assert legacy.ROOT == root
    assert layout.ROOT == root


def test_invalid_seed_never_builds_3_invented_rooms(monkeypatch):
    sm = {"room_name": "A.S. | TERRACO SOCIAL | TERRACO TECNICO",
          "_geom": {"cell": box(0, 0, 120, 180), "circ": []}}
    monkeypatch.setattr(layout, "build_spatial_model", lambda _con, _room: sm)
    monkeypatch.setattr(layout, "_split_zones",
                        lambda _con, _room, _cell: (None, "SEED_ZONE_MISMATCH"))
    boxes, result = legacy.build_boxes({}, "r001")
    assert boxes == []
    assert result == {
        "result": "NO_VALID_LAYOUT",
        "room_name": "A.S. | TERRACO SOCIAL | TERRACO TECNICO",
        "reason": "SEED_ZONE_MISMATCH",
        "placement": "service_layout",
    }


def test_legacy_module_does_not_own_duplicate_builder_source():
    source = Path(legacy.__file__).read_text(encoding="utf-8")
    assert "def build_boxes(" not in source
    assert "def _split_zones(" not in source
    assert "if __name__ == \"__main__\":" in source
