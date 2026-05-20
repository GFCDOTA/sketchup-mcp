"""Geometric invariants on the .skp produced by build_plan_shell_skp.

These tests load `geometry_report.json` (one was generated for
planta_74 in `runs/planta_74_plan_shell/` by an earlier session) and
verify the per-group invariants the user listed:

  • Floor_Group_*  : MUST be planar at z=0, no lateral faces, no
                      pushpull, room-polygon-sized footprint, floor
                      material.
  • PlanShell_Group: full height (2.70 m), wall material, single
                      top-level wall group.
  • SoftBarrier_*  : parapet height (1.10 m), parapet material, NOT
                      huge slabs covering room interiors (footprint
                      should be on the order of a wall-thickness
                      strip times the polyline length, not tens of m²).

The "soft_barrier as huge slab" bug discovered on 2026-05-20 — where
each polyline turned into a slab spanning its full XY bbox, producing
up to 80 m² peitoris where the production exporter renders thin
3.8 cm × len slabs — has a dedicated regression test that asserts
EVERY SoftBarrier_Group's footprint stays below an architectural
ceiling.

The tests are written so that they FAIL on the buggy report and
PASS after the soft_barrier fix lands. Each test is independent and
runs against `runs/planta_74_plan_shell/geometry_report.json`. If
the report is missing the test skips with a clear xfail message
(can't pre-stage a smoke run in CI).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT = REPO_ROOT / "runs" / "planta_74_plan_shell" / "geometry_report.json"

# Architectural ceilings — what we'd accept as plausible.
FLOOR_HEIGHT_EPS = 0.001          # 1 mm tolerance on "flat"
WALL_HEIGHT_M = 2.70
PARAPET_HEIGHT_M = 1.10
HEIGHT_TOL_M = 0.01               # 1 cm tolerance on exact heights
# A real peitoril/esquadria is at most a few cm thick × a few metres
# long, so ~0.3 m² is already generous. Cap at 1.0 m² for the test;
# anything bigger is the bbox bug, period.
MAX_SOFT_BARRIER_FOOTPRINT_M2 = 1.0


def _load_report() -> dict[str, Any]:
    if not REPORT.exists():
        pytest.skip(
            f"geometry_report not found at {REPORT}; "
            "run `python -m tools.build_plan_shell_skp <consensus> --out "
            "<skp>` to generate it"
        )
    return json.loads(REPORT.read_text(encoding="utf-8"))


def _groups_by_prefix(report: dict, prefix: str) -> list[dict]:
    return [g for g in report["groups_diagnostic"]
            if g["name"].startswith(prefix)]


def _plan_shell(report: dict) -> dict | None:
    for g in report["groups_diagnostic"]:
        if g["name"] == "PlanShell_Group":
            return g
    return None


# ---- floor invariants -------------------------------------------


def test_floor_groups_exist() -> None:
    r = _load_report()
    floors = _groups_by_prefix(r, "Floor_Group_")
    assert floors, "no Floor_Group_* found in report"


def test_every_floor_is_planar_at_zero() -> None:
    """Each floor's bbox MUST be flat at z=0 (height ≤ 1 mm)."""
    r = _load_report()
    floors = _groups_by_prefix(r, "Floor_Group_")
    offenders = [
        f["name"] for f in floors
        if abs(f["bbox_m"]["min"][2]) > FLOOR_HEIGHT_EPS
        or abs(f["bbox_m"]["max"][2]) > FLOOR_HEIGHT_EPS
        or f["height_m"] > FLOOR_HEIGHT_EPS
    ]
    assert not offenders, (
        f"floors with non-zero height: {offenders} "
        "(floors must be a single flat face at z=0; never pushpulled)"
    )


def test_no_floor_has_lateral_faces() -> None:
    """A pure floor has zero faces with horizontal normal. Any side
    face means somebody pushpulled the floor — bug."""
    r = _load_report()
    floors = _groups_by_prefix(r, "Floor_Group_")
    offenders = [(f["name"], f["lateral_face_count"]) for f in floors
                 if f["lateral_face_count"] > 0]
    assert not offenders, (
        f"floors with lateral faces (pushpull leak): {offenders}"
    )


def test_every_floor_has_exactly_one_face() -> None:
    """The whole point of Floor_Group is one planar face — no pushpull,
    no triangulation, no extras."""
    r = _load_report()
    floors = _groups_by_prefix(r, "Floor_Group_")
    offenders = [(f["name"], f["face_count"]) for f in floors
                 if f["face_count"] != 1]
    assert not offenders, (
        f"floors with face_count != 1: {offenders} "
        "(expected 1 planar face per room polygon)"
    )


def test_floors_use_floor_material_not_wall() -> None:
    r = _load_report()
    floors = _groups_by_prefix(r, "Floor_Group_")
    wall_material_names = {"plan_wall", "wall_dark", "wall_ring"}
    offenders = [(f["name"], f["primary_material"]) for f in floors
                 if f["primary_material"] in wall_material_names]
    assert not offenders, (
        f"floors painted with wall material: {offenders} "
        "(must use a floor_* material per ROOM_PALETTE)"
    )


def test_no_floor_has_default_material_faces() -> None:
    """`default_material_face_count == 0` per group."""
    r = _load_report()
    floors = _groups_by_prefix(r, "Floor_Group_")
    offenders = [(f["name"], f["default_material_face_count"]) for f in floors
                 if f["default_material_face_count"] > 0]
    assert not offenders, f"floors with default-material faces: {offenders}"


# ---- wall shell invariants --------------------------------------


def test_plan_shell_group_exists_and_is_single() -> None:
    r = _load_report()
    walls = [g for g in r["groups_diagnostic"]
             if g["name"] == "PlanShell_Group"]
    assert len(walls) == 1, f"expected exactly one PlanShell_Group, got {len(walls)}"


