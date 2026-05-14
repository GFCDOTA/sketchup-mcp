"""Visual Fidelity Gate — reader scaffolding for the Visual Fidelity
Gate Protocol (2026-05-14).

This is **PR B2**. The full flow:

  PR B1  produce the 7 evidence artifacts        (tools/produce_visual_evidence.py)
  PR B2  read those artifacts + emit gate_report (this module)              ← here
  PR B3  add 8 algorithmic checks                (replaces not_yet_checked)
  PR B4  hook into verify_fidelities.py          (definitive top-level wire)

PR B2 ships the **scaffolding**: load each of the 7 artifacts,
validate presence + non-emptiness, emit a structured
``gate_report.json`` whose ``checks`` array has one entry per failure
condition. Every check starts in ``not_yet_checked`` state. PR B3
overwrites those statuses with ``pass`` / ``warn`` / ``fail``.

Top-level verdict (B2 only):
  * any artifact missing/empty           → ``FAIL`` (with policy_violation)
  * artifacts present + 0 FAIL checks    → ``WARN`` (advisory: checks
                                            pending B3 implementation)
  * any FAIL check                       → ``FAIL``
  * all checks PASS                      → ``PASS`` (only reachable once
                                            B3 lands)

The eight checks come from the protocol:

  1. door_without_opening
  2. door_crossing_or_displaced
  3. door_swing_diverges
  4. room_polygon_not_closed
  5. room_polygon_bleeds_outside
  6. invented_or_wrong_height_exterior
  7. wet_or_terrace_adjacency_wrong
  8. room_rendered_as_bbox

CLI::

    python -m tools.visual_fidelity_gate \\
        --evidence-dir fixtures/planta_74/visual_evidence \\
        --consensus fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \\
        --pdf planta_74.pdf \\
        --out fixtures/planta_74/visual_fidelity_gate_report.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Mirror the protocol's canonical artifact list (also used by
# ``tools/verify_fidelities.py`` and ``tools/produce_visual_evidence.py``).
REQUIRED_VISUAL_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("original_floorplan", "original_floorplan.png"),
    ("skp_render", "skp_render.png"),
    ("overlay_pdf_skp", "overlay_pdf_skp.png"),
    ("diff_walls", "diff_walls.png"),
    ("diff_doors", "diff_doors.png"),
    ("diff_rooms", "diff_rooms.png"),
    ("mismatches_list", "mismatches_list.md"),
)

# Eight failure conditions from the protocol. ``description`` is the
# operator-facing English. ``severity_on_fail`` is the level the
# check emits when it trips — uniform ``FAIL`` for PR B2 because PR
# B3 is the first cycle where checks actually run; if the protocol
# later needs WARN-level checks (advisory) the column can split.
EIGHT_CHECKS: tuple[dict, ...] = (
    {
        "key": "door_without_opening",
        "description":
            "Door drawn without a real opening in its host wall.",
        "severity_on_fail": "FAIL",
    },
    {
        "key": "door_crossing_or_displaced",
        "description":
            "Door crossing the wall (no carve) or displaced from "
            "the gap.",
        "severity_on_fail": "FAIL",
    },
    {
        "key": "door_swing_diverges",
        "description":
            "Door swing / orientation diverges from the PDF arc.",
        "severity_on_fail": "FAIL",
    },
    {
        "key": "room_polygon_not_closed",
        "description": "Room with a non-closed polygon.",
        "severity_on_fail": "FAIL",
    },
    {
        "key": "room_polygon_bleeds_outside",
        "description":
            "Room polygon bleeding outside the building outline.",
        "severity_on_fail": "FAIL",
    },
    {
        "key": "invented_or_wrong_height_exterior",
        "description":
            "Exterior wall / esquadria / peitoril invented or with "
            "the wrong height.",
        "severity_on_fail": "FAIL",
    },
    {
        "key": "wet_or_terrace_adjacency_wrong",
        "description":
            "Bathroom / lavabo / A.S. / terraço with wrong adjacency.",
        "severity_on_fail": "FAIL",
    },
    {
        "key": "room_rendered_as_bbox",
        "description":
            "Room rendered as a bounding box / block instead of real "
            "geometry.",
        "severity_on_fail": "FAIL",
    },
)

GATE_REPORT_SCHEMA_VERSION = "visual_fidelity_gate_v1"

VISUAL_FIDELITY_POLICY_VIOLATION_TAG = (
    "2026-05-14_visual_fidelity_gate_required"
)


# ---------------------------------------------------------------------------
# Artifact loading
# ---------------------------------------------------------------------------

def _inspect_artifact(evidence_dir: Path, key: str,
                       fname: str) -> dict[str, Any]:
    """Return a status dict for one artifact."""
    path = evidence_dir / fname
    try:
        exists = path.exists()
        size = path.stat().st_size if exists else 0
    except OSError:
        exists = False
        size = 0
    if exists and size > 0:
        status = "present"
    elif exists:
        status = "empty"
    else:
        status = "missing"
    return {
        "key": key,
        "filename": fname,
        "expected_path": str(path),
        "exists": exists,
        "size_bytes": size,
        "status": status,
    }


def load_artifacts(evidence_dir: Path) -> dict[str, Any]:
    """Inspect each of the seven required artifacts under
    ``evidence_dir``.

    Returns::

        {
          "directory": <str>,
          "per_artifact": [{key, filename, expected_path, exists,
                             size_bytes, status}, ...],
          "present_keys":   [...],
          "missing_keys":   [...],
          "empty_keys":     [...],
          "overall_status": "present" | "incomplete" | "missing",
        }

    ``overall_status`` is ``present`` only when ALL seven artifacts
    are ``present`` (>0 bytes). Anything else is ``incomplete`` or
    ``missing`` (when *no* artifact is present).
    """
    per_artifact = [
        _inspect_artifact(evidence_dir, k, f)
        for k, f in REQUIRED_VISUAL_ARTIFACTS
    ]
    present = [a["key"] for a in per_artifact if a["status"] == "present"]
    empty = [a["key"] for a in per_artifact if a["status"] == "empty"]
    missing = [a["key"] for a in per_artifact if a["status"] == "missing"]
    if not present and not empty:
        overall = "missing"
    elif missing or empty:
        overall = "incomplete"
    else:
        overall = "present"
    return {
        "directory": str(evidence_dir),
        "per_artifact": per_artifact,
        "present_keys": present,
        "missing_keys": missing,
        "empty_keys": empty,
        "overall_status": overall,
    }


# ---------------------------------------------------------------------------
# Per-check scaffolding
# ---------------------------------------------------------------------------

def _scaffold_check(check_def: dict) -> dict[str, Any]:
    """Build the default 'not_yet_checked' entry for one check.

    Used when ``consensus`` is unavailable (the caller has no source
    consensus to interrogate). When ``consensus`` IS supplied, the
    real check function for each key is invoked instead — see
    ``CHECK_RUNNERS`` and ``run_check``.
    """
    return {
        "key": check_def["key"],
        "description": check_def["description"],
        "severity_on_fail": check_def["severity_on_fail"],
        "status": "not_yet_checked",
        "verdict": "WARN",  # advisory when consensus unavailable
        "failing_elements": [],
        "notes": (
            "Consensus not supplied; check skipped. Pass --consensus "
            "(CLI) or `consensus_path` (`run_gate`) to enable the "
            "algorithmic check."
        ),
    }


def _make_check_result(check_def: dict, verdict: str,
                         failing_elements: list[dict],
                         notes: str) -> dict[str, Any]:
    """Build the algorithmic-check result record."""
    return {
        "key": check_def["key"],
        "description": check_def["description"],
        "severity_on_fail": check_def["severity_on_fail"],
        "status": "checked",
        "verdict": verdict,
        "failing_elements": failing_elements,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Geometry helpers (no shapely dep — keep gate import-light)
# ---------------------------------------------------------------------------

def _polygon_area_signed(pts: list[list[float]]) -> float:
    n = len(pts)
    if n < 3:
        return 0.0
    acc = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        acc += x0 * y1 - x1 * y0
    return 0.5 * acc


def _polygon_bbox(pts: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _segments_intersect_strict(a: tuple, b: tuple,
                                  c: tuple, d: tuple) -> bool:
    """Strict proper intersection of two open segments (excludes
    endpoint-touching). Used to detect self-intersecting polygons.
    """
    def _orient(p, q, r):
        return ((q[0] - p[0]) * (r[1] - p[1])
                - (q[1] - p[1]) * (r[0] - p[0]))
    o1 = _orient(a, b, c)
    o2 = _orient(a, b, d)
    o3 = _orient(c, d, a)
    o4 = _orient(c, d, b)
    return (o1 * o2 < 0) and (o3 * o4 < 0)


def _polygon_is_self_intersecting(pts: list) -> bool:
    n = len(pts)
    if n < 4:
        return False
    edges = [(tuple(pts[i]), tuple(pts[(i + 1) % n])) for i in range(n)]
    for i in range(n):
        a, b = edges[i]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # wrap-around adjacency shares pts[0]
            c, d = edges[j]
            if _segments_intersect_strict(a, b, c, d):
                return True
    return False


def _wall_bbox(wall: dict, default_thickness: float) -> tuple[float, ...]:
    s = wall.get("start") or [0.0, 0.0]
    e = wall.get("end") or [0.0, 0.0]
    t = float(wall.get("thickness") or default_thickness)
    if wall.get("orientation") == "h":
        return (s[0], s[1] - t / 2, e[0], s[1] + t / 2)
    if wall.get("orientation") == "v":
        return (s[0] - t / 2, s[1], s[0] + t / 2, e[1])
    # Diagonal / unknown: expand the segment endpoints by thickness/2.
    return (min(s[0], e[0]) - t / 2, min(s[1], e[1]) - t / 2,
            max(s[0], e[0]) + t / 2, max(s[1], e[1]) + t / 2)


def _building_bbox_from_walls(walls: list[dict],
                                default_thickness: float
                                ) -> tuple[float, float, float, float] | None:
    if not walls:
        return None
    xs0: list[float] = []
    ys0: list[float] = []
    xs1: list[float] = []
    ys1: list[float] = []
    for w in walls:
        x0, y0, x1, y1 = _wall_bbox(w, default_thickness)
        xs0.append(x0)
        ys0.append(y0)
        xs1.append(x1)
        ys1.append(y1)
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def _bbox_contains_bbox(outer: tuple, inner: tuple,
                          margin: float = 0.0) -> bool:
    """Inner bbox lies inside outer bbox (within margin)."""
    return (
        inner[0] >= outer[0] - margin
        and inner[1] >= outer[1] - margin
        and inner[2] <= outer[2] + margin
        and inner[3] <= outer[3] + margin
    )


# ---------------------------------------------------------------------------
# planta_74-specific adjacency expectations (PR B3, opt-in by plan_id)
# ---------------------------------------------------------------------------

# Each entry is a pair of room name sets that should be linked by at
# least one opening. Adapted to the planta_74 baseline (CLAUDE.md §10).
# The check is intentionally TOLERANT — it does not require the
# adjacency to be via a specific kind_v5; any door / passage /
# glazed_balcony counts.
#
# Future plans can register their own expected adjacencies in this
# dict keyed by `consensus.plan_id`. Plans without an entry fall
# back to a NO-OP check (verdict PASS with note: "no expected
# adjacency map registered for plan_id=X").
PLANTA_74_EXPECTED_ADJACENCIES: list[tuple[set[str], set[str], str]] = [
    ({"BANHO 01"}, {"SUITE 01"},
     "BANHO 01 must be reachable from SUITE 01"),
    ({"BANHO 02"}, {"SUITE 02"},
     "BANHO 02 must be reachable from SUITE 02"),
    ({"LAVABO"}, {"SALA DE JANTAR", "SALA DE ESTAR", "COZINHA"},
     "LAVABO must be reachable from the SALA / COZINHA area"),
    ({"A.S."}, {"COZINHA", "TERRACO SOCIAL", "TERRACO TECNICO"},
     "A.S. must be reachable from COZINHA or a TERRACO"),
    ({"TERRACO SOCIAL"},
     {"SALA DE ESTAR", "SALA DE JANTAR", "COZINHA"},
     "TERRACO SOCIAL must be reachable from the SALA area"),
]

EXPECTED_ADJACENCIES_BY_PLAN_ID: dict[str, list] = {
    "planta_74": PLANTA_74_EXPECTED_ADJACENCIES,
    "planta_74_post_human_walls": PLANTA_74_EXPECTED_ADJACENCIES,
}


# ---------------------------------------------------------------------------
# Algorithmic checks (PR B3)
# ---------------------------------------------------------------------------

_DOOR_KINDS = {"interior_door", "interior_passage", "exterior_door"}

_VALID_HOST_MODES = {"cut_into_wall", "existing_gap"}


def _check_door_without_opening(consensus: dict,
                                  check_def: dict) -> dict[str, Any]:
    """Check 1 — each door / passage / exterior door must have a host
    wall (``wall_id`` set) AND a valid ``host_mode`` indicating an
    actual gap or carve.
    """
    failing: list[dict] = []
    for op in consensus.get("openings") or []:
        kind = op.get("kind_v5") or ""
        if kind not in _DOOR_KINDS:
            continue
        wall_id = op.get("wall_id") or op.get("host_wall_id")
        host_mode = op.get("host_mode")
        if not wall_id or host_mode not in _VALID_HOST_MODES:
            failing.append({
                "opening_id": op.get("id"),
                "kind_v5": kind,
                "wall_id": wall_id,
                "host_mode": host_mode,
            })
    verdict = "FAIL" if failing else "PASS"
    if failing:
        notes = (f"{len(failing)} door-type opening(s) lack a valid "
                 f"host wall + host_mode in {sorted(_VALID_HOST_MODES)}.")
    else:
        notes = "All door-type openings host on a real wall."
    return _make_check_result(check_def, verdict, failing, notes)


def _opening_perpendicular_shift(op: dict,
                                   wall: dict,
                                   default_thickness: float) -> float | None:
    """Perpendicular distance from the opening center to the wall
    centerline. ``None`` when geometry is malformed."""
    center = op.get("center")
    if not center or len(center) != 2:
        return None
    cx, cy = float(center[0]), float(center[1])
    s = wall.get("start") or [0, 0]
    if wall.get("orientation") == "h":
        return abs(cy - float(s[1]))
    if wall.get("orientation") == "v":
        return abs(cx - float(s[0]))
    return None


def _check_door_crossing_or_displaced(
        consensus: dict, check_def: dict) -> dict[str, Any]:
    """Check 2 — each door / passage must sit on its wall's centerline
    within thickness/2. A door whose center lies outside the wall band
    is either "crossing" (host_mode would be unhosted) or displaced.
    """
    walls_by_id = {w.get("id"): w for w in consensus.get("walls") or []}
    default_thickness = float(consensus.get("wall_thickness_pts") or 5.4)
    failing: list[dict] = []
    for op in consensus.get("openings") or []:
        kind = op.get("kind_v5") or ""
        if kind not in _DOOR_KINDS:
            continue
        wall = walls_by_id.get(op.get("wall_id"))
        if wall is None:
            continue  # host-missing is covered by check 1
        shift = _opening_perpendicular_shift(op, wall, default_thickness)
        if shift is None:
            continue
        wall_thickness = float(wall.get("thickness") or default_thickness)
        # Allow a small tolerance on top of half-thickness; openings can
        # sit on the centerline +/- thickness/2 by construction of
        # cut_into_wall. Reject 1 pt beyond the band as displaced.
        tolerance = wall_thickness / 2 + 1.0
        if shift > tolerance:
            failing.append({
                "opening_id": op.get("id"),
                "kind_v5": kind,
                "wall_id": op.get("wall_id"),
                "shift_pts": round(shift, 3),
                "max_tolerated_pts": round(tolerance, 3),
            })
    verdict = "FAIL" if failing else "PASS"
    notes = (f"{len(failing)} door-type opening(s) displaced >"
             f"wall_thickness/2 from the wall centerline."
             if failing else
             "All door-type openings sit on their wall centerline.")
    return _make_check_result(check_def, verdict, failing, notes)


def _check_door_swing_diverges(
        consensus: dict, check_def: dict) -> dict[str, Any]:
    """Check 3 — each interior_door's ``hinge_side`` must agree with
    the PDF arc evidence when one exists.

    The consensus carries this evidence under
    ``opening.evidence.svg_arc``. When the field is missing the
    check has no signal to judge against and the opening is recorded
    as a *warning* (status: ``checked``, verdict: ``WARN``, with the
    opening listed under ``failing_elements`` and a `reason: no_arc`
    tag).

    PR B4 may upgrade the check to consult the PDF directly; for B3
    the consensus is the source of truth.
    """
    failing: list[dict] = []
    warnings: list[dict] = []
    for op in consensus.get("openings") or []:
        if op.get("kind_v5") != "interior_door":
            continue
        hinge = op.get("hinge_side")
        arc = ((op.get("evidence") or {}).get("svg_arc")
               or op.get("svg_arc") or {})
        arc_dir = arc.get("hinge_side") if isinstance(arc, dict) else None
        if not arc:
            warnings.append({
                "opening_id": op.get("id"),
                "reason": "no_arc_evidence_in_consensus",
                "detected_hinge_side": hinge,
            })
            continue
        if arc_dir and hinge and arc_dir != hinge:
            failing.append({
                "opening_id": op.get("id"),
                "detected_hinge_side": hinge,
                "arc_hinge_side": arc_dir,
            })
    if failing:
        verdict = "FAIL"
        notes = (
            f"{len(failing)} interior_door(s) with hinge_side "
            f"differing from PDF arc evidence."
        )
    elif warnings:
        verdict = "WARN"
        notes = (
            f"{len(warnings)} interior_door(s) carry no svg_arc "
            "evidence in consensus; swing direction unverified. PR "
            "B4 may consult the PDF directly to upgrade this WARN."
        )
    else:
        verdict = "PASS"
        notes = "All interior_door hinge_side values match PDF arc evidence."
    return _make_check_result(
        check_def, verdict, failing or warnings, notes,
    )


def _check_room_polygon_not_closed(
        consensus: dict, check_def: dict) -> dict[str, Any]:
    """Check 4 — each room polygon must have >=3 vertices, non-zero
    area, and no self-intersection."""
    failing: list[dict] = []
    for r in consensus.get("rooms") or []:
        pts = r.get("polygon_pts") or []
        if len(pts) < 3:
            failing.append({
                "room_id": r.get("id"),
                "room_name": r.get("name"),
                "reason": "vertex_count_below_3",
                "n_vertices": len(pts),
            })
            continue
        area = _polygon_area_signed(pts)
        if abs(area) <= 1e-6:
            failing.append({
                "room_id": r.get("id"),
                "room_name": r.get("name"),
                "reason": "zero_area",
                "n_vertices": len(pts),
            })
            continue
        if _polygon_is_self_intersecting(pts):
            failing.append({
                "room_id": r.get("id"),
                "room_name": r.get("name"),
                "reason": "self_intersecting",
                "n_vertices": len(pts),
            })
    verdict = "FAIL" if failing else "PASS"
    notes = (f"{len(failing)} room(s) with non-closed / degenerate "
             "polygon." if failing else
             "All room polygons are valid (closed, simple, >0 area).")
    return _make_check_result(check_def, verdict, failing, notes)


def _check_room_polygon_bleeds_outside(
        consensus: dict, check_def: dict) -> dict[str, Any]:
    """Check 5 — each room polygon must lie inside the building bbox
    derived from the wall set. The check tolerates a 1 wall_thickness
    margin to account for parapets/peitoris that wrap the outer envelope.
    """
    walls = consensus.get("walls") or []
    default_thickness = float(consensus.get("wall_thickness_pts") or 5.4)
    bbox = _building_bbox_from_walls(walls, default_thickness)
    if bbox is None:
        return _make_check_result(
            check_def, "WARN", [],
            "no walls in consensus; cannot derive building bbox.",
        )
    margin = default_thickness
    failing: list[dict] = []
    for r in consensus.get("rooms") or []:
        pts = r.get("polygon_pts") or []
        if len(pts) < 3:
            continue  # caught by check 4
        room_bbox = _polygon_bbox(pts)
        if not _bbox_contains_bbox(bbox, room_bbox, margin=margin):
            failing.append({
                "room_id": r.get("id"),
                "room_name": r.get("name"),
                "room_bbox": [round(v, 3) for v in room_bbox],
                "building_bbox": [round(v, 3) for v in bbox],
            })
    verdict = "FAIL" if failing else "PASS"
    notes = (f"{len(failing)} room(s) bleed outside the building "
             "bbox." if failing else
             "All room polygons lie inside the building envelope.")
    return _make_check_result(check_def, verdict, failing, notes)


def _check_invented_or_wrong_height_exterior(
        consensus: dict, check_def: dict) -> dict[str, Any]:
    """Check 6 — exterior walls must have plausible geometry:
    positive length, axis-aligned start/end matching ``orientation``,
    thickness within +/- 25% of the consensus's
    ``wall_thickness_pts``.

    "Wrong height" cannot be verified from the consensus alone (the
    consensus stores walls in 2D; the height comes from the Ruby
    exporter constants). PR B4 may compare against PDF-extracted
    walls. For B3 the check FAILs walls whose 2D geometry is
    implausible (zero length, mismatched orientation, outlier
    thickness).
    """
    walls = consensus.get("walls") or []
    default_thickness = float(consensus.get("wall_thickness_pts") or 5.4)
    failing: list[dict] = []
    for w in walls:
        s = w.get("start") or [0, 0]
        e = w.get("end") or [0, 0]
        length = math.hypot(e[0] - s[0], e[1] - s[1])
        ori = w.get("orientation")
        t = float(w.get("thickness") or default_thickness)
        reasons: list[str] = []
        if length <= 1.0:
            reasons.append("near_zero_length")
        if ori == "h" and abs(e[1] - s[1]) > 0.5:
            reasons.append("orientation_h_but_not_horizontal")
        if ori == "v" and abs(e[0] - s[0]) > 0.5:
            reasons.append("orientation_v_but_not_vertical")
        if ori not in {"h", "v"}:
            reasons.append("orientation_not_axis_aligned")
        if t < default_thickness * 0.75 or t > default_thickness * 1.25:
            reasons.append(
                f"thickness_outlier({t:.3f}_vs_default_{default_thickness:.3f})"
            )
        if reasons:
            failing.append({
                "wall_id": w.get("id"),
                "reasons": reasons,
                "start": s, "end": e,
                "orientation": ori,
                "thickness_pts": t,
                "length_pts": round(length, 3),
            })
    verdict = "FAIL" if failing else "PASS"
    notes = (
        f"{len(failing)} wall(s) with implausible 2D geometry "
        "(near-zero length, mis-oriented, or thickness outlier)."
        if failing else
        "All walls have plausible 2D geometry; "
        "height verification deferred to PR B4."
    )
    return _make_check_result(check_def, verdict, failing, notes)


def _point_in_polygon(x: float, y: float,
                         pts: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon test. No shapely dependency."""
    n = len(pts)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        crosses = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
        )
        if crosses:
            inside = not inside
        j = i
    return inside


