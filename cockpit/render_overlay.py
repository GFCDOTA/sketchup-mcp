"""SVG overlay renderer for the Validation Cockpit.

Takes a consensus dict (post-classifier `c3` shape) and emits an
SVG string that visualizes:
- walls (filled rectangles in PDF coords)
- rooms (translucent polygons + label + area)
- openings (door arcs / wall-gaps as colored markers on host walls)
- (optional, Cycle 12b) the source PDF page rasterised behind it
  via `pypdfium2`, so the consensus is overlaid on the original
  drawing instead of an empty canvas.

Zero hard dependencies for the consensus-only path (pure Python +
stdlib). The PDF underlay path uses `pypdfium2` (already a core dep
since the vector pipeline imports it).

Coord system note: PDF user space has origin at bottom-left and
y axis pointing UP. SVG has origin at top-left and y pointing
DOWN. This module flips y inside the SVG transform so the rendered
view matches what you'd see in a PDF reader. The optional PDF
underlay is rasterised top-down (its native orientation) and placed
OUTSIDE the y-flip group so it renders right-side-up.
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

# ---------- Toggle bag --------------------------------------------------

@dataclass
class OverlayToggles:
    """User-toggleable layers. The Streamlit app constructs this
    from sidebar checkboxes; the renderer respects each flag."""
    walls: bool = True
    rooms: bool = True
    labels: bool = True
    openings: bool = True
    ground_truth_overlay: bool = False
    warnings: bool = True


# ---------- Color palette (deterministic per room name) ----------------

_PALETTE = [
    "#fdd9b5", "#fff2b8", "#dfe7c8", "#c8e6f5", "#e7d2f4",
    "#f4d2e7", "#d2f4e7", "#f4e7d2", "#d2e7f4", "#e7f4d2",
    "#cce0a3",
]


def _color_for(name: str) -> str:
    """Stable color per room name (hash modulo palette)."""
    h = sum(ord(c) for c in (name or ""))
    return _PALETTE[h % len(_PALETTE)]


# ---------- Geometry helpers -------------------------------------------

def _polygon_area_pt2(pts: Sequence[Sequence[float]]) -> float:
    if len(pts) < 3:
        return 0.0
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return abs(a) * 0.5


def _bbox_pt(*polys: Sequence[Sequence[float]]) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for poly in polys:
        for p in poly:
            xs.append(p[0])
            ys.append(p[1])
    if not xs:
        return (0.0, 0.0, 100.0, 100.0)
    return (min(xs), min(ys), max(xs), max(ys))


def _walls_to_polys(walls: list[dict]) -> list[list[list[float]]]:
    """Each wall has start, end, thickness, orientation. Render as
    a thin filled rectangle in PDF coords."""
    polys: list[list[list[float]]] = []
    for w in walls:
        s = w.get("start") or [0, 0]
        e = w.get("end") or [0, 0]
        t = float(w.get("thickness", 5.4))
        if w.get("orientation") == "h":
            x0, x1 = sorted([float(s[0]), float(e[0])])
            cy = float(s[1])
            y0, y1 = cy - t / 2, cy + t / 2
        else:
            cx = float(s[0])
            y0, y1 = sorted([float(s[1]), float(e[1])])
            x0, x1 = cx - t / 2, cx + t / 2
        polys.append([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    return polys


# ---------- SVG primitives ---------------------------------------------

def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))


def _polygon_svg(pts: Sequence[Sequence[float]],
                  fill: str = "none",
                  stroke: str = "#222",
                  stroke_width: float = 0.5,
                  fill_opacity: float = 1.0,
                  class_name: str | None = None,
                  title_text: str | None = None) -> str:
    """Emit a `<polygon>`. When `title_text` is provided, the polygon
    becomes a parent element with a `<title>` child — browsers render
    this as a native tooltip on hover (Cycle 12c). When `class_name`
    is provided the CSS rule in the SVG `<style>` block applies."""
    pts_str = " ".join(f"{p[0]:.2f},{p[1]:.2f}" for p in pts)
    cls = f' class="{class_name}"' if class_name else ""
    if title_text is None:
        return (
            f'<polygon{cls} points="{pts_str}" '
            f'fill="{fill}" fill-opacity="{fill_opacity}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}" />'
        )
    return (
        f'<polygon{cls} points="{pts_str}" '
        f'fill="{fill}" fill-opacity="{fill_opacity}" '
        f'stroke="{stroke}" stroke-width="{stroke_width}">'
        f'<title>{_xml_escape(title_text)}</title>'
        f'</polygon>'
    )


def _circle_svg(cx: float, cy: float, r: float,
                  fill: str = "#f59e0b",
                  stroke: str = "#000",
                  stroke_width: float = 0.4,
                  class_name: str | None = None,
                  title_text: str | None = None) -> str:
    """Emit a `<circle>`. Same `<title>` + `class` extension as
    `_polygon_svg` for hover tooltips (Cycle 12c)."""
    cls = f' class="{class_name}"' if class_name else ""
    if title_text is None:
        return (
            f'<circle{cls} cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}" />'
        )
    return (
        f'<circle{cls} cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}">'
        f'<title>{_xml_escape(title_text)}</title>'
        f'</circle>'
    )


# ---------- Hover-highlight CSS (Cycle 12c) ----------------------------
# Emitted inside the SVG so the file remains self-contained. Pure CSS
# (no JS), works in every browser AND in GitHub's inline SVG renderer.
_HOVER_STYLE_BLOCK = (
    '<style>'
    '.hover-room{transition:fill-opacity 0.15s,stroke-width 0.15s;}'
    '.hover-room:hover{fill-opacity:0.85;stroke-width:2.5;cursor:pointer;}'
    '.hover-opening{transition:stroke-width 0.15s;}'
    '.hover-opening:hover{stroke-width:1.5;cursor:pointer;}'
    '</style>'
)


def _text_svg(x: float, y: float, text: str,
                size_pt: float = 8.0,
                fill: str = "#111") -> str:
    safe = (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" '
        f'font-family="sans-serif" font-size="{size_pt:.1f}" '
        f'fill="{fill}" text-anchor="middle" '
        f'dominant-baseline="middle">{safe}</text>'
    )


# ---------- Public renderer --------------------------------------------

PT_TO_M_DEFAULT = 0.19 / 5.4


@dataclass
class PdfUnderlay:
    """Rasterised PDF page used as a visual base layer.

    Built by `pdf_page_to_data_url`. Carries the page bounds in PT
    so the renderer can align the bitmap to the consensus coord
    space.
    """
    data_url: str
    page_w_pt: float
    page_h_pt: float
    opacity: float = 0.55


def pdf_page_to_data_url(pdf_path: str | Path,
                         page_index: int = 0,
                         dpi: int = 144,
                         opacity: float = 0.55) -> PdfUnderlay:
    """Render a PDF page to a PNG data URL via `pypdfium2`.

    Returns a `PdfUnderlay` carrying the data URL + the page bounds
    in PDF user-space PT. Resolution is `dpi`; default 144 = 2× the
    PDF DPI (72), good enough to read text without exploding the
    embedded base64. Raises `FileNotFoundError` if the path is
    missing.
    """
    import pypdfium2 as pdfium  # local import — not on the SVG-only path

    p = Path(pdf_path)
    if not p.exists():
        raise FileNotFoundError(p)
    doc = pdfium.PdfDocument(str(p))
    try:
        page = doc[page_index]
        page_w_pt = float(page.get_width())
        page_h_pt = float(page.get_height())
        scale = dpi / 72.0
        pil_image = page.render(scale=scale).to_pil()
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG", optimize=True)
        png_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    finally:
        doc.close()
    return PdfUnderlay(
        data_url=f"data:image/png;base64,{png_b64}",
        page_w_pt=page_w_pt,
        page_h_pt=page_h_pt,
        opacity=opacity,
    )


def render_overlay_svg(consensus: dict,
                         toggles: OverlayToggles | None = None,
                         pt_to_m: float = PT_TO_M_DEFAULT,
                         expected_model: dict | None = None,
                         pdf_underlay: PdfUnderlay | None = None) -> str:
    """Build a self-contained SVG string visualizing the consensus.

    Coordinates are in PDF user space; the SVG flips y so PDF-up
    renders as visual-up (matches what you'd see in a PDF reader).

    The viewBox is auto-fit to the union of walls + rooms by
    default. When `pdf_underlay` is provided (Cycle 12b), the
    viewBox is overridden to the PDF page bounds so the rasterised
    page fills the canvas, and the bitmap is placed OUTSIDE the
    y-flip group so it renders in its native top-down orientation.
    """
    toggles = toggles or OverlayToggles()
    walls = consensus.get("walls") or []
    rooms = consensus.get("rooms") or []
    openings = consensus.get("openings") or []
    wall_polys = _walls_to_polys(walls)

    if pdf_underlay is not None:
        # When the PDF page is present, anchor the viewBox to its
        # native bounds: that way the consensus polygons (already in
        # PDF coords) sit perfectly on top of the rasterised page.
        x0, y0 = 0.0, 0.0
        x1, y1 = pdf_underlay.page_w_pt, pdf_underlay.page_h_pt
        w = x1 - x0
        h = y1 - y0
    else:
        all_polys: list[list[list[float]]] = []
        if toggles.walls:
            all_polys.extend(wall_polys)
        if toggles.rooms:
            for r in rooms:
                poly = r.get("polygon_pts") or []
                if poly:
                    all_polys.append(poly)
        if not all_polys:
            all_polys = wall_polys or [[[0, 0], [100, 0], [100, 100], [0, 100]]]

        x0, y0, x1, y1 = _bbox_pt(*all_polys)
        pad = max(10.0, (x1 - x0) * 0.04)
        x0 -= pad
        y0 -= pad
        x1 += pad
        y1 += pad
        w = x1 - x0
        h = y1 - y0

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{x0:.2f} {y0:.2f} {w:.2f} {h:.2f}" '
        f'preserveAspectRatio="xMidYMid meet" '
        f'style="width:100%;height:auto;background:#f8f6ec;'
        f'border:1px solid #ccc;">'
    )
    # Hover-highlight CSS (Cycle 12c). Self-contained inside the SVG
    # so the file stays portable.
    parts.append(_HOVER_STYLE_BLOCK)

    # PDF underlay (raster). Outside the flip group — the bitmap is
    # already top-down (pypdfium2 native), so we place it directly
    # in svg-coords with y running 0..h_pt down. The vector group
    # below applies its own y-flip so PDF-coord polygons land on the
    # correct page region.
    if pdf_underlay is not None:
        parts.append(
            f'<image x="0" y="0" '
            f'width="{pdf_underlay.page_w_pt:.2f}" '
            f'height="{pdf_underlay.page_h_pt:.2f}" '
            f'opacity="{pdf_underlay.opacity:.2f}" '
            f'preserveAspectRatio="none" '
            f'href="{pdf_underlay.data_url}" />'
        )

    # Flip Y so PDF up = visual up.
    parts.append(
        f'<g transform="translate(0 {y0 + y1}) scale(1 -1)">'
    )

    # Build the GT match → outline color map ONCE per render. Empty
    # when GT toggle off or no expected_model supplied (Cycle 12d).
    status_color_map: dict[str, str] = {}
    if toggles.ground_truth_overlay and expected_model is not None:
        status_color_map = _build_room_status_map(
            consensus, expected_model, pt_to_m,
        )

    # Rooms first (so walls render on top).
    if toggles.rooms:
        for r in rooms:
            poly = r.get("polygon_pts") or []
            if len(poly) < 3:
                continue
            color = _color_for(r.get("name") or "")
            stroke_color = "#7a7a7a"
            stroke_width = 0.4
            rid = r.get("id") or ""
            if rid in status_color_map:
                # GT-overlay-on: thicken the outline and recolor it
                # to the match status (green/orange/red/grey).
                stroke_color = status_color_map[rid]
                stroke_width = 2.0
            # Cycle 12c hover tooltip: room name + computed area
            name = r.get("name") or "?"
            area_pt = float(r.get("area_pts2") or _polygon_area_pt2(poly))
            area_m2 = area_pt * pt_to_m * pt_to_m
            tooltip = f"{name} · {area_m2:.1f} m² · id={rid or '?'}"
            parts.append(_polygon_svg(
                poly, fill=color, stroke=stroke_color,
                stroke_width=stroke_width, fill_opacity=0.55,
                class_name="hover-room", title_text=tooltip,
            ))

    # Walls.
    if toggles.walls:
        for poly in wall_polys:
            parts.append(_polygon_svg(
                poly, fill="#3b3326", stroke="none", stroke_width=0,
            ))

    # Labels.
    if toggles.labels:
        for r in rooms:
            poly = r.get("polygon_pts") or []
            if not poly:
                continue
            cx = sum(p[0] for p in poly) / len(poly)
            cy = sum(p[1] for p in poly) / len(poly)
            label = (r.get("name") or "?").upper()
            area_pt = float(r.get("area_pts2") or _polygon_area_pt2(poly))
            area_m2 = area_pt * pt_to_m * pt_to_m
            # Reverse-y the text (it's inside the flip group, so we
            # need to UN-flip the text glyphs back to readable).
            parts.append(
                f'<g transform="translate({cx:.2f} {cy:.2f}) scale(1 -1)">'
            )
            parts.append(_text_svg(0, -2, label, size_pt=8.0))
            parts.append(_text_svg(0, 8, f"{area_m2:.1f} m²",
                                     size_pt=6.0, fill="#444"))
            parts.append("</g>")

    # Openings as colored circles on the wall midpoint.
    if toggles.openings:
        for op in openings:
            c = op.get("center")
            if not c or len(c) < 2:
                continue
            kind = op.get("kind_v5") or op.get("kind") or "?"
            color = _OPENING_KIND_COLORS.get(kind, "#888")
            decision = op.get("decision", "?")
            stroke = "#000" if decision == "clean" else "#888"
            # Cycle 12c hover tooltip: kind + decision + room context
            ev = op.get("evidence") or {}
            room_left = (op.get("room_left_name")
                          or ev.get("room_left") or "?")
            room_right = (op.get("room_right_name")
                           or ev.get("room_right") or "?")
            tooltip = (
                f"{kind} · decision={decision} · "
                f"{room_left} ↔ {room_right} · "
                f"id={op.get('id') or '?'}"
            )
            parts.append(_circle_svg(
                float(c[0]), float(c[1]), r=4.0, fill=color,
                stroke=stroke, stroke_width=0.5,
                class_name="hover-opening", title_text=tooltip,
            ))

    parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


_OPENING_KIND_COLORS = {
    "interior_door": "#f59e0b",       # orange — solid swing door
    "interior_passage": "#fbbf24",    # softer orange — open passage
    "window": "#60a5fa",              # blue — window
    "glazed_balcony": "#34d399",      # green — porta-vidro / balcony
    "exterior_door": "#dc2626",       # red — entry
    "unknown": "#9ca3af",             # grey
}


# ---------- Expected-model match (Cycle 12d) ---------------------------

# Status palette for the expected_model overlay. Tuned to read on the
# beige cockpit background AND alongside the kind-coded opening
# circles without colliding visually.
_EXPECTED_MATCH_COLORS = {
    "in_range": "#16a34a",         # green — observed within expected range
    "out_of_range_low": "#f59e0b",  # orange — observed below expected_min
    "out_of_range_high": "#ea580c", # deeper orange — observed above expected_max
    "missing_polygon": "#dc2626",   # red — expected room but no observed match
    "unmatched_observed": "#9ca3af",# grey — observed room with no expected entry
}


def expected_match_summary(consensus: dict,
                            expected_model: dict | None,
                            pt_to_m: float = PT_TO_M_DEFAULT) -> list[dict]:
    """Build a per-room match table between observed (consensus) and
    expected (ground-truth) rooms.

    Match key is a case-insensitive comparison between observed
    `name` and expected `label`. Schema of each row:

        {
          "expected_id": str | None,
          "expected_label": str | None,
          "observed_id": str | None,
          "observed_name": str | None,
          "observed_area_m2": float | None,
          "expected_area_m2_range": [float, float] | None,
          "status": "in_range" | "out_of_range_low" |
                    "out_of_range_high" | "missing_polygon" |
                    "unmatched_observed",
        }

    Returns one row per expected room, plus extra rows for observed
    rooms with no expected counterpart (status `unmatched_observed`).
    Empty list when `expected_model` is `None` or has no `rooms`.
    """
    if not expected_model:
        return []
    expected_rooms = expected_model.get("rooms") or []
    observed_rooms = consensus.get("rooms") or []

    obs_by_label: dict[str, dict] = {
        (r.get("name") or "").strip().upper(): r for r in observed_rooms
    }
    out: list[dict] = []
    matched_obs_ids: set[str] = set()

    for er in expected_rooms:
        label = (er.get("label") or "").strip()
        rng = er.get("expected_area_m2_range")
        obs = obs_by_label.get(label.upper())
        if obs is None:
            out.append({
                "expected_id": er.get("id"),
                "expected_label": label,
                "observed_id": None,
                "observed_name": None,
                "observed_area_m2": None,
                "expected_area_m2_range": rng,
                "status": "missing_polygon",
            })
            continue
        matched_obs_ids.add(obs.get("id") or "")
        area_pt = float(obs.get("area_pts2") or 0.0)
        area_m2 = area_pt * pt_to_m * pt_to_m
        status = "in_range"
        if rng and len(rng) == 2:
            lo, hi = float(rng[0]), float(rng[1])
            if area_m2 < lo:
                status = "out_of_range_low"
            elif area_m2 > hi:
                status = "out_of_range_high"
        out.append({
            "expected_id": er.get("id"),
            "expected_label": label,
            "observed_id": obs.get("id"),
            "observed_name": obs.get("name"),
            "observed_area_m2": round(area_m2, 2),
            "expected_area_m2_range": rng,
            "status": status,
        })

    # Catch observed rooms with no expected counterpart
    for obs in observed_rooms:
        oid = obs.get("id") or ""
        if oid in matched_obs_ids:
            continue
        area_pt = float(obs.get("area_pts2") or 0.0)
        area_m2 = area_pt * pt_to_m * pt_to_m
        out.append({
            "expected_id": None,
            "expected_label": None,
            "observed_id": oid,
            "observed_name": obs.get("name"),
            "observed_area_m2": round(area_m2, 2),
            "expected_area_m2_range": None,
            "status": "unmatched_observed",
        })

    return out


def _build_room_status_map(consensus: dict,
                            expected_model: dict | None,
                            pt_to_m: float) -> dict[str, str]:
    """Map observed room id → status color (only for observed rows
    in the match summary). Used by the renderer to recolor outlines.
    """
    summary = expected_match_summary(consensus, expected_model, pt_to_m)
    out: dict[str, str] = {}
    for row in summary:
        oid = row.get("observed_id")
        if not oid:
            continue
        out[oid] = _EXPECTED_MATCH_COLORS.get(
            row.get("status") or "", "#9ca3af",
        )
    return out


# ---------- Inspector helpers (text summaries) -------------------------

def room_summary_rows(consensus: dict,
                       pt_to_m: float = PT_TO_M_DEFAULT) -> list[dict]:
    """Each row = {id, name, area_m2, polygon_pts, openings_count}."""
    rooms = consensus.get("rooms") or []
    openings = consensus.get("openings") or []
    by_room: dict[str, int] = {}
    for op in openings:
        ev = op.get("evidence") or {}
        for k in ("room_left_id", "room_right_id"):
            rid = op.get(k) or ev.get(k)
            if rid:
                by_room[rid] = by_room.get(rid, 0) + 1
    out = []
    for r in rooms:
        area_pt = float(r.get("area_pts2") or 0.0)
        out.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "area_m2": round(area_pt * pt_to_m * pt_to_m, 2),
            "polygon_verts": len(r.get("polygon_pts") or []),
            "openings_touching": by_room.get(r.get("id") or "", 0),
            "method": r.get("method"),
        })
    return out


def opening_summary_rows(consensus: dict) -> list[dict]:
    """Each row = {id, kind, decision, room_left, room_right, confidence,
    width_m}."""
    openings = consensus.get("openings") or []
    out = []
    for op in openings:
        ev = op.get("evidence") or {}
        out.append({
            "id": op.get("id"),
            "kind": op.get("kind_v5") or op.get("kind"),
            "decision": op.get("decision"),
            "room_left": (op.get("room_left_name")
                          or ev.get("room_left")),
            "room_right": (op.get("room_right_name")
                            or ev.get("room_right")),
            "confidence": op.get("confidence"),
            "width_m": ev.get("width_m"),
            "host_wall": op.get("wall_id"),
        })
    return out
