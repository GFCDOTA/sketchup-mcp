"""Structural checks for SKP pre-export validation (FP-014 gamma gate).

Pure-Python module called from `scripts/smoke/smoke_skp_export.py`
gate F0. Detects floor/room polygon defects, wall fragmentation,
and topology gaps that produce visually defective SKPs (`docs/diagnostics/
2026-05-09_skp_visual_failure_fp014.md`).

**Scope (do NOT cross):**
- Reads consensus dict + optional fidelity_report dict + optional
  expected_model dict.
- Returns a dict of structural_blockers + structural_warnings + per-room
  metrics. **Never modifies any input.**
- **Does NOT** modify `tools/build_vector_consensus.py` (FP-014 P0
  spike found that detector needs a separate refactor - Option alpha).
- **Does NOT** modify `tools/rooms_from_seeds.py` (input dependency
  on the detector's incomplete topology).
- **Does NOT** modify the SKP exporter (`tools/consume_consensus.rb`).
- **Does NOT** touch `tools/extract_openings_vector.py`.

This module is the gamma gate: it BLOCKS export of structurally defective
SKPs without trying to fix them. Algorithmic fixes are tracked
separately as Option alpha (`build_vector_consensus` refactor) and Option beta
(`rooms_from_seeds` polish).

## Checks

| ID | Severity | Description |
|----|----------|-------------|
| C1 | FAIL >50 / WARN >30 | room polygon vertex count |
| C2 | FAIL >0.30 / WARN >0.15 | free vertex ratio (vts not on any wall) |
| C3 | FAIL <0.95 | polygon area % inside envelope |
| C4 | FAIL | polygon NOT simple (self-intersecting) |
| C5 | WARN >2.0 | shape complexity (perimeter / (4*sqrtarea)) |
| C6 | WARN >0 | long diagonals (>50pt edges not following any wall) |
| C7 | WARN >5 | short wall fragments (walls <1m) |
| C8 | FAIL | colinear gaps >0.5m without an opening |
| C9 | WARN | envelope - thick_walls is a single polygon (no room cells) |
| C10 | WARN | room area exceeds 1.5x expected_area_m2_range upper bound |
| C11 | WARN | total room area > 1.3x envelope estimate |

A FAIL in any check means: F0 verdict = **FAIL** even if fidelity
score is high. A WARN demotes PASS → WARN.

## Coordinates

All coordinates in PDF points (`pt`). `PT_TO_M = 0.19 / 5.4 ~= 0.0352
m/pt`, anchored to `consensus.wall_thickness_pts` (CLAUDE.md §10).

## CLI

::

    python -m tools.structural_checks consensus.json [--expected expected.json]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

# ---------------------------------------------------------------------------
# Public schema constants
# ---------------------------------------------------------------------------

STRUCTURAL_CHECKS_SCHEMA_VERSION = "structural_checks_v1"
PT_TO_M_DEFAULT = 0.19 / 5.4  # planta_74 anchor; consensus may override

# Check thresholds - tunable per-call but defaults are set to detect
# the FP-014 case while not flagging healthy synthetic plants.
DEFAULTS = {
    "polygon_max_vts_warn": 30,
    "polygon_max_vts_fail": 50,
    "free_vertex_ratio_warn": 0.15,
    "free_vertex_ratio_fail": 0.30,
    "in_envelope_pct_fail": 0.95,
    "shape_complexity_warn": 2.0,
    "long_diag_min_len_pt": 50.0,
    "short_wall_max_len_m": 1.0,
    "short_wall_count_warn": 5,
    "colinear_gap_min_m_for_opening_check": 0.5,
    "opening_match_tol_pt": 30.0,
    "envelope_ratio_warn": 1.3,
    "expected_area_overshoot_factor": 1.5,
}

# Severities
FAIL = "fail"
WARN = "warn"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CheckFinding:
    """One blocker or warning emitted by a check."""

    check_id: str
    severity: str  # "fail" | "warn"
    target_kind: str  # "room" | "wall" | "consensus"
    target_id: str | None
    message: str
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "severity": self.severity,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "message": self.message,
            "evidence": dict(self.evidence),
        }


@dataclass
class RoomMetrics:
    """Per-room metrics surfaced for cockpit + audit."""

    room_id: str
    name: str
    vts: int
    free_vts: int
    free_vertex_ratio: float
    area_m2: float
    perimeter_m: float
    shape_complexity_ratio: float
    in_envelope_pct: float
    is_simple: bool
    long_diag_count: int

    def as_dict(self) -> dict:
        return {
            "room_id": self.room_id,
            "name": self.name,
            "vts": self.vts,
            "free_vts": self.free_vts,
            "free_vertex_ratio": round(self.free_vertex_ratio, 4),
            "area_m2": round(self.area_m2, 4),
            "perimeter_m": round(self.perimeter_m, 4),
            "shape_complexity_ratio": round(self.shape_complexity_ratio, 4),
            "in_envelope_pct": round(self.in_envelope_pct, 4),
            "is_simple": self.is_simple,
            "long_diag_count": self.long_diag_count,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wall_lines(consensus: dict) -> list[LineString]:
    return [
        LineString([w["start"], w["end"]])
        for w in consensus.get("walls") or []
    ]


def _wall_endpoints(consensus: dict) -> set[tuple[float, float]]:
    eps: set[tuple[float, float]] = set()
    for w in consensus.get("walls") or []:
        eps.add(tuple(round(x, 1) for x in w["start"]))
        eps.add(tuple(round(x, 1) for x in w["end"]))
    return eps


def _wall_envelope(consensus: dict, thickness: float) -> Polygon:
    """Approximate envelope = convex hull of wall endpoints."""
    walls = consensus.get("walls") or []
    if not walls:
        return Polygon()
    wlines = _wall_lines(consensus)
    union = unary_union(wlines)
    if union.is_empty:
        return Polygon()
    return union.convex_hull


def _ideal_perimeter_m(area_m2: float) -> float:
    """4*sqrtarea - perimeter of a square with the same area."""
    return 4.0 * math.sqrt(max(area_m2, 1e-9))


# ---------------------------------------------------------------------------
# Per-room metric computation
# ---------------------------------------------------------------------------

def _compute_room_metrics(
    consensus: dict,
    pt_to_m: float,
) -> list[RoomMetrics]:
    rooms = consensus.get("rooms") or []
    walls = consensus.get("walls") or []
    thickness = float(consensus.get("wall_thickness_pts") or 5.4)
    tol = thickness * 1.5
    long_diag_min = DEFAULTS["long_diag_min_len_pt"]

    wall_endpoints = _wall_endpoints(consensus)
    wall_lines = _wall_lines(consensus)
    envelope = _wall_envelope(consensus, thickness)

    out: list[RoomMetrics] = []
    for r in rooms:
        pts = r.get("polygon_pts") or []
        if len(pts) < 3:
            # Degenerate; emit minimal metrics
            out.append(RoomMetrics(
                room_id=r.get("id") or "",
                name=r.get("name") or "",
                vts=len(pts),
                free_vts=0,
                free_vertex_ratio=0.0,
                area_m2=0.0,
                perimeter_m=0.0,
                shape_complexity_ratio=0.0,
                in_envelope_pct=0.0,
                is_simple=False,
                long_diag_count=0,
            ))
            continue

        # Shapely polygon
        try:
            poly = Polygon(pts)
            is_simple = poly.is_valid and not poly.is_empty
        except Exception:  # noqa: BLE001
            poly = None
            is_simple = False

        if poly is None or poly.is_empty:
            out.append(RoomMetrics(
                room_id=r.get("id") or "",
                name=r.get("name") or "",
                vts=len(pts),
                free_vts=0,
                free_vertex_ratio=0.0,
                area_m2=0.0,
                perimeter_m=0.0,
                shape_complexity_ratio=0.0,
                in_envelope_pct=0.0,
                is_simple=False,
                long_diag_count=0,
            ))
            continue

        area_m2 = poly.area * pt_to_m ** 2
        perimeter_m = poly.length * pt_to_m

        # Free vertex count
        free = 0
        for p in pts:
            rp = tuple(round(x, 1) for x in p)
            if rp in wall_endpoints:
                continue
            pgeom = Point(p)
            if any(wl.distance(pgeom) < tol for wl in wall_lines):
                continue
            free += 1
        free_ratio = free / len(pts) if pts else 0.0

        # Long diagonals (edges > min_len that don't follow any wall)
        long_diags = 0
        coords = list(poly.exterior.coords)
        for i in range(len(coords) - 1):
            seg = LineString([coords[i], coords[i + 1]])
            if seg.length < long_diag_min:
                continue
            if any(seg.hausdorff_distance(wl) < tol for wl in wall_lines):
                continue
            long_diags += 1

        # In-envelope %
        if envelope.is_empty or poly.is_empty:
            in_env_pct = 0.0
        else:
            try:
                in_env_pct = poly.intersection(envelope).area / poly.area
            except Exception:  # noqa: BLE001
                in_env_pct = 0.0

        # Shape complexity
        ideal = _ideal_perimeter_m(area_m2)
        shape_ratio = perimeter_m / ideal if ideal > 0 else 0.0

        out.append(RoomMetrics(
            room_id=r.get("id") or "",
            name=r.get("name") or "",
            vts=len(pts),
            free_vts=free,
            free_vertex_ratio=free_ratio,
            area_m2=area_m2,
            perimeter_m=perimeter_m,
            shape_complexity_ratio=shape_ratio,
            in_envelope_pct=in_env_pct,
            is_simple=is_simple,
            long_diag_count=long_diags,
        ))
    return out


# ---------------------------------------------------------------------------
# Per-check evaluators
# ---------------------------------------------------------------------------

def _check_room_polygon_vts(
    metrics: list[RoomMetrics],
) -> list[CheckFinding]:
    out: list[CheckFinding] = []
    for m in metrics:
        if m.vts > DEFAULTS["polygon_max_vts_fail"]:
            out.append(CheckFinding(
                check_id="C1_polygon_vts",
                severity=FAIL,
                target_kind="room",
                target_id=m.room_id,
                message=(
                    f"room {m.name!r} polygon has {m.vts} vertices "
                    f"(>{DEFAULTS['polygon_max_vts_fail']}); "
                    f"raster trace contour, not wall-defined cell"
                ),
                evidence={"vts": m.vts, "area_m2": round(m.area_m2, 2)},
            ))
        elif m.vts > DEFAULTS["polygon_max_vts_warn"]:
            out.append(CheckFinding(
                check_id="C1_polygon_vts",
                severity=WARN,
                target_kind="room",
                target_id=m.room_id,
                message=(
                    f"room {m.name!r} polygon has {m.vts} vertices "
                    f"(>{DEFAULTS['polygon_max_vts_warn']})"
                ),
                evidence={"vts": m.vts, "area_m2": round(m.area_m2, 2)},
            ))
    return out


def _check_free_vertex_ratio(
    metrics: list[RoomMetrics],
) -> list[CheckFinding]:
    out: list[CheckFinding] = []
    for m in metrics:
        if m.free_vertex_ratio > DEFAULTS["free_vertex_ratio_fail"]:
            out.append(CheckFinding(
                check_id="C2_free_vertex_ratio",
                severity=FAIL,
                target_kind="room",
                target_id=m.room_id,
                message=(
                    f"room {m.name!r} has {m.free_vts}/{m.vts} "
                    f"({m.free_vertex_ratio:.0%}) vertices not on any "
                    f"wall (>{DEFAULTS['free_vertex_ratio_fail']:.0%})"
                ),
                evidence={
                    "free_vts": m.free_vts,
                    "vts": m.vts,
                    "ratio": round(m.free_vertex_ratio, 3),
                },
            ))
        elif m.free_vertex_ratio > DEFAULTS["free_vertex_ratio_warn"]:
            out.append(CheckFinding(
                check_id="C2_free_vertex_ratio",
                severity=WARN,
                target_kind="room",
                target_id=m.room_id,
                message=(
                    f"room {m.name!r} has {m.free_vts}/{m.vts} "
                    f"({m.free_vertex_ratio:.0%}) free vertices"
                ),
                evidence={
                    "free_vts": m.free_vts,
                    "vts": m.vts,
                    "ratio": round(m.free_vertex_ratio, 3),
                },
            ))
    return out


def _check_polygon_in_envelope(
    metrics: list[RoomMetrics],
) -> list[CheckFinding]:
    out: list[CheckFinding] = []
    for m in metrics:
        if m.in_envelope_pct < DEFAULTS["in_envelope_pct_fail"]:
            out.append(CheckFinding(
                check_id="C3_in_envelope",
                severity=FAIL,
                target_kind="room",
                target_id=m.room_id,
                message=(
                    f"room {m.name!r} has only "
                    f"{m.in_envelope_pct:.0%} of its area inside the "
                    f"wall envelope (<{DEFAULTS['in_envelope_pct_fail']:.0%})"
                ),
                evidence={"in_envelope_pct": round(m.in_envelope_pct, 3)},
            ))
    return out


def _check_polygon_simple(
    metrics: list[RoomMetrics],
) -> list[CheckFinding]:
    out: list[CheckFinding] = []
    for m in metrics:
        if not m.is_simple:
            out.append(CheckFinding(
                check_id="C4_polygon_simple",
                severity=FAIL,
                target_kind="room",
                target_id=m.room_id,
                message=(
                    f"room {m.name!r} polygon is not simple "
                    f"(self-intersecting or invalid)"
                ),
                evidence={"is_simple": False},
            ))
    return out


def _check_shape_complexity(
    metrics: list[RoomMetrics],
) -> list[CheckFinding]:
    out: list[CheckFinding] = []
    for m in metrics:
        if m.shape_complexity_ratio > DEFAULTS["shape_complexity_warn"]:
            out.append(CheckFinding(
                check_id="C5_shape_complexity",
                severity=WARN,
                target_kind="room",
                target_id=m.room_id,
                message=(
                    f"room {m.name!r} shape complexity "
                    f"{m.shape_complexity_ratio:.2f}x rectangle "
                    f"(>{DEFAULTS['shape_complexity_warn']})"
                ),
                evidence={
                    "shape_complexity_ratio": round(m.shape_complexity_ratio, 3),
                    "area_m2": round(m.area_m2, 2),
                    "perimeter_m": round(m.perimeter_m, 2),
                },
            ))
    return out


def _check_long_diagonals(
    metrics: list[RoomMetrics],
) -> list[CheckFinding]:
    out: list[CheckFinding] = []
    for m in metrics:
        if m.long_diag_count > 0:
            out.append(CheckFinding(
                check_id="C6_long_diagonals",
                severity=WARN,
                target_kind="room",
                target_id=m.room_id,
                message=(
                    f"room {m.name!r} has {m.long_diag_count} polygon "
                    f"edges >{DEFAULTS['long_diag_min_len_pt']:.0f}pt that "
                    f"don't follow any wall (diagonal shortcuts)"
                ),
                evidence={"long_diag_count": m.long_diag_count},
            ))
    return out


def _check_short_wall_fragments(
    consensus: dict,
    pt_to_m: float,
) -> list[CheckFinding]:
    walls = consensus.get("walls") or []
    threshold_m = DEFAULTS["short_wall_max_len_m"]
    short = []
    for w in walls:
        L = math.dist(w["start"], w["end"]) * pt_to_m
        if L < threshold_m:
            short.append((w["id"], L))
    out: list[CheckFinding] = []
    if len(short) > DEFAULTS["short_wall_count_warn"]:
        sample = ", ".join(
            f"{wid}({L:.2f}m)" for wid, L in short[:5]
        )
        out.append(CheckFinding(
            check_id="C7_short_wall_fragments",
            severity=WARN,
            target_kind="consensus",
            target_id=None,
            message=(
                f"{len(short)}/{len(walls)} walls < {threshold_m}m; "
                f"sample: {sample}"
            ),
            evidence={
                "short_count": len(short),
                "total_walls": len(walls),
                "sample": [(wid, round(L, 3)) for wid, L in short[:10]],
            },
        ))
    return out


def _find_colinear_gaps(consensus: dict) -> list[dict]:
    """Find pairs of colinear walls separated by a gap (door candidate)."""
    walls = consensus.get("walls") or []
    pairs: list[dict] = []
    for i, w1 in enumerate(walls):
        for w2 in walls[i + 1:]:
            o1 = w1.get("orientation")
            o2 = w2.get("orientation")
            if not o1 or o1 != o2:
                continue
            s1, e1 = w1["start"], w1["end"]
            s2, e2 = w2["start"], w2["end"]
            if o1 == "h":
                if abs(s1[1] - s2[1]) > 1.0:
                    continue
                a1, b1 = sorted([s1[0], e1[0]])
                a2, b2 = sorted([s2[0], e2[0]])
                if b1 < a2:
                    gap = a2 - b1
                    gc = ((b1 + a2) / 2.0, s1[1])
                elif b2 < a1:
                    gap = a1 - b2
                    gc = ((b2 + a1) / 2.0, s1[1])
                else:
                    continue
            else:
                if abs(s1[0] - s2[0]) > 1.0:
                    continue
                a1, b1 = sorted([s1[1], e1[1]])
                a2, b2 = sorted([s2[1], e2[1]])
                if b1 < a2:
                    gap = a2 - b1
                    gc = (s1[0], (b1 + a2) / 2.0)
                elif b2 < a1:
                    gap = a1 - b2
                    gc = (s1[0], (b2 + a1) / 2.0)
                else:
                    continue
            pairs.append({
                "w1": w1["id"], "w2": w2["id"],
                "gap_pt": gap, "center": gc, "orient": o1,
            })
    return pairs


def _check_unmapped_colinear_gaps(
    consensus: dict,
    pt_to_m: float,
) -> list[CheckFinding]:
    """C8 - colinear wall gap >0.5m without an opening anchored to it."""
    pairs = _find_colinear_gaps(consensus)
    openings = consensus.get("openings") or []
    tol = DEFAULTS["opening_match_tol_pt"]
    min_gap_m = DEFAULTS["colinear_gap_min_m_for_opening_check"]
    unmapped: list[dict] = []
    for p in pairs:
        gap_m = p["gap_pt"] * pt_to_m
        if gap_m < min_gap_m:
            continue
        gp = Point(p["center"])
        matched = False
        for o in openings:
            d = gp.distance(Point(o["center"]))
            if d < tol:
                matched = True
                break
        if not matched:
            unmapped.append({**p, "gap_m": round(gap_m, 3)})
    out: list[CheckFinding] = []
    if unmapped:
        sample = ", ".join(
            f"{u['w1']}to{u['w2']}({u['gap_m']}m)"
            for u in unmapped[:5]
        )
        out.append(CheckFinding(
            check_id="C8_unmapped_colinear_gaps",
            severity=FAIL,
            target_kind="consensus",
            target_id=None,
            message=(
                f"{len(unmapped)} colinear wall gaps >{min_gap_m}m have "
                f"NO opening; sample: {sample}"
            ),
            evidence={
                "unmapped_count": len(unmapped),
                "samples": unmapped[:10],
            },
        ))
    return out


def _check_envelope_decomposition(
    consensus: dict,
    pt_to_m: float,
) -> list[CheckFinding]:
    """C9 - envelope - thick_walls should produce >1 disconnected piece."""
    walls = consensus.get("walls") or []
    if not walls:
        return []
    thickness = float(consensus.get("wall_thickness_pts") or 5.4)
    half = thickness / 2.0
    wall_lines = _wall_lines(consensus)
    strips = [ln.buffer(half * 1.1, cap_style=2) for ln in wall_lines]
    wall_block = unary_union(strips)
    all_pts = []
    for w in walls:
        all_pts.append(w["start"])
        all_pts.append(w["end"])
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    bb = box(min(xs) - 5, min(ys) - 5, max(xs) + 5, max(ys) + 5)
    interior = bb.difference(wall_block)
    pieces = []
    if isinstance(interior, MultiPolygon):
        pieces = list(interior.geoms)
    elif isinstance(interior, Polygon) and not interior.is_empty:
        pieces = [interior]
    big_pieces = [p for p in pieces if p.area * pt_to_m ** 2 > 1.0]
    out: list[CheckFinding] = []
    if len(big_pieces) <= 1:
        out.append(CheckFinding(
            check_id="C9_envelope_decomposition",
            severity=WARN,
            target_kind="consensus",
            target_id=None,
            message=(
                f"envelope - thick_walls produces only {len(big_pieces)} "
                f"piece(s) > 1 m^2; walls don't divide envelope into rooms "
                f"(detector incompleteness - see FP-014 spike)"
            ),
            evidence={
                "big_piece_count": len(big_pieces),
                "envelope_area_m2": round(bb.area * pt_to_m ** 2, 2),
                "wall_block_area_m2": round(
                    wall_block.area * pt_to_m ** 2, 2,
                ),
            },
        ))
    return out


def _check_room_area_vs_expected(
    metrics: list[RoomMetrics],
    expected_model: dict | None,
) -> list[CheckFinding]:
    """C10 - room area > 1.5x expected_area_m2_range upper bound."""
    if not expected_model:
        return []
    expected_rooms = expected_model.get("rooms") or []
    by_label = {
        (r.get("label") or "").strip().upper(): r
        for r in expected_rooms
    }
    factor = DEFAULTS["expected_area_overshoot_factor"]
    out: list[CheckFinding] = []
    for m in metrics:
        er = by_label.get((m.name or "").strip().upper())
        if er is None:
            continue
        rng = er.get("expected_area_m2_range")
        if not isinstance(rng, list) or len(rng) != 2:
            continue
        upper = float(rng[1])
        if m.area_m2 > upper * factor:
            out.append(CheckFinding(
                check_id="C10_area_vs_expected",
                severity=WARN,
                target_kind="room",
                target_id=m.room_id,
                message=(
                    f"room {m.name!r} area {m.area_m2:.2f} m^2 > "
                    f"{factor:.1f}x expected upper {upper:.2f} m^2"
                ),
                evidence={
                    "area_m2": round(m.area_m2, 2),
                    "expected_max_m2": upper,
                    "factor": round(m.area_m2 / upper, 2),
                },
            ))
    return out


def _check_total_area_vs_envelope(
    consensus: dict,
    metrics: list[RoomMetrics],
    pt_to_m: float,
) -> list[CheckFinding]:
    """C11 - sum(rooms.area_m2) > 1.3x envelope estimate."""
    walls = consensus.get("walls") or []
    if not walls:
        return []
    all_pts = []
    for w in walls:
        all_pts.append(w["start"])
        all_pts.append(w["end"])
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    bb_area_m2 = (max(xs) - min(xs)) * (max(ys) - min(ys)) * pt_to_m ** 2
    total_room_m2 = sum(m.area_m2 for m in metrics)
    ratio = total_room_m2 / bb_area_m2 if bb_area_m2 > 0 else 0.0
    out: list[CheckFinding] = []
    if ratio > DEFAULTS["envelope_ratio_warn"]:
        out.append(CheckFinding(
            check_id="C11_total_area_vs_envelope",
            severity=WARN,
            target_kind="consensus",
            target_id=None,
            message=(
                f"total room area {total_room_m2:.1f} m^2 > "
                f"{DEFAULTS['envelope_ratio_warn']:.1f}x envelope "
                f"bbox {bb_area_m2:.1f} m^2 (ratio {ratio:.2f})"
            ),
            evidence={
                "total_room_area_m2": round(total_room_m2, 2),
                "envelope_bbox_area_m2": round(bb_area_m2, 2),
                "ratio": round(ratio, 2),
            },
        ))
    return out


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def evaluate_structural_health(
    consensus: dict,
    fidelity_report: dict | None = None,
    expected_model: dict | None = None,
) -> dict:
    """Run all 11 structural checks and return a single dict.

    Returns a dict shaped:

        {
          "schema_version": "structural_checks_v1",
          "structural_blockers": [<finding>, ...],
          "structural_warnings": [<finding>, ...],
          "per_room_metrics": [<RoomMetrics>, ...],
          "summary": {
              "blockers_count": int,
              "warnings_count": int,
              "rooms_with_blocker_count": int,
              "rooms_with_warning_count": int,
          }
        }

    The caller (gate F0) folds blockers_count > 0 into verdict=FAIL,
    warnings_count > 0 into verdict<=WARN.
    """
    pt_to_m = float(consensus.get("_pt_to_m") or PT_TO_M_DEFAULT)
    # Use wall_thickness_pts to back out a more precise PT_TO_M when
    # the canonical 0.19m wall is honored
    if "wall_thickness_pts" in consensus:
        try:
            pt_to_m = 0.19 / float(consensus["wall_thickness_pts"]) * (5.4 / 5.4)
            # ^ keeps 0.19/5.4 as the default if thickness IS 5.4
            # General formula: 0.19 m physical wall = wall_thickness_pts
            pt_to_m = 0.19 / float(consensus["wall_thickness_pts"])
        except (TypeError, ValueError):
            pt_to_m = PT_TO_M_DEFAULT

    metrics = _compute_room_metrics(consensus, pt_to_m)

    blockers: list[CheckFinding] = []
    warnings: list[CheckFinding] = []

    def _split(findings: list[CheckFinding]) -> None:
        for f in findings:
            (blockers if f.severity == FAIL else warnings).append(f)

    _split(_check_room_polygon_vts(metrics))
    _split(_check_free_vertex_ratio(metrics))
    _split(_check_polygon_in_envelope(metrics))
    _split(_check_polygon_simple(metrics))
    _split(_check_shape_complexity(metrics))
    _split(_check_long_diagonals(metrics))
    _split(_check_short_wall_fragments(consensus, pt_to_m))
    _split(_check_unmapped_colinear_gaps(consensus, pt_to_m))
    _split(_check_envelope_decomposition(consensus, pt_to_m))
    _split(_check_room_area_vs_expected(metrics, expected_model))
    _split(_check_total_area_vs_envelope(consensus, metrics, pt_to_m))

    rooms_with_blocker = {
        f.target_id for f in blockers
        if f.target_kind == "room" and f.target_id
    }
    rooms_with_warning = {
        f.target_id for f in warnings
        if f.target_kind == "room" and f.target_id
    }

    return {
        "schema_version": STRUCTURAL_CHECKS_SCHEMA_VERSION,
        "structural_blockers": [b.as_dict() for b in blockers],
        "structural_warnings": [w.as_dict() for w in warnings],
        "per_room_metrics": [m.as_dict() for m in metrics],
        "summary": {
            "blockers_count": len(blockers),
            "warnings_count": len(warnings),
            "rooms_with_blocker_count": len(rooms_with_blocker),
            "rooms_with_warning_count": len(rooms_with_warning),
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _format_summary(report: dict) -> str:
    s = report["summary"]
    lines = [
        f"# structural_checks_v1",
        f"blockers_count        {s['blockers_count']}",
        f"warnings_count        {s['warnings_count']}",
        f"rooms_with_blocker    {s['rooms_with_blocker_count']}",
        f"rooms_with_warning    {s['rooms_with_warning_count']}",
    ]
    if report["structural_blockers"]:
        lines.append("")
        lines.append("## blockers")
        for b in report["structural_blockers"]:
            lines.append(f"  [{b['check_id']}] {b['message']}")
    if report["structural_warnings"]:
        lines.append("")
        lines.append("## warnings")
        for w in report["structural_warnings"]:
            lines.append(f"  [{w['check_id']}] {w['message']}")
    return "\n".join(lines)


def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Run gamma structural health checks for FP-014 (pre-SKP gate)."
        ),
    )
    p.add_argument("consensus", type=Path,
                    help="path to consensus*.json")
    p.add_argument("--expected", type=Path, default=None,
                    help="optional expected_model.json (enables C10)")
    p.add_argument("--out", type=Path, default=None,
                    help="optional path to write the JSON report")
    p.add_argument("--strict", action="store_true",
                    help="exit non-zero if any blocker present")
    args = p.parse_args(argv)

    consensus = json.loads(args.consensus.read_text(encoding="utf-8"))
    expected = None
    if args.expected:
        expected = json.loads(args.expected.read_text(encoding="utf-8"))

    report = evaluate_structural_health(consensus, expected_model=expected)

    if args.out:
        args.out.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[wrote] {args.out}", file=sys.stderr)

    print(_format_summary(report))
    if args.strict and report["summary"]["blockers_count"] > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main())
