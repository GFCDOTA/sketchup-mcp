"""FP-048/T0.4: rigid cross-room frames must not silently mirror anything."""
import math
import pytest
from hypothesis import given, settings, strategies as st

from tools.rooms.shared.geometry_contract import plan_transform, transform_point, transform_direction


def req(source="+Y", target="-Y", angle=0, x=0, y=0, z=0, unit="m"):
    position = lambda n: {"value": n, "unit": unit, "origin": "fixture_synthetic"}
    return {
        "schema_version": "shared_transform.v1", "source_front": source, "target_front": target,
        "pose": {"x": position(x), "y": position(y), "z": position(z),
                 "rotation_deg": {"value": angle, "unit": "deg", "origin": "fixture_synthetic"}},
        "execution_authorized": False,
    }


@pytest.mark.parametrize("angle", [0, 30, 90, 180])
@pytest.mark.parametrize("source,target", [("+Y", "+Y"), ("+Y", "-Y"), ("-Y", "+Y"), ("-Y", "-Y")])
def test_roundtrip_pure_rotation_preserves_length_and_normal(angle, source, target):
    t = plan_transform(req(source, target, angle, 1.5, -0.8, 0.25))
    assert t["state"] == "PLAN_READY_NOT_EXECUTED" and t["determinant"] == 1
    assert t["execution_authorized"] is False
    for point in [(0, 0, 0), (0.63, 0.09, 0.4), (-0.14, 1, 0)]:
        transformed = transform_point(t["matrix"], point)
        restored = transform_point(t["inverse_matrix"], transformed)
        assert restored == pytest.approx(point, abs=1e-11)
    normal = transform_direction(t["matrix"], (0, 1 if source == "+Y" else -1, 0))
    expected_angle = math.radians(angle)
    expected = (-math.sin(expected_angle) * (1 if target == "+Y" else -1),
                math.cos(expected_angle) * (1 if target == "+Y" else -1), 0)
    assert normal == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize("value,unit", [(2, "m"), (200, "cm"), (2000, "mm")])
def test_distance_units_agree(value, unit):
    result = plan_transform(req("+Y", "+Y", 0, value, unit=unit))
    assert transform_point(result["matrix"], (0, 0, 0)) == pytest.approx((2.0, 0.0, 0.0))


def test_flip_front_changes_width_axis_by_rotation_not_reflection():
    plan = plan_transform(req())
    assert plan["determinant"] == 1 and plan["angle_deg"] == 180
    assert transform_direction(plan["matrix"], (0, 1, 0)) == pytest.approx((0, -1, 0))
    assert transform_direction(plan["matrix"], (1, 0, 0)) == pytest.approx((-1, 0, 0))


@pytest.mark.parametrize("patch", [
    lambda r: r.update({"matrix": [[-1, 0, 0], [0, 1, 0], [0, 0, 1]]}),
    lambda r: r.update({"source_front": "+X"}),
    lambda r: r["pose"]["x"].pop("origin"),
    lambda r: r["pose"]["rotation_deg"].update({"unit": "rad"}),
    lambda r: r.update({"execution_authorized": True}),
    lambda r: r["pose"]["x"].update({"unit": "pt"}),
])
def test_invalid_context_cannot_produce_transform(patch):
    data = req()
    patch(data)
    assert plan_transform(data)["state"] == "BLOCKED_TRANSFORM_SCHEMA"


def test_nonfinite_values_are_rejected_before_any_geometry():
    for special in [float("nan"), float("inf"), float("-inf")]:
        data = req(x=special)
        assert plan_transform(data)["state"] == "BLOCKED_TRANSFORM_NONFINITE"


@settings(max_examples=80, deadline=None)
@given(
    x=st.floats(-50, 50, allow_nan=False, allow_infinity=False),
    y=st.floats(-50, 50, allow_nan=False, allow_infinity=False),
    z=st.floats(-50, 50, allow_nan=False, allow_infinity=False),
    angle=st.floats(-360, 360, allow_nan=False, allow_infinity=False),
    px=st.floats(-10, 10, allow_nan=False, allow_infinity=False),
    py=st.floats(-10, 10, allow_nan=False, allow_infinity=False),
)
def test_random_roundtrip_rigid_and_unchanged_height(x, y, z, angle, px, py):
    p = plan_transform(req("+Y", "-Y", angle, x, y, z))
    assert p["state"] == "PLAN_READY_NOT_EXECUTED"
    world = transform_point(p["matrix"], (px, py, 0.7))
    local = transform_point(p["inverse_matrix"], world)
    assert local == pytest.approx((px, py, 0.7), abs=1e-8)
    assert world[2] == pytest.approx(0.7 + z, abs=1e-10)
