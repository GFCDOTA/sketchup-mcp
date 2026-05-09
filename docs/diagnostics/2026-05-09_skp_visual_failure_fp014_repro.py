#!/usr/bin/env python3
"""FP-014 — reproduzir imagens e métricas do diagnóstico.

Gera todas as imagens citadas em
``docs/diagnostics/2026-05-09_skp_visual_failure_fp014.md`` + as
métricas quantitativas (vértices por room, walls fragmentos curtos,
colinear gaps sem opening, etc).

Uso:
    cd <repo>
    .venv/Scripts/python.exe docs/diagnostics/2026-05-09_skp_visual_failure_fp014_repro.py [comando]

Comandos:
    pdf-clean              gera _pdf_planta_clean.png (PDF crop, sem overlay)
    my-interpretation      gera _pdf_my_opening_interpretation.png (Claude visual interpretation)
    detected-overlay       gera _pdf_planta_with_openings.png (extractor output)
    zooms                  gera _pdf_zoom_top.png + _pdf_zoom_bot.png (PDF halves)
    sidebyside             gera _sidebyside_pdf_skp.png (PDF | SKP top | SKP axon)
    metrics                imprime análise quantitativa (vts, free_vts, gaps, fragments)
    all                    roda tudo

Dependências (pip install -e .[cockpit] já cobre):
    pypdfium2  Pillow  shapely

Inputs canônicos (assume arquivos no repo):
    planta_74.pdf
    runs/_milestone_skp_planta74_2026_05_09/consensus.json

Outputs (em runs/_milestone_skp_planta74_2026_05_09/):
    _pdf_planta_clean.png
    _pdf_my_opening_interpretation.png
    _pdf_planta_with_openings.png
    _pdf_zoom_top.png
    _pdf_zoom_bot.png
    _sidebyside_pdf_skp.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import LineString, Point, Polygon

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
PDF_PATH = REPO_ROOT / "planta_74.pdf"
RUN_DIR = REPO_ROOT / "runs" / "_milestone_skp_planta74_2026_05_09"
CONSENSUS_PATH = RUN_DIR / "consensus.json"

# PDF wall-thickness anchor: 0.19 m wall = wall_thickness_pts in consensus
PT_TO_M = 0.19 / 5.4  # ~0.0352 m/pt — anchored to consensus.wall_thickness_pts


def _load_consensus() -> dict:
    return json.loads(CONSENSUS_PATH.read_text())


def _open_pdf():
    pdf = pdfium.PdfDocument(str(PDF_PATH))
    page = pdf[0]
    return pdf, page, page.get_size()


def _font(size: int = 22, bold: bool = True) -> ImageFont.FreeTypeFont:
    name = "arialbd.ttf" if bold else "arial.ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Image generators
# ---------------------------------------------------------------------------

def render_pdf_clean(out: Path | None = None) -> Path:
    """Render PDF cropped to the planta_region only — no overlay."""
    out = out or RUN_DIR / "_pdf_planta_clean.png"
    pdf, page, (W_pt, H_pt) = _open_pdf()
    SCALE = 3.5
    img = page.render(scale=SCALE).to_pil()
    c = _load_consensus()
    planta = c["planta_region"]
    pad = 30
    x0 = (planta[0] - pad) * SCALE
    y0 = (H_pt - planta[3] - pad) * SCALE
    x1 = (planta[2] + pad) * SCALE
    y1 = (H_pt - planta[1] + pad) * SCALE
    crop = img.crop((max(0, x0), max(0, y0), x1, y1))
    out.parent.mkdir(parents=True, exist_ok=True)
    crop.save(out, optimize=True)
    print(f"wrote {out} ({crop.size})")
    return out


# Claude visual interpretation of openings — coords approximated by visual
# inspection of the PDF. Format: (kind, label, cx_pt, cy_pt, width_m, orient)
MY_OPENINGS: list[tuple[str, str, float, float, float, str]] = [
    # ---- TOP REGION (y > 540) ----
    ("door",     "P-COZ-SALA",    155, 685, 0.85, "h"),
    ("door",     "P-LAVABO",      260, 660, 0.85, "v"),
    ("door",     "P-SUITE01",     335, 627, 0.90, "v"),
    ("door",     "P-BAN02-SU01",  413, 587, 1.20, "v"),
    ("door",     "P-SU01-BAN01",  525, 525, 0.85, "v"),
    ("window",   "J-LAVABO",      290, 706, 0.60, "h"),
    ("window",   "J-SU01-TOP",    400, 706, 1.40, "h"),
    ("window",   "J-BAN01",       560, 530, 0.40, "v"),
    # ---- BOT REGION (y < 540) ----
    ("door",     "P-AS",          110, 535, 0.85, "v"),
    ("door",     "P-SUITE02",     370, 484, 1.20, "h"),
    ("door",     "P-BAN02-SU02",  430, 520, 0.85, "h"),
    ("balcony",  "PV-SALA-TERR",  175, 511, 4.20, "h"),
    ("balcony",  "PV-SU02-TERR",  295, 457, 3.20, "h"),
    ("peitoril", "PEIT-TERRSOC",  140, 396, 3.82, "h"),
    ("peitoril", "PEIT-TERRTEC",  273, 405, 1.20, "h"),
    ("window",   "J-AS-EXT",       51, 480, 1.77, "v"),
    ("window",   "J-COZ-EXT",      51, 660, 1.20, "v"),
    ("window",   "J-SALA-EXT",     51, 565, 1.20, "v"),
]


COLORS = {
    "door":     (40, 200, 40, 230),
    "window":   (40, 100, 230, 230),
    "balcony":  (0, 200, 200, 230),
    "peitoril": (200, 0, 200, 230),
}
FILL = {
    "door":     (40, 200, 40, 70),
    "window":   (40, 100, 230, 70),
    "balcony":  (0, 200, 200, 70),
    "peitoril": (200, 0, 200, 70),
}


def render_my_interpretation(out: Path | None = None) -> Path:
    """Render PDF crop + 18 manually-interpreted openings as colored boxes."""
    out = out or RUN_DIR / "_pdf_my_opening_interpretation.png"
    pdf, page, (W_pt, H_pt) = _open_pdf()
    SCALE = 4.5
    img = page.render(scale=SCALE).to_pil().convert("RGBA")
    c = _load_consensus()
    walls = c["walls"]
    planta = c["planta_region"]
    pad = 30
    x0 = (planta[0] - pad) * SCALE
    y0 = (H_pt - planta[3] - pad) * SCALE
    x1 = (planta[2] + pad) * SCALE
    y1 = (H_pt - planta[1] + pad) * SCALE
    crop = img.crop((max(0, x0), max(0, y0), x1, y1))
    draw = ImageDraw.Draw(crop, "RGBA")

    def to_px(x: float, y: float) -> tuple[float, float]:
        return (x * SCALE - x0, (H_pt - y) * SCALE - y0)

    # Walls as light-grey context lines
    for w in walls:
        draw.line([to_px(*w["start"]), to_px(*w["end"])],
                  fill=(60, 60, 60, 80), width=2)

    M_TO_PT = 1.0 / PT_TO_M
    font = _font(22)
    fontL = _font(28)

    for kind, label, cx, cy, w_m, orient in MY_OPENINGS:
        half = (w_m * M_TO_PT) / 2
        thick = 7
        if orient == "h":
            x_a, y_a = cx - half, cy - thick
            x_b, y_b = cx + half, cy + thick
        else:
            x_a, y_a = cx - thick, cy - half
            x_b, y_b = cx + thick, cy + half
        p1 = to_px(x_a, y_b)
        p2 = to_px(x_b, y_a)
        color = COLORS[kind]
        fill = FILL[kind]
        draw.rectangle([p1, p2], outline=color, width=4, fill=fill)
        px, py = to_px(cx, cy)
        draw.text((px + 10, py + 8), f"{label}\n{w_m:.2f}m",
                  fill=color[:3], font=font)

    # Legend
    lx, ly = 20, 20
    for kind in ("door", "window", "balcony", "peitoril"):
        draw.rectangle([lx, ly, lx + 30, ly + 25],
                       outline=COLORS[kind], width=3, fill=FILL[kind])
        draw.text((lx + 40, ly), kind, fill=COLORS[kind][:3], font=fontL)
        ly += 35
    draw.text((lx, ly + 10), "CLAUDE VISUAL INTERPRETATION",
              fill=(0, 0, 0), font=fontL)

    out.parent.mkdir(parents=True, exist_ok=True)
    crop.save(out, optimize=True)
    print(f"wrote {out} ({crop.size}); {len(MY_OPENINGS)} openings")
    return out


def render_detected_overlay(out: Path | None = None) -> Path:
    """Render PDF crop + the 11 openings extracted by the detector."""
    out = out or RUN_DIR / "_pdf_planta_with_openings.png"
    pdf, page, (W_pt, H_pt) = _open_pdf()
    SCALE = 4.5
    img = page.render(scale=SCALE).to_pil().convert("RGBA")
    c = _load_consensus()
    walls = c["walls"]
    openings = c["openings"]
    planta = c["planta_region"]
    pad = 30
    x0 = (planta[0] - pad) * SCALE
    y0 = (H_pt - planta[3] - pad) * SCALE
    x1 = (planta[2] + pad) * SCALE
    y1 = (H_pt - planta[1] + pad) * SCALE
    crop = img.crop((max(0, x0), max(0, y0), x1, y1))
    draw = ImageDraw.Draw(crop, "RGBA")

    def to_px(x, y):
        return (x * SCALE - x0, (H_pt - y) * SCALE - y0)

    for w in walls:
        draw.line([to_px(*w["start"]), to_px(*w["end"])],
                  fill=(80, 80, 80, 90), width=2)

    DETECT_COLORS = {
        "interior_door": (220, 30, 30, 220),
        "interior_passage": (255, 140, 0, 220),
        "window": (30, 90, 220, 220),
        "glazed_balcony": (0, 180, 180, 220),
    }
    font = _font(26)
    for o in openings:
        cx, cy = o["center"]
        px, py = to_px(cx, cy)
        kind = o.get("kind_v5", "unknown")
        color = DETECT_COLORS.get(kind, (160, 160, 160, 220))
        width_m = o.get("opening_width_pts", 0) * PT_TO_M
        R = 22
        draw.ellipse([px - R, py - R, px + R, py + R],
                     outline=color, width=5, fill=(255, 255, 255, 180))
        draw.text((px - R - 5, py + R + 4),
                  f"{o['id']}", fill=color[:3], font=font)
        draw.text((px - 25, py + R + 30),
                  f"{width_m:.2f}m", fill=color[:3], font=font)
        draw.text((px - 20, py - R - 28),
                  f"→{o.get('wall_id', '?')}",
                  fill=color[:3], font=font)

    out.parent.mkdir(parents=True, exist_ok=True)
    crop.save(out, optimize=True)
    print(f"wrote {out} ({crop.size}); {len(openings)} detected openings")
    return out


def render_zooms() -> tuple[Path, Path]:
    """Render the PDF top and bottom halves at high resolution."""
    pdf, page, (W_pt, H_pt) = _open_pdf()
    SCALE = 6.0
    img = page.render(scale=SCALE).to_pil()

    def crop_pt(left, bottom, right, top):
        return img.crop((left * SCALE,
                         (H_pt - top) * SCALE,
                         right * SCALE,
                         (H_pt - bottom) * SCALE))

    top_path = RUN_DIR / "_pdf_zoom_top.png"
    bot_path = RUN_DIR / "_pdf_zoom_bot.png"
    crop_pt(40, 540, 565, 708).save(top_path, optimize=True)
    crop_pt(40, 394, 565, 550).save(bot_path, optimize=True)
    print(f"wrote {top_path}, {bot_path}")
    return top_path, bot_path


def render_sidebyside(out: Path | None = None) -> Path:
    """Compose PDF original | SKP top render | SKP axon render side by side."""
    out = out or RUN_DIR / "_sidebyside_pdf_skp.png"
    pdf_img = Image.open(RUN_DIR / "_pdf_page1.png")
    top_img = Image.open(RUN_DIR / "_smoke_out" / "preview_top.png")
    axon_img = Image.open(RUN_DIR / "_smoke_out" / "preview_axon.png")

    H = 800

    def fit(img, h):
        w = int(img.width * h / img.height)
        return img.resize((w, h), Image.LANCZOS)

    pdf_r, top_r, axon_r = fit(pdf_img, H), fit(top_img, H), fit(axon_img, H)
    margin = 30
    caption_h = 60
    W = pdf_r.width + top_r.width + axon_r.width + 4 * margin
    canvas = Image.new("RGB", (W, H + caption_h + 2 * margin), (245, 245, 245))
    x = margin
    canvas.paste(pdf_r, (x, margin + caption_h))
    x_pdf = x
    x += pdf_r.width + margin
    canvas.paste(top_r, (x, margin + caption_h))
    x_top = x
    x += top_r.width + margin
    canvas.paste(axon_r, (x, margin + caption_h))
    x_axon = x

    draw = ImageDraw.Draw(canvas)
    font = _font(32)
    draw.text((x_pdf + pdf_r.width // 2 - 100, margin + 10),
              "PDF original", fill=(20, 20, 20), font=font)
    draw.text((x_top + top_r.width // 2 - 200, margin + 10),
              "SKP top (consensus render)", fill=(20, 20, 20), font=font)
    draw.text((x_axon + axon_r.width // 2 - 90, margin + 10),
              "SKP axon 3D", fill=(20, 20, 20), font=font)

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, optimize=True)
    print(f"wrote {out} ({canvas.size})")
    return out


# ---------------------------------------------------------------------------
# Quantitative metrics — Sintomas A / B / C
# ---------------------------------------------------------------------------

def metrics() -> None:
    """Print the quantitative metrics that ground FP-014's classification."""
    c = _load_consensus()
    walls = c["walls"]
    rooms = c["rooms"]
    openings = c["openings"]
    THICK = c["wall_thickness_pts"]
    TOL = THICK * 1.5
    print(f"# walls={len(walls)}  rooms={len(rooms)}  openings={len(openings)}")
    print(f"# wall_thickness_pts={THICK:.2f}  TOL={TOL:.2f}")
    print()

    # ---- Sintoma A: room polygon vertex / free-vertex / long-diag stats ----
    wall_endpoints = set()
    for w in walls:
        wall_endpoints.add(tuple(round(x, 1) for x in w["start"]))
        wall_endpoints.add(tuple(round(x, 1) for x in w["end"]))
    wall_lines = [LineString([w["start"], w["end"]]) for w in walls]

    print(f"## Sintoma A — room polygon shape (raster trace produces N>>20 vts)")
    print(f"{'room':24} {'vts':>4} {'free_vts':>9} {'long_diags':>11} {'area_m2':>9}")
    print("-" * 72)
    for r in rooms:
        pts = r["polygon_pts"]
        free = 0
        for p in pts:
            rp = tuple(round(x, 1) for x in p)
            if rp in wall_endpoints:
                continue
            pt_geom = Point(p)
            if any(wl.distance(pt_geom) < TOL for wl in wall_lines):
                continue
            free += 1
        poly = Polygon(pts)
        long_diags = 0
        coords = list(poly.exterior.coords)
        for i in range(len(coords) - 1):
            seg = LineString([coords[i], coords[i + 1]])
            if seg.length < 50:
                continue
            if any(seg.hausdorff_distance(wl) < TOL for wl in wall_lines):
                continue
            long_diags += 1
        print(f"{r['name']:24} {len(pts):>4} {free:>9} {long_diags:>11} "
              f"{poly.area * PT_TO_M ** 2:>9.2f}")

    # ---- Sintoma B: short wall fragments + colinear pairs ----
    print()
    print(f"## Sintoma B — wall fragmentation (carved openings produce short stubs)")
    short_walls = [w for w in walls
                   if LineString([w["start"], w["end"]]).length < 30]
    print(f"walls with length < 1m (=30pt): {len(short_walls)} of {len(walls)}")
    for w in short_walls[:15]:
        L = LineString([w["start"], w["end"]]).length
        print(f"  {w['id']}: {L*PT_TO_M:.2f}m  orient={w['orientation']}")

    # ---- Sintoma C: colinear gaps without an opening ----
    print()
    print(f"## Sintoma C — colinear gaps in walls without an opening")
    pairs = []
    for i, w1 in enumerate(walls):
        for w2 in walls[i + 1:]:
            if w1["orientation"] != w2["orientation"]:
                continue
            s1, e1 = w1["start"], w1["end"]
            s2, e2 = w2["start"], w2["end"]
            if w1["orientation"] == "h":
                if abs(s1[1] - s2[1]) > 1.0:
                    continue
                x1a, x1b = sorted([s1[0], e1[0]])
                x2a, x2b = sorted([s2[0], e2[0]])
                if x1b < x2a:
                    gap = x2a - x1b
                    gc = ((x1b + x2a) / 2, s1[1])
                elif x2b < x1a:
                    gap = x1a - x2b
                    gc = ((x2b + x1a) / 2, s1[1])
                else:
                    continue
            else:
                if abs(s1[0] - s2[0]) > 1.0:
                    continue
                y1a, y1b = sorted([s1[1], e1[1]])
                y2a, y2b = sorted([s2[1], e2[1]])
                if y1b < y2a:
                    gap = y2a - y1b
                    gc = (s1[0], (y1b + y2a) / 2)
                elif y2b < y1a:
                    gap = y1a - y2b
                    gc = (s1[0], (y2b + y1a) / 2)
                else:
                    continue
            if gap < 200:
                pairs.append((w1["id"], w2["id"], gap, gc, w1["orientation"]))

    OPENING_TOL = 30
    print(f"{'w1':>5} {'w2':>5} {'gap_m':>6} {'orient':>6} "
          f"{'opening_id':>10} {'distance':>8}")
    matched = 0
    for w1, w2, gap, gc, ori in pairs:
        gp = Point(gc)
        best = None
        md = 1e9
        for o in openings:
            d = gp.distance(Point(o["center"]))
            if d < md:
                md = d
                if d < OPENING_TOL:
                    best = o["id"]
        if best:
            matched += 1
        print(f"{w1:>5} {w2:>5} {gap*PT_TO_M:>6.2f} {ori:>6} "
              f"{(best or 'NONE'):>10} {md:>8.1f}")
    print(f"\nUNMAPPED COLINEAR GAPS: {len(pairs) - matched} of {len(pairs)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command",
                   choices=("pdf-clean", "my-interpretation",
                            "detected-overlay", "zooms", "sidebyside",
                            "metrics", "all"))
    args = p.parse_args(argv)

    cmd = args.command
    if cmd in ("pdf-clean", "all"):
        render_pdf_clean()
    if cmd in ("my-interpretation", "all"):
        render_my_interpretation()
    if cmd in ("detected-overlay", "all"):
        render_detected_overlay()
    if cmd in ("zooms", "all"):
        render_zooms()
    if cmd in ("sidebyside", "all"):
        try:
            render_sidebyside()
        except FileNotFoundError as e:
            print(f"sidebyside skipped: {e}", file=sys.stderr)
    if cmd in ("metrics", "all"):
        metrics()
    return 0


if __name__ == "__main__":
    sys.exit(main())
