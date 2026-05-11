"""Render a 12-panel zoom mosaic showing each human opening in context.

For each of the 12 human-annotated openings, crops the PDF render to
a small window centered on the opening's original_center_pdf and
overlays: the painted bbox, the adjusted center (post-classifier),
the host wall (or bracketing colinear pair for existing_gap), and a
mode/shift label.

Lets the reviewer visually verify per-opening that:
- the user-paint position matches the wall geometry
- the mode (cut_into_wall / existing_gap / unhosted) is correct
- the shift is small (< 8 pt PASS, 8-15 WARN, > 15 FAIL)
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import pypdfium2 as pdfium
from matplotlib.patches import Patch, Rectangle

KIND_COLOR = {
    "interior_door":   "#00cc00",
    "window":          "#cc00cc",
    "glazed_balcony":  "#ff8800",
}
MODE_COLOR = {
    "cut_into_wall":   "#1565c0",
    "existing_gap":    "#2e7d32",
    "unhosted":        "#d32f2f",
}


def render(pdf_path: Path,
           truth_path: Path,
           consensus_path: Path,
           out_path: Path,
           zoom_radius_pts: float = 75.0,
           dpi: int = 150) -> None:
    truth = json.loads(truth_path.read_text())
    consensus = json.loads(consensus_path.read_text())
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    page_w, page_h = page.get_size()
    bitmap = page.render(scale=2.0).to_pil()
    pdf.close()
    # bitmap pixel coords map: pixel_x = pt_x * 2, pixel_y = (page_h - pt_y) * 2

    walls = consensus.get("walls", [])
    thickness = float(consensus.get("wall_thickness_pts", 5.4))
    host_log = (consensus.get("metadata", {})
                .get("human_openings_truth", {})
                .get("host_log", []))
    host_by_id = {h["opening_id"]: h for h in host_log}

    n = len(truth.get("openings", []))
    cols = 4
    rows = math.ceil(n / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 4.5, rows * 4.5),
                              dpi=dpi, facecolor="white")
    if rows == 1:
        axes = [axes] if cols == 1 else list(axes)
    else:
        axes = [a for row in axes for a in row]

    for idx, op in enumerate(truth["openings"]):
        ax = axes[idx]
        oid = op["id"]
        host = host_by_id.get(oid, {})
        mode = host.get("mode", "?")
        shift = float(host.get("shift_pt", 0))
        host_wall = host.get("host_wall_id")
        gap_id = host.get("gap_id")
        orig = host.get("original_center_pdf") or op.get("center_pts", [0, 0])
        adj = host.get("adjusted_center_pdf") or orig

        cx_pt, cy_pt = orig
        x0 = max(0, cx_pt - zoom_radius_pts)
        x1 = min(page_w, cx_pt + zoom_radius_pts)
        y0 = max(0, cy_pt - zoom_radius_pts)
        y1 = min(page_h, cy_pt + zoom_radius_pts)

        ax.imshow(bitmap, extent=(0, page_w, 0, page_h),
                  aspect="equal", alpha=0.7)
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)

        # Walls in this region
        for w in walls:
            wb = (
                min(w["start"][0], w["end"][0]) - thickness / 2,
                min(w["start"][1], w["end"][1]) - thickness / 2,
                max(w["start"][0], w["end"][0]) + thickness / 2,
                max(w["start"][1], w["end"][1]) + thickness / 2,
            )
            # bbox intersect zoom?
            if wb[2] < x0 or wb[0] > x1 or wb[3] < y0 or wb[1] > y1:
                continue
            color = "#444" if w["id"] == host_wall else "#aaa"
            lw = 1.5 if w["id"] == host_wall else 0.6
            if w["orientation"] == "h":
                xx0, xx1 = sorted([w["start"][0], w["end"][0]])
                cy = w["start"][1]
                ax.add_patch(Rectangle((xx0, cy - thickness/2),
                                       xx1 - xx0, thickness,
                                       facecolor=color, edgecolor="#000",
                                       linewidth=lw, alpha=0.7, zorder=3))
            else:
                cxw = w["start"][0]
                yy0, yy1 = sorted([w["start"][1], w["end"][1]])
                ax.add_patch(Rectangle((cxw - thickness/2, yy0),
                                       thickness, yy1 - yy0,
                                       facecolor=color, edgecolor="#000",
                                       linewidth=lw, alpha=0.7, zorder=3))
            if w["id"] == host_wall:
                # Label the host wall
                ax.text(wb[0], wb[3] + 2, w["id"], fontsize=7,
                         color="#000", zorder=10,
                         bbox=dict(boxstyle="round,pad=0.2", fc="yellow",
                                    ec="#000", lw=0.5, alpha=0.95))

        # Painted bbox (in pt, from extract step)
        bp = op.get("bbox_pts")
        if bp and len(bp) == 4:
            bp_x0, bp_y0, bp_x1, bp_y1 = bp
            ax.add_patch(Rectangle((bp_x0, bp_y0),
                                   max(bp_x1 - bp_x0, 1),
                                   max(bp_y1 - bp_y0, 1),
                                   facecolor=KIND_COLOR.get(op["kind"], "#999"),
                                   edgecolor="#000", linewidth=1.0,
                                   alpha=0.65, zorder=5))
        # Original center
        ax.plot(orig[0], orig[1], "o", color="#000",
                markersize=6, zorder=8,
                markerfacecolor="white", markeredgewidth=1.5)
        # Adjusted center (if different)
        if abs(adj[0] - orig[0]) > 0.5 or abs(adj[1] - orig[1]) > 0.5:
            ax.plot(adj[0], adj[1], "x", color="#000", markersize=8,
                    markeredgewidth=2, zorder=9)
            ax.plot([orig[0], adj[0]], [orig[1], adj[1]],
                    "-", color="#000", linewidth=0.8, alpha=0.5, zorder=7)

        mode_color = MODE_COLOR.get(mode, "#999")
        title = (f"{oid} {op['kind']}\n"
                 f"mode={mode} shift={shift:.2f}pt\n"
                 f"host={host_wall or gap_id or '—'}")
        ax.set_title(title, fontsize=8, color=mode_color, pad=4)
        ax.tick_params(labelsize=6)
        ax.set_aspect("equal")

    # Unused axes
    for j in range(n, len(axes)):
        axes[j].set_visible(False)

    # Legend
    legend = [
        Patch(facecolor=KIND_COLOR["interior_door"], label="interior_door (painted)"),
        Patch(facecolor=KIND_COLOR["window"], label="window (painted)"),
        Patch(facecolor=KIND_COLOR["glazed_balcony"], label="glazed_balcony (painted)"),
        Patch(facecolor=MODE_COLOR["cut_into_wall"], label="mode: cut_into_wall (title color)"),
        Patch(facecolor=MODE_COLOR["existing_gap"], label="mode: existing_gap (title color)"),
        Patch(facecolor=MODE_COLOR["unhosted"], label="mode: unhosted FAIL (title color)"),
    ]
    fig.legend(handles=legend, loc="lower center", ncol=3, fontsize=8,
                bbox_to_anchor=(0.5, -0.02))
    fig.suptitle(f"Human openings zooms — {pdf_path.name}", fontsize=12, y=0.99)
    plt.tight_layout()
    plt.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[ok] zooms -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--zoom-radius-pts", type=float, default=75.0)
    ap.add_argument("--dpi", type=int, default=150)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    render(args.pdf, args.truth, args.consensus, args.out,
            args.zoom_radius_pts, args.dpi)


if __name__ == "__main__":
    main()
