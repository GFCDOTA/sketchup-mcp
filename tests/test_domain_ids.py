import pytest

from core.domain.ids import (
    make_iteration_id,
    make_room_id,
    make_trace_id,
    parse_iteration_id,
    validate_project_id,
)


def test_validate_project_id_accepts_planta_74():
    assert validate_project_id("planta_74") == "planta_74"


@pytest.mark.parametrize("bad", ["Planta_74", "planta-74", "1planta", "", "planta 74"])
def test_validate_project_id_rejects_invalid(bad):
    with pytest.raises(ValueError):
        validate_project_id(bad)


def test_make_room_id_resolves_alias():
    assert make_room_id("kitchen", project_id="planta_74") == "r004"
    assert make_room_id("r004", project_id="planta_74") == "r004"


def test_make_iteration_id_format_and_parse_roundtrip():
    iid = make_iteration_id("planta_74", "r005", 12)
    assert iid == "planta_74.r005.012"
    parsed = parse_iteration_id(iid)
    assert parsed == {"project_id": "planta_74", "room_id": "r005", "seq": 12}


def test_make_iteration_id_rejects_non_canonical_room_id():
    with pytest.raises(ValueError):
        make_iteration_id("planta_74", "kitchen", 0)


def test_make_iteration_id_rejects_negative_seq():
    with pytest.raises(ValueError):
        make_iteration_id("planta_74", "r004", -1)


def test_parse_iteration_id_rejects_malformed():
    with pytest.raises(ValueError):
        parse_iteration_id("not-an-iteration-id")


def test_iteration_ids_sort_lexically_in_seq_order():
    ids = [make_iteration_id("planta_74", "r005", n) for n in (2, 10, 1)]
    assert sorted(ids) == [
        "planta_74.r005.001",
        "planta_74.r005.002",
        "planta_74.r005.010",
    ]


def test_make_trace_id_is_unique_and_hex():
    a, b = make_trace_id(), make_trace_id()
    assert a != b
    assert len(a) == 32
    int(a, 16)  # não levanta ValueError
