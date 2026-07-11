"""Build a single-shell .skp for an entire floor plan from a consensus.

Parallel, EXPERIMENTAL exporter. Does NOT replace consume_consensus.rb.
See docs/adr/ADR-003-plan-shell-exporter.md for the design rationale.

Pipeline:
    consensus.json
       |
       v
    [1] Compute 2D wall footprints
        Each wall = box(start, end, thickness/2) in PDF point coords.
        For horizontal walls (orientation='h'), the box hugs the y-axis;
        for vertical, it hugs the x-axis. Mirrors consume_consensus.rb
        line 67-90 (`add_wall_volume`).
       |
       v
    [2] shapely.unary_union(all footprints)
        Walls whose footprints touch / overlap merge into one polygon.
        Corners — where two perpendicular walls share the corner cell —
        are auto-resolved here: no per-wall corner pillar, no duplicated
        face at the corner.
       |
       v
    [3] buffer-close-gap idiom (epsilon snap)
        planta_74's walls have endpoint-share ratio = 1.000 (every
        endpoint is unique). Adjacent walls that "look connected" in
        the PDF can be SNAP_EPS_PTS apart. Buffering ±SNAP_EPS_PTS / 2
        bridges the visual gap without distorting wall thickness.
       |
       v
    [4] Subtract opening rectangles
        Each opening with wall_id + center + opening_width_pts becomes
        a 2D rectangle aligned with the host wall axis. Subtracting in
        2D before extrude guarantees a clean door gap in the shell —
        no post-extrusion boolean issues.
       |
       v
    [5] Sliver filter
        After union+subtract, micro-polygons can appear from numerical
        noise. Filter polygons whose area < MIN_SLIVER_AREA_PTS2.
       |
       v
    [6] Serialize to _shell_polygon.json
        Outer ring + holes per polygon piece, in PDF points. The Ruby
        exporter reads this and builds the SU face-with-holes + pushpull.

The Ruby exporter (build_plan_shell_skp.rb) is invoked via the same
autorun_consume.rb plugin mechanism used by skp_from_consensus.py —
we only swap line 3 of autorun_control.txt to point at our .rb.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

from core.scale import plant_from_fixture_path, resolve_plant_pt_to_m
from tools.disarm_sketchup_autoruns import disarm as disarm_autoruns
from tools.su_runner_safety import log_mode, parse_mode, should_terminate

SKETCHUP_EXE_DEFAULT = (
    r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
)
PLUGINS_DIR_DEFAULT = Path(os.path.expandvars(
    r"%APPDATA%\SketchUp\SketchUp 2026\SketchUp\Plugins"
))
RUBY_TEMPLATE = Path(__file__).resolve().parent / "build_plan_shell_skp.rb"
CONTROL_FILE = "autorun_control.txt"
METADATA_SUFFIX = ".metadata.json"

# ---- algorithmic tuning constants ------------------------------------

# Snap tolerance used by the buffer-close-gap idiom. PDF points are
# the unit. For planta_74 (PT_TO_M = 0.19/5.4) this is ~3 mm at 0.1 pt.
# Small enough not to merge distinct walls; large enough to bridge
# endpoint-mismatch artefacts where two walls "should" touch but are
# slightly offset (e.g., centerlines stored without snap during extract).
SNAP_EPS_PTS = 0.1

# Minimum area for a polygon piece to survive the sliver filter, in
# (PDF point)^2. A 0.5 pt^2 sliver is ~0.02 mm^2 in real coordinates —
# pure numerical noise from boolean operations. Anything larger is
# preserved.
MIN_SLIVER_AREA_PTS2 = 0.5

# Opening geometry_origin values whose 2D carve we apply. Mirrors
# CARVING_OPENING_ORIGINS in consume_consensus.rb. The rationale:
# - `svg_arc`, `svg_segments`: arc/segment-shaped openings the SVG
#   extractor found inside continuous walls — gap must be carved.
# - `human_annotation`: openings injected by a reviewer painting on
#   a render; same — gap must be carved.
# - `wall_gap`: the source PDF already drew the flanking walls as
#   separate filled rectangles, so the gap is *already* in the wall
#   data. Carving here would double-shrink the geometry. We instead
#   render a passage marker / window panel on top.
CARVING_ORIGINS = frozenset({"svg_arc", "svg_segments", "human_annotation"})

# Opening kinds whose 2D pre-extrude carve goes FULL-HEIGHT (floor to
# ceiling). Doors, passages, and porta-vidro (glazed_balcony) genuinely
# remove wall mass from floor to wall_height. Windows DO NOT — they must
# preserve a peitoril (parapet) below the sill AND a verga (lintel)
# above the head. Window apertures are emitted in a separate
# `window_apertures` field so the Ruby exporter can cut them in 3D at
# WINDOW_SILL_IN..WINDOW_HEAD_IN after extruding the solid wall.
# See ADR-007 and FP-024 for the rationale.
FULL_HEIGHT_CARVE_KINDS = frozenset({
    "interior_door", "door_arc", "door",
    "interior_passage", "open_passage", "passage",
    "glazed_balcony",
})
WINDOW_APERTURE_KINDS = frozenset({"window"})


def opening_kind_v5_normalised(op: dict) -> str:
    """Normalise opening kind. Matches `opening_kind_v5` in the Ruby
    exporter (build_plan_shell_skp.rb:373)."""
    k = op.get("kind_v5") or op.get("kind") or "interior_door"
    if k in ("door_arc", "door"):
        return "interior_door"
    if k in ("open_passage", "passage"):
        return "interior_passage"
    return k


def is_window_aperture(op: dict) -> bool:
    """Window apertures must preserve wall mass above + below.
    Carved in 3D after wall extrusion (NOT in 2D pre-extrude)."""
    return opening_kind_v5_normalised(op) in WINDOW_APERTURE_KINDS


# ---- core geometry ---------------------------------------------------

def wall_footprint(wall: dict, extend_endpoints: bool = True,
                   extend_start: bool | None = None,
                   extend_end: bool | None = None) -> Polygon:
    """Return the 2D rectangle this wall occupies, in PDF points.

    Mirrors the corner computation in consume_consensus.rb's
    ``add_wall_volume`` (lines 67-90): horizontal walls hug the y-axis
    (thickness in y), vertical walls hug the x-axis (thickness in x).

    Endpoint extension is **per-side**, so each end of the wall can
    independently extend by half-thickness or not:

    - ``extend_endpoints`` (default True) sets the default for BOTH ends.
    - ``extend_start`` / ``extend_end`` override per side when explicit
      (None = follow ``extend_endpoints``).

    The canonical corner-completion rule (LL-017 / FP-025) is: at a
    junction where two perpendicular walls meet, BOTH must extend
    halfway into each other so the outer corner is a clean L-shape
    (not a stepped notch). At a **free** wall end (no perpendicular
    wall absorbing the extension), extending creates a visible
    half-thickness stub sticking out into space — the LL-017 stub
    anti-pattern. Pass ``extend_end=False`` (or ``extend_start=False``)
    on those sides to trim the stub.

    See ``_classify_endpoint_junctions`` for the automatic per-end
    classification used by ``build_shell_polygon``.
    """
    s = wall["start"]
    e = wall["end"]
    t = wall.get("thickness")
    if t is None:
        raise ValueError(f"wall {wall.get('id')} missing thickness")
    half = t / 2.0
    es = extend_endpoints if extend_start is None else extend_start
    ee = extend_endpoints if extend_end is None else extend_end

    # Extension amount per end: bool True = half-thickness (legado);
    # bool False/None = 0; float = quantidade explícita em pts, capada em
    # half (o clamp de junção de _classify_endpoint_junctions passa floats
    # pra nunca ultrapassar a face externa do vizinho perpendicular).
    def _amt(v) -> float:
        if v is True:
            return half
        if not v:
            return 0.0
        return min(float(v), half)

    es_amt, ee_amt = _amt(es), _amt(ee)
    # Resolve per-axis: 'start' is the lower coord side, 'end' is the upper.
    ori = wall.get("orientation")
    if ori == "h":
        low_amt, high_amt = (es_amt, ee_amt) if s[0] <= e[0] else (ee_amt, es_amt)
        x0 = min(s[0], e[0]) - low_amt
        x1 = max(s[0], e[0]) + high_amt
        cy = s[1]
        return box(x0, cy - half, x1, cy + half)
    if ori == "v":
        low_amt, high_amt = (es_amt, ee_amt) if s[1] <= e[1] else (ee_amt, es_amt)
        cx = s[0]
        y0 = min(s[1], e[1]) - low_amt
        y1 = max(s[1], e[1]) + high_amt
        return box(cx - half, y0, cx + half, y1)
    raise ValueError(
        f"wall {wall.get('id')} has unsupported orientation={ori!r}; "
        "this exporter only handles axis-aligned walls"
    )


# ---- junction-aware endpoint classification (LL-017 stub trim) ------

# Tolerance for "endpoint falls inside another wall's raw footprint".
# Slightly larger than 0 so endpoints exactly on a wall edge are caught.
JUNCTION_TOL_PTS = 0.5


def _classify_endpoint_junctions(
    walls: list[dict],
) -> dict[str, tuple[float, float]]:
    """Return ``{wall_id: (start_ext_pts, end_ext_pts)}``.

    A wall endpoint is a **junction** iff a buffered version of any
    **perpendicular** wall's raw (un-extended) footprint contains it.
    Buffered by ``JUNCTION_TOL_PTS`` so endpoints exactly on a wall
    edge count. Free endpoints get extension 0.0.

    A extensão devolvida é **capada na face EXTERNA do vizinho** (nunca
    passa dela): min(half-thickness, distância do endpoint até a face
    oposta do vizinho perpendicular na direção da extensão). Sem o clamp,
    um endpoint desenhado NA face externa do vizinho ganhava half-t de
    stub pra fora — a planta_74 gerava 5 stubs fantasmas (~2.7×5.4 pt)
    que só ficavam invisíveis porque _remove_small_teeth os amputava por
    coincidência de constante (2.7 < tol 3.0), levando junto geometria
    REAL do consensus (bug par do vf_004).

    The perpendicularity requirement is critical for the LL-017 stub
    trim: extending into a PERPENDICULAR neighbour closes a T/L
    corner cleanly (the extension is absorbed by the other wall's
    body across the perpendicular axis). Extending into a PARALLEL
    neighbour that just happens to overlap in 2D — e.g. a
    human-painted partition sitting offset by ~thickness from a
    structural wall — would shoot past the parallel wall's own end
    and create a stub anyway.

    Free endpoints (return ``False``) terminate in open space; their
    half-thickness extension would create the LL-017 stub
    anti-pattern, so callers should pass ``extend_start=False`` /
    ``extend_end=False`` accordingly.

    Implementation note: O(n²) but n is small (planta_74 has 35
    walls). A spatial index would only help if n grew past ~500.
    """
    raw_fps = {
        w["id"]: wall_footprint(w, extend_endpoints=False) for w in walls
    }
    orients = {w["id"]: w.get("orientation") for w in walls}
    out: dict[str, tuple[float, float]] = {}
    for w in walls:
        wid = w["id"]
        own_orient = orients[wid]
        half = float(w["thickness"]) / 2.0
        s, e = w["start"], w["end"]
        # eixo da parede (índice da coordenada que varia) e direção
        # "pra fora" em cada ponta
        axis = 0 if own_orient == "h" else 1

        def _ext(p: list[float], outward: float) -> float:
            """Extensão capada pra este endpoint (0.0 = free)."""
            pt = Point(p)
            best = 0.0
            for other_id, fp in raw_fps.items():
                if other_id == wid:
                    continue
                # Skip parallel neighbours — their containment does
                # NOT represent a corner to close (LL-017 stub trim).
                if orients[other_id] == own_orient:
                    continue
                if not fp.buffer(JUNCTION_TOL_PTS).contains(pt):
                    continue
                # distância do endpoint até a face EXTERNA do vizinho na
                # direção da extensão — nunca estender além dela
                minx, miny, maxx, maxy = fp.bounds
                lo, hi = (minx, maxx) if axis == 0 else (miny, maxy)
                needed = (hi - p[axis]) if outward > 0 else (p[axis] - lo)
                best = max(best, max(0.0, min(half, needed)))
            return best

        if abs(e[axis] - s[axis]) < 1e-9:
            out[wid] = (0.0, 0.0)
            continue
        out_s = -1.0 if s[axis] < e[axis] else 1.0
        out[wid] = (_ext(s, out_s), _ext(e, -out_s))
    return out


# ---- canonicalisation (LL-017 / FP-025) ----------------------------

def _canonicalise_axis_aligned_ring(coords: list[tuple[float, float]],
                                    tol: float = 1e-6
                                    ) -> list[tuple[float, float]]:
    """Drop collinear redundant vertices from an axis-aligned ring.

    For axis-aligned polygons every edge is either horizontal or
    vertical. A vertex sandwiched between two edges in the SAME
    cardinal direction (both horizontal or both vertical) is
    redundant and must be dropped — otherwise the union of two
    same-axis wall rectangles can leave "internal" vertices on the
    outer boundary, producing the FP-025 stepped-notch signature
    that survives `shapely.simplify` for orthogonal geometry.
    """
    if len(coords) < 4:
        return coords
    # Drop closing duplicate if present.
    if abs(coords[0][0] - coords[-1][0]) < tol \
            and abs(coords[0][1] - coords[-1][1]) < tol:
        coords = coords[:-1]
    n = len(coords)
    keep = []
    for i in range(n):
        prev = coords[(i - 1) % n]
        cur = coords[i]
        nxt = coords[(i + 1) % n]
        # Vertex is redundant iff prev->cur and cur->nxt share
        # direction (both horizontal or both vertical AND same sign).
        d1x = cur[0] - prev[0]
        d1y = cur[1] - prev[1]
        d2x = nxt[0] - cur[0]
        d2y = nxt[1] - cur[1]
        same_h = abs(d1y) < tol and abs(d2y) < tol
        same_v = abs(d1x) < tol and abs(d2x) < tol
        if same_h or same_v:
            continue
        keep.append(cur)
    return keep


def _remove_small_teeth(ring: list, tol: float = 3.0) -> list:
    """Remove corner-notch 'teeth' — small SYMMETRIC rectangular protrusions/recesses
    of depth < tol AND width < tol that shapely.union leaves at wall junctions
    (half-thickness step = the 'toquinhos' Felipe flagged 2026-06-03, ~2.7pt).
    Only collapses a tooth whose two side edges are equal length, so the
    reconnected base stays axis-aligned — NEVER creates a diagonal.

    O dente precisa ser pequeno nas DUAS dimensões: exigir só profundidade
    < tol fazia o filtro comer geometria REAL do consensus de qualquer
    largura (medido na planta_74: remanescente de 1.26pt junto ao carve da
    h_o005 e overhang de 2.08pt da m006, ambos com largura 5.4 = espessura
    de parede). Feature real rasa-mas-larga agora sobrevive; artefato de
    canto (raso E estreito) continua removido."""
    import math as _m
    pts = [tuple(p) for p in ring]
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    changed, guard = True, 0
    while changed and len(pts) >= 6 and guard < 4000:
        changed, guard, n = False, guard + 1, len(pts)
        for i in range(n):
            P, Q, R, S = pts[i], pts[(i+1) % n], pts[(i+2) % n], pts[(i+3) % n]
            pq = (Q[0]-P[0], Q[1]-P[1]); qr = (R[0]-Q[0], R[1]-Q[1]); rs = (S[0]-R[0], S[1]-R[1])
            lpq, lrs = _m.hypot(*pq), _m.hypot(*rs)
            lqr = _m.hypot(*qr)
            if (abs(pq[0]*qr[0]+pq[1]*qr[1]) < 1e-6 and abs(rs[0]*qr[0]+rs[1]*qr[1]) < 1e-6
                    and (pq[0]*rs[0]+pq[1]*rs[1]) < 0 and abs(lpq-lrs) < 1e-6
                    and 1e-9 < lpq < tol and 1e-9 < lrs < tol
                    and 1e-9 < lqr < tol):
                for k in sorted([(i+1) % n, (i+2) % n], reverse=True):
                    pts.pop(k)
                changed = True
                break
    return pts


def canonicalise_axis_aligned_polygon(poly: Polygon,
                                       tol: float = 1e-6) -> Polygon:
    """Strip redundant collinear vertices from an axis-aligned polygon, after removing
    half-thickness corner-notch teeth at junctions.

    A clean rectangular wall shell with a single interior room has
    EXACTLY 4 outer + 4 inner vertices after canonicalisation. Any
    excess is the FP-025 corner-notch signature.
    """
    outer = _canonicalise_axis_aligned_ring(
        _remove_small_teeth(list(poly.exterior.coords)), tol=tol,
    )
    interiors = []
    for ring in poly.interiors:
        cleaned = _canonicalise_axis_aligned_ring(
            _remove_small_teeth(list(ring.coords)), tol=tol,
        )
        if len(cleaned) >= 3:
            interiors.append(cleaned)
    if len(outer) < 3:
        return poly
    return Polygon(outer, holes=interiors)


def opening_carve_rect(opening: dict, host_wall: dict,
                       default_thickness: float) -> Polygon:
    """Compute the 2D rectangle to subtract from the shell for this opening.

    The carve rectangle is aligned with the host wall axis and spans
    ``opening_width_pts`` along the wall plus the wall's full thickness
    perpendicular to it (so the subtraction reaches both faces of the
    wall, not just one side).
    """
    t = host_wall.get("thickness", default_thickness)
    half = t / 2.0
    cx, cy = opening["center"]
    w = opening.get("opening_width_pts")
    if w is None or w <= 0:
        raise ValueError(
            f"opening {opening.get('id')} missing/invalid opening_width_pts"
        )
    half_w = w / 2.0
    ori = host_wall.get("orientation")
    if ori == "h":
        wall_cy = host_wall["start"][1]
        return box(cx - half_w, wall_cy - half, cx + half_w, wall_cy + half)
    if ori == "v":
        wall_cx = host_wall["start"][0]
        return box(wall_cx - half, cy - half_w, wall_cx + half, cy + half_w)
    raise ValueError(
        f"host wall {host_wall.get('id')} orientation={ori!r} unsupported"
    )


def build_shell_polygon(consensus: dict) -> tuple[list[Polygon], dict]:
    """Return (polygons, stats) for the plan shell.

    Each polygon may have holes (interior loops). The list is what the
    Ruby exporter iterates over to create face-with-holes + pushpull.
    """
    walls = consensus.get("walls", [])
    if not walls:
        raise ValueError("consensus has no walls — cannot build shell")
    openings = consensus.get("openings", [])
    default_thickness = consensus.get("wall_thickness_pts")

    # [1] wall footprints (junction-aware extension — LL-017 stub trim)
    # Classify each wall endpoint as junction-or-free. Extend by half-
    # thickness only at junction endpoints (where extension closes a
    # corner with a perpendicular wall). At free endpoints, do not
    # extend — extending into open space creates the LL-017 stub
    # anti-pattern (half-thickness rectangle sticking out past where
    # the wall actually terminates per the consensus / PDF).
    junctions = _classify_endpoint_junctions(walls)
    free_end_count = sum(
        (0 if a else 1) + (0 if b else 1) for (a, b) in junctions.values()
    )
    wall_boxes = [
        wall_footprint(
            w,
            extend_start=junctions[w["id"]][0],
            extend_end=junctions[w["id"]][1],
        )
        for w in walls
    ]

    # [2] union
    shell = unary_union(wall_boxes)

    # [3] buffer-close-gap with mitre joins.
    # Default round joins would replace every right-angle corner with
    # a fan of 16 short segments — both visually and quantitatively
    # wrong for an axis-aligned floor plan (a 100x100m room would end
    # up with ~64 outer perimeter verts instead of 4). join_style=2
    # (mitre) keeps the corner geometry exact, only filling/bridging
    # micro-gaps under SNAP_EPS_PTS. mitre_limit caps spike length on
    # very acute corners so we don't shoot a needle out at <5 degree
    # bends — shouldn't trigger for axis-aligned walls.
    shell = (
        shell
        .buffer(SNAP_EPS_PTS, join_style=2, mitre_limit=10.0)
        .buffer(-SNAP_EPS_PTS, join_style=2, mitre_limit=10.0)
    )

    # [4] subtract opening rectangles
    walls_by_id = {w["id"]: w for w in walls if "id" in w}
    carve_rects: list[Polygon] = []
    window_apertures: list[dict] = []
    openings_skipped_by_origin: list[dict] = []
    openings_skipped_by_error: list[str] = []
    for op in openings:
        wid = op.get("wall_id")
        host = walls_by_id.get(wid)
        if host is None:
            openings_skipped_by_error.append(
                f"{op.get('id')}: host wall_id={wid!r} not in walls[]"
            )
            continue
        # geometry_origin gates whether we carve OR leave the wall
        # data alone (because the source PDF already encoded the gap).
        origin = op.get("geometry_origin", "")
        if origin and origin not in CARVING_ORIGINS:
            openings_skipped_by_origin.append({
                "id": op.get("id"),
                "geometry_origin": origin,
                "reason": (
                    f"origin {origin!r} not in CARVING_ORIGINS "
                    f"({sorted(CARVING_ORIGINS)}); gap already in wall data"
                ),
            })
            continue
        # Window vs door-like semantics (ADR-007 / FP-024).
        # Windows preserve wall mass below sill + above head — they
        # must NOT be carved full-height in 2D. Hand them to the Ruby
        # exporter as a window_aperture for post-extrude 3D carve.
        if is_window_aperture(op):
            w_pts = op.get("opening_width_pts")
            if w_pts is None or w_pts <= 0:
                openings_skipped_by_error.append(
                    f"{op.get('id')}: window missing/invalid opening_width_pts"
                )
                continue
            window_apertures.append({
                "id": op.get("id"),
                "wall_id": wid,
                "kind_v5": opening_kind_v5_normalised(op),
                "center": list(op["center"]),
                "opening_width_pts": float(w_pts),
                "host_wall_orientation": host.get("orientation"),
                "host_wall_thickness_pts": float(
                    host.get("thickness", default_thickness)
                ),
            })
            continue
        # Hard Rule #2: full-height carve SÓ pra kinds da whitelist.
        # Kind desconhecido (extractor futuro, typo) NUNCA vira buraco
        # chão-teto silencioso — vai pro bucket de erro.
        kind = opening_kind_v5_normalised(op)
        if kind not in FULL_HEIGHT_CARVE_KINDS:
            openings_skipped_by_error.append(
                f"{op.get('id')}: kind_v5 {kind!r} not in "
                f"FULL_HEIGHT_CARVE_KINDS nor window aperture — refusing "
                f"full-height carve (Hard Rule #2)"
            )
            continue
        try:
            carve_rects.append(opening_carve_rect(op, host, default_thickness))
        except (ValueError, KeyError, TypeError) as e:
            openings_skipped_by_error.append(f"{op.get('id')}: {e!r}")

    if carve_rects:
        carve_union = unary_union(carve_rects)
        shell_with_gaps = shell.difference(carve_union)
    else:
        shell_with_gaps = shell

    # [5] sliver filter + normalise to list of Polygon
    if isinstance(shell_with_gaps, Polygon):
        polygons = [shell_with_gaps]
    elif isinstance(shell_with_gaps, MultiPolygon):
        polygons = list(shell_with_gaps.geoms)
    else:
        raise TypeError(
            f"unexpected geometry type after subtract: {type(shell_with_gaps)}"
        )
    slivers_removed = 0
    kept: list[Polygon] = []
    redundant_vertices_dropped = 0
    for p in polygons:
        if not p.is_valid:
            slivers_removed += 1
            continue
        if p.area < MIN_SLIVER_AREA_PTS2:
            slivers_removed += 1
            continue
        # [5b] Canonicalise: strip collinear redundant vertices left by
        # unary_union on adjacent axis-aligned rectangles. This is the
        # FP-025 cleanup step — without it, the outer ring of even a
        # clean 4-wall shell carries 12 vertices (4 corners × 3 each)
        # instead of the canonical 4.
        before_outer = len(p.exterior.coords)
        before_holes = sum(len(r.coords) for r in p.interiors)
        clean = canonicalise_axis_aligned_polygon(p)
        after_outer = len(clean.exterior.coords)
        after_holes = sum(len(r.coords) for r in clean.interiors)
        redundant_vertices_dropped += (
            (before_outer - after_outer) + (before_holes - after_holes)
        )
        kept.append(clean)
    if not kept:
        raise RuntimeError(
            "all shell polygons were filtered as slivers — input or "
            "tuning parameters are wrong"
        )

    stats = {
        "input_walls": len(walls),
        "input_openings": len(openings),
        "openings_carved": len(carve_rects),
        "window_apertures_3d": len(window_apertures),
        # LL-017 stub trim — count of endpoints that were classified as
        # FREE (not at a junction) and therefore had their half-thickness
        # extension dropped. Quadrado-healthy on a fully-closed fixture
        # is 0; planta_74 has many because most interior walls don't
        # share endpoints with neighbours.
        "endpoints_free": free_end_count,
        "endpoints_junction": 2 * len(walls) - free_end_count,
        # Split into two buckets: by_origin is legitimate (wall_gap
        # origin; gap is already in the wall data, no carve needed).
        # by_error is a real failure (missing wall_id, zero width,
        # etc) and must be 0 on a healthy consensus.
        "openings_skipped_by_origin": openings_skipped_by_origin,
        "openings_skipped_by_error": openings_skipped_by_error,
        # Back-compat: keep the flat field for old test readers, but
        # only populate with the error bucket — origin-based skips
        # are by design and shouldn't trip "skipped is not empty"
        # checks. Removed entirely once test suite migrates.
        "openings_skipped": list(openings_skipped_by_error),
        "shell_pieces_after_union": len(polygons),
        "shell_pieces_after_sliver_filter": len(kept),
        "slivers_removed": slivers_removed,
        # FP-025 cleanup counters: total redundant collinear vertices
        # dropped by canonicalise_axis_aligned_polygon after union+carve.
        # On a healthy build, a clean rectangle has exactly 4 outer +
        # 4 inner vertices, so an N-wall quadrado-style fixture drops
        # 8 redundant vertices (the corner notches).
        "redundant_vertices_dropped": redundant_vertices_dropped,
        "snap_eps_pts": SNAP_EPS_PTS,
        "min_sliver_area_pts2": MIN_SLIVER_AREA_PTS2,
        "carving_origins": sorted(CARVING_ORIGINS),
        "total_shell_area_pts2": round(sum(p.area for p in kept), 4),
        # ADR-007 / FP-024: windows are NOT 2D-carved. The Ruby exporter
        # reads this list from the serialized _shell_polygon.json
        # (top-level `window_apertures`) and post-extrudes a 3D aperture
        # per entry.
        "window_apertures": window_apertures,
    }
    return kept, stats


def _drop_coincident(coords: list, tol: float = 1e-3) -> list:
    """Drop consecutive near-coincident vertices + the ring-wrap. shapely's
    boolean union of float-noisy thicknesses (e.g. m012 5.399517 vs a neighbour)
    can emit two points <1e-3 pdf-pt apart at a corner; SU's add_face then raises
    "Duplicate points in array". tol 1e-3 pdf-pt (~3.5 um) removes only that union
    noise — real vertices are orders larger. (Gate :8765 modo B, Option B,
    2026-06-03; same noise floor as the axis-aligned test.)
    """
    out: list = []
    for x, y in coords:
        if not out or abs(out[-1][0] - x) > tol or abs(out[-1][1] - y) > tol:
            out.append((x, y))
    if (len(out) > 1 and abs(out[-1][0] - out[0][0]) <= tol
            and abs(out[-1][1] - out[0][1]) <= tol):
        out.pop()
    return out


# ---- room floors (slabs that reach the wall inner faces) -------------
# Felipe 2026-06-04: "isso ai vai ser o piso e ele TEM QUE ENCOSTAR na parede".
# The room polygon from consensus is recessed / slightly misaligned from the
# wall faces, leaving a gray gap between the colored slab and the wall. Instead
# of trusting that polygon, we fill the FREE-SPACE CELL the room lives in
# (apartment envelope minus the wall mass): the cell is bounded *exactly* by the
# wall inner faces, so the slab reaches the wall with no gap and tucks slightly
# under it. Integrated rooms that share one cell (sala+cozinha, no solid wall
# between) are split back apart by their room polygons.
FLOOR_SNAP_EPS_PTS = 6.0
FLOOR_CELL_MIN_AREA_PTS2 = 50.0
FLOOR_UNDER_FRAC = 0.4          # tuck slab 0.4*thickness under the wall: reaches
#                                 the inner face + hides the seam, but two
#                                 adjacent slabs (0.4+0.4=0.8<1) never overlap.
#                                 Swept 0.3-0.6: <=0.45 gives ZERO slab overlap.
FLOOR_SIMPLIFY_TOL_PTS = 0.5    # kill boolean-noise micro-edges before SU add_face


def _floor_snap_coords(ring: list, eps: float) -> list:
    """Group near-equal x's (and y's) and move each to the group mean — kills
    the micro-teeth ('toquinhos') the room polygon inherits from wall junctions.
    Mirrors the Ruby snap_coords so both paths agree."""
    pts = [[float(p[0]), float(p[1])] for p in ring]
    for dim in (0, 1):
        vals = sorted({p[dim] for p in pts})
        if not vals:
            continue
        m: dict = {}
        group = [vals[0]]
        for v in vals[1:]:
            if v - group[-1] < eps:
                group.append(v)
            else:
                avg = sum(group) / len(group)
                for g in group:
                    m[g] = avg
                group = [v]
        avg = sum(group) / len(group)
        for g in group:
            m[g] = avg
        for p in pts:
            p[dim] = m[p[dim]]
    return [(p[0], p[1]) for p in pts]


def _floor_dedup(ring: list, eps: float = 0.05) -> list:
    if not ring:
        return ring
    out = [ring[0]]
    for p in ring[1:]:
        if abs(p[0] - out[-1][0]) > eps or abs(p[1] - out[-1][1]) > eps:
            out.append(p)
    if (len(out) >= 2 and abs(out[0][0] - out[-1][0]) < eps
            and abs(out[0][1] - out[-1][1]) < eps):
        out.pop()
    return out


def _floor_drop_collinear(ring: list, eps: float = 1e-4) -> list:
    n = len(ring)
    if n < 3:
        return ring
    out = []
    for i in range(n):
        a, b, c = ring[(i - 1) % n], ring[i], ring[(i + 1) % n]
        if abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) > eps:
            out.append(b)
    return out


def _floor_clean_ring(raw: list) -> list:
    r = _floor_dedup(raw)
    r = _floor_snap_coords(r, FLOOR_SNAP_EPS_PTS)
    r = _floor_dedup(r)
    r = _floor_drop_collinear(r)
    r = _floor_dedup(r)
    return r


def compute_room_floors(consensus: dict) -> dict:
    """Return {room_id: [[x, y], ...]} — each room's floor ring expanded to the
    inner faces of its surrounding walls (no gray gap), in PDF points. Rooms with
    no resolvable cell are omitted (Ruby falls back to its snap path)."""
    rooms = consensus.get("rooms", []) or []
    walls = consensus.get("walls", []) or []
    if not rooms or not walls:
        return {}
    wt = float(consensus.get("wall_thickness_pts") or 5.4)
    wp = []
    for w in walls:
        try:
            wp.append(wall_footprint(w, extend_endpoints=True))
        except Exception:
            continue
    if not wp:
        return {}
    wall_mass = unary_union(wp)
    # soft barriers (guarda-corpo) close the envelope where the varanda has a
    # rail instead of a wall — without them the cell would leak past the facade.
    sb_lines = []
    for s in consensus.get("soft_barriers", []) or []:
        pl = s.get("polyline_pts") or []
        if len(pl) >= 2:
            sb_lines.append(LineString([(float(x), float(y)) for x, y in pl])
                            .buffer(wt / 2.0, cap_style=2, join_style=2))
    env_src = unary_union(wp + sb_lines)
    egeoms = list(env_src.geoms) if isinstance(env_src, MultiPolygon) else [env_src]
    envelope = unary_union([Polygon(g.exterior) for g in egeoms])

    # The cell stops at the inner face of BOTH walls and soft barriers. Without
    # subtracting the barriers, the varanda cell ran to the OUTER edge of the
    # glass guard-rail, so the slab poked past the (transparent) glass — visible
    # as the floor "leaking past the wall" (Felipe 2026-06-04). Subtracting the
    # rail makes the slab stop at its inner face (+ the small tuck under it).
    barrier_mass = unary_union([wall_mass, *sb_lines]) if sb_lines else wall_mass
    free = envelope.difference(barrier_mass)
    cells = [g for g in (free.geoms if isinstance(free, MultiPolygon) else [free])
             if g.area > FLOOR_CELL_MIN_AREA_PTS2]

    polys: list = []
    for rm in rooms:
        raw = [(float(p[0]), float(p[1])) for p in (rm.get("polygon_pts") or [])]
        if len(raw) >= 2 and raw[0] == raw[-1]:
            raw = raw[:-1]
        ring = _floor_clean_ring(raw)
        p = Polygon(ring) if len(ring) >= 3 else None
        if p is not None and not p.is_valid:
            p = p.buffer(0)
        polys.append(p if (p is not None and not p.is_empty) else None)

    under = wt * FLOOR_UNDER_FRAC
    floor_by_room: list = [None] * len(polys)
    for cell in cells:
        here = [i for i, p in enumerate(polys)
                if p is not None and cell.intersection(p).area > FLOOR_CELL_MIN_AREA_PTS2]
        if not here:
            continue
        tucked = cell.buffer(under, join_style=2).intersection(envelope)
        if len(here) == 1:
            floor_by_room[here[0]] = tucked
            continue
        # multiple rooms share this cell (integrated, no solid wall between) —
        # split it back apart by the room polygons; leftover gap -> nearest room.
        here.sort(key=lambda i: -polys[i].area)
        assigned = None
        parts: dict = {}
        for i in here:
            piece = polys[i].buffer(under, join_style=2).intersection(tucked)
            if assigned is not None:
                piece = piece.difference(assigned)
            parts[i] = piece
            assigned = piece if assigned is None else unary_union([assigned, piece])
        resto = tucked.difference(assigned) if assigned is not None else tucked
        if not resto.is_empty:
            for piece in (resto.geoms if isinstance(resto, MultiPolygon) else [resto]):
                if piece.is_empty:
                    continue
                nearest = min(here, key=lambda i: polys[i].distance(piece))
                parts[nearest] = unary_union([parts[nearest], piece])
        for i in here:
            floor_by_room[i] = parts[i]

    out: dict = {}
    for i, rm in enumerate(rooms):
        floor = floor_by_room[i]
        if floor is None or floor.is_empty:
            continue
        if isinstance(floor, MultiPolygon):
            floor = max(floor.geoms, key=lambda g: g.area)
        floor = floor.simplify(FLOOR_SIMPLIFY_TOL_PTS, preserve_topology=True)
        if floor.is_empty or floor.geom_type != "Polygon":
            continue
        outer = _drop_coincident(list(floor.exterior.coords))
        if len(outer) < 3:
            continue
        # Preserve holes: when an integrated room (sala) wraps another (cozinha),
        # the cozinha is a HOLE in sala's slab. Dropping it (exterior-only) would
        # double-cover the cozinha. Ruby's build_floor cuts each hole like the
        # shell does (add inner face -> erase, leaving the hole topology).
        holes = []
        for ring in floor.interiors:
            h = _drop_coincident(list(ring.coords))
            if len(h) >= 3 and abs(Polygon(h).area) > FLOOR_CELL_MIN_AREA_PTS2:
                holes.append([[float(x), float(y)] for x, y in h])
        rid = str(rm.get("id") or f"r{i}")
        out[rid] = {
            "outer": [[float(x), float(y)] for x, y in outer],
            "holes": holes,
        }
    return out


def serialize_polygons(polygons: list[Polygon],
                       consensus: dict, stats: dict) -> dict:
    """Build the dict that the Ruby exporter reads (`_shell_polygon.json`)."""
    pieces = []
    for poly in polygons:
        # Drop the shapely ring-close AND any near-coincident union-noise
        # vertices, else SU add_face raises "Duplicate points in array".
        outer = _drop_coincident(list(poly.exterior.coords))
        holes = []
        for ring in poly.interiors:
            h = _drop_coincident(list(ring.coords))
            if len(h) >= 3:
                holes.append([[float(x), float(y)] for x, y in h])
        pieces.append({
            "outer": [[float(x), float(y)] for x, y in outer],
            "holes": holes,
            "area_pts2": round(poly.area, 4),
        })
    return {
        "schema_version": "1.0.0",
        "tool": "build_plan_shell_skp",
        "consensus_source": consensus.get("source"),
        "wall_thickness_pts": consensus.get("wall_thickness_pts"),
        "page_size_pts": consensus.get("page_size_pts"),
        "polygons": pieces,
        "rooms": consensus.get("rooms", []),
        # Pre-computed floor rings (slab reaches the wall inner faces, no gap).
        # Ruby's build_floor uses room_floors[id] when present, else its snap path.
        "room_floors": compute_room_floors(consensus),
        "soft_barriers": consensus.get("soft_barriers", []),
        # ADR-007 / FP-024: surface window_apertures at top level so
        # the Ruby exporter can iterate without unpacking stats.
        "window_apertures": stats.get("window_apertures", []),
        "stats": stats,
    }


# ---- cache (mirror skp_from_consensus.py sidecar pattern) ----------

def _file_sha256(path: Path) -> str:
    """Stream the file and return its SHA256 hex digest."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def metadata_path(out_skp: Path) -> Path:
    """Path of the sidecar metadata file for a given .skp."""
    return out_skp.with_name(out_skp.name + METADATA_SUFFIX)


