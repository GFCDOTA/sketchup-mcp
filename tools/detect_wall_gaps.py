"""Wall-gap detector — emits openings with ``geometry_origin: "wall_gap"``.

Brazilian sales-brochure PDFs draw doorways/passages as a BREAK in a wall
line: two collinear filled wall rectangles separated by a gap roughly the
width of a door (~70 cm) or a passage (up to ~3 m). The vector wall
extractor (``tools/build_vector_consensus.py``) reads each filled wall
rectangle as one ``WallSeg``. The arc/window detectors
(``tools/extract_openings_vector.py``) only fire when the architect
actually drew a swing arc or a glazing line. When neither is drawn, the
opening is invisible to those detectors — but the GAP between two
collinear walls is still observable evidence of a passage.

This module scans the wall set for those gaps and emits openings with
``geometry_origin: "wall_gap"``. The V5 classifier
(``tools/classify_opening_kind.py``) labels every wall_gap origin as
``open_passage``. No door arcs are invented: a wall_gap opening is just
"the wall stops here, then resumes there", which is what the PDF
literally drew.

Algorithm
---------
1. Group walls by orientation. For each group, cluster by collinear band
   (cross-axis centerline within ``thickness * collinearity_tol_factor``).
2. Within each band, sort by axis position and walk adjacent pairs.
   ``gap = wR_min - wL_max`` along the wall axis.
3. Emit a wall_gap opening when ``gap_min_pts <= gap <= gap_max_pts``
   AND no perpendicular wall crosses the gap region AND no existing
   opening already sits at the gap centroid.

Honest data per ``feedback_nao_fabricar_sem_medidas``: a wall_gap
opening is emitted only when the source PDF actually drew the wall
discontinuity. The detector neither invents gaps nor fills them in.

Schema-additive: ``kind`` stays ``"door"`` (the canonical value the Ruby
exporter understands) and the V5 classifier names it ``open_passage`` via
``kind_v5``. Two new optional fields are emitted:

* ``gap_neighbor_wall_id`` — the second wall bounding the gap
* ``gap_collinearity_offset_pts`` — cross-axis offset between the two
  walls' centerlines (0 = perfect alignment)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


# Defaults match the smallest sensible passage (~30 cm at 1:50) and the
# widest opening that still reads as a wall break before becoming "no
# wall here at all" (~3 m).
DEFAULT_GAP_MIN_PTS = 30.0
DEFAULT_GAP_MAX_PTS = 250.0

# Collinearity: walls in the same band share a centerline. We allow up
# to half the wall thickness of cross-axis drift, so a 4 pt thick wall
# tolerates ~2 pt of drawing imprecision.
DEFAULT_COLLINEARITY_TOL_FACTOR = 0.5

# Existing-opening dedupe: skip a candidate gap whose center lies within
# ``thickness * this`` of an already-detected opening (door arc, window).
EXISTING_OPENING_DEDUPE_FACTOR = 4.0

# Confidence ramp: the detector is observational but less certain than
# an explicit svg_arc. We scale collinearity quality + gap-width
# plausibility into [0, 1]. Ideal door ~75 PDF pts (~90 cm at 1:50).
IDEAL_DOOR_GAP_PTS = 75.0
GAP_PLAUSIBILITY_RANGE_PTS = 100.0


def _wall_axis_indexes(orientation: str) -> tuple[int, int]:
    """Return (axis_idx, cross_idx). 'h' walls vary in x, share y."""
    return (0, 1) if orientation == "h" else (1, 0)


def _wall_axis_range(wall: dict, axis_idx: int) -> tuple[float, float]:
    s = wall["start"][axis_idx]
    e = wall["end"][axis_idx]
    return (min(s, e), max(s, e))


def _wall_cross_position(wall: dict, cross_idx: int) -> float:
    """The wall's centerline along the cross axis. For an H wall this is
    the y where it sits; for a V wall it's the x. ``start`` and ``end``
    share the same cross value by construction."""
    return wall["start"][cross_idx]


def _group_collinear_bands(walls: list[dict], cross_idx: int,
                           tol: float) -> list[list[dict]]:
    """Cluster walls into bands whose cross-axis centerlines are within
    ``tol`` of each other. A band is a candidate for gap analysis."""
    bands: list[list[dict]] = []
    for w in walls:
        c = _wall_cross_position(w, cross_idx)
        placed = False
        for band in bands:
            band_c = _wall_cross_position(band[0], cross_idx)
            if abs(c - band_c) <= tol:
                band.append(w)
                placed = True
                break
        if not placed:
            bands.append([w])
    return bands


def _perpendicular_blocks_gap(center: tuple[float, float], gap: float,
                              orientation: str, walls: list[dict],
                              thickness: float) -> bool:
    """Returns True when a wall of the OPPOSITE orientation passes
    through the candidate gap. Such a wall is the actual continuation of
    the structure (e.g. a T-junction); the "gap" we'd emit would be a
    false positive standing in for a real corner."""
    cx, cy = center
    half_axis = gap / 2.0
    cross_band = thickness * 0.6
    if orientation == "h":
        for w in walls:
            if w["orientation"] != "v":
                continue
            wx = _wall_cross_position(w, 0)
            wy0, wy1 = _wall_axis_range(w, 1)
            if (cx - half_axis <= wx <= cx + half_axis
                    and wy0 - cross_band <= cy <= wy1 + cross_band):
                return True
    else:
        for w in walls:
            if w["orientation"] != "h":
                continue
            wy = _wall_cross_position(w, 1)
            wx0, wx1 = _wall_axis_range(w, 0)
            if (cy - half_axis <= wy <= cy + half_axis
                    and wx0 - cross_band <= cx <= wx1 + cross_band):
                return True
    return False


def _existing_opening_near(openings: list[dict], center: tuple[float, float],
                           radius: float) -> bool:
    cx, cy = center
    r2 = radius * radius
    for o in openings:
        oc = o.get("center")
        if not oc or len(oc) < 2:
            continue
        dx = oc[0] - cx
        dy = oc[1] - cy
        if dx * dx + dy * dy <= r2:
            return True
    return False


def _gap_confidence(gap: float, collinearity_offset: float,
                    thickness: float) -> float:
    """Confidence score in [0, 1]. Higher when the two walls are
    perfectly collinear and the gap matches a typical door width."""
    align = max(0.0, 1.0 - collinearity_offset / max(thickness, 1e-3))
    plausibility = max(
        0.0,
        1.0 - abs(gap - IDEAL_DOOR_GAP_PTS) / GAP_PLAUSIBILITY_RANGE_PTS,
    )
    return round(0.6 * align + 0.4 * plausibility, 3)


def _emit_gap(left_wall: dict, right_wall: dict, gap: float,
              center: tuple[float, float], collinearity_offset: float,
              thickness: float) -> dict[str, Any]:
    return {
        "center":           [round(center[0], 3), round(center[1], 3)],
        "kind":             "door",
        "geometry_origin":  "wall_gap",
        "confidence":       _gap_confidence(gap, collinearity_offset,
                                            thickness),
        "wall_id":          left_wall["id"],
        "opening_width_pts": round(gap, 3),
        "gap_neighbor_wall_id":         right_wall["id"],
        "gap_collinearity_offset_pts":  round(collinearity_offset, 3),
    }


def _scan_orientation(walls: list[dict], all_walls: list[dict],
                      orientation: str, gap_min: float, gap_max: float,
                      collinearity_tol: float, existing_openings: list[dict],
                      thickness: float) -> list[dict[str, Any]]:
    band_walls = [w for w in walls if w.get("orientation") == orientation]
    if len(band_walls) < 2:
        return []

    axis_idx, cross_idx = _wall_axis_indexes(orientation)
    bands = _group_collinear_bands(band_walls, cross_idx, collinearity_tol)
    dedupe_radius = thickness * EXISTING_OPENING_DEDUPE_FACTOR

    out: list[dict[str, Any]] = []
    for band in bands:
        if len(band) < 2:
            continue
        sorted_band = sorted(
            band,
            key=lambda w: _wall_axis_range(w, axis_idx)[0],
        )
        for i in range(len(sorted_band) - 1):
            wL = sorted_band[i]
            wR = sorted_band[i + 1]
            _, wL_max = _wall_axis_range(wL, axis_idx)
            wR_min, _ = _wall_axis_range(wR, axis_idx)
            gap = wR_min - wL_max
            if not (gap_min <= gap <= gap_max):
                continue

            cross_L = _wall_cross_position(wL, cross_idx)
            cross_R = _wall_cross_position(wR, cross_idx)
            cross_pos = (cross_L + cross_R) / 2.0
            collinearity_offset = abs(cross_L - cross_R)

            axis_center = (wL_max + wR_min) / 2.0
            if orientation == "h":
                center = (axis_center, cross_pos)
            else:
                center = (cross_pos, axis_center)

            if _perpendicular_blocks_gap(center, gap, orientation,
                                         all_walls, thickness):
                continue
            if _existing_opening_near(existing_openings + out, center,
                                      dedupe_radius):
                continue

            out.append(_emit_gap(wL, wR, gap, center,
                                 collinearity_offset, thickness))
    return out


def detect_wall_gaps(consensus: dict[str, Any], *,
                     gap_min_pts: float = DEFAULT_GAP_MIN_PTS,
                     gap_max_pts: float = DEFAULT_GAP_MAX_PTS,
                     collinearity_tol_factor: float =
                     DEFAULT_COLLINEARITY_TOL_FACTOR
                     ) -> dict[str, Any]:
    """Mutate ``consensus`` in place: append wall_gap openings to
    ``consensus["openings"]`` and stamp ``metadata.wall_gap_detector``.

    Returns the same dict for convenience. Walls / rooms /
    soft_barriers are untouched. Existing openings are preserved and
    new ids never collide with theirs.
    """
    walls = consensus.get("walls") or []
    existing = list(consensus.get("openings") or [])
    thickness = float(consensus.get("wall_thickness_pts") or 4.0)
    collinearity_tol = thickness * collinearity_tol_factor

    n_existing = len(existing)
    new_openings: list[dict[str, Any]] = []
    for orientation in ("h", "v"):
        new_openings.extend(_scan_orientation(
            walls, walls, orientation,
            gap_min_pts, gap_max_pts, collinearity_tol,
            existing + new_openings, thickness,
        ))

    # Sequential ids never collide with existing ones thanks to the 'g'
    # prefix; the arc/window detector uses 'o<i>'.
    for i, op in enumerate(new_openings):
        op["id"] = f"g{i:03d}"

    consensus["openings"] = existing + new_openings

    md = consensus.setdefault("metadata", {})
    md["wall_gap_detector"] = {
        "version": "1.0.0",
        "n_gaps_detected": len(new_openings),
        "n_openings_input": n_existing,
        "n_openings_output": len(consensus["openings"]),
        "gap_min_pts": gap_min_pts,
        "gap_max_pts": gap_max_pts,
        "collinearity_tol_pts": round(collinearity_tol, 3),
    }
    md["opening_count"] = len(consensus["openings"])
    return consensus


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("consensus", type=Path,
                    help="path to consensus_model.json (mutated in place "
                         "unless --out is set)")
    ap.add_argument("--out", type=Path, default=None,
                    help="write enriched consensus here; default: overwrite "
                         "input")
    ap.add_argument("--gap-min-pts", type=float, default=DEFAULT_GAP_MIN_PTS)
    ap.add_argument("--gap-max-pts", type=float, default=DEFAULT_GAP_MAX_PTS)
    ap.add_argument("--collinearity-tol-factor", type=float,
                    default=DEFAULT_COLLINEARITY_TOL_FACTOR)
    args = ap.parse_args()

    consensus = json.loads(args.consensus.read_text())
    detect_wall_gaps(
        consensus,
        gap_min_pts=args.gap_min_pts,
        gap_max_pts=args.gap_max_pts,
        collinearity_tol_factor=args.collinearity_tol_factor,
    )
    out = args.out or args.consensus
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(consensus, indent=2))
    md = consensus["metadata"]["wall_gap_detector"]
    print(f"[ok] wall_gap_detector: {md['n_gaps_detected']} gaps "
          f"({md['n_openings_input']} -> {md['n_openings_output']} "
          f"openings) -> {out}")


if __name__ == "__main__":
    main()