def _room_constituent_labels(room: dict) -> list[str]:
    """Return the room labels stored in a (possibly merged) cell.
    A merged cell like ``"SALA DE JANTAR | SALA DE ESTAR"`` becomes
    ``["SALA DE JANTAR", "SALA DE ESTAR"]``; a single-label cell
    returns ``[name]``.
    """
    name = (room.get("name") or "").strip()
    if not name:
        return []
    if "|" in name:
        return [n.strip() for n in name.split("|") if n.strip()]
    return [name]


def _room_at_point(x: float, y: float,
                    rooms: list[dict]) -> dict | None:
    """First room whose polygon contains the point. ``None`` when
    no room matches."""
    for r in rooms:
        pts = r.get("polygon_pts") or []
        if _point_in_polygon(x, y, pts):
            return r
    return None


def _opening_room_labels(op: dict,
                          walls_by_id: dict[str, dict],
                          rooms: list[dict],
                          default_thickness: float,
                          probe_offset: float = 6.0,
                          ) -> tuple[set[str], set[str]]:
    """Probe slightly off the opening center on either side of the
    host wall and read which rooms contain those probes. Returns a
    (left_labels, right_labels) tuple of sets so a merged cell on
    one side surfaces every constituent label.
    """
    wall = walls_by_id.get(op.get("wall_id"))
    if wall is None:
        return set(), set()
    center = op.get("center")
    if not center or len(center) != 2:
        return set(), set()
    cx, cy = float(center[0]), float(center[1])
    t = float(wall.get("thickness") or default_thickness)
    offset = (t / 2) + probe_offset
    if wall.get("orientation") == "h":
        below = _room_at_point(cx, cy - offset, rooms)
        above = _room_at_point(cx, cy + offset, rooms)
        return (
            set(_room_constituent_labels(below)) if below else set(),
            set(_room_constituent_labels(above)) if above else set(),
        )
    if wall.get("orientation") == "v":
        left = _room_at_point(cx - offset, cy, rooms)
        right = _room_at_point(cx + offset, cy, rooms)
        return (
            set(_room_constituent_labels(left)) if left else set(),
            set(_room_constituent_labels(right)) if right else set(),
        )
    return set(), set()


