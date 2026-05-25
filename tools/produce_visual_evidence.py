"""Produce the seven visual evidence artifacts required by the
Visual Fidelity Gate Protocol (2026-05-14).

This is PR B1 of the protocol: the **producers**. The artifact set
each producer emits is the minimum the gate needs to clear its
artifact-presence check (PR A). The algorithmic content checks for
the 8 failure conditions land in PR B3
(`tools/visual_fidelity_gate.py`).

The seven artifacts:

| key                  | filename                  | producer                       |
|----------------------|---------------------------|--------------------------------|
| original_floorplan   | original_floorplan.png    | _produce_original_floorplan    |
| skp_render           | skp_render.png            | _produce_skp_render            |
| overlay_pdf_skp      | overlay_pdf_skp.png       | _produce_overlay               |
| diff_walls           | diff_walls.png            | _produce_diff_walls            |
| diff_doors           | diff_doors.png            | _produce_diff_doors            |
| diff_rooms           | diff_rooms.png            | _produce_diff_rooms            |
| mismatches_list      | mismatches_list.md        | _produce_mismatches_list       |

Reuses helpers from `tools/render_preflight.py` where possible
(``render_axon``, ``render_door_audit``, ``render_side_by_side``).

Usage::

    python -m tools.produce_visual_evidence \\
        --pdf planta_74.pdf \\
        --consensus fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \\
        --output-dir fixtures/planta_74/visual_evidence/

The orchestrator writes ALL seven files. Per-producer failures are
logged but do not abort the run (so the operator always sees the
maximum evidence the pipeline could surface).
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Headless backend (required for CI / pytest)

import matplotlib.pyplot as plt  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402

THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS))


# Mirrors `tools.verify_fidelities.REQUIRED_VISUAL_ARTIFACTS`. Kept
# duplicated here intentionally so the producer can be invoked without
# pulling in verify_fidelities' transitive deps.
REQUIRED_VISUAL_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("original_floorplan", "original_floorplan.png"),
    ("skp_render", "skp_render.png"),
    ("overlay_pdf_skp", "overlay_pdf_skp.png"),
    ("diff_walls", "diff_walls.png"),
    ("diff_doors", "diff_doors.png"),
    ("diff_rooms", "diff_rooms.png"),
    ("mismatches_list", "mismatches_list.md"),
)

# Eight failure conditions per the protocol. PR B3 wires the
# algorithmic checks; PR B1 emits the template with each check
# starting in `not_yet_checked` state so the cockpit + the gate know
# the slot is reserved.
EIGHT_CHECKS: tuple[tuple[str, str], ...] = (
    ("door_without_opening",
     "Door drawn without a real opening in its host wall."),
    ("door_crossing_or_displaced",
     "Door crossing the wall (no carve) or displaced from the gap."),
    ("door_swing_diverges",
     "Door swing / orientation diverges from the PDF arc."),
    ("room_polygon_not_closed",
     "Room with a non-closed polygon."),
    ("room_polygon_bleeds_outside",
     "Room polygon bleeding outside the building outline."),
    ("invented_or_wrong_height_exterior",
     "Exterior wall / esquadria / peitoril invented or wrong height."),
    ("wet_or_terrace_adjacency_wrong",
     "Bathroom / lavabo / A.S. / terraço with wrong adjacency."),
    ("room_rendered_as_bbox",
     "Room rendered as a bounding box / block instead of real "
     "geometry."),
)


# ---------------------------------------------------------------------------
# PR B1 — individual producers
# ---------------------------------------------------------------------------

def _produce_original_floorplan(pdf_path: Path, out_path: Path,
                                  scale: float = 2.0) -> None:
    """PDF page 1 → PNG. Full-page render at the supplied scale."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page = pdf[0]
        img = page.render(scale=scale).to_pil()
    finally:
        pdf.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")


def _produce_skp_render(consensus: dict, out_path: Path,
                          dpi: int = 200) -> None:
    """Axon PNG of the consensus. Reuses
    ``tools.render_preflight.render_axon`` (no SKP file needed —
    consensus is sufficient and we want pure-Python).
    """
    from render_preflight import render_axon
    out_path.parent.mkdir(parents=True, exist_ok=True)
    render_axon(consensus, out_path, dpi=dpi)


