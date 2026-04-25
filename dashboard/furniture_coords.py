"""Project consensus furniture into PDF-pt space and overlay on planta image.

Inputs:
  - dashboard/detections/cubicasa_<run>.json     (CubiCasa raw detections)
  - runs/<run>/consensus_model.json              (consensus rooms in svg PDF pts)
  - sketchup-mcp/runs/planta_74/raw_page.png     (raw rasterised PDF page)

Outputs:
  - runs/<run>/consensus_model.json              (mutated: each furniture[] gets
                                                  center_pdf_pt and pixel hint)
  - runs/<run>/furniture_overlay.png             (planta + furniture icons)

Strategy:
  * CubiCasa furniture comes in cubicasa_resized space (image coords).
    We compute the cubicasa wall bbox (excluding furniture) and the consensus
    svg wall bbox; both describe the same physical apartment, so a linear
    bbox-to-bbox map projects cubicasa coords into svg PDF-pt space directly
    (no rotation needed - both spaces happen to share orientation).
  * Qwen furniture only carries a room_label; we look up the matching room
    polygon in the consensus_model and place the item near the room centroid,
    optionally nudged by a small per-type offset so multiple items in the
    same room don't stack on top of each other.
  * For the overlay PNG we draw on the consensus svg PDF-pt canvas (same
    space as walls/rooms/openings) so positioning is consistent with the
    rest of the pipeline. The raw_page.png is rendered at the appropriate
    location for visual context. If raw_page can't be aligned cleanly (it
    is in a different aspect than svg), we render a synthetic outline of
    the consensus walls instead.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont


# ----- Paths ---------------------------------------------------------------

ROOT = Path(r"E:\Claude")
CONSENSUS_PATH = ROOT / "sketchup-mcp-exp-dedup" / "runs" / "final_planta_74" / "consensus_model.json"
CUBICASA_PATH = ROOT / "sketchup-mcp-exp-dedup" / "dashboard" / "detections" / "cubicasa_final_planta_74.json"
RAW_PAGE_PATH = ROOT / "sketchup-mcp" / "runs" / "planta_74" / "raw_page.png"
OVERLAY_PATH = ROOT / "sketchup-mcp-exp-dedup" / "runs" / "final_planta_74" / "furniture_overlay.png"


# ----- Type → icon style ---------------------------------------------------

# (shape, fill_rgba, outline_rgba, label)
ICON_STYLE: Dict[str, Tuple[str, Tuple[int, int, int, int], Tuple[int, int, int, int], str]] = {
    "bed":             ("rect",   (139,  90,  43, 200), (60,  30,   0, 255), "BED"),
    "sofa":            ("rect",   ( 60, 160,  90, 200), (20,  90,  40, 255), "SOFA"),
    "dining table":    ("rect",   (180, 140,  80, 200), (100, 70,  20, 255), "TBL"),
    "kitchen island":  ("rect",   (200, 200, 200, 200), (90,  90,  90, 255), "KI"),
    "table":           ("rect",   (180, 140,  80, 200), (100, 70,  20, 255), "TBL"),
    "sink":            ("circle", ( 70, 130, 220, 220), (20,  60, 140, 255), "SK"),
    "toilet":          ("circle", (245, 245, 245, 220), (40,  40,  40, 255), "WC"),
    "closet":          ("rect",   (160, 110,  70, 200), (80,  50,  20, 255), "CLO"),
    "bath":            ("circle", (180, 220, 240, 220), (60, 100, 160, 255), "BATH"),
}
DEFAULT_STYLE = ("circle", (200, 200, 200, 200), (60, 60, 60, 255), "?")

# Per-type offset (in SVG PDF pts) so 2 items in same room don't overlap.
# Order/index modulates the offset within a type bucket.
ROOM_OFFSET_BY_TYPE: Dict[str, Tuple[float, float]] = {
    "bed":            (   0.0,  -30.0),  # bed pushed toward upper wall
    "sofa":           ( -25.0,    0.0),  # sofa to the left
    "dining table":   (  10.0,    0.0),  # table near centroid
    "kitchen island": (   0.0,   20.0),  # island slightly down
}


# ----- Helpers -------------------------------------------------------------

def bbox_of_points(points: Sequence[Sequence[float]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def polygon_centroid(polygon: Sequence[Sequence[float]]) -> Tuple[float, float]:
    """Area-weighted centroid via the shoelace formula. Falls back to the
    arithmetic mean if the polygon is degenerate."""
    if not polygon:
        return 0.0, 0.0
    n = len(polygon)
    if n < 3:
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        return sum(xs) / n, sum(ys) / n

    a = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        x0, y0 = polygon[i][0], polygon[i][1]
        x1, y1 = polygon[(i + 1) % n][0], polygon[(i + 1) % n][1]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if abs(a) < 1e-9:
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        return sum(xs) / n, sum(ys) / n
    cx /= 6.0 * a
    cy /= 6.0 * a
    return cx, cy


def cubicasa_wall_bbox(cubicasa: dict) -> Tuple[float, float, float, float]:
    walls = [d for d in cubicasa.get("detections", [])
             if d.get("kind") == "wall" and d.get("polygon")]
    pts: List[Sequence[float]] = []
    for w in walls:
        pts.extend(w["polygon"])
    if not pts:
        raise RuntimeError("cubicasa has no wall detections; cannot calibrate map")
    return bbox_of_points(pts)


def consensus_wall_bbox(consensus: dict) -> Tuple[float, float, float, float]:
    pts: List[Sequence[float]] = []
    for w in consensus.get("walls", []):
        pts.append(w["start"])
        pts.append(w["end"])
    if not pts:
        raise RuntimeError("consensus has no walls; cannot calibrate map")
    return bbox_of_points(pts)


def make_cubicasa_to_svg(cc_bbox, svg_bbox):
    cc_minx, cc_miny, cc_maxx, cc_maxy = cc_bbox
    sv_minx, sv_miny, sv_maxx, sv_maxy = svg_bbox
    sx = (sv_maxx - sv_minx) / max(cc_maxx - cc_minx, 1e-9)
    sy = (sv_maxy - sv_miny) / max(cc_maxy - cc_miny, 1e-9)

    def project(cc_x: float, cc_y: float) -> Tuple[float, float]:
        return (sv_minx + (cc_x - cc_minx) * sx,
                sv_miny + (cc_y - cc_miny) * sy)

    return project


def find_room_by_label(rooms: List[dict], label: str) -> dict | None:
    target = label.strip().lower()
    for r in rooms:
        cand = (r.get("label_qwen") or "").strip().lower()
        if cand == target:
            return r
    # Loose contains-match as fallback
    for r in rooms:
        cand = (r.get("label_qwen") or "").strip().lower()
        if cand and (target in cand or cand in target):
            return r
    return None


def in_bounds(pt: Tuple[float, float], bounds: dict) -> bool:
    x, y = pt
    return (bounds["min_x"] <= x <= bounds["max_x"]
            and bounds["min_y"] <= y <= bounds["max_y"])


# ----- Main fusion ---------------------------------------------------------

def project_furniture(consensus: dict, cubicasa: dict) -> Tuple[List[dict], dict]:
    cc_bbox = cubicasa_wall_bbox(cubicasa)
    sv_bbox = consensus_wall_bbox(consensus)
    cc_to_svg = make_cubicasa_to_svg(cc_bbox, sv_bbox)

    # The consensus uses an svg-derived PDF-pt space; this differs from the
    # legacy v13 page_bounds but is the canonical space for rooms/walls in
    # the file we mutate. Re-derive page_bounds from svg walls so the
    # in_bounds check matches the consensus polygons.
    svg_bounds_dict = {
        "min_x": sv_bbox[0], "min_y": sv_bbox[1],
        "max_x": sv_bbox[2], "max_y": sv_bbox[3],
    }

    type_seen: Dict[str, int] = {}
    new_furniture = []
    diag = {
        "cubicasa_in": 0, "cubicasa_mapped": 0, "cubicasa_out_of_bounds": 0,
        "qwen_in": 0, "qwen_mapped": 0, "qwen_no_room_match": 0, "qwen_out_of_bounds": 0,
        "cubicasa_wall_bbox": cc_bbox,
        "svg_wall_bbox": sv_bbox,
        "svg_bounds_used": svg_bounds_dict,
    }

    for f in consensus.get("furniture", []):
        out = dict(f)  # shallow copy
        ftype = (out.get("type") or "").lower()
        bucket_idx = type_seen.get(ftype, 0)
        type_seen[ftype] = bucket_idx + 1

        cc_center = out.get("approx_center_cubicasa_resized")
        room_label = out.get("room_label")

        center_pdf_pt: Tuple[float, float] | None = None
        method = None

        if cc_center is not None:
            diag["cubicasa_in"] += 1
            center_pdf_pt = cc_to_svg(cc_center[0], cc_center[1])
            method = "cubicasa_bbox_map"
            if not in_bounds(center_pdf_pt, svg_bounds_dict):
                diag["cubicasa_out_of_bounds"] += 1
            else:
                diag["cubicasa_mapped"] += 1
        elif room_label:
            diag["qwen_in"] += 1
            room = find_room_by_label(consensus.get("rooms", []), room_label)
            if room and room.get("polygon"):
                cx, cy = polygon_centroid(room["polygon"])
                ox, oy = ROOM_OFFSET_BY_TYPE.get(ftype, (0.0, 0.0))
                # Stagger duplicates within same type/room with a small jitter
                cx += ox + (bucket_idx * 12.0)
                cy += oy + (bucket_idx * 8.0)
                center_pdf_pt = (cx, cy)
                method = "room_centroid_offset"
                if in_bounds(center_pdf_pt, svg_bounds_dict):
                    diag["qwen_mapped"] += 1
                else:
                    diag["qwen_out_of_bounds"] += 1
            else:
                diag["qwen_no_room_match"] += 1

        if center_pdf_pt is not None:
            out["center_pdf_pt"] = [round(center_pdf_pt[0], 2), round(center_pdf_pt[1], 2)]
            out["coord_method"] = method
        new_furniture.append(out)

    return new_furniture, diag


# ----- Overlay rendering ---------------------------------------------------

def render_overlay(consensus: dict, raw_page_path: Path, out_path: Path) -> dict:
    """Render furniture icons + room outlines on a canvas large enough to
    contain the consensus svg PDF-pt extents.

    We optionally paste raw_page.png into the canvas as a faded background.
    Because raw_page.png is in a different aspect than the svg PDF-pt space
    (the raster covers the entire PDF page, including title block / legend,
    while the consensus is just the apartment ROI), we approximate the
    raster→svg-pt scale via the cubicasa↔svg wall bboxes already computed
    inside project_furniture. For the overlay we instead render a clean
    synthetic background drawn from the consensus walls + rooms, which is
    sufficient to verify each furniture lands in the correct room.
    """
    walls = consensus.get("walls", [])
    rooms = consensus.get("rooms", [])
    furniture = consensus.get("furniture", [])

    sv_bbox = consensus_wall_bbox(consensus)
    minx, miny, maxx, maxy = sv_bbox
    pad = 30.0
    minx -= pad; miny -= pad; maxx += pad; maxy += pad
    width_pt = maxx - minx
    height_pt = maxy - miny

    # Render at ~3.5 px / pt for crisp icons; bigger means a heavier file.
    px_per_pt = 3.5
    W = int(round(width_pt * px_per_pt))
    H = int(round(height_pt * px_per_pt))

    def to_px(x: float, y: float) -> Tuple[int, int]:
        return (int(round((x - minx) * px_per_pt)),
                int(round((y - miny) * px_per_pt)))

    img = Image.new("RGBA", (W, H), (252, 252, 250, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    # --- Try to paste raw_page.png as faded background, scaled to the apt
    # extents in the raster. We only know the cubicasa→svg map, not the
    # raster→svg map directly. Skip pasting; rely on synthetic background.
    # (Keeping the hook documented for later: a future refinement could fit
    # a raster ROI by detecting the apartment bbox in raw_page.png.)
    if raw_page_path.exists():
        # Best-effort: load and place raw_page rotated into a corner thumbnail
        # so the user can compare the icons against the real planta.
        try:
            raw = Image.open(raw_page_path).convert("RGBA")
            thumb_w = max(W // 4, 320)
            ratio = thumb_w / raw.width
            thumb = raw.resize((thumb_w, int(round(raw.height * ratio))))
            img.paste(thumb, (W - thumb.width - 12, 12), thumb)
            draw.rectangle(
                [(W - thumb.width - 12, 12),
                 (W - 12, 12 + thumb.height)],
                outline=(120, 120, 120, 255), width=2)
            draw.text((W - thumb.width - 8, 14),
                      "raw_page.png (reference)",
                      fill=(40, 40, 40, 255))
        except Exception:
            pass

    # --- Draw room polygons (faint fill + outline)
    palette = [
        (235, 240, 255, 90),
        (240, 250, 235, 90),
        (255, 245, 235, 90),
        (250, 240, 250, 90),
        (240, 250, 250, 90),
        (255, 250, 230, 90),
        (245, 235, 240, 90),
    ]
    for i, room in enumerate(rooms):
        poly = room.get("polygon") or []
        if len(poly) < 3:
            continue
        pts_px = [to_px(p[0], p[1]) for p in poly]
        fill = palette[i % len(palette)]
        draw.polygon(pts_px, fill=fill, outline=(160, 160, 160, 200))
        # Label at centroid
        cx, cy = polygon_centroid(poly)
        cx_px, cy_px = to_px(cx, cy)
        label = room.get("label_qwen") or room.get("room_id", "")
        if label:
            draw.text((cx_px - 22, cy_px - 6), label, fill=(60, 60, 60, 220))

    # --- Draw walls on top
    for w in walls:
        sx, sy = to_px(w["start"][0], w["start"][1])
        ex, ey = to_px(w["end"][0], w["end"][1])
        draw.line([(sx, sy), (ex, ey)], fill=(40, 40, 40, 230), width=3)

    # --- Draw furniture icons
    icon_radius = max(int(8 * px_per_pt / 3.5), 8)
    drawn = 0
    for f in furniture:
        c = f.get("center_pdf_pt")
        if not c:
            continue
        px, py = to_px(c[0], c[1])
        ftype = (f.get("type") or "").lower()
        shape, fill, outline, label = ICON_STYLE.get(ftype, DEFAULT_STYLE)
        if shape == "rect":
            r = icon_radius + 4
            draw.rectangle([(px - r, py - r), (px + r, py + r)],
                           fill=fill, outline=outline, width=2)
        else:
            r = icon_radius
            draw.ellipse([(px - r, py - r), (px + r, py + r)],
                         fill=fill, outline=outline, width=2)
        # Tag with short label
        draw.text((px - r + 1, py - 6), label, fill=(0, 0, 0, 255))
        drawn += 1

    # --- Header strip
    header_text = (f"furniture_overlay  n={drawn}  "
                   f"svg_pdf_pt bbox=[{minx:.1f},{miny:.1f}]→[{maxx:.1f},{maxy:.1f}]")
    draw.rectangle([(0, 0), (W, 26)], fill=(255, 255, 255, 200))
    draw.text((10, 6), header_text, fill=(20, 20, 20, 255))

    img.save(out_path, "PNG", optimize=True)
    return {
        "overlay_path": str(out_path),
        "size_bytes": out_path.stat().st_size,
        "image_size": [W, H],
        "drawn_furniture": drawn,
    }


# ----- Entry point ---------------------------------------------------------

def main() -> None:
    consensus = json.loads(CONSENSUS_PATH.read_text(encoding="utf-8"))
    cubicasa = json.loads(CUBICASA_PATH.read_text(encoding="utf-8"))

    before = {
        "n_furniture": len(consensus.get("furniture", [])),
        "with_pdf_pt_before": sum(1 for f in consensus.get("furniture", [])
                                  if f.get("center_pdf_pt")),
    }

    new_fur, diag = project_furniture(consensus, cubicasa)
    consensus["furniture"] = new_fur

    after = {
        "n_furniture": len(new_fur),
        "with_pdf_pt_after": sum(1 for f in new_fur if f.get("center_pdf_pt")),
    }

    CONSENSUS_PATH.write_text(json.dumps(consensus, indent=2, ensure_ascii=False),
                              encoding="utf-8")

    overlay_info = render_overlay(consensus, RAW_PAGE_PATH, OVERLAY_PATH)

    print(json.dumps({
        "before": before,
        "after": after,
        "diag": diag,
        "overlay": overlay_info,
        "first_3_with_pdf_pt": [
            {"type": f["type"], "sources": f.get("sources"),
             "center_pdf_pt": f.get("center_pdf_pt"),
             "room_label": f.get("room_label"),
             "coord_method": f.get("coord_method")}
            for f in new_fur if f.get("center_pdf_pt")
        ][:3],
    }, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