def _adjacent_room_pairs(consensus: dict) -> set[frozenset[str]]:
    """Set of frozenset({room_name_a, room_name_b}) pairs that share at
    least one opening in the consensus.

    For each opening, probe the host wall on each side and read the
    room polygons containing those probes. Merged cells contribute
    every constituent label.
    """
    rooms = consensus.get("rooms") or []
    walls_by_id = {w.get("id"): w for w in consensus.get("walls") or []}
    default_thickness = float(consensus.get("wall_thickness_pts") or 5.4)
    pairs: set[frozenset[str]] = set()
    for op in consensus.get("openings") or []:
        left_labels, right_labels = _opening_room_labels(
            op, walls_by_id, rooms, default_thickness,
        )
        for ln in left_labels:
            for rn in right_labels:
                if ln != rn:
                    pairs.add(frozenset({ln, rn}))
    # Merged-cell membership: every constituent in a merged cell is
    # trivially adjacent to every other from a walkability standpoint.
    for r in rooms:
        constituents = _room_constituent_labels(r)
        if len(constituents) < 2:
            continue
        for i in range(len(constituents)):
            for j in range(i + 1, len(constituents)):
                pairs.add(frozenset({constituents[i], constituents[j]}))
    # Filter out any names not actually present in the rooms list.
    valid_names = {n for r in rooms for n in _room_constituent_labels(r)}
    return {p for p in pairs if all(name in valid_names for name in p)}


