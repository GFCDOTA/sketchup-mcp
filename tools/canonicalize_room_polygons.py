"""Snap room polygon vertices to wall-induced axis grids.

Why
---
`tools/rooms_from_seeds.py` detects rooms via a raster watershed: walls
are rasterised, label seeds expand outward, and the union of pixels
assigned to each seed is contoured back into a PDF-coord polygon. When
two rooms share an opening (no separating wall), the watershed boundary
between them becomes a 45° pixel-stair. After
``CHAIN_APPROX_TC89_L1`` + Douglas-Peucker simplify, those stairs
collapse into long diagonal edges (e.g. SALA DE ESTAR has a 39.77 pt
edge at exactly 45° between SALA DE ESTAR and TERRACO TECNICO — the
"mordida diagonal" V1 visible in
``runs/skp_current_*/sidebyside_pdf_vs_skp.png``).

The fix is local and safe: snap each room polygon vertex to the
nearest wall-induced axis (vertical wall x-edges or horizontal wall
y-edges), but only when the vertex is within ``tol_pts`` of an axis.
Vertices that already sit on an axis don't move; vertices truly off-
grid stay where they are. After snapping, consecutive duplicates are
deduped so the polygon stays simple.

The approach

* Does NOT touch the watershed algorithm or any threshold (no
  CLAUDE.md §1.3 trigger).
* Does NOT touch wall positions, the schema, openings, or the
  exporter.
* Operates per-room, so A.S. (a thin strip already aligned to walls)
  is preserved by construction — its vertices already sit on the
  wall grid.
* Is opt-in: callers must explicitly invoke ``canonicalize_rooms``;
  the default `detect_rooms` flow is unchanged unless the caller
  asks for it.

Usage
-----
    from tools.canonicalize_room_polygons import canonicalize_rooms
    walls = consensus["walls"]
    t = consensus["wall_thickness_pts"]
    consensus["rooms"] = canonicalize_rooms(consensus["rooms"], walls, t)
"""

from __future__ import annotations

from typing import Iterable

# Default snap tolerance is roughly one wall thickness. The watershed
# stair-step amplitude is bounded by 1 / scale_factor (raster scale = 8
# px/pt -> 0.125 pt per pixel) plus the contour simplify tolerance
# (0.5 pt). One wall thickness (~5 pt on planta_74) covers both with
# margin while staying well below the smallest legitimate non-grid
# offset we'd expect on this scale.
DEFAULT_SNAP_TOL_PTS = 5.0


def axis_grids_from_walls(
    walls: Iterable[dict], thickness_pts: float
) -> tuple[list[float], list[float]]:
    """Return sorted (x_axes, y_axes) lists derived from wall edges.

    For every wall we add both edges (centerline ± thickness/2) to the
    matching axis: a vertical wall contributes two x-values, a
    horizontal wall contributes two y-values. Centerlines are NOT added
    to keep the grid pure — room polygons trace wall faces, not centers.
    """
    xs: set[float] = set()
    ys: set[float] = set()
    half_t = thickness_pts / 2.0
    for w in walls:
        s = w["start"]
        e = w["end"]
        orient = w.get("orientation")
        if orient == "v":
            cx = s[0]
            xs.add(cx - half_t)
            xs.add(cx + half_t)
        elif orient == "h":
            cy = s[1]
            ys.add(cy - half_t)
            ys.add(cy + half_t)
        else:
            # Unknown orientation: still try to learn axes from endpoints.
            if abs(e[0] - s[0]) < 1e-3:
                xs.add(s[0] - half_t)
                xs.add(s[0] + half_t)
            elif abs(e[1] - s[1]) < 1e-3:
                ys.add(s[1] - half_t)
                ys.add(s[1] + half_t)
    return sorted(xs), sorted(ys)


