"""Render the base annotation image for human-painted walls.

Generates `fixtures/planta_74/human_walls_annotation_base.png` — the
PNG the reviewer paints on to mark missing structural divisors. The
base image shows:

- PDF page rendering as background (semi-transparent)
- All consensus walls drawn as filled gray rectangles with red ID labels
  (so the reviewer can reference which walls already exist)
- The merged cells highlighted with a semi-transparent yellow overlay
  (so the reviewer knows where the missing dividers belong)
- Each unhosted opening (from consensus.metadata.human_openings_truth)
  marked with a red X (so the reviewer knows where a wall is needed
  specifically to host that opening)
- A legend strip at the top with the BLUE color contract and brush rules

Painting protocol (printed on the base image):
  Use BLUE #0000ff for missing structural walls.
  Each blob = one wall. Use solid filled rectangles, aligned with the
  PDF grid. Aspect ratio determines orientation (long axis = wall
  centerline). Wall thickness in pixels can be anything ≥ 6 px; the
  extractor uses consensus wall_thickness_pts when emitting the wall.

Companion: ``tools/extract_human_walls.py``,
``tools/apply_human_walls.py``,
``fixtures/planta_74/human_walls_truth.schema.json``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pypdfium2 as pdfium
from matplotlib.patches import Patch, Rectangle


def render(pdf_path: Path,
           consensus_path: Path,
           out_path: Path,
           dpi: int = 200) -> None:
    consensus = json.loads(consensus_path.read_text())
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    page_w, page_h = page.get_size()
    bitmap = page.render(scale=2.5).to_pil()
    pdf.close()

    walls = consensus.get("walls", [])
    thickness = float(consensus.get("wall_thickness_pts", 5.4))
    rooms = consensus.get("rooms", [])
    openings = consensus.get("openings", [])
    host_log = (consensus.get("metadata", {})
                .get("human_openings_truth", {})
                .get("host_log", []))
    unhosted = [h for h in host_log if h.get("mode") == "unhosted"]

    fig, ax = plt.subplots(figsize=(14, 18), dpi=dpi, facecolor="white")
    ax.imshow(bitmap, extent=(0, page_w, 0, page_h),
              aspect="equal", alpha=0.65)

    # Highlight merged cells (rooms with "|" in their name)
    for r in rooms:
        name = r.get("name", "")
        if "|" not in name:
            continue
        pts = r.get("polygon_pts", [])
        if len(pts) < 3:
            continue
        from matplotlib.patches import Polygon as MplPolygon
        ax.add_patch(MplPolygon(pts, closed=True,
                                 facecolor="#fff59d",  # light yellow
                                 edgecolor="#f57f17",  # amber border
                                 linewidth=1.5, alpha=0.30, zorder=2,
                                 hatch="//"))
        # Label centroid
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        ax.text(cx, cy, f"MERGED\n{name}",
                fontsize=7, ha="center", va="center", color="#5d4037",
                zorder=10,
                bbox=dict(boxstyle="round,pad=0.4", fc="#fff9c4",
                           ec="#f57f17", lw=0.8, alpha=0.9))

    # Walls: gray boxes with red ID labels
    for w in walls:
        s, e = w["start"], w["end"]
        if w["orientation"] == "h":
            x0, x1 = sorted([s[0], e[0]])
            cy = s[1]
            ax.add_patch(Rectangle((x0, cy - thickness/2),
                                    x1 - x0, thickness,
                                    facecolor="#9e9e9e", edgecolor="#212121",
                                    linewidth=0.5, alpha=0.80, zorder=4))
            lx, ly = x1 + 2, cy
        else:
            cx = s[0]
            y0, y1 = sorted([s[1], e[1]])
            ax.add_patch(Rectangle((cx - thickness/2, y0),
                                    thickness, y1 - y0,
                                    facecolor="#9e9e9e", edgecolor="#212121",
                                    linewidth=0.5, alpha=0.80, zorder=4))
            lx, ly = cx, y1 + 2
        ax.text(lx, ly, w["id"], fontsize=4, color="#d32f2f",
                zorder=11,
                bbox=dict(boxstyle="square,pad=0.05", fc="white",
                           ec="#d32f2f", lw=0.3, alpha=0.85))

    # Unhosted openings — red X marker + label
    for u in unhosted:
        cx, cy = u["original_center_pdf"]
        ax.plot(cx, cy, "X", color="#d32f2f", markersize=18,
                markeredgewidth=3, zorder=15)
        ax.text(cx + 6, cy + 6,
                f'UNHOSTED {u["opening_id"]} ({u["kind"]})\nneeds a wall here',
                fontsize=7, color="#d32f2f", zorder=16,
                bbox=dict(boxstyle="round,pad=0.3", fc="white",
                           ec="#d32f2f", lw=1.0, alpha=0.95))

    # Also draw hosted openings as small light dots for context
    for op in openings:
        if op.get("geometry_origin") != "human_annotation":
            continue
        c = op.get("center")
        if not c:
            continue
        if op.get("host_mode") == "unhosted":
            continue
        ax.plot(c[0], c[1], "o", color="#666",
                markersize=5, alpha=0.45, zorder=9,
                markerfacecolor="#fff", markeredgewidth=1.0)

    # Top instruction strip
    instructions = (
        "PAINT MISSING WALLS HERE — color contract:\n"
        "  BLUE #0000ff = structural wall (any orientation, solid filled rectangle)\n"
        "  • aspect ratio long/short → orientation (long axis = wall centerline)\n"
        "  • each blob = one wall; cover the missing divisor with a contiguous rectangle\n"
        "  • do NOT use red / green / magenta / orange — those are reserved\n"
        "  • the yellow hatched regions are MERGED cells in the current consensus —\n"
        "    paint walls inside them to split into their real architectural rooms\n"
        "  • the red X marker is an UNHOSTED opening — the wall you paint must cover\n"
        "    its position so it can host"
    )
    ax.text(page_w / 2, page_h - 5, instructions,
            fontsize=8, ha="center", va="top", color="#0d47a1",
            zorder=20,
            bbox=dict(boxstyle="round,pad=0.4", fc="#e3f2fd",
                       ec="#0d47a1", lw=1.0, alpha=0.95))

    # Legend
    legend = [
        Patch(facecolor="#9e9e9e", edgecolor="#212121",
              label=f"consensus walls ({len(walls)}; w000..w{len(walls)-1:03d})"),
        Patch(facecolor="#fff59d", edgecolor="#f57f17", hatch="//",
              label=f"merged cells (paint walls here to split: "
                    f"{sum(1 for r in rooms if '|' in r.get('name', ''))})"),
        Patch(facecolor="#d32f2f", edgecolor="#d32f2f",
              label=f"unhosted openings (paint wall to host: {len(unhosted)})"),
        Patch(facecolor="#0000ff", edgecolor="#000",
              label="paint MISSING WALLS in this BLUE"),
    ]
    ax.legend(handles=legend, loc="lower left", fontsize=9, framealpha=0.95)

    ax.set_xlim(0, page_w)
    ax.set_ylim(0, page_h)
    ax.set_aspect("equal")
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[ok] human walls annotation base -> {out_path}")
    print(f"  walls drawn:     {len(walls)}")
    print(f"  merged cells:    {sum(1 for r in rooms if '|' in r.get('name', ''))}")
    print(f"  unhosted markers: {len(unhosted)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--consensus", type=Path, required=True,
                    help="consensus_human.json (with human openings + host_log).")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    render(args.pdf, args.consensus, args.out, args.dpi)


if __name__ == "__main__":
    main()
