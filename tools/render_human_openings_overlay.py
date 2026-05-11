"""Render an overlay showing the planta + human truth + final openings.

Visual verification for the human-openings pipeline. Produces a PNG
that lets a reviewer confirm at a glance that:

1. Every blob the human painted shows up where they painted it.
2. The final consensus opening list matches the human truth.
3. No spurious openings were introduced.

The render is RAM-only — no SketchUp spawn. Cheap visual gate per
CLAUDE.md §3.

Companion: ``tools/extract_human_openings.py``,
``tools/apply_human_openings.py``, ``tools/structural_checks_human.py``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pypdfium2 as pdfium
from matplotlib.patches import Patch, Rectangle

KIND_COLOR = {
    "interior_door":   "#00cc00",   # green
    "window":          "#cc00cc",   # magenta
    "glazed_balcony":  "#ff8800",   # orange
    "interior_passage":"#888888",   # gray (legacy kind, no human color)
}


def render(pdf_path: Path,
           truth_path: Path,
           consensus_path: Path,
           out_path: Path,
           dpi: int = 200) -> None:
    truth = json.loads(truth_path.read_text())
    consensus = json.loads(consensus_path.read_text())

    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    page_w, page_h = page.get_size()
    bitmap = page.render(scale=2.0).to_pil()
    pdf.close()

    fig, ax = plt.subplots(figsize=(14, 18), dpi=dpi, facecolor="white")
    ax.imshow(bitmap, extent=(0, page_w, 0, page_h),
              aspect="equal", alpha=0.40)

    # 1) Walls (gray)
    t = float(consensus.get("wall_thickness_pts", 5.4))
    for w in consensus.get("walls", []):
        s, e = w["start"], w["end"]
        if w["orientation"] == "h":
            x0, x1 = sorted([s[0], e[0]])
            cy = s[1]
            rect = Rectangle((x0, cy - t/2), x1 - x0, t,
                              facecolor="#666", edgecolor="#222",
                              linewidth=0.4, alpha=0.85, zorder=3)
        else:
            cx = s[0]
            y0, y1 = sorted([s[1], e[1]])
            rect = Rectangle((cx - t/2, y0), t, y1 - y0,
                              facecolor="#666", edgecolor="#222",
                              linewidth=0.4, alpha=0.85, zorder=3)
        ax.add_patch(rect)

    # 2) Human truth bboxes (the painted blobs) at their original
    #    PDF positions. Solid colored rectangles per kind.
    n_truth_by_kind: dict[str, int] = {}
    for op in truth.get("openings", []):
        kind = op["kind"]
        n_truth_by_kind[kind] = n_truth_by_kind.get(kind, 0) + 1
        x0, y0, x1, y1 = op["bbox_pts"]
        color = KIND_COLOR.get(kind, "#999")
        rect = Rectangle((x0, y0), max(x1 - x0, 1), max(y1 - y0, 1),
                          facecolor=color, edgecolor="#000",
                          linewidth=0.7, alpha=0.80, zorder=5)
        ax.add_patch(rect)
        ax.text(op["center_pts"][0], op["center_pts"][1] + 5,
                op["id"], fontsize=5, ha="center", va="bottom",
                color="#000", zorder=8,
                bbox=dict(boxstyle="round,pad=0.1", fc="white",
                           ec=color, lw=0.5, alpha=0.85))

    # 3) Final consensus openings (whatever applied step produced).
    #    Visualize as outlined circles so we can see if any drifted
    #    from the human truth.
    n_final_by_kind: dict[str, int] = {}
    for op in consensus.get("openings", []):
        kind = op.get("kind_v5") or op.get("kind", "?")
        n_final_by_kind[kind] = n_final_by_kind.get(kind, 0) + 1
        c = op.get("center")
        if not c:
            continue
        w_pt = float(op.get("opening_width_pts", 0)) or 15.0
        # Determine orientation from wall if any
        wall_id = op.get("wall_id")
        wall = next((w for w in consensus.get("walls", [])
                     if w.get("id") == wall_id), None)
        if wall and wall.get("orientation") == "v":
            w_render, h_render = 8.0, w_pt
        else:
            w_render, h_render = w_pt, 8.0
        color = KIND_COLOR.get(kind, "#999")
        rect = Rectangle((c[0] - w_render/2, c[1] - h_render/2),
                          w_render, h_render,
                          facecolor="none", edgecolor=color,
                          linewidth=1.4, linestyle="--",
                          alpha=0.95, zorder=6)
        ax.add_patch(rect)

    # 4) Explicit-constraint search regions (informational)
    for c in truth.get("explicit_constraints", []):
        region = c.get("search_region_pts")
        if not region:
            continue
        x0, y0, x1, y1 = region
        kind = c.get("kind", "?")
        policy = c.get("policy", "?")
        edge = "#00cc00" if policy == "require_present" else "#ff0000"
        ls = "-" if policy == "require_present" else ":"
        rect = Rectangle((x0, y0), x1 - x0, y1 - y0,
                          facecolor="none", edgecolor=edge,
                          linewidth=0.6, linestyle=ls,
                          alpha=0.55, zorder=2)
        ax.add_patch(rect)
        ax.text(x0 + 2, y0 + 2, c.get("name", "?"),
                fontsize=4, color=edge, zorder=2,
                bbox=dict(boxstyle="round,pad=0.1", fc="white",
                           ec=edge, lw=0.4, alpha=0.8))

    # Legend
    legend = [
        Patch(facecolor=KIND_COLOR["interior_door"], edgecolor="#000",
              label=f"interior_door (truth={n_truth_by_kind.get('interior_door', 0)} "
                    f"final={n_final_by_kind.get('interior_door', 0)})"),
        Patch(facecolor=KIND_COLOR["window"], edgecolor="#000",
              label=f"window (truth={n_truth_by_kind.get('window', 0)} "
                    f"final={n_final_by_kind.get('window', 0)})"),
        Patch(facecolor=KIND_COLOR["glazed_balcony"], edgecolor="#000",
              label=f"glazed_balcony (truth={n_truth_by_kind.get('glazed_balcony', 0)} "
                    f"final={n_final_by_kind.get('glazed_balcony', 0)})"),
        Patch(facecolor="none", edgecolor="#00cc00",
              label="constraint region (require_present)"),
        Patch(facecolor="none", edgecolor="#ff0000",
              label="constraint region (require_absent)"),
    ]
    ax.legend(handles=legend, loc="upper left", fontsize=8, framealpha=0.9)

    ax.set_title(f"Human openings overlay — {pdf_path.name}\n"
                 f"truth: {len(truth.get('openings', []))} | "
                 f"final: {len(consensus.get('openings', []))}",
                 fontsize=10, pad=8)
    ax.set_xlim(0, page_w)
    ax.set_ylim(0, page_h)
    ax.set_aspect("equal")
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[ok] overlay -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    render(args.pdf, args.truth, args.consensus, args.out, args.dpi)


if __name__ == "__main__":
    main()