def _nearest(value: float, candidates: list[float]) -> tuple[float, float]:
    """Closest candidate to ``value`` and the absolute distance to it."""
    if not candidates:
        return value, float("inf")
    best = min(candidates, key=lambda a: abs(a - value))
    return best, abs(best - value)


def snap_polygon(
    polygon_pts: list[list[float]],
    x_axes: list[float],
    y_axes: list[float],
    tol_pts: float = DEFAULT_SNAP_TOL_PTS,
) -> list[list[float]]:
    """Snap each vertex's x and y to the closest axis within ``tol_pts``.

    Vertices outside ``tol_pts`` of any axis stay put. Consecutive
    vertices that collapse to the same point are deduplicated. A polygon
    that becomes degenerate (< 4 distinct vertices) is returned in its
    original form to avoid corrupting the schema.
    """
    if not polygon_pts:
        return polygon_pts

    snapped: list[list[float]] = []
    for x, y in polygon_pts:
        sx, dx = _nearest(x, x_axes)
        sy, dy = _nearest(y, y_axes)
        nx = sx if dx <= tol_pts else x
        ny = sy if dy <= tol_pts else y
        snapped.append([round(nx, 3), round(ny, 3)])

    # Dedupe consecutive duplicates (closing seam handled separately).
    deduped: list[list[float]] = []
    for v in snapped:
        if not deduped or deduped[-1] != v:
            deduped.append(v)
    # Polygon close: drop trailing duplicate of the first vertex.
    if len(deduped) >= 2 and deduped[-1] == deduped[0]:
        deduped.pop()

    if len(deduped) < 4:
        return polygon_pts
    return deduped


def canonicalize_rooms(
    rooms: list[dict],
    walls: list[dict],
    thickness_pts: float,
    tol_pts: float = DEFAULT_SNAP_TOL_PTS,
) -> list[dict]:
    """Return a new rooms list with each polygon snapped to wall axes.

    Each room dict is shallow-copied with ``polygon_pts`` replaced; all
    other fields (id, name, area_pts2, seed_pt, ...) are preserved
    verbatim. Empty rooms list is returned unchanged.
    """
    if not rooms:
        return rooms
    x_axes, y_axes = axis_grids_from_walls(walls, thickness_pts)
    out: list[dict] = []
    for r in rooms:
        new_r = dict(r)
        new_r["polygon_pts"] = snap_polygon(
            r.get("polygon_pts", []), x_axes, y_axes, tol_pts
        )
        out.append(new_r)
    return out


def diagonal_signature(polygon_pts: list[list[float]]) -> dict:
    """Diagnostic helper: count axis-aligned vs diagonal segments.

    Returns ``{"n_segments": N, "axis": A, "near_orth": NO, "diag": D,
    "diag_total_len": float}`` where:
      - axis: edges within 0.5° of horizontal/vertical
      - near_orth: edges within 5° (raster snap residue)
      - diag: edges 5° or more off axis (the V1 signature)
    """
    import math

    if not polygon_pts or len(polygon_pts) < 2:
        return {"n_segments": 0, "axis": 0, "near_orth": 0, "diag": 0,
                "diag_total_len": 0.0}
    n = len(polygon_pts)
    counts = {"axis": 0, "near_orth": 0, "diag": 0}
    diag_total = 0.0
    for i in range(n):
        x0, y0 = polygon_pts[i]
        x1, y1 = polygon_pts[(i + 1) % n]
        dx = x1 - x0
        dy = y1 - y0
        L = math.hypot(dx, dy)
        if L < 1e-3:
            continue
        angle = math.degrees(math.atan2(dy, dx)) % 180
        d_axis = min(abs(angle - 0), abs(angle - 90), abs(angle - 180))
        if d_axis < 0.5:
            counts["axis"] += 1
        elif d_axis < 5:
            counts["near_orth"] += 1
        else:
            counts["diag"] += 1
            diag_total += L
    return {
        "n_segments": n,
        **counts,
        "diag_total_len": round(diag_total, 3),
    }