def _name_set_overlaps(pair: frozenset[str], names: set[str]) -> bool:
    return any(n in names for n in pair)


def _infer_plan_id(consensus: dict) -> str:
    """Derive a plan_id for adjacency-map lookup.

    Order of precedence:
      1. explicit ``consensus.plan_id``
      2. basename of ``consensus.source`` minus the extension (so
         ``"planta_74.pdf"`` -> ``"planta_74"``)
      3. empty string when neither is available
    """
    if consensus.get("plan_id"):
        return str(consensus["plan_id"])
    source = consensus.get("source") or ""
    if isinstance(source, str) and source:
        stem = Path(source).stem
        if stem:
            return stem
    return ""


def _check_wet_or_terrace_adjacency_wrong(
        consensus: dict, check_def: dict) -> dict[str, Any]:
    """Check 7 — bath / lavabo / A.S. / terraço cells must connect to
    the rooms the project's adjacency map says they should.

    The expected map is indexed by ``consensus.plan_id`` (with a
    fallback to ``consensus.source`` stem so a fresh
    ``planta_74.pdf`` consensus still resolves). Plans without a
    registered map fall back to a no-op PASS.
    """
    plan_id = _infer_plan_id(consensus)
    expected = EXPECTED_ADJACENCIES_BY_PLAN_ID.get(plan_id)
    if expected is None:
        return _make_check_result(
            check_def, "PASS", [],
            f"no expected_adjacency map registered for plan_id="
            f"{plan_id!r}; check is a no-op for this plan.",
        )
    actual_pairs = _adjacent_room_pairs(consensus)
    failing: list[dict] = []
    for from_set, to_set, description in expected:
        # Find an edge that crosses from any from_set to any to_set.
        ok = False
        for p in actual_pairs:
            if (_name_set_overlaps(p, from_set)
                    and _name_set_overlaps(p, to_set)
                    # Ensure the pair actually spans both groups.
                    and not p.issubset(from_set)
                    and not p.issubset(to_set)):
                ok = True
                break
        if not ok:
            failing.append({
                "from": sorted(from_set),
                "to": sorted(to_set),
                "description": description,
            })
    verdict = "FAIL" if failing else "PASS"
    notes = (
        f"{len(failing)} expected adjacency(ies) not present in the "
        f"consensus for plan_id={plan_id!r}."
        if failing else
        f"All expected adjacencies for plan_id={plan_id!r} are present."
    )
    return _make_check_result(check_def, verdict, failing, notes)


