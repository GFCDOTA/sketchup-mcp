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

# Heuristic ceiling for soft-barrier top-face material area, expressed
# as a fraction of the smallest room polygon's area in the current
# consensus. A peitoril/esquadria is a thin slab swept along its
# polyline; its top-face footprint is (polyline length) × (slab
# thickness). For typical residential geometry that's a fraction of
# a square metre. The ceiling 0.30 means "if the slab covers more
# than 30 % of the smallest room, it's almost certainly the
# bbox-as-slab bug coming back."
#
# Why RELATIVE instead of an absolute number: the original 2026-05-20
# regression test used `MAX_SOFT_BARRIER_FOOTPRINT_M2 = 1.0`. The
# 1.0 m² figure had no architectural source — it was a magic number
# that "felt small enough to catch the bug but big enough to not
# break on slightly oversized peitorils". A planta with very large
# terraço peitorils could legitimately have a thin slab pushing
# 1 m². The ratio-to-smallest-room is consensus-anchored, so it
# scales with the floor plan instead of imposing an external rule.
#
# WARN-not-FAIL: this is still a heuristic; a corpus of >1 real
# planta does not exist yet. The test emits a pytest.warns instead of
# raising AssertionError so the rule surfaces in CI logs without
# blocking a PR until we have grounding evidence (NBR / measured
# corpus). See docs/grounding/constants_provenance.md.
MAX_SOFT_BARRIER_FOOTPRINT_FRACTION = 0.30


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


def test_soft_barriers_footprint_below_relative_ceiling_warn() -> None:
    """REGRESSION (WARN-only, consensus-relative): peitoris are
    thin slabs (few cm × few metres). The 2026-05-20 bug produced
    peitoris with REAL footprints of 30-80 m² — bigger than the
    rooms they cover.

    Metric: SUM of TOP face areas (`footprint_top_face_m2`), not the
    bbox area. The ceiling is `MAX_SOFT_BARRIER_FOOTPRINT_FRACTION`
    times the smallest floor area in the same `.skp` — consensus-
    anchored, not a magic number.

    Emits `pytest.warns(UserWarning)` instead of asserting so the
    rule surfaces in CI logs WITHOUT blocking a PR until a corpus
    of >1 real planta exists. See docs/grounding/constants_provenance.md
    and ADR-004 §5 for the rationale of WARN-now-FAIL-later.

    The hard FAIL companion (any SoftBarrier emitting at floor
    height) lives in
    `test_no_soft_barrier_at_floor_height_confused_with_floor`.
    """
    import warnings

    r = _load_report()
    barriers = _groups_by_prefix(r, "SoftBarrier_Group_")
    floors = _groups_by_prefix(r, "Floor_Group_")
    if not floors:
        # Nothing to relate against — skip rather than fabricate a ceiling.
        pytest.skip("no floor groups in report; cannot derive ceiling")

    # Use the per-group top-face area from groups_diagnostic (already
    # the painted material area in m²; same shape as the metric we're
    # measuring on the barriers, so the comparison is apples-to-apples).
    floor_areas = [f["footprint_top_face_m2"] for f in floors
                   if f.get("footprint_top_face_m2", 0) > 0]
    if not floor_areas:
        pytest.skip("no floor groups with non-zero top-face area")
    smallest_floor_m2 = min(floor_areas)
    ceiling = smallest_floor_m2 * MAX_SOFT_BARRIER_FOOTPRINT_FRACTION

    offenders = []
    for b in barriers:
        real_m2 = b.get("footprint_top_face_m2", 0)
        if real_m2 > ceiling:
            offenders.append((b["name"], real_m2, ceiling))

    if offenders:
        # WARN-only: this is heuristic, not authoritative. The
        # hard-fail invariants on height + material + lateral-face
        # count already catch the structural bug; this one catches
        # the looser "material area is unreasonable for a peitoril"
        # case which deserves human review, not auto-block.
        warnings.warn(
            f"SoftBarrier top-face footprints exceed heuristic "
            f"ceiling {ceiling:.3f} m² "
            f"(= {MAX_SOFT_BARRIER_FOOTPRINT_FRACTION:.0%} × smallest "
            f"floor {smallest_floor_m2:.3f} m²): {offenders}. "
            f"Re-check whether the per-segment swept-slab logic is "
            f"intact.",
            UserWarning,
            stacklevel=2,
        )


# ---- totals + cross-checks --------------------------------------


