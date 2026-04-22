"""Audited PNG overlay of observed_model.

Renders the post-pipeline model as a single PNG with:
- rooms filled in a rotating pastel palette
- walls in dark ink, thickness scaled from the model
- walls belonging to orphan connected components (<= _ORPHAN_MAX_NODES)
  highlighted in magenta — the GPT-flagged check: if these are legend /
  furniture fragments, they cluster visually at the edges of the drawing;
  if they are missing structural walls, they sit on the perimeter of
  rooms that look "unsealed"
- junction dots color-coded by kind (cross / tee / end / pass_through)
- a header line with counts so anyone reviewing the PNG can see whether
  a single number (rooms, orphans) moved between runs

When a ``raster_image`` is provided (the PDF first page rendered by
ingest), the output is a side-by-side composition: PDF raster on the
left, model overlay on the right, both scaled to the same height. This
follows the project convention of auditing every planta change with
the real PDF alongside the extracted model.

PIL-only (already a transitive dependency through the existing render_*
scripts). Output path is chosen by the caller so the pipeline places it
inside ``runs/<name>/`` alongside the JSON artifacts.
"""
from __future__ import annotations

from pathlib import Path

import networkx as nx
import numpy as np
from PIL import Image, ImageDraw, ImageFont


_ORPHAN_MAX_NODES = 3

_PALETTE = [
    (254, 226, 226), (254, 215, 170), (254, 240, 138), (187, 247, 208),
    (186, 230, 253), (216, 180, 254), (252, 165, 165), (253, 186, 116),
    (250, 204, 21), (134, 239, 172), (125, 211, 252), (196, 181, 253),
    (248, 113, 113), (249, 115, 22),
]
_MAIN_WALL_COLOR = (15, 23, 42)
_ORPHAN_WALL_COLOR = (217, 70, 239)  # magenta


