"""Path-level diagnostic comparing planta_74.pdf vs planta_74_clean.pdf.

Why this exists
---------------
`tools/build_vector_consensus.py` returns `[err] no wall paths detected`
on `planta_74_clean.pdf` while succeeding on `planta_74.pdf`. ChatGPT's
recommendation: before touching the extractor, dump a side-by-side
inventory of the two PDFs at the path level and confirm whether the
"clean" version actually lost the filled wall paths or just changed
their attributes (color, fill rule, stroke flag, layer/clipping).

Output
------
runs/planta_74_clean_debug/
    path_inventory_original.json
    path_inventory_clean.json
    path_diff_summary.json        — counts/colors side-by-side + verdict
    paths_original.png            — vector render of all paths
    paths_clean.png               — same for clean

Run
---
    .venv/Scripts/python.exe -m scripts.investigation.planta_74_clean_diff
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402

# Import the production helpers so the diff matches what the extractor
# actually sees. _read_paths returns list[(PathInfo, raw)] and
# _identify_wall_paths is the wall filter. PathInfo has
# bbox/fill/fillmode/stroke_on/nseg.
from build_vector_consensus import (  # noqa: E402
    PathInfo,
    _identify_wall_paths,
    _read_paths,
)

OUT_DIR = REPO_ROOT / "runs" / "planta_74_clean_debug"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _path_to_dict(p: PathInfo) -> dict[str, Any]:
    l, b, r, t = p.bbox
    return {
        "bbox": [round(l, 3), round(b, 3), round(r, 3), round(t, 3)],
        "width": round(r - l, 3),
        "height": round(t - b, 3),
        "min_dim": round(min(r - l, t - b), 3),
        "max_dim": round(max(r - l, t - b), 3),
        "fill_rgba": list(p.fill),
        "fillmode": p.fillmode,         # 0 = no fill, 1 = nonzero, 2 = even-odd
        "stroke_on": p.stroke_on,       # 0/1
        "nseg": p.nseg,
    }


def _summarize(paths: list[tuple[PathInfo, object]]) -> dict[str, Any]:
    n = len(paths)
    by_fillmode: Counter = Counter()
    by_stroke: Counter = Counter()
    by_kind: Counter = Counter()  # ("filled_only" | "stroked_only" | "filled_stroked" | "neither")
    by_fill_color: Counter = Counter()
    by_color_kind: Counter = Counter()
    total_seg = 0

    for pi, _raw in paths:
        by_fillmode[pi.fillmode] += 1
        by_stroke[pi.stroke_on] += 1
        kind = (
            "filled_only" if pi.fillmode != 0 and pi.stroke_on == 0 else
            "stroked_only" if pi.fillmode == 0 and pi.stroke_on else
            "filled_stroked" if pi.fillmode != 0 and pi.stroke_on else
            "neither"
        )
        by_kind[kind] += 1
        by_fill_color[tuple(pi.fill)] += 1
        if kind == "filled_only":
            by_color_kind[tuple(pi.fill)] += 1
        total_seg += pi.nseg

    # Top fill colors among filled-only paths (the wall candidate set
    # that _identify_wall_paths sees).
    top_filled_colors = [
        {"rgba": list(c), "count": n_}
        for c, n_ in by_color_kind.most_common(10)
    ]

    return {
        "total_path_objects": n,
        "total_segments": total_seg,
        "by_fillmode": dict(by_fillmode),
        "by_stroke_on": dict(by_stroke),
        "by_kind": dict(by_kind),
        "top_filled_only_colors": top_filled_colors,
        "n_unique_fill_colors": len(by_fill_color),
    }


def _try_identify_walls(paths: list[tuple[PathInfo, object]]) -> dict[str, Any]:
    walls = _identify_wall_paths(paths)
    if not walls:
        return {"wall_count": 0, "verdict": "extractor_returns_empty"}
    import statistics

    short = [min(p.bbox[2] - p.bbox[0], p.bbox[3] - p.bbox[1]) for p in walls]
    return {
        "wall_count": len(walls),
        "thickness_pts_median": round(statistics.median(short), 3),
        "verdict": "extractor_succeeds",
    }


def _inventory(pdf_path: Path) -> dict[str, Any]:
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    width, height = page.get_size()
    paths = _read_paths(page)
    summary = _summarize(paths)
    walls = _try_identify_walls(paths)
    detail = [_path_to_dict(pi) for pi, _ in paths]
    return {
        "pdf": str(pdf_path.relative_to(REPO_ROOT)),
        "page_size_pts": [round(width, 3), round(height, 3)],
        "summary": summary,
        "walls": walls,
        "paths": detail,
    }


def _render_paths(paths: list[tuple[PathInfo, object]],
                  page_size: tuple[float, float],
                  out_png: Path,
                  title: str) -> None:
    """Render every path's bbox as a translucent rectangle, color-coded by
    fillmode/stroke kind, so we can visually see where the geometry sits.
    """
    pw, ph = page_size
    fig, ax = plt.subplots(figsize=(11, 11 * ph / pw), dpi=100)
    color_map = {
        "filled_only": "#1f6feb",
        "stroked_only": "#9a6700",
        "filled_stroked": "#cf222e",
        "neither": "#999",
    }
    for pi, _ in paths:
        l, b, r, t = pi.bbox
        kind = (
            "filled_only" if pi.fillmode != 0 and pi.stroke_on == 0 else
            "stroked_only" if pi.fillmode == 0 and pi.stroke_on else
            "filled_stroked" if pi.fillmode != 0 and pi.stroke_on else
            "neither"
        )
        rect = mpatches.Rectangle(
            (l, b), r - l, t - b,
            facecolor=color_map[kind] if kind == "filled_only" else "none",
            edgecolor=color_map[kind],
            alpha=0.35 if kind == "filled_only" else 0.5,
            linewidth=0.5,
        )
        ax.add_patch(rect)
    ax.set_xlim(0, pw)
    ax.set_ylim(0, ph)
    ax.set_aspect("equal")
    ax.set_title(title)
    legend_handles = [
        mpatches.Patch(facecolor=c, edgecolor=c, label=k, alpha=0.5)
        for k, c in color_map.items()
    ]
    ax.legend(handles=legend_handles, loc="upper right", fontsize=8)
    plt.tight_layout()
    plt.savefig(out_png, bbox_inches="tight")
    plt.close()


def main() -> int:
    targets = [
        ("original", REPO_ROOT / "planta_74.pdf",
         OUT_DIR / "path_inventory_original.json",
         OUT_DIR / "paths_original.png"),
        ("clean", REPO_ROOT / "planta_74_clean.pdf",
         OUT_DIR / "path_inventory_clean.json",
         OUT_DIR / "paths_clean.png"),
    ]
    inventories: dict[str, dict[str, Any]] = {}
    for tag, pdf_path, json_out, png_out in targets:
        if not pdf_path.exists():
            print(f"[skip] {pdf_path} not found", file=sys.stderr)
            continue
        inv = _inventory(pdf_path)
        json_out.write_text(json.dumps(inv, indent=2), encoding="utf-8")
        # Render
        pdf = pdfium.PdfDocument(str(pdf_path))
        page = pdf[0]
        paths = _read_paths(page)
        _render_paths(paths, page.get_size(), png_out, f"{tag} — {pdf_path.name}")
        inventories[tag] = inv
        print(f"[{tag}] {len(inv['paths'])} paths, "
              f"{inv['summary']['by_kind']}, walls={inv['walls']}")

    # Diff summary
    if "original" in inventories and "clean" in inventories:
        orig = inventories["original"]["summary"]
        clean = inventories["clean"]["summary"]
        diff = {
            "page_size_pts": {
                "original": inventories["original"]["page_size_pts"],
                "clean": inventories["clean"]["page_size_pts"],
            },
            "total_paths": {
                "original": orig["total_path_objects"],
                "clean": clean["total_path_objects"],
                "delta": clean["total_path_objects"] - orig["total_path_objects"],
            },
            "by_kind_delta": {
                k: clean["by_kind"].get(k, 0) - orig["by_kind"].get(k, 0)
                for k in set(orig["by_kind"]) | set(clean["by_kind"])
            },
            "filled_only_count": {
                "original": orig["by_kind"].get("filled_only", 0),
                "clean": clean["by_kind"].get("filled_only", 0),
            },
            "wall_extractor": {
                "original": inventories["original"]["walls"],
                "clean": inventories["clean"]["walls"],
            },
            "verdict": _verdict(inventories),
        }
        (OUT_DIR / "path_diff_summary.json").write_text(
            json.dumps(diff, indent=2), encoding="utf-8")
        print()
        print("=== DIFF SUMMARY ===")
        print(json.dumps(diff, indent=2, ensure_ascii=False))
    return 0


def _verdict(inventories: dict[str, dict[str, Any]]) -> str:
    """Plain-English verdict so a reader doesn't have to parse the JSON."""
    orig = inventories["original"]
    clean = inventories["clean"]
    orig_filled = orig["summary"]["by_kind"].get("filled_only", 0)
    clean_filled = clean["summary"]["by_kind"].get("filled_only", 0)
    orig_walls = orig["walls"].get("wall_count", 0)
    clean_walls = clean["walls"].get("wall_count", 0)

    if clean["summary"]["total_path_objects"] == 0:
        return "clean has ZERO path objects — PDF is rasterized, no vector geometry to extract"
    if clean_filled == 0:
        return ("clean has paths but ZERO filled-only — wall fill flag was dropped "
                "(extractor_returns_empty). Likely converted to stroke-only or filled+stroked.")
    if clean_walls == 0 and orig_walls > 0:
        return ("clean has filled paths but _identify_wall_paths rejects them — color "
                "or thickness clustering changed.")
    if clean_walls > 0 and orig_walls > 0:
        return f"BOTH extractors succeed: original={orig_walls} walls, clean={clean_walls} walls"
    return "uncategorized; inspect path_inventory_*.json manually"


if __name__ == "__main__":
    sys.exit(main())
