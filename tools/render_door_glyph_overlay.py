"""Render door-glyph diagnostic overlay.

Visual companion to ``tools/detect_door_glyphs.py``. Plots the PDF
page with:
- consensus walls (light gray)
- human openings (color-coded by kind: green/magenta/orange)
- detected door glyphs (colored by cross_ref):
    blue   = matched_human (glyph + human opening + host wall)
    purple = glyph_without_host_wall (the headline diagnostic — visible
             evidence that the user-painted door is correct architecture
             and the missing piece is the host wall)
    gray   = unmatched_glyph (glyph detected but no human paint near;
             may be a real door the reviewer didn't mark, or a
             decorative arc)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pypdfium2 as pdfium
from matplotlib.patches import Patch, Rectangle

KIND_COLOR = {
    "interior_door":   "#00cc00",
    "window":          "#cc00cc",
    "glazed_balcony":  "#ff8800",
}
CROSS_REF_COLOR = {
    "matched_human":             "#1565c0",
    "glyph_without_host_wall":   "#8e24aa",
    "unmatched_glyph":           "#757575",
}


def render(pdf_path: Path,
           consensus_path: Path,
           glyphs_path: Path,
           out_path: Path,
           dpi: int = 180) -> None:
    consensus = json.loads(consensus_path.read_text())
    glyphs_report = json.loads(glyphs_path.read_text())
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    page_w, page_h = page.get_size()
    bitmap = page.render(scale=2.0).to_pil()
    pdf.close()

    walls = consensus.get("walls", [])
    thickness = float(consensus.get("wall_thickness_pts", 5.4))
    human_openings = [op for op in consensus.get("openings", [])
                      if op.get("geometry_origin") == "human_annotation"]

    fig, ax = plt.subplots(figsize=(14, 18), dpi=dpi, facecolor="white")
    ax.imshow(bitmap, extent=(0, page_w, 0, page_h),
              aspect="equal", alpha=0.45)

    # Walls in light gray
    for w in walls:
        s, e = w["start"], w["end"]
        if w["orientation"] == "h":
            x0, x1 = sorted([s[0], e[0]])
            cy = s[1]
            ax.add_patch(Rectangle((x0, cy - thickness/2),
                                    x1 - x0, thickness,
                                    facecolor="#bbb", edgecolor="#666",
                                    linewidth=0.4, alpha=0.7, zorder=3))
        else:
            cx = s[0]
            y0, y1 = sorted([s[1], e[1]])
            ax.add_patch(Rectangle((cx - thickness/2, y0),
                                    thickness, y1 - y0,
                                    facecolor="#bbb", edgecolor="#666",
                                    linewidth=0.4, alpha=0.7, zorder=3))

    # Human openings dots
    for op in human_openings:
        c = op.get("center")
        if not c:
            continue
        kind = op.get("kind_v5") or op.get("kind", "?")
        color = KIND_COLOR.get(kind, "#999")
        ax.plot(c[0], c[1], "o", color=color, markersize=8,
                markeredgewidth=1.5, markeredgecolor="#000",
                zorder=8, alpha=0.85)
        ax.text(c[0] + 2, c[1] + 2, op["id"],
                fontsize=5, color="#000", zorder=9,
                bbox=dict(boxstyle="round,pad=0.15", fc="white",
                           ec=color, lw=0.4, alpha=0.85))

    # Glyphs
    for g in glyphs_report["glyphs"]:
        b = g["bbox_pts"]
        color = CROSS_REF_COLOR.get(g["cross_ref"], "#999")
        # Bbox rectangle
        ax.add_patch(Rectangle((b[0], b[1]),
                                max(b[2] - b[0], 1),
                                max(b[3] - b[1], 1),
                                facecolor="none", edgecolor=color,
                                linewidth=1.4, alpha=0.85, zorder=6))
        # Hinge corner marker
        hp = g["hinge_corner_pt"]
        ax.plot(hp[0], hp[1], "s", color=color, markersize=6,
                markeredgewidth=1.5, markeredgecolor="#000",
                zorder=7)
        # Chord line from hinge to chord corner
        cp = g["chord_corner_pt"]
        ax.plot([hp[0], cp[0]], [hp[1], cp[1]],
                "-", color=color, linewidth=1.0, alpha=0.7, zorder=6)
        ax.text(hp[0] - 2, hp[1] - 2, g["id"],
                fontsize=4, color=color, zorder=10,
                bbox=dict(boxstyle="round,pad=0.1", fc="white",
                           ec=color, lw=0.3, alpha=0.85))

    s = glyphs_report["summary"]
    legend = [
        Patch(facecolor="#bbb", label=f"consensus walls ({len(walls)})"),
        Patch(facecolor=KIND_COLOR["interior_door"],
              label=f"human interior_door ({sum(1 for o in human_openings if (o.get('kind_v5') or o.get('kind')) == 'interior_door')})"),
        Patch(facecolor=KIND_COLOR["window"],
              label=f"human window ({sum(1 for o in human_openings if (o.get('kind_v5') or o.get('kind')) == 'window')})"),
        Patch(facecolor=KIND_COLOR["glazed_balcony"],
              label=f"human glazed_balcony ({sum(1 for o in human_openings if (o.get('kind_v5') or o.get('kind')) == 'glazed_balcony')})"),
        Patch(facecolor="none", edgecolor=CROSS_REF_COLOR["matched_human"], linewidth=1.4,
              label=f"glyph matched_human ({s['by_cross_ref']['matched_human']})"),
        Patch(facecolor="none", edgecolor=CROSS_REF_COLOR["glyph_without_host_wall"], linewidth=1.4,
              label=f"glyph_without_host_wall ({s['by_cross_ref']['glyph_without_host_wall']})"),
        Patch(facecolor="none", edgecolor=CROSS_REF_COLOR["unmatched_glyph"], linewidth=1.4,
              label=f"unmatched_glyph ({s['by_cross_ref']['unmatched_glyph']})"),
    ]
    ax.legend(handles=legend, loc="upper left", fontsize=8, framealpha=0.9)
    ax.set_title(
        f"Door glyph overlay — {pdf_path.name}\n"
        f"{s['n_glyphs']} glyphs vs {s['n_human_openings']} human openings",
        fontsize=11, pad=8,
    )
    ax.set_xlim(0, page_w)
    ax.set_ylim(0, page_h)
    ax.set_aspect("equal")
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[ok] glyph overlay -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--glyphs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    render(args.pdf, args.consensus, args.glyphs, args.out)


if __name__ == "__main__":
    main()
