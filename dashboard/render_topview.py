"""
render_topview.py
=================

Renders a top-down (orthographic) view of the consensus geometry next to the
original PDF page, so the dashboard can show a direct PDF-vs-SKP comparison
without booting SketchUp.

Pipeline
--------
1. Try to render the GLB (`<run_dir>/consensus_3d.glb`) via trimesh's offscreen
   renderer (Scene.save_image, which uses pyglet/pyrender if available).
2. If trimesh offscreen fails (no OpenGL on this Windows box), fall back to a
   matplotlib top-down 2D plot drawn directly from `walls_consolidated`,
   which gives an equivalent CAD-style top view for the dashboard.
3. Render the PDF page 0 with PyMuPDF at 150 dpi.
4. Composite [PDF | top view] side-by-side and write
   <run_dir>/pdf_vs_skp_topview.png.

Usage:
    E:/Python312/python.exe render_topview.py [run_dir] [pdf_path]
"""
from __future__ import annotations

import io
import json
import math
import sys
import traceback
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUN = REPO_ROOT / "runs" / "final_planta_74"
DEFAULT_PDF = REPO_ROOT / "planta_74.pdf"

TARGET_HEIGHT = 1100         # px, height the panels are normalized to
GAP = 30
HEADER_H = 56
BG = (245, 245, 245)


# --------------------------------------------------------------------------
# Trimesh offscreen attempt
# --------------------------------------------------------------------------


def _render_glb_offscreen(glb_path: Path, height_px: int) -> Image.Image | None:
    """Try to render the GLB top view via trimesh.Scene.save_image. Returns
    PIL.Image on success, or None on any failure (so we can fall back)."""
    try:
        import numpy as np
        import trimesh
    except Exception:
        return None
    try:
        scene = trimesh.load(str(glb_path), force="scene")
        if isinstance(scene, trimesh.Trimesh):
            s = trimesh.Scene()
            s.add_geometry(scene)
            scene = s
        # Top-down camera: look straight down -Z
        bounds = scene.bounds  # (2, 3)
        cx, cy, _ = (bounds[0] + bounds[1]) / 2.0
        size_xy = max(
            float(bounds[1][0] - bounds[0][0]),
            float(bounds[1][1] - bounds[0][1]),
            1.0,
        )
        # camera height well above the scene
        cz = float(bounds[1][2]) + size_xy * 1.5
        # build a camera transform (look down)
        cam_tf = np.eye(4)
        cam_tf[:3, 3] = [cx, cy, cz]
        scene.camera_transform = cam_tf
        # Wide enough FOV to cover the floor plan
        scene.camera.fov = (50.0, 50.0)
        png_bytes = scene.save_image(resolution=(height_px, height_px), visible=False)
        if not png_bytes:
            return None
        return Image.open(io.BytesIO(png_bytes)).convert("RGB")
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return None


# --------------------------------------------------------------------------
# Matplotlib fallback (CAD-style top down from walls_consolidated)
# --------------------------------------------------------------------------


