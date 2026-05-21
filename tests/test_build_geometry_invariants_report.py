"""Unit tests for `tools.build_geometry_invariants_report`.

The grader is pure (dict in → dict out), so this entire module runs
without launching SketchUp. We feed it synthetic group records that
emulate each failure mode the user listed in the 2026-05-20 review
and assert the verdict + the specific reason string.
"""
from __future__ import annotations

from tools.build_geometry_invariants_report import (
    build_invariants_report,
    classify_semantic_type,
)

# ---- semantic_type classification --------------------------------


def test_classify_wall_shell() -> None:
    assert classify_semantic_type({"name": "PlanShell_Group"}) == "wall_shell"


def test_classify_floor() -> None:
    assert classify_semantic_type({"name": "Floor_Group_r000"}) == "floor"


def test_classify_soft_barrier() -> None:
    assert (
        classify_semantic_type({"name": "SoftBarrier_Group_3"})
        == "soft_barrier"
    )


def test_classify_unknown_falls_through() -> None:
    assert classify_semantic_type({"name": "Random_Group"}) == "unknown"
    assert classify_semantic_type({"name": ""}) == "unknown"
    assert classify_semantic_type({}) == "unknown"


# ---- synthetic group records helpers -----------------------------


def _good_plan_shell() -> dict:
    return {
        "name": "PlanShell_Group",
        "primary_material": "plan_wall",
        "height_m": 2.70,
        "face_count": 100,
        "edge_count": 200,
        "lateral_face_count": 80,
        "default_material_face_count": 0,
        "footprint_top_face_m2": 10.0,
        "footprint_bbox_m2": 100.0,
        "bbox_m": {"min": [0, 0, 0], "max": [10, 10, 2.7]},
    }


def _good_floor(idx: int = 0, area_m2: float = 10.0) -> dict:
    return {
        "name": f"Floor_Group_r{idx:03d}",
        "primary_material": f"floor_r{idx:03d}",
        "height_m": 0.0,
        "face_count": 1,
        "edge_count": 4,
        "lateral_face_count": 0,
        "default_material_face_count": 0,
        "footprint_top_face_m2": area_m2,
        "footprint_bbox_m2": area_m2,
        "bbox_m": {"min": [0, 0, 0], "max": [3, 3, 0]},
    }


def _good_soft_barrier(idx: int = 0) -> dict:
    return {
        "name": f"SoftBarrier_Group_{idx}",
        "primary_material": "plan_parapet",
        "height_m": 1.10,
        "face_count": 6,
        "edge_count": 12,
        "lateral_face_count": 4,
        "default_material_face_count": 0,
        "footprint_top_face_m2": 0.1,
        "footprint_bbox_m2": 1.0,
        "bbox_m": {"min": [0, 0, 0], "max": [3, 0.04, 1.1]},
    }


def _wrap(*records: dict) -> dict:
    return {
        "skp_path": "synthetic",
        "groups_diagnostic": list(records),
    }


# ---- happy path ---------------------------------------------------


def test_pristine_model_is_pass() -> None:
    rep = build_invariants_report(_wrap(
        _good_plan_shell(),
        _good_floor(0, 10.0),
        _good_floor(1, 5.0),
        _good_soft_barrier(0),
    ))
    assert rep["summary"]["verdict"] == "PASS"
    assert rep["summary"]["FAIL"] == 0
    assert rep["summary"]["WARN"] == 0
    assert rep["summary"]["PASS"] == 4


# ---- floor FAIL paths (the regression target) -------------------


def test_floor_with_pushpull_fails() -> None:
    bad = _good_floor()
    bad["height_m"] = 0.5
    bad["bbox_m"] = {"min": [0, 0, 0], "max": [3, 3, 0.5]}
    rep = build_invariants_report(_wrap(_good_plan_shell(), bad))
    bad_record = next(g for g in rep["groups"] if g["name"] == bad["name"])
    assert bad_record["status"] == "FAIL"
    assert any("height" in r and "FLOOR_HEIGHT_EPS" in r
               for r in bad_record["reasons"])


