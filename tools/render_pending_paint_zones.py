"""Render an annotated paint guide showing PENDING soft-barrier zones.

Builds on top of ``render_human_soft_barriers_annotation_base.py``:
in addition to highlighting the merged cell that needs painting,
this tool draws explicit RED zones over the spots the reviewer is
expected to paint CYAN, AND a green check + label over already-
painted ``geometry_origin=human_annotation`` soft_barriers.

Output: `<out>` PNG with:
  * PDF underlay (semi-transparent)
  * Trio polygon hatched in yellow ("paint inside")
  * Green ✓ overlays on existing human soft_barriers
  * RED dashed rectangles + labels per pending zone, in
    counter-clockwise order around the L's outer perimeter
  * Top instruction strip + a per-zone legend

PR scope: this is a reviewer-aid render only — it does NOT change
the consensus and does NOT touch the gate. The reviewer is still
the source of truth for the actual paint operation; this guide
just makes the target zones explicit so a fresh paint cycle lands
the right segments.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Patch  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402

THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS))


# Planta_74 pending paint zones. Coordinates derived from inspection
# of the trio polygon bbox + the PDF labels (PEITORIL H=1,10M wraps
# the outer L envelope of A.S. + TERRACO SOCIAL + TERRACO TECNICO;
# MURETA H=0,70M sits between TER.SOC and TER.TECNICO).
#
# Format: (label, bbox_pts (x0,y0,x1,y1), barrier_type, height_m,
#          instruction).
PLANTA_74_PENDING_ZONES: list[tuple[str, tuple[float, float, float, float],
                                       str, float, str]] = [
    (
        "ZONE_1 — east_peitoril_TER_TECNICO",
        (252.0, 400.0, 268.0, 460.0),
        "peitoril", 1.10,
        "Vertical peitoril at the east edge of TER.TECNICO "
        "(outer envelope of the L; H=1,10M).",
    ),
    (
        "ZONE_2 — internal_mureta_TER.SOC↔TER.TEC",
        (210.0, 400.0, 240.0, 470.0),
        "mureta", 0.70,
        "Internal mureta between TER.SOCIAL and TER.TECNICO. PDF "
        "labels 'MURETA H=0,70M' at this interface (height 70cm).",
    ),
    (
        "ZONE_3 — west_peitoril_A.S._exterior",
        (44.0, 400.0, 60.0, 700.0),
        "peitoril", 1.10,
        "Vertical peitoril on the WEST exterior edge of the L "
        "(if the PDF shows a parapet there; otherwise leave blank).",
    ),
]


def _render_pdf_underlay(pdf_path: Path, ax, alpha: float = 0.55) -> tuple:
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page = pdf[0]
        page_w, page_h = page.get_size()
        img = page.render(scale=2).to_pil()
    finally:
        pdf.close()
    ax.imshow(
        img,
        extent=(0, page_w, 0, page_h),
        origin="upper",
        alpha=alpha,
        aspect="equal",
        zorder=0,
    )
    return (page_w, page_h)


def render(pdf_path: Path,
           consensus: dict,
           out_path: Path,
           dpi: int = 220) -> None:
    fig, ax = plt.subplots(figsize=(13, 10))
    page_w, page_h = _render_pdf_underlay(pdf_path, ax)

    # 1. Highlight the trio cell (yellow hatched)
    trio = next(
        (r for r in (consensus.get("rooms") or [])
         if "A.S." in (r.get("name") or "")),
        None,
    )
    if trio:
        pts = trio.get("polygon_pts") or []
        ax.add_patch(MplPolygon(
            pts, closed=True, facecolor="#fff59d",
            edgecolor="#f57f17", hatch="///", linewidth=1.2,
            alpha=0.40, zorder=2,
        ))

    # 2. Existing human soft_barriers — green check + label
    h_count = 0
    for sb in consensus.get("soft_barriers") or []:
        if sb.get("geometry_origin") != "human_annotation":
            continue
        pts = sb.get("polyline_pts") or []
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, color="#1b5e20", linewidth=3.5,
                alpha=0.95, zorder=6)
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        ax.text(cx, cy - 10,
                f"✓ {sb['id']} ({sb.get('barrier_type', 'peitoril')})",
                fontsize=8, ha="center", va="top", color="#1b5e20",
                bbox=dict(boxstyle="round,pad=0.25", fc="#c8e6c9",
                           ec="#1b5e20", lw=0.6, alpha=0.95),
                zorder=12)
        h_count += 1

    # 3. Pending zones — RED dashed rectangles
    for label, bbox, btype, height_m, instr in PLANTA_74_PENDING_ZONES:
        x0, y0, x1, y1 = bbox
        ax.add_patch(FancyBboxPatch(
            (x0, y0), x1 - x0, y1 - y0,
            boxstyle="round,pad=2",
            fc="#ffcdd2", ec="#b71c1c",
            linewidth=2.0, linestyle="--", alpha=0.55,
            zorder=8,
        ))
        ax.text(
            (x0 + x1) / 2, (y0 + y1) / 2,
            f"{label}\n{btype} H={height_m}m",
            fontsize=7, ha="center", va="center", color="#b71c1c",
            bbox=dict(boxstyle="round,pad=0.3", fc="#ffebee",
                       ec="#b71c1c", lw=0.8, alpha=0.95),
            zorder=14,
        )

    # 4. Top instructions
    instructions = (
        "PAINT PENDING SOFT BARRIERS — color contract:\n"
        "  CYAN #00ffff  paint inside each RED zone with a "
        "rectangular brush; cover the suggested span end-to-end\n"
        "  • aspect ratio: long axis = barrier centerline "
        "(extractor reads orientation from bbox aspect)\n"
        "  • after painting all zones, save the PNG and run "
        "`tools.extract_human_soft_barriers`\n"
        "  • each ✓ in green is already in consensus (DO NOT paint over)"
    )
    ax.text(page_w / 2, page_h - 5, instructions,
            fontsize=9, ha="center", va="top", color="#006064",
            zorder=20,
            bbox=dict(boxstyle="round,pad=0.4", fc="#e0f7fa",
                       ec="#006064", lw=1.0, alpha=0.95))

    legend = [
        Patch(facecolor="#fff59d", edgecolor="#f57f17",
              hatch="///", label="trio cell (paint inside)"),
        Patch(facecolor="#c8e6c9", edgecolor="#1b5e20",
              label=f"already painted ({h_count})"),
        Patch(facecolor="#ffcdd2", edgecolor="#b71c1c",
              label=f"PENDING zones (paint CYAN here): "
                    f"{len(PLANTA_74_PENDING_ZONES)}"),
    ]
    ax.legend(handles=legend, loc="lower left", fontsize=10,
              framealpha=0.95)

    ax.set_xlim(0, page_w)
    ax.set_ylim(0, page_h)
    ax.set_aspect("equal")
    ax.set_axis_off()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=dpi, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="render_pending_paint_zones",
        description=(
            "Render an annotated paint guide highlighting the "
            "PENDING soft-barrier zones for planta_74. Reviewer "
            "paints CYAN inside each RED zone."
        ),
    )
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dpi", type=int, default=220)
    args = ap.parse_args(argv)

    consensus = json.loads(args.consensus.read_text(encoding="utf-8"))
    render(args.pdf, consensus, args.out, dpi=args.dpi)
    print(f"[wrote] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
