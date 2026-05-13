"""Render leak-map debug for merged polygonize cells.

Reads ``loop_closure_candidates.json`` and overlays the per-pair
classification on the PDF. Lets the reviewer answer 3 questions at a
glance:

  1. Onde a cell ainda está vazando? (merged cells colored by id)
  2. Pra cada room-pair dentro de uma merged cell, é wall, soft_barrier
     ou semantic_split?
  3. O que devo pintar (BLUE) vs o que NÃO devo pintar?

Color contract for the closure lines:
  RED    = candidate_type=human_wall, should_user_paint=YES
  ORANGE = candidate_type=human_soft_barrier (do NOT paint as wall;
           should land in soft_barriers via separate protocol)
  GRAY   = candidate_type=semantic_room_split (open-plan, NO PHYSICAL
           SEPARATOR — DO NOT paint)
  CYAN   = candidate_type=already_explained (existing opening covers
           the boundary; cell-merge resolves once the host wall loops)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pypdfium2 as pdfium
from matplotlib.patches import Patch, Rectangle
from matplotlib.patches import Polygon as MplPolygon

CANDIDATE_COLOR = {
    "human_wall":          "#d32f2f",   # red — paint this
    "human_soft_barrier":  "#ff8f00",   # orange — soft_barrier, not wall
    "semantic_room_split": "#9e9e9e",   # gray — open plan, no separator
    "already_explained":   "#0288d1",   # cyan — opening covers it
}
CELL_PALETTE = [
    "#fff59d",  # yellow
    "#ce93d8",  # purple
    "#a5d6a7",  # green
    "#ffab91",  # peach
]


def render(pdf_path: Path,
           consensus_path: Path,
           candidates_path: Path,
           labels_path: Path,
           out_path: Path,
           dpi: int = 180) -> None:
    consensus = json.loads(consensus_path.read_text())
    candidates_report = json.loads(candidates_path.read_text())
    labels = json.loads(labels_path.read_text())

    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    page_w, page_h = page.get_size()
    bitmap = page.render(scale=2.0).to_pil()
    pdf.close()

    walls = consensus.get("walls", [])
    thickness = float(consensus.get("wall_thickness_pts", 5.4))
    rooms = consensus.get("rooms", [])
    soft_barriers = consensus.get("soft_barriers", [])
    human_openings = [op for op in consensus.get("openings", [])
                      if op.get("geometry_origin") == "human_annotation"]

    fig, ax = plt.subplots(figsize=(14, 18), dpi=dpi, facecolor="white")
    ax.imshow(bitmap, extent=(0, page_w, 0, page_h),
              aspect="equal", alpha=0.40)

    # Highlight merged cells in pastel
    merged_cells = [r for r in rooms if "|" in r.get("name", "")]
    for ci, cell in enumerate(merged_cells):
        pts = cell.get("polygon_pts", [])
        if len(pts) < 3:
            continue
        color = CELL_PALETTE[ci % len(CELL_PALETTE)]
        ax.add_patch(MplPolygon(pts, closed=True, facecolor=color,
                                 edgecolor="#666", linewidth=0.5,
                                 alpha=0.30, zorder=1,
                                 hatch=".."))

    # Consensus walls in gray; human walls highlighted in dark blue
    for w in walls:
        s, e = w["start"], w["end"]
        is_human = w.get("geometry_origin") == "human_annotation"
        fc = "#1a237e" if is_human else "#9e9e9e"
        ec = "#000" if is_human else "#616161"
        lw = 1.2 if is_human else 0.4
        z = 6 if is_human else 3
        if w["orientation"] == "h":
            x0, x1 = sorted([s[0], e[0]])
            cy = s[1]
            ax.add_patch(Rectangle((x0, cy - thickness/2),
                                    x1 - x0, thickness,
                                    facecolor=fc, edgecolor=ec,
                                    linewidth=lw, alpha=0.85, zorder=z))
        else:
            cx = s[0]
            y0, y1 = sorted([s[1], e[1]])
            ax.add_patch(Rectangle((cx - thickness/2, y0),
                                    thickness, y1 - y0,
                                    facecolor=fc, edgecolor=ec,
                                    linewidth=lw, alpha=0.85, zorder=z))
        if is_human:
            ax.text(s[0] + 2, s[1] + 2, w["id"], fontsize=5,
                    color="#1a237e", zorder=10,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white",
                               ec="#1a237e", lw=0.5, alpha=0.95))

    # Soft barriers as orange polylines
    for b in soft_barriers:
        pts = b.get("polyline_pts", [])
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, color="#ff6f00", linewidth=1.2,
                alpha=0.75, zorder=4)

    # Human openings — small dots
    for op in human_openings:
        c = op.get("center")
        if not c:
            continue
        kind = op.get("kind_v5") or op.get("kind", "?")
        kind_color = {"interior_door": "#00cc00", "window": "#cc00cc",
                      "glazed_balcony": "#ff8800"}.get(kind, "#999")
        ax.plot(c[0], c[1], "o", color=kind_color, markersize=6,
                markeredgewidth=1.0, markeredgecolor="#000",
                zorder=8, alpha=0.85)
        ax.text(c[0] + 2, c[1] + 2, op["id"],
                fontsize=4, color="#000", zorder=9,
                bbox=dict(boxstyle="round,pad=0.1", fc="white",
                           ec=kind_color, lw=0.3, alpha=0.85))

    # Seeds for ALL labels (so the reviewer sees where each room name lives)
    label_names_in_merged = set()
    for cell in merged_cells:
        for n in cell["name"].split("|"):
            label_names_in_merged.add(n.strip())
    for lb in labels:
        if lb["name"] not in label_names_in_merged:
            continue
        sp = lb.get("seed_pt")
        if not sp:
            continue
        ax.plot(sp[0], sp[1], "*", color="#000", markersize=14,
                markerfacecolor="#ffeb3b", markeredgewidth=1.5,
                zorder=12)
        ax.text(sp[0] + 4, sp[1], lb["name"],
                fontsize=7, color="#000", zorder=13,
                bbox=dict(boxstyle="round,pad=0.25", fc="white",
                           ec="#000", lw=0.6, alpha=0.95))

    # Closure-candidate lines
    for c in candidates_report["candidates"]:
        color = CANDIDATE_COLOR.get(c["candidate_type"], "#999")
        sx, sy = c["seed_from"]
        ex, ey = c["seed_to"]
        # Connector dashed line between seeds
        ax.plot([sx, ex], [sy, ey],
                "--", color=color, linewidth=1.1,
                alpha=0.85, zorder=11)
        mx, my = c["midpoint_pdf"]
        # If wall, draw the SUGGESTED wall segment as a solid bold bar
        if (c["candidate_type"] == "human_wall"
                and c["suggested_segment_pdf"]):
            seg = c["suggested_segment_pdf"]
            ax.plot([seg[0], seg[2]], [seg[1], seg[3]],
                    "-", color=color, linewidth=4.0,
                    alpha=0.55, zorder=10)
        # Label at midpoint
        from_short = c["from_room"][:3]
        to_short = c["to_room"][:3]
        paint_tag = "PAINT" if c["should_user_paint"] else "skip"
        ax.text(mx, my,
                f"{from_short}↔{to_short}\n{c['candidate_type']}\n{paint_tag}",
                fontsize=6, ha="center", va="center",
                color=color, zorder=14,
                bbox=dict(boxstyle="round,pad=0.25", fc="white",
                           ec=color, lw=0.8, alpha=0.95))

    # Legend
    legend = [
        Patch(facecolor=CANDIDATE_COLOR["human_wall"],
              label="human_wall (PAINT in BLUE)"),
        Patch(facecolor=CANDIDATE_COLOR["human_soft_barrier"],
              label="human_soft_barrier (DO NOT paint as wall)"),
        Patch(facecolor=CANDIDATE_COLOR["already_explained"],
              label="already_explained (existing opening covers it)"),
        Patch(facecolor=CANDIDATE_COLOR["semantic_room_split"],
              label="semantic_room_split (open plan, DO NOT paint)"),
        Patch(facecolor="#1a237e",
              label="human walls already painted"),
        Patch(facecolor="#fff59d", edgecolor="#666",
              label="merged cell #1 (4 rooms)"),
        Patch(facecolor="#ce93d8", edgecolor="#666",
              label="merged cell #2 (2 rooms)"),
    ]
    ax.legend(handles=legend, loc="lower left", fontsize=8, framealpha=0.95)
    rc = candidates_report
    ax.set_title(
        f"Cell leak debug — {pdf_path.name}\n"
        f"merged cells: {rc['n_merged_cells']}  pairs: {rc['n_pairs']}  "
        f"should_paint: {rc['n_should_user_paint']}  "
        f"skip: {rc['n_should_not_paint']}",
        fontsize=10, pad=8,
    )
    ax.set_xlim(0, page_w)
    ax.set_ylim(0, page_h)
    ax.set_aspect("equal")
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[ok] leak debug -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--candidates", type=Path, required=True)
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    render(args.pdf, args.consensus, args.candidates, args.labels, args.out)


if __name__ == "__main__":
    main()
