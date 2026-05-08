"""On-demand thumbnail rendering for cockpit History view (Cycle 12g).

When a run dir has no PNG/SVG previews, render a small thumbnail
directly from the consensus JSON via a stripped-down PIL polygon
renderer, then cache under
``runs/<run_id>/_cockpit_cache/cockpit_thumbnail.png`` so subsequent
loads are free.

Design choices (Cycle 12g):

- **Pure Python + PIL only.** No new optional dependency. The
  cockpit's existing renderer (`cockpit.render_overlay`) emits
  SVG, not raster, and rasterising SVG would require ``cairosvg``
  (system-libcairo dependency, awkward on Windows). Instead we
  reuse the consensus geometry primitives (`_walls_to_polys`,
  ``_color_for``, ``_OPENING_KIND_COLORS``) and draw straight to
  ``PIL.Image`` via ``ImageDraw``. Visually leaner than the SVG
  inspector but sufficient as a History-row preview.

- **Cache-by-content via mtime.** The thumbnail goes stale when
  ``consensus_path.mtime > thumbnail_path.mtime``; otherwise we
  short-circuit. This mirrors §3 (the "cache-by-content" SKP
  rule) — cheap to check, no SHA needed for a 320 px PNG.

- **Graceful degradation.** Any failure (PIL missing, write
  permission denied, malformed consensus) returns ``None`` and
  logs a warning. The History view falls back to "no previews
  discovered" exactly as before — Cycle 12g must NEVER take down
  the cockpit.

- **No streamlit / no SketchUp imports.** This module stays
  pure-Python so the unit tests can exercise it without the
  Streamlit runtime.

Public API:
- ``CACHE_DIRNAME``     — ``"_cockpit_cache"``
- ``THUMBNAIL_FILENAME`` — ``"cockpit_thumbnail.png"``
- ``DEFAULT_WIDTH_PX``   — 320
- ``thumbnail_path``     — locate the cached PNG
- ``ensure_thumbnail``   — render if missing/stale, return path or None
- ``render_consensus_thumbnail`` — pure consensus → PNG bytes
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Sequence

# We deliberately import lazily inside ``render_consensus_thumbnail``
# rather than at module-import-time so a stripped checkout (no PIL)
# can still ``import cockpit.thumbnails`` and call ``thumbnail_path``.
# The render path raises ImportError, which ``ensure_thumbnail``
# catches and converts to a graceful ``None``.

# Cache configuration — kept module-level so tests can monkey-patch.
CACHE_DIRNAME = "_cockpit_cache"
THUMBNAIL_FILENAME = "cockpit_thumbnail.png"
DEFAULT_WIDTH_PX = 320
DEFAULT_HEIGHT_PX = 240
# Background of the thumbnail: matches the cockpit SVG canvas
# (`background:#f8f6ec` in `render_overlay.py`).
_BG_COLOR = (248, 246, 236)
# Wall color — same `#3b3326` the SVG renderer uses.
_WALL_COLOR = (59, 51, 38)
# Soft outline for room polygons.
_ROOM_OUTLINE = (122, 122, 122)
# Padding (in pixels) around the bbox so the geometry never touches
# the canvas border.
_PADDING_PX = 8

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def thumbnail_path(run_dir: Path) -> Path:
    """Return the on-disk path where the cached thumbnail lives.

    Does NOT check existence — callers that need a yes/no should
    test ``thumbnail_path(run_dir).exists()`` separately. The cache
    dir is NOT created here either; that is ``ensure_thumbnail``'s
    job (only when it actually has bytes to write)."""
    return run_dir / CACHE_DIRNAME / THUMBNAIL_FILENAME


def _is_thumbnail_stale(thumb_path: Path, consensus_path: Path) -> bool:
    """Stale = consensus file mtime > thumbnail file mtime, OR the
    consensus has been rebuilt since the cache was warmed."""
    try:
        cm = consensus_path.stat().st_mtime
        tm = thumb_path.stat().st_mtime
    except OSError:
        # If we can't stat either side, treat it as stale so we
        # re-render rather than silently serving wrong bytes.
        return True
    return cm > tm


# ---------------------------------------------------------------------------
# Geometry helpers — kept tiny so we don't grow a dependency on
# render_overlay's import surface (avoids cyclic imports if the
# cockpit ever shifts to a renderers package).
# ---------------------------------------------------------------------------

# Color palette — mirrors `cockpit.render_overlay._PALETTE` so a
# room rendered to PNG matches the SVG's color choice for the same
# name. Hex strings converted to RGB tuples below.
_PALETTE_HEX = (
    "#fdd9b5", "#fff2b8", "#dfe7c8", "#c8e6f5", "#e7d2f4",
    "#f4d2e7", "#d2f4e7", "#f4e7d2", "#d2e7f4", "#e7f4d2",
    "#cce0a3",
)


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


_PALETTE_RGB: tuple[tuple[int, int, int], ...] = tuple(
    _hex_to_rgb(h) for h in _PALETTE_HEX
)


def _color_for(name: str) -> tuple[int, int, int]:
    """Stable color per room name (hash modulo palette). Mirrors
    ``render_overlay._color_for`` but returns RGB instead of hex."""
    h = sum(ord(c) for c in (name or ""))
    return _PALETTE_RGB[h % len(_PALETTE_RGB)]


# Opening color map — mirrors `_OPENING_KIND_COLORS` in render_overlay.
_OPENING_RGB = {
    "interior_door": _hex_to_rgb("#f59e0b"),
    "interior_passage": _hex_to_rgb("#fbbf24"),
    "window": _hex_to_rgb("#60a5fa"),
    "glazed_balcony": _hex_to_rgb("#34d399"),
    "exterior_door": _hex_to_rgb("#dc2626"),
    "unknown": _hex_to_rgb("#9ca3af"),
}


def _walls_to_polys(walls: list[dict]) -> list[list[tuple[float, float]]]:
    """Each wall has start, end, thickness, orientation. Render as
    a thin filled rectangle in PDF coords. Same logic as
    ``render_overlay._walls_to_polys`` but yields tuples instead of
    nested lists, which PIL's polygon() likes more."""
    polys: list[list[tuple[float, float]]] = []
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
        polys.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    return polys