def _render_topview_matplotlib(consensus: dict, height_px: int) -> Image.Image:
    """Top-down CAD-style render of walls_consolidated with thickness."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPolygon
    from matplotlib.collections import PatchCollection

    cwalls = consensus.get("walls_consolidated") or []
    rooms = consensus.get("rooms") or []
    openings = consensus.get("openings") or []

    # Derive bounds from actual wall geometry (page_bounds in this run is in
    # a different coord space and would frame the plan badly).
    xs: list[float] = []
    ys: list[float] = []
    for w in cwalls:
        xs.extend([w["centerline_start"][0], w["centerline_end"][0]])
        ys.extend([w["centerline_start"][1], w["centerline_end"][1]])
    if not xs:
        page = consensus["metadata"]["page_bounds"]
        minx, miny = page["min_x"], page["min_y"]
        maxx, maxy = page["max_x"], page["max_y"]
    else:
        minx, miny = min(xs), min(ys)
        maxx, maxy = max(xs), max(ys)
    w_pt = maxx - minx
    h_pt = maxy - miny
    aspect = w_pt / h_pt if h_pt > 0 else 1.0

    dpi = 110
    fig_h_in = height_px / dpi
    fig_w_in = fig_h_in * aspect
    fig = plt.figure(figsize=(fig_w_in, fig_h_in), dpi=dpi)
    ax = fig.add_subplot(1, 1, 1)
    ax.set_facecolor("#fafaf7")

    # ---- room slabs (light pastel, behind walls) ----
    palette = [
        "#ffe0b2", "#dcedc8", "#bbdefb", "#f8bbd0",
        "#fff59d", "#c5cae9", "#ffccbc", "#c8e6c9",
    ]
    for i, r in enumerate(rooms):
        poly = r.get("polygon") or []
        if len(poly) < 3:
            continue
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        ax.fill(xs, ys, color=palette[i % len(palette)], alpha=0.55,
                edgecolor="#caa050", linewidth=0.6, zorder=1)

    # ---- walls (oriented rectangles using thickness) ----
    agreed_patches: list[MplPolygon] = []
    svg_patches: list[MplPolygon] = []
    for w in cwalls:
        sx, sy = w["centerline_start"]
        ex, ey = w["centerline_end"]
        dx, dy = ex - sx, ey - sy
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L
        thk = float(w.get("thickness_pt") or 4.0)
        thk = max(thk, 2.5)
        half = thk / 2.0
        corners = [
            (sx + nx * half, sy + ny * half),
            (ex + nx * half, ey + ny * half),
            (ex - nx * half, ey - ny * half),
            (sx - nx * half, sy - ny * half),
        ]
        patch = MplPolygon(corners, closed=True)
        if "pipeline_v13" in (w.get("sources_pooled") or []):
            agreed_patches.append(patch)
        else:
            svg_patches.append(patch)

    if svg_patches:
        ax.add_collection(PatchCollection(
            svg_patches, facecolor="#dc6464", edgecolor="#3c3c3c",
            linewidths=0.5, zorder=2,
        ))
    if agreed_patches:
        ax.add_collection(PatchCollection(
            agreed_patches, facecolor="#b41e1e", edgecolor="#1c1c1c",
            linewidths=0.5, zorder=3,
        ))

    # ---- openings (markers) ----
    for op in openings:
        cx, cy = op["center"]
        if op.get("geometry_origin") == "svg_arc":
            color = "#ff8c00"
        else:
            color = "#ffc864"
        ax.plot([cx], [cy], marker="D", markersize=6,
                markerfacecolor=color, markeredgecolor="#3c2300",
                linewidth=0, zorder=4)

    # frame the view to page bounds, equal aspect, flip Y so the plan
    # reads the same way as the PDF (PDF Y grows down)
    ax.set_xlim(minx - 10, maxx + 10)
    ax.set_ylim(maxy + 10, miny - 10)
    ax.set_aspect("equal", adjustable="box")
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    for spine in ax.spines.values():
        spine.set_edgecolor("#bdbdbd")
    ax.set_title(
        f"SKP top view (matplotlib fallback)  -  "
        f"{len(cwalls)} logical walls, "
        f"{len(rooms)} rooms, {len(openings)} openings",
        fontsize=10, color="#404040", pad=8,
    )

    fig.tight_layout(pad=0.6)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor="#fafaf7")
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


# --------------------------------------------------------------------------
# PDF render
# --------------------------------------------------------------------------


def _render_pdf_page0(pdf_path: Path, dpi: int = 150) -> Image.Image:
    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(0)
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()


# --------------------------------------------------------------------------
# Composite
# --------------------------------------------------------------------------


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _normalize_height(img: Image.Image, target_h: int) -> Image.Image:
    if img.height == target_h:
        return img
    new_w = max(int(img.width * target_h / img.height), 1)
    return img.resize((new_w, target_h), Image.LANCZOS)


def composite(pdf_img: Image.Image, top_img: Image.Image,
              top_label: str, out_path: Path) -> Path:
    pdf_img = _normalize_height(pdf_img, TARGET_HEIGHT)
    top_img = _normalize_height(top_img, TARGET_HEIGHT)

    canvas_w = pdf_img.width + GAP + top_img.width
    canvas_h = TARGET_HEIGHT + HEADER_H
    canvas = Image.new("RGB", (canvas_w, canvas_h), BG)
    canvas.paste(pdf_img, (0, HEADER_H))
    canvas.paste(top_img, (pdf_img.width + GAP, HEADER_H))

    draw = ImageDraw.Draw(canvas)
    font = _font(22)
    draw.text((20, 14), "PDF original (planta_74.pdf)", fill=(40, 40, 40), font=font)
    draw.text((pdf_img.width + GAP + 20, 14), top_label, fill=(40, 40, 40), font=font)

    canvas.save(out_path, "PNG", optimize=True)
    return out_path


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    run_dir = Path(argv[1]) if len(argv) > 1 else DEFAULT_RUN
    pdf_path = Path(argv[2]) if len(argv) > 2 else DEFAULT_PDF
    if not run_dir.exists():
        print(f"[render_topview] run_dir not found: {run_dir}", file=sys.stderr)
        return 2
    if not pdf_path.exists():
        print(f"[render_topview] PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    consensus = json.loads((run_dir / "consensus_model.json").read_text(encoding="utf-8"))
    glb_path = run_dir / "consensus_3d.glb"

    top_img: Image.Image | None = None
    top_label = ""

    if glb_path.exists():
        print(f"[render_topview] trying trimesh offscreen render of {glb_path.name}")
        top_img = _render_glb_offscreen(glb_path, TARGET_HEIGHT)
        if top_img is not None:
            top_label = "SKP top view (trimesh offscreen render of consensus_3d.glb)"
            print("[render_topview] trimesh offscreen render OK")

    if top_img is None:
        print("[render_topview] falling back to matplotlib CAD top view")
        top_img = _render_topview_matplotlib(consensus, TARGET_HEIGHT)
        top_label = (
            "SKP top view (matplotlib CAD fallback - "
            "walls_consolidated + rooms + openings)"
        )

    print(f"[render_topview] rendering PDF page 0 from {pdf_path.name}")
    pdf_img = _render_pdf_page0(pdf_path, dpi=150)

    out = run_dir / "pdf_vs_skp_topview.png"
    composite(pdf_img, top_img, top_label, out)
    size = out.stat().st_size
    print(f"[render_topview] wrote {out}  ({size/1024:.1f} KB)")
    if size < 50_000:
        print(f"[render_topview] WARNING: file is {size} B (< 50 KB target)",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