def read_metadata(out_skp: Path) -> dict[str, Any] | None:
    """Read the sidecar metadata. Returns None if missing or unparseable."""
    p = metadata_path(out_skp)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_metadata(out_skp: Path, *, consensus_sha256: str,
                   sketchup_exe: Path, command: list[str]) -> Path:
    """Write the sidecar metadata next to the .skp. Returns the path written."""
    p = metadata_path(out_skp)
    data = {
        "schema_version": "1.0.0",
        "exporter": "build_plan_shell_skp",
        "consensus_sha256": consensus_sha256,
        "skp_path": str(out_skp),
        "created_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "sketchup_path": str(sketchup_exe),
        "command": " ".join(command),
    }
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return p


def should_skip(out_skp: Path, consensus_sha256: str) -> bool:
    """True iff the .skp exists and its sidecar's consensus_sha256 matches.

    Caller is responsible for honouring `force_skp` BEFORE calling this —
    we don't take that flag here so the helper stays trivially testable.
    """
    if not out_skp.exists():
        return False
    meta = read_metadata(out_skp)
    if not meta:
        return False
    # Only skip when the SAME exporter produced the cached .skp.
    # Otherwise consume-produced .skp would be reused for a plan-shell
    # request (and vice-versa), corrupting the user's intent.
    if meta.get("exporter") != "build_plan_shell_skp":
        return False
    return meta.get("consensus_sha256") == consensus_sha256


