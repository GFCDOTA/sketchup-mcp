"""Room polygonization via wall-rectangle subtraction.

Walls in vector PDFs are slim filled rectangles whose BODIES (not just
centerlines) carry the geometry. Polygonising centerlines fails when
adjacent walls are joined via short connector segments rather than
sharing endpoints exactly. The robust approach:

  1. Build the union of all wall rectangles → wall_mask (MultiPolygon).
  2. Detect door openings: pairs of collinear wall ends with a gap
     in the door range → synthesise a door-bridge RECTANGLE of full
     thickness covering the gap.
  3. Add bridges to wall_mask. Now door openings are sealed.
  4. Take the planta envelope (bbox + margin), subtract the
     wall_mask. The result is a MultiPolygon whose connected pieces
     are rooms (the very largest piece is the OUTSIDE — it touches
     the envelope border on all sides — which we drop).
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

# Semantic keywords that mark a soft_barrier as a legitimate peitoril
# /mureta/guarda — these are the only barriers eligible for near-miss
# endpoint extension. Wall-coincident SBs (FP-006) MUST never be
# extended, regardless of label, since they're noise from the V7
# extractor catching wall edges as peitoris.
_SEMANTIC_BARRIER_KEYWORDS = (
    "peitoril", "mureta", "guarda", "esquadria", "parapet",
)
_SEMANTIC_BARRIER_TYPES = frozenset({
    "peitoril", "mureta", "guarda_corpo", "esquadria", "parapet",
})


def _wall_to_box(w: dict, t: float, end_extend: float = 0.0) -> Polygon:
    """Wall as a filled rect. ``end_extend`` lengthens the rect along
    the wall's long axis (BOTH ends) so T-junctions close: a partition
    that almost touches a backbone wall, but stops a fraction of t
    short, will reach into the backbone after extension. The thickness
    axis is left alone so rooms keep their drawn dimensions."""
    s, e = w["start"], w["end"]
    if w["orientation"] == "h":
        x0, x1 = sorted([s[0], e[0]])
        cy = s[1]
        return box(x0 - end_extend, cy - t / 2, x1 + end_extend, cy + t / 2)
    else:
        cx = s[0]
        y0, y1 = sorted([s[1], e[1]])
        return box(cx - t / 2, y0 - end_extend, cx + t / 2, y1 + end_extend)


def _detect_door_bridges(walls: list[dict], t: float,
                         door_min: float, door_max: float) -> list[dict]:
    coll_tol = t * 0.5
    bins: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for w in walls:
        const = w["start"][1] if w["orientation"] == "h" else w["start"][0]
        bins[(w["orientation"], int(round(const / coll_tol)))].append(w)

    grouped: list[list[dict]] = []
    seen: set[tuple[str, int]] = set()
    for k in sorted(bins):
        if k in seen:
            continue
        cluster = list(bins[k])
        seen.add(k)
        if (k[0], k[1] + 1) in bins:
            cluster.extend(bins[(k[0], k[1] + 1)])
            seen.add((k[0], k[1] + 1))
        grouped.append(cluster)

    bridges: list[dict] = []
    bid = 0
    for cluster in grouped:
        if len(cluster) < 2:
            continue
        ori = cluster[0]["orientation"]
        if ori == "h":
            cluster.sort(key=lambda w: min(w["start"][0], w["end"][0]))
        else:
            cluster.sort(key=lambda w: min(w["start"][1], w["end"][1]))
        for i in range(len(cluster) - 1):
            a, b = cluster[i], cluster[i + 1]
            if ori == "h":
                a_end = max(a["start"][0], a["end"][0])
                b_start = min(b["start"][0], b["end"][0])
                gap = b_start - a_end
                if door_min <= gap <= door_max:
                    cy = (a["start"][1] + b["start"][1]) / 2.0
                    bridges.append({
                        "id": f"door_{bid:03d}",
                        "start": [a_end, cy],
                        "end": [b_start, cy],
                        "thickness": t,
                        "orientation": "h",
                        "synthetic": True,
                    })
                    bid += 1
            else:
                a_end = max(a["start"][1], a["end"][1])
                b_start = min(b["start"][1], b["end"][1])
                gap = b_start - a_end
                if door_min <= gap <= door_max:
                    cx = (a["start"][0] + b["start"][0]) / 2.0
                    bridges.append({
                        "id": f"door_{bid:03d}",
                        "start": [cx, a_end],
                        "end": [cx, b_start],
                        "thickness": t,
                        "orientation": "v",
                        "synthetic": True,
                    })
                    bid += 1
    return bridges


def _soft_barriers_to_polys(barriers: list[dict], width_pts: float) -> list[Polygon]:
    """Buffer each soft_barrier polyline into a thin closed strip.

    Soft_barriers carry non-structural separators (peitoril, grade,
    terraço outlines) that bound rooms but are NOT load-bearing walls.
    Polygonize needs them in the wall_union to close interior cells —
    without them a vector PDF planta with peitoris keeps 60–80 % of
    its rooms open (env.difference returns one giant merged "outside"
    region and only a couple of small enclosed cells, FP-014 §"Opção A"
    failure mode observed on planta_74). Buffered as thin (``width_pts``)
    strips so the envelope cap doesn't shrink room interiors.
    """
    polys: list[Polygon] = []
    if width_pts <= 0:
        return polys
    half = width_pts / 2.0
    for b in barriers:
        pts = b.get("polyline_pts", [])
        if not pts or len(pts) < 2:
            continue
        try:
            ls = LineString([(float(p[0]), float(p[1])) for p in pts])
            polys.append(ls.buffer(half, cap_style="flat"))
        except Exception:
            continue
    return polys


# ---- soft-barrier near-miss extension (Frente 3 — 2026-05-21) -------


def _sb_overlap_fraction_with_walls(barrier: dict, walls: list[dict],
                                    thickness_pt: float,
                                    tol_pt: float = 1.0) -> float:
    """Mirror of the FP-006 3-point sample, but returns a continuous
    fraction in [0, 1]: the proportion of the polyline's total length
    whose midpoint sits inside any wall's axis-aligned footprint.

    Used as a SAFETY GUARD before extending a near-miss SB: an SB whose
    polyline is mostly coincident with a wall is FP-006 noise (sb000…
    sb003, sb005…sb007 on planta_74), not a peitoril, and must NOT be
    extended — extending it would carve real walls.
    """
    pts = barrier.get("polyline_pts", [])
    if len(pts) < 2:
        return 0.0
    half = thickness_pt / 2.0
    wall_rects: list[tuple[float, float, float, float]] = []
    for w in walls:
        s = w.get("start")
        e = w.get("end")
        if not s or not e:
            continue
        ori = w.get("orientation")
        if ori == "h":
            x0, x1 = sorted([s[0], e[0]])
            cy = s[1]
            wall_rects.append((x0 - tol_pt, cy - half - tol_pt,
                               x1 + tol_pt, cy + half + tol_pt))
        elif ori == "v":
            cx = s[0]
            y0, y1 = sorted([s[1], e[1]])
            wall_rects.append((cx - half - tol_pt, y0 - tol_pt,
                               cx + half + tol_pt, y1 + tol_pt))

    def _inside_any(px: float, py: float) -> bool:
        return any(x0 <= px <= x1 and y0 <= py <= y1
                   for x0, y0, x1, y1 in wall_rects)

    total = 0.0
    inside = 0.0
    for i in range(len(pts) - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        seg_len = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        total += seg_len
        mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
        if _inside_any(mx, my):
            inside += seg_len
    return inside / total if total > 0 else 0.0


def _sb_has_semantic_origin(barrier: dict) -> bool:
    """True iff the SB looks like a real peitoril/mureta/guarda by
    schema field OR by free-text annotation. Hard signals first:

      - geometry_origin == 'human_annotation' (CYAN painted barrier
        from the human_soft_barrier protocol — operator-confirmed real)
      - barrier_type in {peitoril, mureta, guarda_corpo, esquadria, parapet}

    Soft signal: case-insensitive keyword in id / name / label.
    """
    origin = (barrier.get("geometry_origin") or "").strip().lower()
    if origin == "human_annotation":
        return True
    btype = (barrier.get("barrier_type") or "").strip().lower()
    if btype in _SEMANTIC_BARRIER_TYPES:
        return True
    # Free-text fallback: id/name/label may carry the PDF text annotation.
    blob = " ".join(str(barrier.get(k, "")) for k in
                    ("id", "name", "label", "annotation")).lower()
    return any(kw in blob for kw in _SEMANTIC_BARRIER_KEYWORDS)


def _is_suspicious_cell(poly: Polygon, median_area: float,
                        area_factor: float = 2.0,
                        concavity_threshold: float = 0.30) -> bool:
    """A polygonize cell is a candidate for SB-extension splitting when
    it's an area outlier OR significantly concave.

    Heuristic (no seed info available at polygonize layer):
      area_m2 > area_factor × median(areas), OR
      1 - area / convex_hull.area > concavity_threshold

    Both signals catch the 'merged 3-rooms' polygon on planta_74 (r001
    area=28.21 vs median=11.68 → factor 2.41; concavity=0.19 → fails the
    concavity check but flagged by area). The OR is intentional — relying
    on either signal alone would miss roughly-rectangular merges.
    """
    if median_area <= 0:
        return False
    if poly.area > area_factor * median_area:
        return True
    try:
        hull_area = poly.convex_hull.area
        if hull_area > 0:
            concavity = 1.0 - poly.area / hull_area
            if concavity > concavity_threshold:
                return True
    except Exception:
        pass
    return False


def _try_extend_endpoint(
    polyline_pts: list[list[float]],
    endpoint_idx: int,
    suspicious_cells: list[Polygon],
    *,
    gap_tol_pt: float,
    step_pt: float = 0.5,
) -> tuple[list[float] | None, float, int | None]:
    """Probe a single endpoint of a polyline for a near-miss extension.

    "Near-miss" is the specific case where the endpoint sits OUTSIDE
    every suspicious cell but is close enough that extending OUTWARD
    (in the polyline's direction at that end) by ``<= gap_tol_pt``
    puts it inside one of the cells' interiors. The function returns
    ``(adjusted_endpoint, gap_pt, cell_index)`` for the first such
    crossing. If the endpoint is ALREADY inside a suspicious cell —
    not a near-miss at all — the function returns
    ``(None, 0.0, None)`` so we never apply useless cosmetic
    extensions on deep-interior endpoints.

    Why this matters: an earlier draft returned at the first step that
    "the polyline crosses interior", which fires immediately when one
    endpoint is already deep inside a cell (the polyline is already
    crossing!). That produced 0.5pt extensions that didn't change the
    polygonize topology at all (verified on planta_74's h_sb000
    endpoint A=[105, 429.7] — it sits 49pt inside cell[5], so the
    polyline obviously crosses interior; extending A by 0.5pt outward
    is meaningless geometrically and pollutes the provenance log).
    """
    if len(polyline_pts) < 2:
        return (None, 0.0, None)
    if endpoint_idx not in (0, -1):
        raise ValueError(f"endpoint_idx must be 0 or -1, got {endpoint_idx}")

    end_pt = polyline_pts[endpoint_idx]
    neighbour_idx = 1 if endpoint_idx == 0 else -2
    near_pt = polyline_pts[neighbour_idx]

    # Pre-check: skip if endpoint is already inside any suspicious cell
    # (interior OR boundary). This is the "not a near-miss at all" case.
    # We use ``covers`` rather than ``contains`` because shapely's
    # ``contains`` excludes the boundary — a polyline endpoint that
    # sits exactly on the cell boundary (e.g. planta_74's h_sb000
    # endpoint A=[105, 429.7] sits on cell[2]'s boundary at the
    # building outline trace) would otherwise slip through and trigger
    # a useless 0.5pt extension.
    from shapely.geometry import Point as _Point
    endpoint_geom = _Point(float(end_pt[0]), float(end_pt[1]))
    for cell in suspicious_cells:
        if cell.covers(endpoint_geom):
            return (None, 0.0, None)

    dx = float(end_pt[0]) - float(near_pt[0])
    dy = float(end_pt[1]) - float(near_pt[1])
    seg_len = (dx * dx + dy * dy) ** 0.5
    if seg_len < 1e-9:
        return (None, 0.0, None)
    ux, uy = dx / seg_len, dy / seg_len

    # Walk outward in step_pt increments. Accept the FIRST step where
    # the extended endpoint enters a suspicious cell's interior — that
    # bridges the near-miss gap minimally without overshooting.
    n_steps = max(1, int(gap_tol_pt / step_pt))
    for k in range(1, n_steps + 1):
        d = k * step_pt
        new_pt = (float(end_pt[0]) + ux * d, float(end_pt[1]) + uy * d)
        new_pt_geom = _Point(new_pt[0], new_pt[1])
        for ci, cell in enumerate(suspicious_cells):
            interior = cell.buffer(-1e-3)
            if not interior.is_valid or interior.is_empty:
                continue
            if interior.contains(new_pt_geom):
                return ([round(new_pt[0], 6), round(new_pt[1], 6)],
                        round(d, 4), ci)
    return (None, 0.0, None)


def extend_near_miss_soft_barriers(
    walls: list[dict],
    soft_barriers: list[dict],
    base_cells: list[Polygon],
    wall_thickness_pts: float,
    *,
    gap_tol_pt: float = 8.0,
    fp006_overlap_threshold: float = 0.50,
    require_semantic_origin: bool = True,
    area_factor: float = 2.0,
    concavity_threshold: float = 0.30,
) -> tuple[list[dict], list[dict]]:
    """Return (extended_soft_barriers, provenance).

    For each SB that passes the safety guards (FP-006 wall-overlap
    threshold + semantic origin), probe each polyline endpoint for a
    near-miss extension that would enter the interior of a suspicious
    cell. Extension is capped at ``gap_tol_pt`` and only applied when
    the probe genuinely crosses the cell interior.

    Suspicious cells are detected via ``_is_suspicious_cell`` on the
    median of the base cell areas — caller-provided ``base_cells`` are
    the polygons produced by a polygonize pass WITHOUT extension.

    The original ``polyline_pts`` are preserved by writing them to
    ``polyline_pts_original`` on the extended entries. ``provenance``
    is a list of dicts with the schema documented in
    ``_try_extend_endpoint`` — one record per applied extension.
    """
    if not soft_barriers or not base_cells:
        return ([dict(sb) for sb in soft_barriers], [])
    areas = sorted(c.area for c in base_cells if c.area > 0)
    if not areas:
        return ([dict(sb) for sb in soft_barriers], [])
    median_area = areas[len(areas) // 2]
    suspicious = [c for c in base_cells
                  if _is_suspicious_cell(c, median_area,
                                          area_factor=area_factor,
                                          concavity_threshold=concavity_threshold)]
    if not suspicious:
        return ([dict(sb) for sb in soft_barriers], [])

    extended: list[dict] = []
    provenance: list[dict] = []
    for sb in soft_barriers:
        copy = dict(sb)
        pts = sb.get("polyline_pts", [])
        if len(pts) < 2:
            extended.append(copy)
            continue
        # Guard 1: FP-006 wall coincidence (NEVER extend a noise SB).
        overlap_frac = _sb_overlap_fraction_with_walls(
            sb, walls, wall_thickness_pts)
        if overlap_frac > fp006_overlap_threshold:
            extended.append(copy)
            continue
        # Guard 2: semantic origin (peitoril/mureta/etc).
        if require_semantic_origin and not _sb_has_semantic_origin(sb):
            extended.append(copy)
            continue
        # Probe both endpoints.
        new_pts = [[float(p[0]), float(p[1])] for p in pts]
        candidate_records: list[dict] = []
        for endpoint_idx in (0, -1):
            new_endpoint, gap, ci = _try_extend_endpoint(
                new_pts, endpoint_idx, suspicious,
                gap_tol_pt=gap_tol_pt,
            )
            if new_endpoint is None:
                continue
            original = list(pts[endpoint_idx])
            new_pts[endpoint_idx] = new_endpoint
            candidate_records.append({
                "source_soft_barrier_id": sb.get("id"),
                "endpoint_index": endpoint_idx,
                "original_endpoint_pt": [round(original[0], 4),
                                          round(original[1], 4)],
                "adjusted_endpoint_pt": new_endpoint,
                "gap_pt": gap,
                "affected_cell_index": ci,
                "reason_code": "soft_barrier_near_miss_split",
                "fp006_overlap_fraction": round(overlap_frac, 4),
                "geometry_origin": sb.get("geometry_origin"),
                "barrier_type": sb.get("barrier_type"),
            })
        if candidate_records:
            copy["polyline_pts"] = new_pts
            copy["polyline_pts_original"] = [list(p) for p in pts]
            provenance.extend(candidate_records)
        extended.append(copy)

    return (extended, provenance)


def _validate_extension_effectiveness(
    walls: list[dict],
    base_soft_barriers: list[dict],
    extended_soft_barriers: list[dict],
    thickness_pt: float,
    *,
    door_min_pts: float,
    door_max_pts: float,
    envelope_margin_pts: float,
    min_room_area_factor: float,
    planta_region: tuple | None,
    sb_width_pts: float,
    use_soft_barriers: bool,
    min_cell_count_delta: int = 1,
    min_area_reduction_factor: float = 0.20,
) -> tuple[bool, dict]:
    """Confirm an extension actually changes the polygonize topology.

    Re-runs polygonize twice — once with the original SBs, once with
    the extended ones — and checks one of:
      a) new cell count exceeds baseline by ``min_cell_count_delta`` (a
         genuine split occurred);
      b) any baseline suspicious cell's area shrinks by at least
         ``min_area_reduction_factor`` (the cell was bisected or
         significantly reshaped).

    Returns ``(is_effective, delta_report)`` where ``delta_report`` is
    diagnostic info suitable for the provenance log.
    """
    base = _polygonize_cells_only(
        walls, base_soft_barriers, thickness_pt,
        door_min_pts=door_min_pts, door_max_pts=door_max_pts,
        envelope_margin_pts=envelope_margin_pts,
        min_room_area_factor=min_room_area_factor,
        planta_region=planta_region, sb_width_pts=sb_width_pts,
        use_soft_barriers=use_soft_barriers,
    )
    after = _polygonize_cells_only(
        walls, extended_soft_barriers, thickness_pt,
        door_min_pts=door_min_pts, door_max_pts=door_max_pts,
        envelope_margin_pts=envelope_margin_pts,
        min_room_area_factor=min_room_area_factor,
        planta_region=planta_region, sb_width_pts=sb_width_pts,
        use_soft_barriers=use_soft_barriers,
    )
    delta_count = len(after) - len(base)
    base_areas = sorted([c.area for c in base], reverse=True)
    after_areas = sorted([c.area for c in after], reverse=True)
    # Largest baseline cell shrink (signal a bisection event)
    largest_shrink_frac = 0.0
    if base_areas and after_areas:
        for ba in base_areas[:5]:  # check top 5 baseline cells
            # Find closest matching after-cell by area for fair comparison
            # (cell ordering can shuffle on small geometry changes).
            closest = min(after_areas, key=lambda a: abs(a - ba))
            if ba > 0 and closest < ba:
                shrink = 1.0 - closest / ba
                if shrink > largest_shrink_frac:
                    largest_shrink_frac = shrink
    is_effective = (
        delta_count >= min_cell_count_delta
        or largest_shrink_frac >= min_area_reduction_factor
    )
    return is_effective, {
        "base_cell_count": len(base),
        "after_cell_count": len(after),
        "cell_count_delta": delta_count,
        "largest_shrink_fraction": round(largest_shrink_frac, 4),
    }


def _polygonize_cells_only(walls: list[dict], soft_barriers: list[dict],
                           thickness_pt: float, *,
                           door_min_pts: float, door_max_pts: float,
                           envelope_margin_pts: float,
                           min_room_area_factor: float,
                           planta_region: tuple | None,
                           sb_width_pts: float,
                           use_soft_barriers: bool) -> list[Polygon]:
    """Internal: run the wall+SB union → env.difference pipeline once
    and return only the interior cell Polygons (no naming, no dict
    wrapping). Used by ``polygonize_rooms`` to compute a baseline cell
    set when the near-miss extension feature is enabled.

    Mirrors the main code path in ``polygonize_rooms`` deliberately —
    keeping the two in lock-step so the baseline matches the
    pre-extension pass's geometry exactly.
    """
    bridges = _detect_door_bridges(walls, thickness_pt,
                                    door_min_pts, door_max_pts)
    all_walls = walls + bridges
    wall_polys = [_wall_to_box(w, thickness_pt, end_extend=thickness_pt)
                  for w in all_walls]
    if use_soft_barriers:
        wall_polys.extend(_soft_barriers_to_polys(soft_barriers, sb_width_pts))
    wall_union = unary_union(wall_polys)
    if planta_region:
        env = box(planta_region[0] - envelope_margin_pts,
                  planta_region[1] - envelope_margin_pts,
                  planta_region[2] + envelope_margin_pts,
                  planta_region[3] + envelope_margin_pts)
    else:
        env = wall_union.envelope.buffer(envelope_margin_pts)
    interior = env.difference(wall_union)
    if interior.is_empty:
        return []
    parts = list(interior.geoms) if hasattr(interior, "geoms") else [interior]
    env_xmin, env_ymin, env_xmax, env_ymax = env.bounds
    eps = 1e-3
    out: list[Polygon] = []
    min_area = min_room_area_factor * thickness_pt * thickness_pt
    for p in parts:
        bx0, by0, bx1, by1 = p.bounds
        touches_all = (bx0 <= env_xmin + eps and bx1 >= env_xmax - eps
                       and by0 <= env_ymin + eps and by1 >= env_ymax - eps)
        if touches_all:
            continue
        if p.area < min_area:
            continue
        out.append(p)
    return out


def polygonize_rooms(consensus: dict,
                     door_min_pts: float = 15.0,
                     door_max_pts: float = 50.0,
                     envelope_margin_pts: float = 2.0,
                     min_room_area_factor: float = 12.0,
                     use_soft_barriers: bool = True,
                     soft_barrier_width_pts: float | None = None,
                     extend_near_miss_sbs: bool = False,
                     near_miss_gap_tol_pt: float = 8.0,
                     near_miss_fp006_threshold: float = 0.50,
                     near_miss_require_semantic: bool = True,
                     near_miss_area_factor: float = 2.0,
                     near_miss_concavity_threshold: float = 0.30,
                     extension_provenance_out: list[dict] | None = None,
                     ) -> tuple[list[dict], list[dict]]:
    """Polygonize rooms via wall-rectangle subtraction.

    When ``extend_near_miss_sbs=True``, a pre-pass detects suspicious
    cells (area outliers + highly concave polygons) in the baseline
    layout, then attempts to extend the endpoints of any peitoril/mureta
    soft_barriers that stop just outside a suspicious cell's interior.
    Extensions are capped at ``near_miss_gap_tol_pt`` (default 8 pt) and
    guarded by an FP-006 wall-overlap threshold + semantic origin filter
    (see ``extend_near_miss_soft_barriers``). The default is OFF so all
    existing callers see byte-equivalent behaviour.

    ``extension_provenance_out``: when a list is passed, the function
    appends one record per applied extension. The caller is responsible
    for stamping these into the consensus metadata so the change is
    auditable.
    """
    walls = consensus["walls"]
    t = consensus["wall_thickness_pts"]

    sb_width = (soft_barrier_width_pts
                if soft_barrier_width_pts is not None else 0.4 * t)

    soft_barriers = consensus.get("soft_barriers", []) if use_soft_barriers else []

    # Optional pre-pass: extend near-miss soft_barriers so they cross
    # the interior of an otherwise-merged cell. Pipeline:
    #
    #   (a) polygonize once with ORIGINAL SBs → baseline cells
    #   (b) extend_near_miss_soft_barriers → candidate extensions
    #   (c) _validate_extension_effectiveness → only keep extensions
    #       that actually change polygonize topology
    #
    # Step (c) is critical: a candidate extension is rejected when it
    # adjusts an endpoint but doesn't change cell count nor shrink any
    # baseline suspicious cell by ≥20%. This protects against the
    # "polyline already crosses but ends in interior" failure mode
    # documented on planta_74 (h_sb000 endpoint A sits on cell[2]
    # boundary; sb004 endpoint A extends into an adjacent cell but
    # doesn't reform any merged cell). Rejected candidates are still
    # recorded in provenance with ``applied=False`` so the audit
    # trail shows what was tried.
    original_soft_barriers = list(soft_barriers)
    if extend_near_miss_sbs and soft_barriers:
        baseline_cells = _polygonize_cells_only(
            walls, soft_barriers, t,
            door_min_pts=door_min_pts, door_max_pts=door_max_pts,
            envelope_margin_pts=envelope_margin_pts,
            min_room_area_factor=min_room_area_factor,
            planta_region=consensus.get("planta_region"),
            sb_width_pts=sb_width,
            use_soft_barriers=True,
        )
        candidate_sbs, candidate_prov = extend_near_miss_soft_barriers(
            walls, soft_barriers, baseline_cells, t,
            gap_tol_pt=near_miss_gap_tol_pt,
            fp006_overlap_threshold=near_miss_fp006_threshold,
            require_semantic_origin=near_miss_require_semantic,
            area_factor=near_miss_area_factor,
            concavity_threshold=near_miss_concavity_threshold,
        )
        applied = False
        eff_report: dict = {}
        if candidate_prov:
            applied, eff_report = _validate_extension_effectiveness(
                walls, original_soft_barriers, candidate_sbs, t,
                door_min_pts=door_min_pts, door_max_pts=door_max_pts,
                envelope_margin_pts=envelope_margin_pts,
                min_room_area_factor=min_room_area_factor,
                planta_region=consensus.get("planta_region"),
                sb_width_pts=sb_width, use_soft_barriers=True,
            )
            for rec in candidate_prov:
                rec["applied"] = applied
                rec["effectiveness_report"] = eff_report
            if extension_provenance_out is not None:
                extension_provenance_out.extend(candidate_prov)
        if applied:
            soft_barriers = candidate_sbs

    bridges = _detect_door_bridges(walls, t, door_min_pts, door_max_pts)
    all_walls = walls + bridges

    # End-extend by t so partition walls reach into the backbone wall
    # at T-junctions; the perpendicular wall absorbs the overshoot.
    wall_polys = [_wall_to_box(w, t, end_extend=t) for w in all_walls]

    # Soft barriers (peitoris, grades, terraço outlines) close interior
    # cells that walls alone leave open — without them, polygonize on
    # vector-PDF plantas with peitoris collapses most rooms into the
    # outside cell. Buffer width defaults to a thin strip (~0.4 × wall
    # thickness) so the envelope cap doesn't eat room interiors.
    if use_soft_barriers:
        wall_polys.extend(_soft_barriers_to_polys(soft_barriers, sb_width))

    wall_union = unary_union(wall_polys)

    # If the wall network still has multiple disconnected components,
    # bridge the closest pair of components iteratively until merged.
    # This handles partition walls that don't quite touch a backbone
    # at any door-aligned axis (e.g. a freestanding partition wall
    # between two rooms whose ends fall slightly short of the
    # neighbouring backbone walls).
    if wall_union.geom_type == "MultiPolygon":
        comps = list(wall_union.geoms)
        max_iter = len(comps) + 5
        merge_bridges: list[Polygon] = []
        while len(comps) > 1 and max_iter > 0:
            max_iter -= 1
            comps.sort(key=lambda p: -p.area)
            biggest = comps[0]
            best = None
            best_d = float("inf")
            for other in comps[1:]:
                d = biggest.distance(other)
                if d < best_d:
                    best_d = d
                    best = other
            # Use a more permissive distance for merging components
            # than the door range — partitions can sit further from
            # backbone walls than a typical door width.
            if best is None or best_d > door_max_pts * 4:
                break
            # Pair of nearest points between biggest and best
            from shapely.ops import nearest_points
            p1, p2 = nearest_points(biggest, best)
            # Build a thin bridge rectangle along the segment p1→p2
            dx = p2.x - p1.x
            dy = p2.y - p1.y
            length = (dx * dx + dy * dy) ** 0.5
            if length < 1e-6:
                # Tangent/touching but treated as separate by float
                # imprecision; pad with a unit box to seal them.
                bridge = box(p1.x - t / 2, p1.y - t / 2,
                             p1.x + t / 2, p1.y + t / 2)
            else:
                from shapely.geometry import LineString as _LS
                bridge = _LS([(p1.x, p1.y), (p2.x, p2.y)]).buffer(t / 2,
                                                                   cap_style="square")
            merge_bridges.append(bridge)
            wall_union = unary_union([wall_union, bridge])
            comps = (list(wall_union.geoms) if wall_union.geom_type == "MultiPolygon"
                     else [wall_union])

    region = consensus.get("planta_region")
    if region:
        env = box(region[0] - envelope_margin_pts,
                  region[1] - envelope_margin_pts,
                  region[2] + envelope_margin_pts,
                  region[3] + envelope_margin_pts)
    else:
        env = wall_union.envelope.buffer(envelope_margin_pts)

    interior = env.difference(wall_union)
    if interior.is_empty:
        return [], bridges
    parts = list(interior.geoms) if hasattr(interior, "geoms") else [interior]
    parts.sort(key=lambda p: -p.area)

    # The OUTSIDE piece is the one that wraps the entire planta — it
    # touches the envelope on all four edges. Identify it and drop.
    env_xmin, env_ymin, env_xmax, env_ymax = env.bounds
    def touches_all_edges(p: Polygon) -> bool:
        bx0, by0, bx1, by1 = p.bounds
        eps = 1e-3
        return (bx0 <= env_xmin + eps and bx1 >= env_xmax - eps
                and by0 <= env_ymin + eps and by1 >= env_ymax - eps)

    rooms_raw = [p for p in parts if not touches_all_edges(p)]

    min_area = min_room_area_factor * t * t
    rooms: list[dict] = []
    for i, poly in enumerate(rooms_raw):
        if poly.area < min_area:
            continue
        rooms.append({
            "id": f"r{i:03d}",
            "polygon_pts": [[round(x, 3), round(y, 3)] for x, y in poly.exterior.coords],
            "area_pts2": round(poly.area, 2),
            "centroid": [round(poly.centroid.x, 3), round(poly.centroid.y, 3)],
        })
    return rooms, bridges


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("consensus", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--door-min", type=float, default=15.0)
    ap.add_argument("--door-max", type=float, default=50.0)
    args = ap.parse_args()
    out = args.out or args.consensus
    d = json.loads(args.consensus.read_text())
    rooms, bridges = polygonize_rooms(d, args.door_min, args.door_max)
    d["rooms"] = rooms
    d["openings"] = [
        {"id": b["id"], "type": "door", "wall_a_end": b["start"],
         "wall_b_start": b["end"],
         "width_pts": ((b["end"][0] - b["start"][0]) if b["orientation"] == "h"
                       else (b["end"][1] - b["start"][1]))}
        for b in bridges
    ]
    out.write_text(json.dumps(d, indent=2))
    print(f"[ok] {len(rooms)} rooms, {len(bridges)} door bridges -> {out}")