def _produce_overlay(pdf_path: Path,
                      skp_render_path: Path,
                      out_path: Path) -> None:
    """PDF (left) + SKP axon (right) overlay on a shared canvas.

    PR B1 uses the side-by-side layout (already implemented in
    ``render_preflight``). PR B3 may replace this with a true
    pixel-aligned superposition once the algorithmic gate exists.
    """
    from render_preflight import render_side_by_side
    out_path.parent.mkdir(parents=True, exist_ok=True)
    render_side_by_side(pdf_path, skp_render_path, out_path)


def _produce_diff_doors(pdf_path: Path, consensus: dict,
                          out_path: Path, dpi: int = 200) -> None:
    """Per-door pass/fail badge map. PR B1 emits the door_audit
    top-down view (consensus doors + D1..D7 mapping). PR B3 paints
    each door's badge based on the algorithmic check verdict.
    """
    from render_preflight import render_door_audit
    out_path.parent.mkdir(parents=True, exist_ok=True)
    render_door_audit(consensus, out_path, dpi=dpi)


def _render_pdf_underlay(pdf_path: Path, ax,
                          alpha: float = 0.45) -> tuple[float, float]:
    """Render the PDF page as a semi-transparent underlay on ``ax``.

    Returns the page bbox in PDF points (width, height) so the caller
    can size the axes correctly.

    Coordinate note: PDF points are y-up but pypdfium2's rasterized
    image is y-down (row 0 = top). To align with consensus polygons
    (which are stored in PDF points, y-up), pass ``origin="upper"``
    and let the extent map pixel (0,0) -> (0, page_h) — i.e. the top
    edge of the page. matplotlib's data axes still go bottom-up so
    polygons plot correctly.
    """
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


def _produce_diff_walls(pdf_path: Path, consensus: dict,
                          out_path: Path, dpi: int = 200) -> None:
    """Walls overlaid on the PDF page, colored by ``geometry_origin``.

    PR B1 surfaces *all* walls (`detector` vs `human_annotation`) so
    the reviewer can see the wall set the gate will judge. PR B3
    upgrades this to a true diff against PDF-detected wall segments
    (walls present in PDF and absent from the consensus, and vice
    versa).
    """
    fig, ax = plt.subplots(figsize=(12, 9))
    page_w, page_h = _render_pdf_underlay(pdf_path, ax)
    thickness = float(consensus.get("wall_thickness_pts", 5.4))
    walls = consensus.get("walls", [])
    n_human = 0
    n_detector = 0
    for w in walls:
        s = w.get("start") or [0.0, 0.0]
        e = w.get("end") or [0.0, 0.0]
        origin = w.get("geometry_origin") or "detector"
        if origin == "human_annotation":
            color = "#1a237e"  # deep blue — human-painted
            n_human += 1
        else:
            color = "#212121"  # near-black — detector
            n_detector += 1
        ori = w.get("orientation")
        t = float(w.get("thickness") or thickness)
        if ori == "h":
            ax.add_patch(MplPolygon(
                [[s[0], s[1] - t / 2], [e[0], s[1] - t / 2],
                 [e[0], s[1] + t / 2], [s[0], s[1] + t / 2]],
                closed=True, facecolor=color, edgecolor=color,
                linewidth=0.6, alpha=0.78, zorder=4,
            ))
        elif ori == "v":
            ax.add_patch(MplPolygon(
                [[s[0] - t / 2, s[1]], [s[0] + t / 2, s[1]],
                 [s[0] + t / 2, e[1]], [s[0] - t / 2, e[1]]],
                closed=True, facecolor=color, edgecolor=color,
                linewidth=0.6, alpha=0.78, zorder=4,
            ))
        else:
            ax.plot([s[0], e[0]], [s[1], e[1]], color=color,
                     linewidth=1.5, alpha=0.78, zorder=4)
    title = (
        f"diff_walls — consensus walls overlaid on PDF "
        f"(detector={n_detector}, human={n_human}; PR B1 minimal)"
    )
    ax.set_title(title, fontsize=10)
    ax.set_xlim(0, page_w)
    ax.set_ylim(0, page_h)
    ax.set_aspect("equal")
    ax.set_axis_off()
    legend = [
        Patch(facecolor="#212121", edgecolor="#000",
              label=f"detector walls ({n_detector})"),
        Patch(facecolor="#1a237e", edgecolor="#000",
              label=f"human_annotation walls ({n_human})"),
    ]
    ax.legend(handles=legend, loc="lower right", fontsize=9,
              framealpha=0.95)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=dpi, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)