def _polygon_looks_like_bbox(pts: list[list[float]]) -> bool:
    """Heuristic: True iff the polygon has exactly 4 vertices, all
    angles ~90deg, and bbox area == polygon area within 1%.
    """
    if len(pts) != 4:
        return False
    bbox = _polygon_bbox(pts)
    bbox_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    poly_area = abs(_polygon_area_signed(pts))
    if poly_area <= 0:
        return False
    # All four vertices on the bbox corners?
    expected_corners = {
        (bbox[0], bbox[1]), (bbox[2], bbox[1]),
        (bbox[2], bbox[3]), (bbox[0], bbox[3]),
    }
    actual_corners = {(p[0], p[1]) for p in pts}
    if expected_corners != actual_corners:
        return False
    return abs(poly_area - bbox_area) / max(poly_area, 1e-9) < 0.01


def _check_room_rendered_as_bbox(
        consensus: dict, check_def: dict) -> dict[str, Any]:
    """Check 8 — flag rooms whose polygon is exactly the room's
    bounding box rectangle when the project's wall set is dense
    enough that we expect real (non-bbox) geometry.

    Heuristic for B3:
      * any rectangle-only polygon counts as a candidate bbox-substitute
      * IF the consensus has >=5 walls (i.e. there is meaningful
        wall geometry that could form non-rectangular cells), a
        bbox-shaped room is flagged
      * single-wall plans (raster fallbacks) are exempt
    """
    walls = consensus.get("walls") or []
    if len(walls) < 5:
        return _make_check_result(
            check_def, "WARN", [],
            f"only {len(walls)} wall(s) in consensus — too few to "
            "judge whether room shapes are honest cells or bbox "
            "substitutes; check skipped.",
        )
    failing: list[dict] = []
    for r in consensus.get("rooms") or []:
        pts = r.get("polygon_pts") or []
        if not _polygon_looks_like_bbox(pts):
            continue
        failing.append({
            "room_id": r.get("id"),
            "room_name": r.get("name"),
            "n_vertices": len(pts),
            "bbox_pts": [round(v, 3) for v in _polygon_bbox(pts)],
        })
    verdict = "FAIL" if failing else "PASS"
    notes = (
        f"{len(failing)} room(s) rendered as plain bbox rectangle "
        "in a multi-wall plan — likely bbox substitute rather than "
        "real cell geometry."
        if failing else
        "No rooms collapsed to a bbox rectangle."
    )
    return _make_check_result(check_def, verdict, failing, notes)