def test_floor_with_lateral_faces_fails() -> None:
    bad = _good_floor()
    bad["lateral_face_count"] = 4  # got pushpulled accidentally
    rep = build_invariants_report(_wrap(_good_plan_shell(), bad))
    bad_record = next(g for g in rep["groups"] if g["name"] == bad["name"])
    assert bad_record["status"] == "FAIL"
    assert any("lateral faces" in r for r in bad_record["reasons"])


def test_floor_with_multiple_faces_fails() -> None:
    bad = _good_floor()
    bad["face_count"] = 6  # tessellated by mistake
    rep = build_invariants_report(_wrap(_good_plan_shell(), bad))
    bad_record = next(g for g in rep["groups"] if g["name"] == bad["name"])
    assert bad_record["status"] == "FAIL"
    assert any("face_count" in r for r in bad_record["reasons"])


def test_floor_painted_with_wall_material_fails() -> None:
    bad = _good_floor()
    bad["primary_material"] = "plan_wall"
    rep = build_invariants_report(_wrap(_good_plan_shell(), bad))
    bad_record = next(g for g in rep["groups"] if g["name"] == bad["name"])
    assert bad_record["status"] == "FAIL"
    assert any("wall/parapet" in r for r in bad_record["reasons"])


# ---- soft_barrier FAIL paths ------------------------------------


def test_soft_barrier_at_wall_height_fails() -> None:
    bad = _good_soft_barrier()
    bad["height_m"] = 2.70  # rendered as full wall
    rep = build_invariants_report(_wrap(_good_plan_shell(), bad))
    bad_record = next(g for g in rep["groups"] if g["name"] == bad["name"])
    assert bad_record["status"] == "FAIL"
    assert any("WALL_HEIGHT_M" in r or "full wall" in r
               for r in bad_record["reasons"])


def test_soft_barrier_at_floor_level_fails_confused_with_floor() -> None:
    bad = _good_soft_barrier()
    bad["height_m"] = 0.0  # the regression target: visually a floor
    rep = build_invariants_report(_wrap(_good_plan_shell(), bad))
    bad_record = next(g for g in rep["groups"] if g["name"] == bad["name"])
    assert bad_record["status"] == "FAIL"
    assert any("floor" in r.lower() for r in bad_record["reasons"])


def test_soft_barrier_with_wrong_material_fails() -> None:
    bad = _good_soft_barrier()
    bad["primary_material"] = "plan_wall"
    rep = build_invariants_report(_wrap(_good_plan_shell(), bad))
    bad_record = next(g for g in rep["groups"] if g["name"] == bad["name"])
    assert bad_record["status"] == "FAIL"
    assert any("parapet" in r for r in bad_record["reasons"])


# ---- soft_barrier WARN path (the 2026-05-20 bbox-as-slab bug) ----


def test_soft_barrier_oversized_footprint_warns_not_fails() -> None:
    """The bbox-as-slab class of bug. Heuristic ceiling = 30% of
    smallest floor. WARN, not FAIL — see ADR-004 §5."""
    bad = _good_soft_barrier()
    # smallest floor will be 5 m² in this fixture; 30% = 1.5 m²; bad = 5 m²
    bad["footprint_top_face_m2"] = 5.0
    rep = build_invariants_report(_wrap(
        _good_plan_shell(),
        _good_floor(0, 10.0),
        _good_floor(1, 5.0),
        bad,
    ))
    bad_record = next(g for g in rep["groups"] if g["name"] == bad["name"])
    assert bad_record["status"] == "WARN", bad_record
    assert any("heuristic ceiling" in r for r in bad_record["reasons"])
    # Overall verdict picks the worst — WARN here.
    assert rep["summary"]["verdict"] == "WARN"


def test_soft_barrier_within_ceiling_is_pass() -> None:
    good = _good_soft_barrier()
    good["footprint_top_face_m2"] = 0.3  # well below 30% of 5 m² = 1.5
    rep = build_invariants_report(_wrap(
        _good_plan_shell(),
        _good_floor(0, 10.0),
        _good_floor(1, 5.0),
        good,
    ))
    rec = next(g for g in rep["groups"] if g["name"] == good["name"])
    assert rec["status"] == "PASS"