# ---- launcher --------------------------------------------------------

def write_control(plugins_dir: Path, consensus: Path, out_skp: Path) -> None:
    plugins_dir.mkdir(parents=True, exist_ok=True)
    txt = "\n".join([
        str(consensus.resolve()).replace("\\", "/"),
        str(out_skp.resolve()).replace("\\", "/"),
        str(RUBY_TEMPLATE.resolve()).replace("\\", "/"),
    ])
    (plugins_dir / CONTROL_FILE).write_text(txt, encoding="utf-8")


def find_bootstrap(out_skp: Path) -> Path | None:
    candidates = sorted(
        (p for p in out_skp.parent.glob("*.skp") if p != out_skp),
        key=lambda p: -p.stat().st_mtime,
    )
    if candidates:
        return candidates[0]
    template_dir = Path(
        r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp"
        r"\resources\en-US\Templates"
    )
    for name in ("Temp01a - Simple.skp", "Temp01b - Simple.skp"):
        t = template_dir / name
        if t.exists():
            bootstrap = out_skp.parent / "_bootstrap.skp"
            if not bootstrap.exists():
                shutil.copy2(t, bootstrap)
            return bootstrap
    return None


def _default_runner_mode() -> str:
    """Pick a safe default runner mode based on environment.

    - If `CI=true` or `GITHUB_ACTIONS=true`: assume `headless`
      (preserves the historical terminate-after-SKP behaviour on CI).
    - Otherwise: `interactive` (the safe default — do NOT terminate
      SU automatically, protecting any concurrent human session).

    Callers can override via the `mode` argument, `--mode` CLI flag,
    `--no-terminate` shorthand, or `RUN_MODE` env var (resolved
    by `tools.su_runner_safety.parse_mode`).
    """
    ci_env = os.environ.get("CI", "").lower() == "true"
    gh_actions = os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
    return "headless" if (ci_env or gh_actions) else "interactive"