CHECK_RUNNERS: dict[str, Any] = {
    "door_without_opening": _check_door_without_opening,
    "door_crossing_or_displaced": _check_door_crossing_or_displaced,
    "door_swing_diverges": _check_door_swing_diverges,
    "room_polygon_not_closed": _check_room_polygon_not_closed,
    "room_polygon_bleeds_outside": _check_room_polygon_bleeds_outside,
    "invented_or_wrong_height_exterior":
        _check_invented_or_wrong_height_exterior,
    "wet_or_terrace_adjacency_wrong":
        _check_wet_or_terrace_adjacency_wrong,
    "room_rendered_as_bbox": _check_room_rendered_as_bbox,
}


def run_check(check_def: dict, consensus: dict | None) -> dict[str, Any]:
    """Dispatch one check. When ``consensus`` is ``None``, returns
    the not_yet_checked scaffold so downstream consumers always get a
    well-shaped record."""
    if consensus is None:
        return _scaffold_check(check_def)
    runner = CHECK_RUNNERS.get(check_def["key"])
    if runner is None:
        return _scaffold_check(check_def)
    return runner(consensus, check_def)


def _scaffold_all_checks() -> list[dict[str, Any]]:
    return [_scaffold_check(d) for d in EIGHT_CHECKS]


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