# ---- wall_shell FAIL paths ---------------------------------------


def test_plan_shell_wrong_height_fails() -> None:
    bad = _good_plan_shell()
    bad["height_m"] = 5.0  # somebody changed WALL_HEIGHT_M
    rep = build_invariants_report(_wrap(bad))
    rec = next(g for g in rep["groups"] if g["name"] == bad["name"])
    assert rec["status"] == "FAIL"
    assert any("WALL_HEIGHT_M" in r for r in rec["reasons"])


def test_plan_shell_no_lateral_faces_fails() -> None:
    bad = _good_plan_shell()
    bad["lateral_face_count"] = 0
    rep = build_invariants_report(_wrap(bad))
    rec = next(g for g in rep["groups"] if g["name"] == bad["name"])
    assert rec["status"] == "FAIL"
    assert any("lateral" in r for r in rec["reasons"])


def test_plan_shell_default_material_faces_fail() -> None:
    bad = _good_plan_shell()
    bad["default_material_face_count"] = 3
    rep = build_invariants_report(_wrap(bad))
    rec = next(g for g in rep["groups"] if g["name"] == bad["name"])
    assert rec["status"] == "FAIL"
    assert any("missing material" in r for r in rec["reasons"])


# ---- unknown groups always FAIL ----------------------------------


def test_unknown_top_level_group_fails() -> None:
    weird = {"name": "Weird_Group_42", "primary_material": "x",
             "height_m": 1.0, "face_count": 1, "edge_count": 4,
             "lateral_face_count": 0, "default_material_face_count": 0,
             "footprint_top_face_m2": 0, "footprint_bbox_m2": 0,
             "bbox_m": {"min": [0, 0, 0], "max": [1, 1, 1]}}
    rep = build_invariants_report(_wrap(_good_plan_shell(), weird))
    rec = next(g for g in rep["groups"] if g["name"] == "Weird_Group_42")
    assert rec["semantic_type"] == "unknown"
    assert rec["status"] == "FAIL"


def test_empty_group_name_classifies_as_unknown_and_fails() -> None:
    nameless = {"name": "", "primary_material": None, "height_m": 0,
                "face_count": 0, "edge_count": 0, "lateral_face_count": 0,
                "default_material_face_count": 0,
                "footprint_top_face_m2": 0, "footprint_bbox_m2": 0,
                "bbox_m": {"min": [0, 0, 0], "max": [0, 0, 0]}}
    rep = build_invariants_report(_wrap(_good_plan_shell(), nameless))
    rec = next(g for g in rep["groups"] if g["name"] == "")
    assert rec["semantic_type"] == "unknown"
    assert rec["status"] == "FAIL"


# ---- verdict aggregation -----------------------------------------


def test_verdict_is_worst_status_across_groups() -> None:
    rep = build_invariants_report(_wrap(
        _good_plan_shell(),
        _good_floor(0, 10.0),
        # one bad floor → overall FAIL
        {**_good_floor(1), "height_m": 0.5},
    ))
    assert rep["summary"]["verdict"] == "FAIL"


def test_verdict_pass_only_when_all_pass() -> None:
    rep = build_invariants_report(_wrap(
        _good_plan_shell(),
        _good_floor(0, 10.0),
        _good_soft_barrier(0),
    ))
    assert rep["summary"]["verdict"] == "PASS"


# ---- structural metadata -----------------------------------------


def test_report_has_rules_applied_block() -> None:
    rep = build_invariants_report(_wrap(_good_plan_shell()))
    assert "rules_applied_by_type" in rep
    assert "wall_shell" in rep["rules_applied_by_type"]
    assert "floor" in rep["rules_applied_by_type"]
    assert "soft_barrier" in rep["rules_applied_by_type"]


def test_report_schema_version_is_pinned() -> None:
    rep = build_invariants_report(_wrap(_good_plan_shell()))
    assert rep["schema_version"] == "1.0.0"