def _produce_diff_rooms(pdf_path: Path, consensus: dict,
                          out_path: Path, dpi: int = 200) -> None:
    """Room polygons overlaid on the PDF, color-coded by merge state.

    - Single-label rooms render in a translucent green (PASS-like).
    - Merged cells (name contains ``|``) render in translucent orange
      — these are the cells the protocol's checks 4/5/8 will scrutinize.

    PR B3 upgrades this with per-room badges (closed?, bleeds outside?,
    bbox-shaped?) and an `expected_model` comparison when available.
    """
    fig, ax = plt.subplots(figsize=(12, 9))
    page_w, page_h = _render_pdf_underlay(pdf_path, ax)
    rooms = consensus.get("rooms", [])
    n_single = 0
    n_merged = 0
    for r in rooms:
        pts = r.get("polygon_pts") or []
        if len(pts) < 3:
            continue
        name = r.get("name") or ""
        is_merged = "|" in name
        if is_merged:
            face = "#ffcc80"
            edge = "#e65100"
            n_merged += 1
        else:
            face = "#a5d6a7"
            edge = "#2e7d32"
            n_single += 1
        ax.add_patch(MplPolygon(
            pts, closed=True, facecolor=face, edgecolor=edge,
            linewidth=1.0, alpha=0.45, zorder=3,
        ))
        seed = r.get("seed_pt") or [
            sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts),
        ]
        ax.text(seed[0], seed[1], name, fontsize=7,
                ha="center", va="center", color="#212121",
                bbox=dict(boxstyle="round,pad=0.2", fc="white",
                           ec=edge, lw=0.5, alpha=0.85),
                zorder=10)
    title = (
        f"diff_rooms — consensus room polygons over PDF "
        f"(single={n_single}, merged={n_merged}; PR B1 minimal)"
    )
    ax.set_title(title, fontsize=10)
    ax.set_xlim(0, page_w)
    ax.set_ylim(0, page_h)
    ax.set_aspect("equal")
    ax.set_axis_off()
    legend = [
        Patch(facecolor="#a5d6a7", edgecolor="#2e7d32",
              label=f"single-label rooms ({n_single})"),
        Patch(facecolor="#ffcc80", edgecolor="#e65100",
              label=f"merged cells ({n_merged})"),
    ]
    ax.legend(handles=legend, loc="lower right", fontsize=9,
              framealpha=0.95)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=dpi, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)