def write_audited_overlay(
    observed_model: dict,
    output_path: Path,
    raster_image: np.ndarray | None = None,
) -> None:
    walls = observed_model.get("walls", [])
    juncs = observed_model.get("junctions", [])
    rooms = observed_model.get("rooms", [])
    scores = observed_model.get("scores", {})
    if not walls:
        return

    orphan_wall_ids = _compute_orphan_wall_ids(walls)

    xs, ys = [], []
    for w in walls:
        xs += [w["start"][0], w["end"][0]]
        ys += [w["start"][1], w["end"][1]]
    for j in juncs:
        xs.append(j["point"][0])
        ys.append(j["point"][1])
    margin = 40
    min_x, min_y = min(xs) - margin, min(ys) - margin
    max_x, max_y = max(xs) + margin, max(ys) + margin
    w_px = max(200, int(max_x - min_x))
    h_px = max(200, int(max_y - min_y))

    img = Image.new("RGB", (w_px, h_px), "white")
    draw = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.truetype("arial.ttf", 18)
        font_small = ImageFont.truetype("arial.ttf", 12)
    except Exception:
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()

    for i, room in enumerate(rooms):
        poly = room.get("polygon") or []
        if not poly or len(poly) < 3:
            continue
        color = _PALETTE[i % len(_PALETTE)] + (140,)
        pts = [(p[0] - min_x, p[1] - min_y) for p in poly]
        draw.polygon(pts, fill=color, outline=(80, 80, 80))
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        draw.text(
            (cx - 10, cy - 8),
            room["room_id"].replace("room-", "R"),
            fill="black",
            font=font_small,
        )

    # walls: orphan branches painted last so they overlay the rest.
    for wall in walls:
        if wall["wall_id"] in orphan_wall_ids:
            continue
        _draw_wall(draw, wall, min_x, min_y, _MAIN_WALL_COLOR)
    for wall in walls:
        if wall["wall_id"] not in orphan_wall_ids:
            continue
        _draw_wall(draw, wall, min_x, min_y, _ORPHAN_WALL_COLOR, width_boost=1)

    for j in juncs:
        cx = j["point"][0] - min_x
        cy = j["point"][1] - min_y
        kind = j.get("kind", "")
        if kind == "cross":
            color = (220, 38, 38)
        elif kind == "tee":
            color = (234, 88, 12)
        elif kind == "end":
            color = (37, 99, 235)
        else:
            color = (100, 116, 139)
        r = 4
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

    draw.rectangle([0, 0, w_px, 30], fill=(255, 255, 255, 235))
    header = (
        f"walls={len(walls)}  orphans={len(orphan_wall_ids)}  "
        f"rooms={len(rooms)}  juncs={len(juncs)}  "
        f"geom={scores.get('geometry', 0)}  topo={scores.get('topology', 0)}"
    )
    draw.text((6, 6), header, fill="black", font=font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if raster_image is not None:
        composed = _compose_side_by_side(raster_image, img)
        composed.save(output_path)
    else:
        img.save(output_path)


def _compose_side_by_side(raster: np.ndarray, model: Image.Image) -> Image.Image:
    """Place PDF raster on the left, model overlay on the right.

    Both panels are scaled to the same height so a reviewer can scan
    horizontally and check room-for-room correspondence. A thin
    separator and small labels make the split obvious at a glance.
    """
    if raster.ndim == 2:
        pdf_img = Image.fromarray(raster).convert("RGB")
    elif raster.shape[2] == 4:
        pdf_img = Image.fromarray(raster[:, :, :3]).convert("RGB")
    else:
        pdf_img = Image.fromarray(raster).convert("RGB")

    target_h = max(pdf_img.height, model.height)
    pdf_scaled = _scale_to_height(pdf_img, target_h)
    model_scaled = _scale_to_height(model, target_h)

    separator_w = 6
    total_w = pdf_scaled.width + separator_w + model_scaled.width
    canvas = Image.new("RGB", (total_w, target_h + 32), "white")
    canvas.paste(pdf_scaled, (0, 32))
    canvas.paste(model_scaled, (pdf_scaled.width + separator_w, 32))

    draw = ImageDraw.Draw(canvas)
    try:
        label_font = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        label_font = ImageFont.load_default()
    draw.rectangle([0, 0, total_w, 32], fill=(240, 240, 240))
    draw.text((6, 6), "PDF (ground truth)", fill="black", font=label_font)
    draw.text(
        (pdf_scaled.width + separator_w + 6, 6),
        "Extracted model",
        fill="black",
        font=label_font,
    )
    # separator column
    draw.rectangle(
        [pdf_scaled.width, 32, pdf_scaled.width + separator_w, 32 + target_h],
        fill=(180, 180, 180),
    )
    return canvas


def _scale_to_height(img: Image.Image, target_h: int) -> Image.Image:
    if img.height == target_h:
        return img
    ratio = target_h / img.height
    new_w = max(1, int(round(img.width * ratio)))
    return img.resize((new_w, target_h), Image.LANCZOS)


def _draw_wall(
    draw: ImageDraw.ImageDraw,
    wall: dict,
    min_x: float,
    min_y: float,
    color: tuple[int, int, int],
    width_boost: int = 0,
) -> None:
    x1 = wall["start"][0] - min_x
    y1 = wall["start"][1] - min_y
    x2 = wall["end"][0] - min_x
    y2 = wall["end"][1] - min_y
    thickness = wall.get("thickness", 4)
    stroke = max(2, int(thickness / 2)) + width_boost
    draw.line([(x1, y1), (x2, y2)], fill=color, width=stroke)


def _compute_orphan_wall_ids(walls: list[dict]) -> set[str]:
    """Return wall_ids that belong to a connected component with
    fewer nodes than ``_ORPHAN_MAX_NODES`` in a per-page graph.

    Mirrors the topology-level orphan definition so the visual
    highlight matches the connectivity_report counts.
    """
    orphan_ids: set[str] = set()
    by_page: dict[int, list[dict]] = {}
    for wall in walls:
        by_page.setdefault(wall.get("page_index", 0), []).append(wall)
    for page_walls in by_page.values():
        g: nx.Graph = nx.Graph()
        for wall in page_walls:
            g.add_edge(
                tuple(wall["start"]),
                tuple(wall["end"]),
                wall_id=wall["wall_id"],
            )
        for component in nx.connected_components(g):
            if len(component) > _ORPHAN_MAX_NODES:
                continue
            subgraph = g.subgraph(component)
            for _u, _v, data in subgraph.edges(data=True):
                orphan_ids.add(data["wall_id"])
    return orphan_ids