def run(consensus_path: Path, out_skp: Path, *, sketchup_exe: Path,
        plugins_dir: Path = PLUGINS_DIR_DEFAULT,
        timeout_s: int = 180,
        out_png_iso: Path | None = None,
        out_png_top: Path | None = None,
        out_report: Path | None = None,
        out_shell_json: Path | None = None,
        soft_barriers_mode: str = "groups",
        force_skp: bool = False,
        mode: str | None = None) -> dict[str, Any]:
    """Build the plan shell .skp end-to-end.

    Args:
      consensus_path: input consensus_model.json (or
        amended_observed.json — overrides-blind per ADR-001).
      out_skp: output .skp path.
      soft_barriers_mode: "groups" (emit at 1.10m as SoftBarrier_Group_N)
        or "skip" (record in report, do not emit).
      force_skp: bypass the content-hash cache. Default False.
      mode: SU runner mode per CLAUDE.md §18 (LL-015, FP-023). When
        None (default), resolves via parse_mode with a CI-aware safe
        default. Pass an explicit string (``"headless"`` /
        ``"interactive"`` / ``"attach"``) to override.

    Returns a dict with paths and stats. Honours the content-hash
    cache via a sidecar `<out_skp>.metadata.json` (matches the
    skp_from_consensus.py pattern); reruns short-circuit when the
    consensus SHA256 matches and force_skp is False.
    """
    started = time.time()
    out_skp.parent.mkdir(parents=True, exist_ok=True)
    if out_png_iso is None:
        out_png_iso = out_skp.with_name("model_iso.png")
    if out_png_top is None:
        out_png_top = out_skp.with_name("model_top.png")
    if out_report is None:
        out_report = out_skp.with_name("geometry_report.json")
    if out_shell_json is None:
        out_shell_json = out_skp.with_name("_shell_polygon.json")

    # ---- skip path: re-use unchanged .skp ----
    consensus_sha = (
        _file_sha256(consensus_path) if consensus_path.exists() else None
    )
    if (
        not force_skp
        and consensus_sha is not None
        and should_skip(out_skp, consensus_sha)
    ):
        elapsed = time.time() - started
        print(
            f"[skip] {out_skp} unchanged consensus "
            f"(sha {consensus_sha[:12]}); skipped SU launch"
        )
        return {
            "ok": True,
            "skipped": True,
            "skp_path": str(out_skp),
            "consensus_sha256": consensus_sha,
            "elapsed_s": round(elapsed, 4),
        }

    # Clean stale outputs (incl. stale sidecar metadata).
    meta_p = metadata_path(out_skp)
    for p in (out_skp, out_png_iso, out_png_top, out_report,
              out_shell_json, meta_p):
        if p.exists():
            p.unlink()

    # [Python phase] consensus -> shell polygon JSON
    consensus = json.loads(consensus_path.read_text(encoding="utf-8"))
    polygons, stats = build_shell_polygon(consensus)
    payload = serialize_polygons(polygons, consensus, stats)
    out_shell_json.write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(f"[py] shell polygon -> {out_shell_json}")
    print(
        f"[py] stats: walls={stats['input_walls']} "
        f"openings_carved={stats['openings_carved']} "
        f"pieces={stats['shell_pieces_after_sliver_filter']} "
        f"area={stats['total_shell_area_pts2']:.1f} pts^2"
    )

    # [Ruby phase] launch SU, autorun reads control file
    for p in disarm_autoruns(plugins_dir):
        print(f"[pre-launch disarm] removed orphan {p.name}")
    write_control(plugins_dir, consensus_path, out_skp)

    bootstrap = find_bootstrap(out_skp)
    cmd = [str(sketchup_exe)]
    if bootstrap:
        cmd.append(str(bootstrap))

    env = os.environ.copy()
    env["PNG_ISO_OUT"] = str(out_png_iso.resolve()).replace("\\", "/")
    env["PNG_TOP_OUT"] = str(out_png_top.resolve()).replace("\\", "/")
    env["REPORT_OUT"] = str(out_report.resolve()).replace("\\", "/")
    env["SHELL_JSON_IN"] = str(out_shell_json.resolve()).replace("\\", "/")
    env["SOFT_BARRIERS_MODE"] = soft_barriers_mode
    # Inject the verified per-plant real-world scale unless the caller set
    # PT_TO_M explicitly. Plants without a verified anchor keep the Ruby
    # default (0.0352). See PLANT_PT_TO_M for the planta_74 derivation.
    _plant_scale = resolve_plant_pt_to_m(consensus_path, env)
    if _plant_scale is not None:
        env["PT_TO_M"] = _plant_scale
        print(
            f"[scale] {plant_from_fixture_path(consensus_path)}: "
            f"PT_TO_M={_plant_scale} (verified cota anchor)"
        )
    # Resolve runner mode (CLAUDE.md §18, LL-015, FP-023).
    # Safe default = `interactive` for local dev; `headless` on CI so
    # we preserve historical terminate-after-SKP behaviour. CLI flags
    # (`--mode`, `--no-terminate`) and `RUN_MODE` env var override.
    resolved_mode = mode if mode is not None else parse_mode(
        default=_default_runner_mode()
    )
    log_mode(resolved_mode)
    terminate_allowed = should_terminate(resolved_mode)

    print(f"[run] launching SU: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        env=env,
    )

    try:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if out_skp.exists():
                time.sleep(2)  # flush
                print(f"[ok] {out_skp} ({out_skp.stat().st_size} bytes)")
                _pid = getattr(proc, "pid", "?")
                if terminate_allowed:
                    try:
                        proc.terminate()
                        print(f"[su-runner] terminated own child PID {_pid}")
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    print(
                        f"[su-runner] artifact ready; SU left running "
                        f"(PID {_pid}) per mode={resolved_mode}"
                    )
                # Persist sidecar metadata so a future run with the
                # same consensus short-circuits the cache check.
                if consensus_sha is not None:
                    write_metadata(
                        out_skp,
                        consensus_sha256=consensus_sha,
                        sketchup_exe=sketchup_exe,
                        command=cmd,
                    )
                return {
                    "ok": True,
                    "skipped": False,
                    "skp_path": str(out_skp),
                    "png_iso": str(out_png_iso),
                    "png_top": str(out_png_top),
                    "report": str(out_report),
                    "shell_json": str(out_shell_json),
                    "consensus_sha256": consensus_sha,
                    "elapsed_s": round(time.time() - started, 4),
                    "stats": stats,
                }
            if proc.poll() is not None:
                err_file = plugins_dir / "autorun_error.txt"
                print(
                    f"[err] SU exited prematurely code={proc.returncode}"
                )
                if err_file.exists():
                    print("---- ruby error ----")
                    print(err_file.read_text(
                        encoding="utf-8", errors="replace"
                    ))
                return {"ok": False, "stats": stats}
            time.sleep(1)
        print(f"[err] timeout {timeout_s}s waiting for {out_skp}")
        # Timeout cleanup respects mode: in `interactive`/`attach` we
        # leave SU running so the user can inspect what went wrong;
        # in `headless` we terminate our own child cleanly.
        _pid = getattr(proc, "pid", "?")
        if terminate_allowed:
            try:
                proc.terminate()
                time.sleep(2)
                proc.kill()
                print(f"[su-runner] timeout terminated own child PID {_pid}")
            except Exception:  # noqa: BLE001
                pass
        else:
            print(
                f"[su-runner] timeout — SU left running (PID {_pid}) "
                f"per mode={resolved_mode}; investigate manually"
            )
        return {"ok": False, "stats": stats, "timeout": True}
    finally:
        for p in disarm_autoruns(plugins_dir):
            print(f"[post-run disarm] removed {p.name}")