def _produce_mismatches_list(consensus: dict, out_path: Path,
                              consensus_path: Path | None = None,
                              ) -> None:
    """Markdown checklist of the eight failure conditions.

    PR B1 emits the template with every condition starting at
    ``not_yet_checked``. PR B3 wires
    ``tools/visual_fidelity_gate.py`` to overwrite this file with
    real per-check verdicts (`pass` / `fail` + per-element IDs).
    """
    n_walls = len(consensus.get("walls") or [])
    n_rooms = len(consensus.get("rooms") or [])
    n_openings = len(consensus.get("openings") or [])
    n_soft = len(consensus.get("soft_barriers") or [])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = [
        "# Visual Fidelity Mismatches — PR B1 template",
        "",
        f"- generated_at: `{now}`",
        f"- consensus_path: `{consensus_path}`"
        if consensus_path else "- consensus_path: (in-memory)",
        f"- walls: {n_walls}",
        f"- rooms: {n_rooms}",
        f"- openings: {n_openings}",
        f"- soft_barriers: {n_soft}",
        "",
        "> **Status:** PR B1 template. Every check below starts at "
        "`not_yet_checked`. PR B3 (`tools/visual_fidelity_gate.py`) "
        "fills these in with `pass` / `fail` + per-element IDs.",
        "",
        "## Eight failure conditions",
        "",
    ]
    for key, description in EIGHT_CHECKS:
        lines.append(f"- [ ] **{key}** — {description}")
        lines.append("  - status: `not_yet_checked`")
        lines.append("  - failing_elements: `[]`")
        lines.append("  - notes: _populated by PR B3._")
        lines.append("")
    lines.append("## Cross-reference")
    lines.append("")
    lines.append(
        "- Protocol: "
        "[`docs/protocols/visual_fidelity_gate_protocol.md`]"
        "(../../docs/protocols/visual_fidelity_gate_protocol.md)"
    )
    lines.append(
        "- Gate entrypoint: `tools/verify_fidelities.py "
        "--require-visual-evidence`"
    )
    lines.append("")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def produce_visual_evidence(pdf_path: Path,
                              consensus_path: Path,
                              output_dir: Path,
                              dpi: int = 200) -> dict:
    """Produce all seven artifacts under ``output_dir``.

    Returns a dict keyed by artifact key with each value carrying
    ``{path, status, error?}``. ``status`` is one of ``ok``,
    ``error``; on ``error`` the ``error`` field carries the
    short message + a one-line traceback excerpt.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    consensus = json.loads(consensus_path.read_text(encoding="utf-8"))

    # Lookup-table for filename per key + the callable.
    skp_path = output_dir / "skp_render.png"
    producers: list[tuple[str, Path, callable]] = [
        ("original_floorplan",
         output_dir / "original_floorplan.png",
         lambda p: _produce_original_floorplan(pdf_path, p)),
        ("skp_render", skp_path,
         lambda p: _produce_skp_render(consensus, p, dpi=dpi)),
        ("overlay_pdf_skp",
         output_dir / "overlay_pdf_skp.png",
         lambda p: _produce_overlay(pdf_path, skp_path, p)),
        ("diff_walls",
         output_dir / "diff_walls.png",
         lambda p: _produce_diff_walls(pdf_path, consensus, p, dpi=dpi)),
        ("diff_doors",
         output_dir / "diff_doors.png",
         lambda p: _produce_diff_doors(pdf_path, consensus, p, dpi=dpi)),
        ("diff_rooms",
         output_dir / "diff_rooms.png",
         lambda p: _produce_diff_rooms(pdf_path, consensus, p, dpi=dpi)),
        ("mismatches_list",
         output_dir / "mismatches_list.md",
         lambda p: _produce_mismatches_list(
             consensus, p, consensus_path=consensus_path)),
    ]
    results: dict[str, dict] = {}
    for key, path, fn in producers:
        try:
            fn(path)
            size = path.stat().st_size if path.exists() else 0
            results[key] = {
                "path": str(path),
                "status": "ok" if size > 0 else "empty",
                "size_bytes": size,
            }
        except Exception as exc:  # noqa: BLE001 — keep the run going
            tb = traceback.format_exc().splitlines()[-1]
            results[key] = {
                "path": str(path),
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": tb,
            }
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="produce_visual_evidence",
        description=(
            "Produce the seven visual evidence artifacts required by "
            "the Visual Fidelity Gate Protocol (2026-05-14). PR B1: "
            "artifact-presence baseline. PR B3 will introduce "
            "tools/visual_fidelity_gate.py with per-check verdicts."
        ),
    )
    ap.add_argument("--pdf", type=Path, required=True,
                    help="source planta PDF (page 1 is rendered).")
    ap.add_argument("--consensus", type=Path, required=True,
                    help="consensus_with_human_walls_and_soft_barriers.json"
                         " (or the post-walls equivalent).")
    ap.add_argument("--output-dir", type=Path, required=True,
                    help="directory the 7 artifacts are written to.")
    ap.add_argument("--dpi", type=int, default=200,
                    help="raster DPI for matplotlib-rendered artifacts.")
    ap.add_argument("--strict", action="store_true",
                    help="exit 2 when any artifact ends in `error` or "
                         "`empty` (default: exit 0 regardless).")
    args = ap.parse_args(argv)

    if not args.pdf.exists():
        print(f"[produce_visual_evidence] PDF not found: {args.pdf}",
              file=sys.stderr)
        return 2
    if not args.consensus.exists():
        print(f"[produce_visual_evidence] consensus not found: "
              f"{args.consensus}", file=sys.stderr)
        return 2

    results = produce_visual_evidence(
        pdf_path=args.pdf,
        consensus_path=args.consensus,
        output_dir=args.output_dir,
        dpi=args.dpi,
    )

    print()
    print(f"=== Visual evidence artifacts -> {args.output_dir} ===")
    print()
    print(f"{'key':>22}  {'status':>7}  {'size':>9}  path")
    print(f"{'-'*22:>22}  {'-'*7:>7}  {'-'*9:>9}  {'-'*40}")
    for key, _fname in REQUIRED_VISUAL_ARTIFACTS:
        r = results.get(key) or {}
        status = r.get("status", "?")
        size = r.get("size_bytes")
        size_str = f"{size:>9,}" if isinstance(size, int) else "n/a".rjust(9)
        print(f"{key:>22}  {status:>7}  {size_str}  {r.get('path', '')}")
        if status == "error":
            print(f"{'':>22}  {'':>7}  {'':>9}  -> {r.get('error', '')}")

    has_failure = any(r.get("status") != "ok" for r in results.values())
    if args.strict and has_failure:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