def _summarise_checks(checks: list[dict]) -> dict[str, int]:
    counts = {
        "checks_pass": 0,
        "checks_warn": 0,
        "checks_fail": 0,
        "checks_not_yet_checked": 0,
    }
    for c in checks:
        status = c.get("status", "not_yet_checked")
        verdict = (c.get("verdict") or "WARN").upper()
        if status == "not_yet_checked":
            counts["checks_not_yet_checked"] += 1
        elif verdict == "PASS":
            counts["checks_pass"] += 1
        elif verdict == "FAIL":
            counts["checks_fail"] += 1
        else:
            counts["checks_warn"] += 1
    return counts


def _compute_top_level(artifacts_status: str,
                        check_counts: dict[str, int]) -> str:
    """Compute the gate's top-level verdict.

    Precedence (highest wins):
      * any missing/empty artifact   → FAIL
      * any check FAIL                → FAIL
      * any check WARN OR not_yet_checked → WARN
      * all checks PASS              → PASS

    PR B2 always lands in WARN once artifacts are present (because
    the 8 checks are all ``not_yet_checked``). PR B3 supplies the
    algorithms; PASS becomes reachable then.
    """
    if artifacts_status != "present":
        return "FAIL"
    if check_counts.get("checks_fail", 0) > 0:
        return "FAIL"
    if (check_counts.get("checks_warn", 0) > 0
            or check_counts.get("checks_not_yet_checked", 0) > 0):
        return "WARN"
    return "PASS"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_gate(evidence_dir: Path,
              consensus_path: Path | None = None,
              pdf_path: Path | None = None) -> dict[str, Any]:
    """Inspect the evidence directory and produce the gate report.

    When ``consensus_path`` points to a readable consensus JSON, every
    one of the eight algorithmic checks (PR B3) runs against it. When
    ``consensus_path`` is ``None`` (or the file is unreadable), every
    check stays in the ``not_yet_checked`` scaffold state.

    ``pdf_path`` is accepted for forward compatibility — PR B4 / a
    future revision may parse the PDF for stricter checks (eg arc
    extraction for `door_swing_diverges`). It is not consumed in B3.
    """
    artifacts = load_artifacts(evidence_dir)
    consensus = _load_consensus_if_readable(consensus_path)
    checks = [run_check(c, consensus) for c in EIGHT_CHECKS]
    summary = {
        "artifacts_present": len(artifacts["present_keys"]),
        "artifacts_empty": len(artifacts["empty_keys"]),
        "artifacts_missing": len(artifacts["missing_keys"]),
        **_summarise_checks(checks),
    }
    top_level = _compute_top_level(
        artifacts["overall_status"], summary,
    )
    report: dict[str, Any] = {
        "schema_version": GATE_REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ",
        ),
        "evidence_dir": str(evidence_dir),
        "consensus_path": (
            str(consensus_path) if consensus_path is not None else None
        ),
        "pdf_path": (
            str(pdf_path) if pdf_path is not None else None
        ),
        "verdict_top_level": top_level,
        "artifacts": artifacts,
        "checks": checks,
        "summary": summary,
    }
    if artifacts["overall_status"] != "present":
        report["policy_violation"] = VISUAL_FIDELITY_POLICY_VIOLATION_TAG
        report["policy_reason"] = (
            "Visual Fidelity Gate Protocol (2026-05-14): "
            f"artifact-presence check failed "
            f"(overall_status={artifacts['overall_status']!r}; "
            f"missing={len(artifacts['missing_keys'])}, "
            f"empty={len(artifacts['empty_keys'])}). The gate cannot "
            "judge artifact content until all seven artifacts exist "
            "and are non-empty. Produce them via "
            "`python -m tools.produce_visual_evidence`."
        )
    if summary["checks_not_yet_checked"] > 0:
        # Hint preserved so cockpit / CI consumers can detect a B2-
        # only run (no consensus supplied → scaffolded checks).
        report["pending_algorithmic_checks_pr"] = "B3"
    return report