def _bbox(polys: Sequence[Sequence[tuple[float, float]]],
          extras: Sequence[tuple[float, float]] = ()
          ) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for poly in polys:
        for p in poly:
            xs.append(p[0])
            ys.append(p[1])
    for p in extras:
        xs.append(p[0])
        ys.append(p[1])
    if not xs:
        return (0.0, 0.0, 100.0, 100.0)
    return (min(xs), min(ys), max(xs), max(ys))


def _blend(color: tuple[int, int, int],
            bg: tuple[int, int, int],
            alpha: float) -> tuple[int, int, int]:
    """Pre-multiply ``color`` over ``bg`` so we can fake translucency
    on a non-RGBA PIL image (cheap PNG output, no alpha channel
    overhead)."""
    a = max(0.0, min(1.0, alpha))
    return tuple(  # type: ignore[return-value]
        int(round(color[i] * a + bg[i] * (1 - a))) for i in range(3)
    )


# ---------------------------------------------------------------------------
# Public render path
# ---------------------------------------------------------------------------

def render_consensus_thumbnail(consensus: dict,
                               width_px: int = DEFAULT_WIDTH_PX,
                               height_px: int | None = None) -> bytes:
    """Render the consensus to a PNG and return the bytes.

    Renders walls + rooms (translucent fill + label-skipped — small
    canvas, labels would just smear) + openings (small filled
    circles) onto a beige canvas. Y axis is flipped so PDF-up
    renders as visual-up, matching the SVG view.

    Raises:
        ImportError: when Pillow is not installed (the caller
        ``ensure_thumbnail`` catches this and degrades gracefully).
        ValueError: if ``width_px`` is non-positive.
    """
    if width_px <= 0:
        raise ValueError(f"width_px must be > 0, got {width_px}")

    # Lazy import — if a checkout has no PIL, we want the import
    # error to surface here (and ``ensure_thumbnail`` to catch it),
    # not at module load.
    from PIL import Image, ImageDraw  # noqa: WPS433

    walls = consensus.get("walls") or []
    rooms = consensus.get("rooms") or []
    openings = consensus.get("openings") or []
    wall_polys = _walls_to_polys(walls)
    room_polys: list[tuple[list[tuple[float, float]], str]] = []
    for r in rooms:
        poly = r.get("polygon_pts") or []
        if len(poly) < 3:
            continue
        room_polys.append(([(float(p[0]), float(p[1])) for p in poly],
                            r.get("name") or ""))
    opening_pts: list[tuple[float, float, str]] = []
    for op in openings:
        c = op.get("center")
        if not c or len(c) < 2:
            continue
        kind = op.get("kind_v5") or op.get("kind") or "unknown"
        opening_pts.append((float(c[0]), float(c[1]), kind))

    # bbox over everything we plan to draw, with a safe fallback when
    # the consensus is so empty there's nothing to plot.
    bbox_polys = list(wall_polys) + [poly for poly, _ in room_polys]
    if not bbox_polys and not opening_pts:
        bbox_polys = [[(0.0, 0.0), (100.0, 0.0),
                       (100.0, 100.0), (0.0, 100.0)]]
    extras = [(x, y) for x, y, _ in opening_pts]
    x0, y0, x1, y1 = _bbox(bbox_polys, extras)

    # Auto-derive height from data aspect ratio when the caller
    # didn't pin one. Keeps the cockpit thumbnail proportional even
    # for very long horizontal plants.
    data_w = max(1.0, x1 - x0)
    data_h = max(1.0, y1 - y0)
    if height_px is None:
        # Fit-to-width: keep aspect ratio but cap at DEFAULT_HEIGHT_PX
        # so a panoramic plant doesn't produce a 320×40 sliver.
        target_h = int(round(width_px * (data_h / data_w)))
        height_px = max(80, min(DEFAULT_HEIGHT_PX, target_h))
    if height_px <= 0:
        raise ValueError(f"height_px must be > 0, got {height_px}")

    # Compute the world-to-pixel scale so the bbox fills the canvas
    # (minus padding). Use the same scale on both axes so we don't
    # squash circles into ellipses.
    avail_w = width_px - 2 * _PADDING_PX
    avail_h = height_px - 2 * _PADDING_PX
    scale = min(avail_w / data_w, avail_h / data_h)
    # Center within the available space.
    px_w = data_w * scale
    px_h = data_h * scale
    off_x = (width_px - px_w) / 2.0
    off_y = (height_px - px_h) / 2.0

    def to_px(p: tuple[float, float]) -> tuple[float, float]:
        # PDF y-up → image y-down. We map x linearly and flip y.
        x = off_x + (p[0] - x0) * scale
        y = off_y + (y1 - p[1]) * scale
        return (x, y)

    image = Image.new("RGB", (width_px, height_px), _BG_COLOR)
    draw = ImageDraw.Draw(image)

    # Rooms FIRST (so walls render on top, matching the SVG).
    for poly, name in room_polys:
        rgb = _color_for(name)
        # Fake the SVG's fill-opacity=0.55 by pre-blending against bg.
        fill = _blend(rgb, _BG_COLOR, 0.55)
        px_poly = [to_px(p) for p in poly]
        draw.polygon(px_poly, fill=fill, outline=_ROOM_OUTLINE)

    # Walls (solid dark fill).
    for poly in wall_polys:
        px_poly = [to_px(p) for p in poly]
        draw.polygon(px_poly, fill=_WALL_COLOR)

    # Openings — small filled circles. Radius scales with canvas.
    op_r = max(2, int(round(min(width_px, height_px) * 0.012)))
    for x, y, kind in opening_pts:
        cx, cy = to_px((x, y))
        rgb = _OPENING_RGB.get(kind, _OPENING_RGB["unknown"])
        bbox = (cx - op_r, cy - op_r, cx + op_r, cy + op_r)
        draw.ellipse(bbox, fill=rgb, outline=(0, 0, 0))

    # Encode to PNG bytes.
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def ensure_thumbnail(run_dir: Path,
                      consensus_path: Path,
                      width_px: int = DEFAULT_WIDTH_PX,
                      force: bool = False) -> Path | None:
    """Return the on-disk thumbnail path, rendering it if missing or stale.

    Args:
        run_dir: The run directory whose preview we're warming.
        consensus_path: Path to the consensus JSON. Must be readable;
            if it can't be parsed we return ``None`` (graceful).
        width_px: Override default 320 px width. Height is derived
            from the consensus aspect ratio.
        force: When True, always re-render (ignores the freshness
            check). Useful for debugging.

    Returns:
        Path to the PNG when the cache is warm (either pre-existing
        and fresh, or freshly rendered). ``None`` if rendering
        failed for any reason — the History view treats that as
        "no preview" and falls back to its existing message.

    Never raises. All I/O / PIL / JSON failures are caught and
    converted to a logged warning + ``None``.
    """
    thumb = thumbnail_path(run_dir)

    # Fast path: cached thumbnail already exists and is fresh.
    if not force and thumb.exists():
        if not consensus_path.exists():
            # Defensive: if the consensus has been deleted but the
            # cache survives, we trust the cache.
            return thumb
        if not _is_thumbnail_stale(thumb, consensus_path):
            return thumb

    # Slow path: render. Wrap everything in a try so a render
    # failure never bubbles up into the History view.
    try:
        if not consensus_path.exists():
            log.warning(
                "ensure_thumbnail: consensus_path missing for %s (%s)",
                run_dir, consensus_path,
            )
            return None
        import json  # noqa: WPS433 — local for the same lazy reason
        try:
            consensus = json.loads(
                consensus_path.read_text(encoding="utf-8"),
            )
        except (OSError, json.JSONDecodeError) as exc:
            log.warning(
                "ensure_thumbnail: cannot parse consensus %s: %s",
                consensus_path, exc,
            )
            return None
        png_bytes = render_consensus_thumbnail(consensus, width_px=width_px)
    except ImportError as exc:
        log.warning(
            "ensure_thumbnail: rendering deps missing (%s); "
            "skipping thumbnail for %s",
            exc, run_dir,
        )
        return None
    except Exception as exc:  # noqa: BLE001 — graceful degradation
        log.warning(
            "ensure_thumbnail: render failed for %s: %s",
            run_dir, exc,
        )
        return None

    # Write atomically: render to a sibling tmp then rename. Avoids
    # half-written PNGs if the process is killed mid-write.
    try:
        thumb.parent.mkdir(parents=True, exist_ok=True)
        tmp = thumb.with_suffix(thumb.suffix + ".tmp")
        tmp.write_bytes(png_bytes)
        tmp.replace(thumb)
    except OSError as exc:
        log.warning(
            "ensure_thumbnail: cache write failed for %s: %s",
            thumb, exc,
        )
        return None

    return thumb
