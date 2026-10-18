import pytest

from core.domain.room_registry import PROJECT_ID, resolve_room_id, room_info, rooms_for_project

EXPECTED_ROOM_IDS = ["r000", "r001", "r002", "r003", "r004", "r005", "r006", "r007"]


def test_all_planta_74_rooms_present():
    rooms = rooms_for_project(PROJECT_ID)
    assert sorted(r.room_id for r in rooms) == EXPECTED_ROOM_IDS


def test_resolve_canonical_room_id_is_identity():
    for room_id in EXPECTED_ROOM_IDS:
        assert resolve_room_id(room_id) == room_id


def test_resolve_known_aliases():
    assert resolve_room_id("kitchen") == "r004"
    assert resolve_room_id("suite_01") == "r000"
    assert resolve_room_id("suite_02") == "r003"
    assert resolve_room_id("bathroom_01") == "r005"
    assert resolve_room_id("lavabo") == "r007"


def test_resolve_is_case_insensitive():
    assert resolve_room_id("KITCHEN") == "r004"
    assert resolve_room_id("R004") == "r004"


def test_unknown_alias_raises():
    with pytest.raises(KeyError):
        resolve_room_id("garage")


def test_unknown_project_raises():
    with pytest.raises(KeyError):
        resolve_room_id("r000", project_id="nonexistent_project")


def test_room_info_type_inferred_correctly():
    assert room_info("kitchen").room_type == "kitchen"
    assert room_info("suite_01").room_type == "bedroom"
    assert room_info("lavabo").room_type == "bathroom"
    assert room_info("r002").room_type == "living_room"