def _infer_plant(consensus_path, explicit=None):
    """Plant for --promote: explicit, else fixtures/<plant>/..., else planta_74."""
    if explicit:
        return explicit
    parts = Path(consensus_path).resolve().parts
    if "fixtures" in parts:
        i = parts.index("fixtures")
        if i + 1 < len(parts):
            return parts[i + 1]
    return "planta_74"


def _auto_promote(args, result):
    """After a green build, copy it to the stable deliverable artifacts/<plant>/.
    Returns a status line to print. Gate-guarded: a failed self-check gate, a
    cached (not rebuilt) build, or a missing report is NOT promoted — we never
    push a broken/unverified build to the fixed path."""
    if not getattr(args, "promote", False):
        return None
    if not result.get("ok"):
        return "PROMOTE_SKIPPED build not ok"
    if result.get("skipped"):
        return "PROMOTE_SKIPPED build was cached (use --force-skp to rebuild+promote)"
    report_p = args.out.resolve().parent / "geometry_report.json"
    try:
        gates = json.loads(report_p.read_text("utf-8")).get("gates_self_check") or {}
    except Exception:
        gates = {}
    if not gates:
        return "PROMOTE_SKIPPED no gates_self_check in report"
    failed = sorted(k for k, v in gates.items() if not v)
    if failed:
        return f"PROMOTE_SKIPPED self-check gates failed: {failed}"
    # full deterministic fidelity suite must be green too: opening_host +
    # wall_overlap + wall_presence (exact projection). The deliverable must
    # never land at the fixed path with a deterministic FAIL/INCOMPLETE.
    out_dir = args.out.resolve().parent
    try:
        from tools.run_deterministic_gates import run_all
        det = run_all(consensus_path=str(args.consensus),
                      render_path=str(out_dir / "model_top.png"))
    except Exception as e:  # pragma: no cover - defensive
        return f"PROMOTE_SKIPPED deterministic gates errored: {e}"
    if det.get("overall") != "PASS":
        bad = {k: v.get("overall", v.get("verdict"))
               for k, v in det.get("gates", {}).items()
               if v.get("overall", v.get("verdict")) != "PASS"}
        return f"PROMOTE_SKIPPED deterministic gates {det.get('overall')}: {bad}"
    from tools.promote_canonical import promote as _promote
    plant = _infer_plant(args.consensus, args.plant)
    res = _promote(out_dir, plant)
    return (f"PROMOTED -> artifacts/{plant}/{plant}.skp sha={res['sha']} "
            f"(self-check + deterministic gates green)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("consensus", type=Path,
                    help="consensus_model.json or amended_observed.json")
    ap.add_argument("--out", type=Path, required=True,
                    help="output .skp path")
    ap.add_argument("--sketchup", type=Path,
                    default=Path(SKETCHUP_EXE_DEFAULT))
    ap.add_argument("--plugins", type=Path, default=PLUGINS_DIR_DEFAULT)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--soft-barriers", choices=("groups", "skip"),
                    default="groups",
                    help='"groups": emit each as SoftBarrier_Group_N at '
                         '1.10 m; "skip": skip and record in report')
    ap.add_argument("--force-skp", action="store_true",
                    help="bypass the consensus-hash cache, always launch SU")
    ap.add_argument(
        "--mode",
        choices=["headless", "ci", "interactive", "debug", "attach", "manual"],
        default=None,
        help=(
            "SU runner mode (CLAUDE.md §18). `headless`/`ci`: terminate "
            "own SU child after the marker. `interactive`/`debug`: leave "
            "SU running. `attach`/`manual`: don't launch SU. Default: "
            "CI-aware (`headless` on CI env, `interactive` elsewhere). "
            "Can also be set via RUN_MODE env."
        ),
    )
    ap.add_argument(
        "--no-terminate",
        action="store_true",
        help="Shorthand for --mode interactive (do not terminate SU).",
    )
    ap.add_argument(
        "--promote",
        action="store_true",
        help="After a successful build whose self-check gates are all green, "
             "copy it to the stable deliverable artifacts/<plant>/ so the "
             "latest correct build is always at one fixed path. A failed gate "
             "or a cached build skips the promote. (Appearance changes still "
             "go through Felipe's VISUAL_REVIEW before you build with this.)",
    )
    ap.add_argument(
        "--plant",
        default=None,
        help="Plant name for --promote (default: inferred from a "
             "fixtures/<plant>/ consensus path, else 'planta_74').",
    )
    args = ap.parse_args()
    resolved_mode = parse_mode(default=_default_runner_mode())
    result = run(
        args.consensus.resolve(), args.out.resolve(),
        sketchup_exe=args.sketchup,
        plugins_dir=args.plugins,
        timeout_s=args.timeout,
        soft_barriers_mode=args.soft_barriers,
        force_skp=args.force_skp,
        mode=resolved_mode,
    )
    if result.get("skipped"):
        sha = result.get("consensus_sha256") or ""
        print(f"SKIPPED_UNCHANGED_CONSENSUS sha={sha[:12]}")
    promo = _auto_promote(args, result)
    if promo:
        print(promo)
    raise SystemExit(0 if result.get("ok") else 1)