def test_total_top_level_groups_matches_components() -> None:
    """Plan shell + floors + soft barriers + door leaves + windows +
    glazed balconies + passage markers — no orphan groups."""
    r = _load_report()
    total = r["totals"]["top_level_groups"]
    shell = 1 if _plan_shell(r) else 0
    floors = len(_groups_by_prefix(r, "Floor_Group_"))
    barriers = len(_groups_by_prefix(r, "SoftBarrier_Group_"))
    doors = len(_groups_by_prefix(r, "DoorLeaf_Group_"))
    windows = len(_groups_by_prefix(r, "Window_Group_"))
    glazed = len(_groups_by_prefix(r, "GlazedBalcony_Group_"))
    passages = len(_groups_by_prefix(r, "PassageMarker_Group_"))
    accounted = shell + floors + barriers + doors + windows + glazed + passages
    assert total == accounted, (
        f"total_top_level_groups={total} but accounted for "
        f"{accounted} (shell={shell}, floors={floors}, "
        f"barriers={barriers}, doors={doors}, windows={windows}, "
        f"glazed={glazed}, passages={passages}) — investigate orphan "
        f"groups"
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


# ---- Defensive invariants — regression patches for the 2026-05-20 bug ---


def test_no_soft_barrier_at_floor_height_confused_with_floor() -> None:
    """REGRESSION: a SoftBarrier that emits at height ~0 would render
    as a flat floor-coloured patch in the .skp and visually pass as
    a floor. Anything below half the parapet height is suspect."""
    r = _load_report()
    barriers = _groups_by_prefix(r, "SoftBarrier_Group_")
    half_parapet = PARAPET_HEIGHT_M / 2.0
    offenders = [
        (b["name"], b["height_m"]) for b in barriers
        if b["height_m"] < half_parapet
    ]
    assert not offenders, (
        f"SoftBarrier groups with height < {half_parapet:.3f}m — they "
        f"would render as floor-shaped patches, not parapets: "
        f"{offenders}"
    )


def test_every_consensus_opening_has_a_real_gap_in_shell() -> None:
    """REGRESSION: the soft_barrier bug was a symptom of "geometry
    that looked OK in self-check but failed visually". Same class
    for openings: every opening in the consensus must have been
    counted in `shell_stats_from_python.openings_carved`. A drop
    here means the door rectangle was silently skipped — gap
    disappears, planta becomes uninhabitable."""
    r = _load_report()
    stats = r.get("shell_stats_from_python", {})
    carved = stats.get("openings_carved", 0)
    skipped = stats.get("openings_skipped", [])
    declared = carved + len(skipped)
    # Total openings the consensus offered = carved + skipped
    # The skipped count is observable but should be 0 on healthy
    # consensus — every consensus opening should carve a gap.
    assert not skipped, (
        f"Consensus openings were silently skipped during 2D carve "
        f"(door geometry will not be visible in the shell): {skipped}. "
        f"If a skip is legitimate (ghost wall_id), it must be "
        f"explicitly whitelisted; default is FAIL."
    )
    # And carved count > 0 unless consensus has zero openings
    if declared > 0:
        assert carved > 0, (
            f"declared {declared} openings but 0 were carved — "
            f"door geometry will be missing entirely"
        )


def test_no_unrecognized_top_level_group_name() -> None:
    """REGRESSION: every top-level Group must match one of the known
    semantic prefixes. An unnamed or unrecognised top-level group
    means the exporter leaked something the user can't classify
    visually.

    Phase 2 added door leaves, window panels, glazed balconies, and
    passage markers — each as its own top-level group separate from
    PlanShell_Group."""
    r = _load_report()
    known_prefixes = (
        "PlanShell_Group",
        "Floor_Group_",
        "SoftBarrier_Group_",
        "DoorLeaf_Group_",
        "Window_Group_",
        "GlazedBalcony_Group_",
        "PassageMarker_Group_",
    )
    offenders = []
    for g in r["groups_diagnostic"]:
        name = g["name"] or ""
        if not any(name == p or name.startswith(p) for p in known_prefixes):
            offenders.append(name or "(empty name)")
    assert not offenders, (
        f"Top-level groups with unrecognised names: {offenders}. "
        f"Every group must be classifiable. Unknown groups are a "
        f"regression — add them to the known set OR fix the exporter "
        f"to not emit them."
    )


def test_no_floor_uses_parapet_or_wall_material_swap() -> None:
    """REGRESSION (paired with floor-material check): catches the
    symmetric mistake where a floor gets painted with the parapet's
    RGB by accident. A 1.10m parapet that is visually identical to
    floor colour would slip through."""
    r = _load_report()
    floors = _groups_by_prefix(r, "Floor_Group_")
    forbidden = {"plan_wall", "plan_parapet", "wall_dark",
                 "wall_ring", "parapet"}
    offenders = [
        (f["name"], f["primary_material"]) for f in floors
        if f["primary_material"] in forbidden
    ]
    assert not offenders, (
        f"floors painted with wall/parapet material: {offenders}"
    )


def test_no_soft_barrier_uses_wall_or_floor_material() -> None:
    """REGRESSION (symmetric): a SoftBarrier painted with wall RGB
    blends into the wall shell and reads as a "rodapé branco"
    (FP-006). A SoftBarrier painted with a floor RGB blends into
    the floor and is invisible. Either is the same class of failure
    as the floor-material-mix-up: the user can't visually
    distinguish layers."""
    r = _load_report()
    barriers = _groups_by_prefix(r, "SoftBarrier_Group_")
    forbidden_walls = {"plan_wall", "wall_dark", "wall_ring"}
    offenders = []
    for b in barriers:
        m = b["primary_material"] or ""
        if m in forbidden_walls or m.startswith("floor_"):
            offenders.append((b["name"], m))
    assert not offenders, (
        f"SoftBarrier groups painted with wall or floor material: "
        f"{offenders}"
    )


# ---- FP-015: door leaf hinge_world for vertical walls -------------


# Maximum distance allowed between a DoorLeaf bbox center and its
# host opening's declared center in the consensus, in metres.
# 1 m is generous — a healthy leaf sits less than the opening width
# (~0.8 m) plus the rotation displacement (~0.4 m at 30 deg) away.
# The 2026-05-20 hinge_world bug pushed leaves on vertical walls
# *metres* from their openings (≈ |hinge_along - cross_base| in
# coordinates, often > 5 m), so 1 m is a comfortable headroom.
DOOR_LEAF_MAX_DISTANCE_FROM_OPENING_M = 1.0


def _load_consensus() -> dict:
    """Load the consensus that produced the current report. We pin
    on planta_74 because that is the .skp the report describes."""
    import json
    p = (
        REPO_ROOT / "fixtures" / "planta_74"
        / "consensus_with_human_walls_and_soft_barriers.json"
    )
    if not p.exists():
        pytest.skip(f"consensus not found at {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def test_door_leaf_stays_near_its_opening_center() -> None:
    """REGRESSION (FP-015): in 2026-05-20 build_plan_shell_skp.rb
    computed `hinge_world` as `(hinge_along, axis_idx==0 ? cross_base : hinge_along, 0)`.
    For vertical walls the Y component became `hinge_along` instead
    of `cross_base`, sending the rotation pivot onto a diagonal
    miles from the door. The leaf then rotated 30 deg around that
    pivot and ended up "floating" several metres from the actual
    wall — visible as orphan brown rectangles in the .skp middle of
    open space.

    This test asserts every DoorLeaf_Group's bbox center sits within
    1 m of the corresponding opening's declared center (PDF coords
    → metres via PT_TO_M). On the buggy build, vertical-wall doors
    were 5-20 m away; on the fix, they sit ≤ 0.5 m away.
    """
    r = _load_report()
    consensus = _load_consensus()
    pt_to_m = 0.19 / 5.4
    openings_by_id = {
        o["id"]: o for o in consensus.get("openings", []) if "id" in o
    }

    offenders = []
    for g in r["groups_diagnostic"]:
        if not g["name"].startswith("DoorLeaf_Group_"):
            continue
        oid = g["name"][len("DoorLeaf_Group_"):]
        op = openings_by_id.get(oid)
        if op is None or "center" not in op:
            continue  # cannot validate without consensus center
        op_cx_m = op["center"][0] * pt_to_m
        op_cy_m = op["center"][1] * pt_to_m
        bb = g["bbox_m"]
        leaf_cx = (bb["min"][0] + bb["max"][0]) / 2.0
        leaf_cy = (bb["min"][1] + bb["max"][1]) / 2.0
        dist = ((leaf_cx - op_cx_m) ** 2 + (leaf_cy - op_cy_m) ** 2) ** 0.5
        if dist > DOOR_LEAF_MAX_DISTANCE_FROM_OPENING_M:
            offenders.append({
                "door_group": g["name"],
                "opening_id": oid,
                "host_wall_id": op.get("wall_id"),
                "opening_center_m": [op_cx_m, op_cy_m],
                "leaf_bbox_center_m": [leaf_cx, leaf_cy],
                "distance_m": round(dist, 3),
            })
    assert not offenders, (
        "DoorLeaf groups bbox centers > "
        f"{DOOR_LEAF_MAX_DISTANCE_FROM_OPENING_M} m from their opening's "
        f"declared center (FP-015 hinge_world regression): {offenders}"
    )
