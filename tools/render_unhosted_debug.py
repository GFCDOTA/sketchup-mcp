"""Render a debug overlay focused on unhosted human openings.

Highlights each unhosted opening (red bbox + red center + connector
lines to the 3 nearest wall candidates and 3 nearest colinear-gap
candidates) so the reviewer can diagnose the cause:

A) wall_missing_in_consensus — no wall in the consensus is near
B) gap_missing_because_wall_fragmentation
C) host_algorithm_bug_center_only
D) calibration_drift
E) human_annotation_off_wall
F) unsupported_border/opening_type

Reads the ``nearest_candidates`` array stamped by
``apply_human_openings`` and overlays them on the PDF render.
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
           truth_path: Path,
           out_path: Path,
           dpi: int = 180) -> None:
    consensus = json.loads(consensus_path.read_text())
    truth = json.loads(truth_path.read_text())
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    page_w, page_h = page.get_size()
    bitmap = page.render(scale=2.0).to_pil()
    pdf.close()

    walls = consensus.get("walls", [])
    walls_by_id = {w["id"]: w for w in walls}
    thickness = float(consensus.get("wall_thickness_pts", 5.4))
    host_log = (consensus.get("metadata", {})
                .get("human_openings_truth", {})
                .get("host_log", []))
    unhosted = [h for h in host_log if h["mode"] == "unhosted"]

    fig, ax = plt.subplots(figsize=(14, 18), dpi=dpi, facecolor="white")
    ax.imshow(bitmap, extent=(0, page_w, 0, page_h),
              aspect="equal", alpha=0.45)

    # Background: all walls in gray
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

    # Background: all human openings as light circles
    for op in truth["openings"]:
        c = op.get("center_pts") or [0, 0]
        ax.plot(c[0], c[1], "o", color="#aaa", markersize=4,
                alpha=0.5, zorder=4)

    # Highlight unhosted
    for u in unhosted:
        cx, cy = u["original_center_pdf"]
        # User-paint position
        ax.plot(cx, cy, "X", color="#d32f2f", markersize=14,
                markeredgewidth=2, zorder=10)
        # Label
        ax.text(cx + 5, cy + 5,
                f'{u["opening_id"]} ({u["kind"]}) UNHOSTED',
                fontsize=8, color="#d32f2f", zorder=11,
                bbox=dict(boxstyle="round,pad=0.3", fc="white",
                           ec="#d32f2f", lw=1.0, alpha=0.95))

        # Connector lines to nearest candidates
        for cand in u.get("nearest_candidates", [])[:6]:
            if cand["kind"] == "wall":
                w = walls_by_id.get(cand["wall_id"])
                if not w:
                    continue
                # Midpoint of wall
                mx = (w["start"][0] + w["end"][0]) / 2
                my = (w["start"][1] + w["end"][1]) / 2
                color = "#ff9800"
                ax.plot([cx, mx], [cy, my], "--",
                        color=color, linewidth=0.8, alpha=0.65, zorder=9)
                ax.text((cx + mx) / 2 + 2, (cy + my) / 2,
                        f'wall {cand["wall_id"]}\nΔcross={cand["cross_diff"]:.1f}',
                        fontsize=5, color=color, zorder=10,
                        bbox=dict(boxstyle="round,pad=0.15", fc="white",
                                   ec=color, lw=0.4, alpha=0.85))
            elif cand["kind"] == "gap":
                ga = cand["gap_axis_range"]
                # Determine orientation from wall pair
                w1 = walls_by_id.get(cand["walls"][0])
                if not w1:
                    continue
                if w1["orientation"] == "h":
                    # Gap is horizontal between x=ga[0] and x=ga[1] at cross y = wall y
                    wy = w1["start"][1]
                    gx = (ga[0] + ga[1]) / 2
                    gy = wy
                else:
                    wx = w1["start"][0]
                    gy = (ga[0] + ga[1]) / 2
                    gx = wx
                color = "#388e3c"
                ax.plot([cx, gx], [cy, gy], "--",
                        color=color, linewidth=0.8, alpha=0.65, zorder=9)
                ax.text((cx + gx) / 2 + 2, (cy + gy) / 2,
                        f'gap w={cand["gap_width_pts"]:.0f}pt\nΔcross={cand["cross_diff"]:.1f}',
                        fontsize=5, color=color, zorder=10,
                        bbox=dict(boxstyle="round,pad=0.15", fc="white",
                                   ec=color, lw=0.4, alpha=0.85))

    # Legend
    legend = [
        Patch(facecolor="#bbb", label="walls (consensus)"),
        Patch(facecolor="#aaa", label="hosted openings (light dot)"),
        Patch(facecolor="#d32f2f", label=f"UNHOSTED openings ({len(unhosted)})"),
        Patch(facecolor="#ff9800", label="nearest WALL candidate (orange dashed)"),
        Patch(facecolor="#388e3c", label="nearest GAP candidate (green dashed)"),
    ]
    ax.legend(handles=legend, loc="upper left", fontsize=9, framealpha=0.9)

    ax.set_title(
        f"Unhosted debug — {pdf_path.name}\n"
        f"{len(unhosted)} unhosted of {len(truth['openings'])} human openings",
        fontsize=11, pad=8,
    )
    ax.set_xlim(0, page_w)
    ax.set_ylim(0, page_h)
    ax.set_aspect("equal")
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[ok] unhosted overlay -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    render(args.pdf, args.consensus, args.truth, args.out)


if __name__ == "__main__":
    main()