def test_plan_shell_height_matches_wall_height() -> None:
    r = _load_report()
    s = _plan_shell(r)
    assert s is not None
    assert math.isclose(s["height_m"], WALL_HEIGHT_M, abs_tol=HEIGHT_TOL_M), (
        f"PlanShell height {s['height_m']} != {WALL_HEIGHT_M} ± {HEIGHT_TOL_M}"
    )


def test_plan_shell_has_lateral_faces() -> None:
    """The wall shell is mostly vertical surfaces. If lateral_face_count == 0,
    we're emitting a flat floor by mistake."""
    r = _load_report()
    s = _plan_shell(r)
    assert s is not None
    assert s["lateral_face_count"] > 0, (
        "PlanShell has no lateral faces — looks like a flat floor, not a "
        "wall shell"
    )


def test_plan_shell_uses_wall_material() -> None:
    r = _load_report()
    s = _plan_shell(r)
    assert s is not None
    assert s["primary_material"] in {"plan_wall", "wall_dark", "wall_ring"}, (
        f"PlanShell primary_material={s['primary_material']!r}; "
        "expected a wall material"
    )


# ---- soft barrier invariants ------------------------------------


def test_soft_barriers_height_is_parapet_not_wall() -> None:
    """Soft barriers must read as PARAPET height, NEVER full wall."""
    r = _load_report()
    barriers = _groups_by_prefix(r, "SoftBarrier_Group_")
    for b in barriers:
        assert b["height_m"] != pytest.approx(WALL_HEIGHT_M, abs=HEIGHT_TOL_M), (
            f"SoftBarrier {b['name']} height={b['height_m']}m — must NOT be "
            f"full wall height; expected ~{PARAPET_HEIGHT_M}m"
        )
        assert math.isclose(
            b["height_m"], PARAPET_HEIGHT_M, abs_tol=HEIGHT_TOL_M,
        ), (
            f"SoftBarrier {b['name']} height={b['height_m']}m != "
            f"{PARAPET_HEIGHT_M} ± {HEIGHT_TOL_M}"
        )


def test_soft_barriers_use_parapet_material() -> None:
    r = _load_report()
    barriers = _groups_by_prefix(r, "SoftBarrier_Group_")
    offenders = [
        (b["name"], b["primary_material"]) for b in barriers
        if b["primary_material"] not in {"plan_parapet", "parapet"}
    ]
    assert not offenders, (
        f"SoftBarriers with non-parapet material: {offenders}"
    )


def test_soft_barriers_footprint_below_architectural_ceiling() -> None:
    """REGRESSION: peitorils/esquadrias are thin slabs (few cm thick
    × few metres long). The "soft_barrier-bbox-as-slab" bug
    (2026-05-20) produced peitorils with REAL footprints of 30-80 m²,
    which is bigger than the rooms they cover.

    The metric to enforce is the SUM of TOP face areas
    (`footprint_top_face_m2`), not the group's bbox area
    (`footprint_bbox_m2`) — once the fix lands, a single SoftBarrier
    can have many sub-segment slabs spread along an L-shape polyline,
    so its bbox-rectangle is large but the material it actually
    covers is tiny. The top-face-sum is the architecturally correct
    figure: it equals (sum of segment lengths) × (slab thickness).

    Before fix: top face area = bbox area = 30-80 m² ← bug.
    After fix:  top face area ≈ Σ segment lengths × 0.038 m ≪ 1 m²
                (room-sized bbox is fine because slabs are sparse
                inside that bbox).

    This test FAILS on the buggy report and PASSES after the
    per-segment swept slab fix lands.
    """
    r = _load_report()
    barriers = _groups_by_prefix(r, "SoftBarrier_Group_")
    offenders = []
    for b in barriers:
        # Prefer the real metric; fall back to bbox on older reports
        # that didn't capture top_face_area yet.
        real_m2 = b.get("footprint_top_face_m2")
        if real_m2 is None:
            real_m2 = b.get("footprint_m2", b.get("footprint_bbox_m2", 0))
        if real_m2 > MAX_SOFT_BARRIER_FOOTPRINT_M2:
            offenders.append((b["name"], real_m2))
    assert not offenders, (
        f"SoftBarrier top-face footprints exceed "
        f"{MAX_SOFT_BARRIER_FOOTPRINT_M2} m² (bbox-as-slab bug): "
        f"{offenders}"
    )


# ---- totals + cross-checks --------------------------------------


def test_total_top_level_groups_matches_components() -> None:
    """Plan shell + floors + soft barriers — no orphan groups."""
    r = _load_report()
    total = r["totals"]["top_level_groups"]
    shell = 1 if _plan_shell(r) else 0
    floors = len(_groups_by_prefix(r, "Floor_Group_"))
    barriers = len(_groups_by_prefix(r, "SoftBarrier_Group_"))
    accounted = shell + floors + barriers
    assert total == accounted, (
        f"total_top_level_groups={total} but accounted for "
        f"{accounted} (shell={shell}, floors={floors}, "
        f"barriers={barriers}) — investigate orphan groups"
    )


def test_no_group_has_empty_name() -> None:
    r = _load_report()
    offenders = [g for g in r["groups_diagnostic"] if not g["name"]]
    assert not offenders, f"groups with empty name: {offenders}"


def test_gates_self_check_all_true() -> None:
    """The Ruby exporter writes a `gates_self_check` block that mirrors
    the bare-minimum invariants. All of them MUST be true."""
    r = _load_report()
    g = r["gates_self_check"]
    failures = [k for k, v in g.items() if not v]
    assert not failures, f"gates_self_check failures: {failures}"