def _load_consensus_if_readable(path: Path | None) -> dict | None:
    if path is None:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="visual_fidelity_gate",
        description=(
            "Visual Fidelity Gate (PR B2, reader scaffolding). "
            "Inspects the seven evidence artifacts produced by "
            "`tools/produce_visual_evidence.py` and emits a "
            "gate_report.json. Algorithmic checks land in PR B3."
        ),
    )
    ap.add_argument(
        "--evidence-dir", type=Path, required=True,
        help=(
            "Directory containing the seven required artifacts "
            "(original_floorplan.png, skp_render.png, "
            "overlay_pdf_skp.png, diff_walls.png, diff_doors.png, "
            "diff_rooms.png, mismatches_list.md)."
        ),
    )
    ap.add_argument(
        "--consensus", type=Path, default=None,
        help=(
            "Source consensus JSON. Not consumed in PR B2; reserved "
            "so PR B3 can wire the algorithmic checks without a "
            "CLI change."
        ),
    )
    ap.add_argument(
        "--pdf", type=Path, default=None,
        help=(
            "Source PDF. Not consumed in PR B2; reserved for the "
            "PR B3 algorithmic checks."
        ),
    )
    ap.add_argument("--out", type=Path, default=None,
                    help="Path to write gate_report.json.")
    ap.add_argument(
        "--strict", action="store_true",
        help=(
            "Exit 2 when the top-level verdict is FAIL. Without "
            "--strict the script always exits 0 so callers can "
            "inspect the report regardless."
        ),
    )
    args = ap.parse_args(argv)

    if not args.evidence_dir.exists():
        print(f"[visual_fidelity_gate] evidence directory does not "
              f"exist: {args.evidence_dir}", file=sys.stderr)
        return 2

    report = run_gate(
        evidence_dir=args.evidence_dir,
        consensus_path=args.consensus,
        pdf_path=args.pdf,
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2),
                              encoding="utf-8")
        print(f"[ok] gate report -> {args.out}")

    print()
    print(f"=== Visual Fidelity Gate verdict: "
          f"{report['verdict_top_level']} ===")
    if report.get("policy_violation"):
        print(f"  policy_violation: {report['policy_violation']}")
    print(f"  evidence_dir:     {report['evidence_dir']}")
    print(f"  artifacts:        "
          f"{report['summary']['artifacts_present']}/"
          f"{len(REQUIRED_VISUAL_ARTIFACTS)} present, "
          f"{report['summary']['artifacts_missing']} missing, "
          f"{report['summary']['artifacts_empty']} empty")
    print(f"  checks:           "
          f"{report['summary']['checks_pass']} pass, "
          f"{report['summary']['checks_warn']} warn, "
          f"{report['summary']['checks_fail']} fail, "
          f"{report['summary']['checks_not_yet_checked']} "
          f"not_yet_checked (pending PR B3)")

    if args.strict and report["verdict_top_level"] == "FAIL":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
