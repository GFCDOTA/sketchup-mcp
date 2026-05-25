"""Render the base annotation image for human-painted soft barriers.

Sister of ``tools/render_human_walls_annotation_base.py``. Generates the
PNG the reviewer paints on to mark MISSING peitoris / guarda-corpos /
esquadrias / parapetos between cells that the leak_map classified as
``candidate_type = human_soft_barrier``.

What the base image shows:

- PDF page rendering as semi-transparent background
- Consensus walls (gray boxes; not the painting target)
- Human walls already painted (dark blue boxes; also not painting target —
  visible for context so the operator sees the wall protocol has run)
- Existing soft_barriers in the consensus (light orange polylines)
- Cells that NEED a soft_barrier highlighted in cyan-hatched yellow
  (per ``candidate_type = human_soft_barrier`` in
  ``loop_closure_candidates_after_walls.json``)
- For each missing-soft-barrier pair: a dashed cyan line between the
  two room seeds with the suggested barrier_type
- Cells that are honest semantic_room_split (open plan) in soft gray
  hatching with "OPEN PLAN" label — operator must NOT paint here
- Cells with already_explained pairs in pale blue (also DO NOT paint)

Painting protocol (printed on the base):
  CYAN #00ffff = soft barrier (peitoril / guarda-corpo / esquadria / parapet)
  Each blob = one barrier. Same axis-aligned brushwork as walls
  (extractor reuses extract_human_walls calibration + L/T-shape
  decomposition).

Companion: ``tools/extract_human_soft_barriers.py``,
``tools/apply_human_soft_barriers.py``,
``docs/protocols/human_soft_barriers_protocol.md``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pypdfium2 as pdfium
from matplotlib.patches import Patch, Rectangle
from matplotlib.patches import Polygon as MplPolygon


CELL_COLOR = {
    # cell needs human_soft_barrier (paint here)
    "needs_sbarrier":   {"fc": "#fff59d", "ec": "#f57f17",
                          "hatch": "++", "label": "PAINT CYAN HERE"},
    # cell is honest open plan (do NOT paint)
    "semantic_only":    {"fc": "#e0e0e0", "ec": "#9e9e9e",
                          "hatch": "..", "label": "OPEN PLAN — DO NOT PAINT"},
    # cell merge already explained by an existing wall (no action)
    "already_explained":{"fc": "#bbdefb", "ec": "#0288d1",
                          "hatch": "xx", "label": "ALREADY EXPLAINED"},
    # mixed / undocumented
    "mixed":            {"fc": "#ffe0b2", "ec": "#fb8c00",
                          "hatch": "//", "label": "MIXED — REVIEW"},
}


def _classify_cell(cell_name: str, candidates: list[dict]) -> str:
    """Classify a merged cell by the union of its pair types."""
    names = {n.strip() for n in cell_name.split("|")}
    pairs = [c for c in candidates
              if c.get("from_room") in names
              and c.get("to_room") in names]
    types = {c.get("candidate_type") for c in pairs}
    if not types:
        return "mixed"
    if types == {"human_soft_barrier"}:
        return "needs_sbarrier"
    if types == {"semantic_room_split"}:
        return "semantic_only"
    if types == {"already_explained"}:
        return "already_explained"
    if "human_soft_barrier" in types:
        # any soft_barrier pair makes the whole cell paintable for
        # the soft_barrier pass (other pairs are explained / semantic)
        return "needs_sbarrier"
    return "mixed"


def render(pdf_path: Path,
           consensus_path: Path,
           candidates_path: Path,
           out_path: Path,
           dpi: int = 200) -> None:
    consensus = json.loads(consensus_path.read_text())
    candidates_report = json.loads(candidates_path.read_text())
    candidates = candidates_report.get("candidates", [])

    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    page_w, page_h = page.get_size()
    bitmap = page.render(scale=2.5).to_pil()
    pdf.close()

    walls = consensus.get("walls", [])
    thickness = float(consensus.get("wall_thickness_pts", 5.4))
    rooms = consensus.get("rooms", [])
    soft_barriers = consensus.get("soft_barriers", [])

    fig, ax = plt.subplots(figsize=(14, 18), dpi=dpi, facecolor="white")
    ax.imshow(bitmap, extent=(0, page_w, 0, page_h),
              aspect="equal", alpha=0.55)

    # Classify + draw merged cells
    n_needs_sb = 0
    n_semantic = 0
    n_already = 0
    for r in rooms:
        name = r.get("name", "")
        if "|" not in name:
            continue
        pts = r.get("polygon_pts", [])
        if len(pts) < 3:
            continue
        kind = _classify_cell(name, candidates)
        if kind == "needs_sbarrier":
            n_needs_sb += 1
        elif kind == "semantic_only":
            n_semantic += 1
        elif kind == "already_explained":
            n_already += 1
        style = CELL_COLOR[kind]
        ax.add_patch(MplPolygon(pts, closed=True,
                                 facecolor=style["fc"],
                                 edgecolor=style["ec"],
                                 linewidth=1.5, alpha=0.35, zorder=2,
                                 hatch=style["hatch"]))
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        ax.text(cx, cy, f'{style["label"]}\n{name}',
                fontsize=7, ha="center", va="center", color="#3e2723",
                zorder=10,
                bbox=dict(boxstyle="round,pad=0.4", fc="#fff9c4",
                           ec=style["ec"], lw=0.8, alpha=0.92))

    # Consensus walls: gray boxes (not paint target)
    for w in walls:
        s, e = w["start"], w["end"]
        is_human = w.get("geometry_origin") == "human_annotation"
        fc = "#1a237e" if is_human else "#9e9e9e"
        ec = "#000" if is_human else "#212121"
        if w["orientation"] == "h":
            x0, x1 = sorted([s[0], e[0]])
            cy = s[1]
            ax.add_patch(Rectangle((x0, cy - thickness/2),
                                    x1 - x0, thickness,
                                    facecolor=fc, edgecolor=ec,
                                    linewidth=0.5, alpha=0.80, zorder=4))
        else:
            cx = s[0]
            y0, y1 = sorted([s[1], e[1]])
            ax.add_patch(Rectangle((cx - thickness/2, y0),
                                    thickness, y1 - y0,
                                    facecolor=fc, edgecolor=ec,
                                    linewidth=0.5, alpha=0.80, zorder=4))

    # Existing soft_barriers — orange polylines
    for b in soft_barriers:
        pts = b.get("polyline_pts", [])
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, color="#ff6f00", linewidth=1.5,
                alpha=0.75, zorder=5)

    # Pair connectors: dashed cyan/gray lines per candidate (informational)
    for c in candidates:
        if c["candidate_type"] != "human_soft_barrier":
            continue
        sx, sy = c["seed_from"]
        ex, ey = c["seed_to"]
        ax.plot([sx, ex], [sy, ey], "--", color="#00838f",
                linewidth=1.1, alpha=0.75, zorder=8)
        mx, my = c["midpoint_pdf"]
        ax.text(mx, my,
                f"paint peitoril\nor parapet here",
                fontsize=6, ha="center", va="center", color="#00838f",
                zorder=12,
                bbox=dict(boxstyle="round,pad=0.25", fc="#e0f7fa",
                           ec="#00838f", lw=0.6, alpha=0.95))

    # Top instructions
    instructions = (
        "PAINT MISSING SOFT BARRIERS HERE — color contract:\n"
        "  CYAN #00ffff = peitoril / guarda-corpo / esquadria / parapet\n"
        "  • aspect ratio long/short → orientation (long axis = barrier centerline)\n"
        "  • each blob = one barrier; cover the missing peitoril span\n"
        "  • DO NOT paint where label says 'OPEN PLAN' (semantic_room_split)\n"
        "  • DO NOT paint where a BLUE human wall already covers the boundary\n"
        "  • the dashed teal lines connect the seed pair that NEEDS the barrier\n"
        "  • default barrier_type = peitoril; height_m defaults to 1.10\n"
        "  • use --barrier-type at extract time to override per-pass"
    )
    ax.text(page_w / 2, page_h - 5, instructions,
            fontsize=8, ha="center", va="top", color="#006064",
            zorder=20,
            bbox=dict(boxstyle="round,pad=0.4", fc="#e0f7fa",
                       ec="#006064", lw=1.0, alpha=0.95))

    legend = [
        Patch(facecolor=CELL_COLOR["needs_sbarrier"]["fc"],
              edgecolor=CELL_COLOR["needs_sbarrier"]["ec"],
              hatch=CELL_COLOR["needs_sbarrier"]["hatch"],
              label=f"needs soft_barrier (paint CYAN): {n_needs_sb} cells"),
        Patch(facecolor=CELL_COLOR["semantic_only"]["fc"],
              edgecolor=CELL_COLOR["semantic_only"]["ec"],
              hatch=CELL_COLOR["semantic_only"]["hatch"],
              label=f"open plan — do NOT paint: {n_semantic} cells"),
        Patch(facecolor=CELL_COLOR["already_explained"]["fc"],
              edgecolor=CELL_COLOR["already_explained"]["ec"],
              hatch=CELL_COLOR["already_explained"]["hatch"],
              label=f"already explained — no action: {n_already} cells"),
        Patch(facecolor="#9e9e9e", edgecolor="#212121",
              label="consensus walls (context only)"),
        Patch(facecolor="#1a237e", edgecolor="#000",
              label="human walls already painted (context only)"),
        Patch(facecolor="#ff6f00", edgecolor="#ff6f00",
              label=f"existing soft_barriers: {len(soft_barriers)}"),
        Patch(facecolor="#00ffff", edgecolor="#006064",
              label="paint MISSING SOFT BARRIERS in this CYAN"),
    ]
    ax.legend(handles=legend, loc="lower left", fontsize=9, framealpha=0.95)

    ax.set_xlim(0, page_w)
    ax.set_ylim(0, page_h)
    ax.set_aspect("equal")
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[ok] soft_barriers annotation base -> {out_path}")
    print(f"  cells that need painting (CYAN):   {n_needs_sb}")
    print(f"  cells open plan (do NOT paint):    {n_semantic}")
    print(f"  cells already explained:           {n_already}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--consensus", type=Path, required=True,
                    help="Post-walls consensus (consensus_with_human_walls.json).")
    ap.add_argument("--candidates", type=Path, required=True,
                    help="loop_closure_candidates_after_walls.json — the "
                         "leak map for the post-walls state.")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    render(args.pdf, args.consensus, args.candidates, args.out, args.dpi)


if __name__ == "__main__":
    main()
