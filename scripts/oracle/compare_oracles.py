"""3-way oracle comparison: pipeline vs CubiCasa DL oracle vs LLM diagnosis.

Reads the pipeline's `observed_model.json`, the CubiCasa oracle's
`cubicasa_observed.json`, and the LLM architect's `oracle_diagnosis_llm.json`
and emits a single `oracle_comparison.json` with counts, deltas, cross-signal
flags (rooms/openings the pipeline emits that no oracle confirms), and a
short narrative interpretation.

Usage:
    python scripts/oracle/compare_oracles.py \\
        --pipeline runs/openings_refine_final \\
        --cubicasa runs/cubicasa_p74 \\
        --out runs/openings_refine_final/oracle_comparison.json

All three sources are optional except the pipeline run. Missing oracles are
skipped with a warning. Pipeline `observed_model.json` is required; absent
input fails loud with exit 1.

Observational only — never writes back into the pipeline output.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from shapely.geometry import Point, Polygon

DEFAULT_MIN_MATCH_DISTANCE_PX = 30.0


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _warn(msg: str) -> None:
    print(f"compare_oracles: WARNING: {msg}", file=sys.stderr)


def _die(msg: str, code: int = 1) -> "NoReturn":  # type: ignore[name-defined]
    print(f"compare_oracles: {msg}", file=sys.stderr)
    sys.exit(code)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _die(f"{label} at {path} is not valid JSON: {exc.msg} (line {exc.lineno})")
    except OSError as exc:
        _die(f"failed to read {label} at {path}: {exc}")


def _require_keys(blob: dict[str, Any], keys: list[str], label: str, path: Path) -> None:
    """Fail loud if any of the keys is missing. Treats missing as schema violation."""
    missing = [k for k in keys if k not in blob]
    if missing:
        _die(f"{label} at {path} missing required keys: {missing}")


def _centroid_of(item: dict[str, Any]) -> tuple[float, float] | None:
    """Best-effort centroid for a room / opening. Returns None if no geometry."""
    centroid = item.get("centroid")
    if isinstance(centroid, (list, tuple)) and len(centroid) >= 2:
        return float(centroid[0]), float(centroid[1])
    center = item.get("center")
    if isinstance(center, (list, tuple)) and len(center) >= 2:
        return float(center[0]), float(center[1])
    polygon = item.get("polygon")
    if isinstance(polygon, list) and len(polygon) >= 3:
        try:
            poly = Polygon(polygon)
            if poly.is_valid and poly.area > 0:
                c = poly.centroid
                return float(c.x), float(c.y)
            # Fall back to vertex mean (degenerate polygon).
            xs = [float(p[0]) for p in polygon]
            ys = [float(p[1]) for p in polygon]
            return sum(xs) / len(xs), sum(ys) / len(ys)
        except Exception:  # noqa: BLE001 - geometry can be wonky; we just want a fallback
            return None
    return None


def _id_of(item: dict[str, Any], key_a: str, key_b: str) -> str:
    return str(item.get(key_a) or item.get(key_b) or "<no-id>")


# --------------------------------------------------------------------------- #
# Loading                                                                     #
# --------------------------------------------------------------------------- #


def load_pipeline(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "observed_model.json"
    if not path.is_file():
        _die(f"pipeline output not found at {path}", code=1)
    blob = _load_json(path, "pipeline observed_model.json")
    _require_keys(blob, ["walls", "rooms", "openings"], "pipeline observed_model.json", path)
    return blob


def load_cubicasa(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "cubicasa_observed.json"
    if not path.is_file():
        _warn(f"cubicasa output not found at {path} - skipping cubicasa column")
        return None
    blob = _load_json(path, "cubicasa_observed.json")
    _require_keys(blob, ["walls", "rooms", "openings"], "cubicasa_observed.json", path)
    return blob


def load_llm_diagnosis(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "oracle_diagnosis_llm.json"
    if not path.is_file():
        _warn(f"LLM diagnosis not found at {path} - skipping llm column")
        return None
    blob = _load_json(path, "oracle_diagnosis_llm.json")
    _require_keys(blob, ["defects"], "oracle_diagnosis_llm.json", path)
    return blob


# --------------------------------------------------------------------------- #
# Comparison core                                                             #
# --------------------------------------------------------------------------- #


def count_collection(blob: dict[str, Any] | None, key: str) -> int:
    if blob is None:
        return 0
    return len(blob.get(key) or [])


def llm_severity_breakdown(diagnosis: dict[str, Any] | None) -> dict[str, int]:
    out = {"high": 0, "medium": 0, "low": 0}
    if diagnosis is None:
        return out
    for d in diagnosis.get("defects", []) or []:
        sev = d.get("severity", "low")
        if sev in out:
            out[sev] += 1
    return out


def llm_high_severity_room_ids(diagnosis: dict[str, Any] | None) -> list[str]:
    if diagnosis is None:
        return []
    ids: list[str] = []
    for d in diagnosis.get("defects", []) or []:
        if d.get("severity") == "high" and d.get("element_type") == "room":
            eid = d.get("element_id")
            if eid:
                ids.append(str(eid))
    return ids


def unmatched_centroids(
    pipeline_items: list[dict[str, Any]],
    oracle_items: list[dict[str, Any]],
    id_keys: tuple[str, str],
    min_distance_px: float,
) -> list[str]:
    """Return IDs of pipeline items whose centroid has no oracle centroid within tol."""
    oracle_pts: list[Point] = []
    for o in oracle_items:
        c = _centroid_of(o)
        if c is not None:
            oracle_pts.append(Point(c))
    unmatched: list[str] = []
    for p in pipeline_items:
        c = _centroid_of(p)
        if c is None:
            continue  # cannot match what we cannot place
        pt = Point(c)
        if not any(pt.distance(op) <= min_distance_px for op in oracle_pts):
            unmatched.append(_id_of(p, id_keys[0], id_keys[1]))
    return unmatched


# --------------------------------------------------------------------------- #
# Narrative                                                                   #
# --------------------------------------------------------------------------- #


def _ratio(a: int, b: int) -> float:
    return round(a / max(b, 1), 3)


def _delta(a: int, b: int) -> dict[str, Any]:
    return {"diff": a - b, "ratio": _ratio(a, b)}


def build_interpretation(
    counts: dict[str, Any],
    deltas: dict[str, Any],
    cross: dict[str, Any],
    has_cubicasa: bool,
    has_llm: bool,
) -> str:
    """One-paragraph narrative summarising the deltas. Concise, actionable."""
    pipe = counts["pipeline"]
    parts: list[str] = []

    if has_cubicasa:
        cub = counts["cubicasa"]
        wr = deltas["walls_pipeline_vs_cubicasa"]["ratio"]
        rr = deltas["rooms_pipeline_vs_cubicasa"]["ratio"]
        orr = deltas["openings_pipeline_vs_cubicasa"]["ratio"]
        if wr >= 1.4:
            parts.append(
                f"Pipeline emits {wr:.1f}x more walls than CubiCasa "
                f"({pipe['walls']} vs {cub['walls']}). Likely fragmentation of single "
                f"walls into multiple Hough segments — see patches 01-04."
            )
        elif wr <= 0.7:
            parts.append(
                f"Pipeline reports fewer walls than CubiCasa "
                f"({pipe['walls']} vs {cub['walls']}, ratio {wr:.2f}). "
                f"Possible under-detection or overly aggressive dedup."
            )
        else:
            parts.append(
                f"Wall counts are comparable to CubiCasa "
                f"({pipe['walls']} vs {cub['walls']}, ratio {wr:.2f})."
            )

        if rr >= 1.5:
            high_ids = cross.get("llm_high_severity_room_ids", [])
            tail = ""
            if high_ids:
                shown = ", ".join(sorted(set(high_ids))[:5])
                tail = (
                    f" LLM flagged {len(high_ids)} high-severity room defect(s) "
                    f"({shown}). Apply room sliver filter."
                )
            parts.append(
                f"Pipeline reports {pipe['rooms']} rooms vs CubiCasa's "
                f"{cub['rooms']} (ratio {rr:.2f}) — strong over-polygonization.{tail}"
            )
        elif rr <= 0.6:
            parts.append(
                f"Pipeline finds fewer rooms than CubiCasa "
                f"({pipe['rooms']} vs {cub['rooms']}). Possible polygonize closure failure."
            )

        if orr >= 1.4 or orr <= 0.7:
            parts.append(
                f"Openings ratio is {orr:.2f} ({pipe['openings']} pipeline vs "
                f"{cub['openings']} cubicasa)."
            )

        rooms_only = cross.get("rooms_only_in_pipeline", [])
        ops_only = cross.get("openings_only_in_pipeline", [])
        if rooms_only:
            parts.append(
                f"{len(rooms_only)} pipeline room(s) have no CubiCasa centroid within tol "
                f"(candidates for sliver pruning)."
            )
        if ops_only:
            parts.append(
                f"{len(ops_only)} pipeline opening(s) have no CubiCasa confirmation "
                f"(candidates for opening_no_host audit)."
            )
    else:
        parts.append("CubiCasa oracle absent — geometric sanity check skipped.")

    if has_llm:
        sev = counts.get("llm_defects_by_severity", {})
        total = counts.get("llm_defects_total", 0)
        parts.append(
            f"LLM diagnosis: {total} defect(s) (high={sev.get('high', 0)}, "
            f"medium={sev.get('medium', 0)}, low={sev.get('low', 0)})."
        )
    else:
        parts.append("LLM diagnosis absent — visual cross-check skipped.")

    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Optional PNG                                                                #
# --------------------------------------------------------------------------- #


def render_png(
    pipeline: dict[str, Any],
    cubicasa: dict[str, Any] | None,
    llm: dict[str, Any] | None,
    cross: dict[str, Any],
    out_path: Path,
) -> None:
    """Three-column side-by-side. Skipped silently if matplotlib is missing."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon as MplPoly  # noqa: N813
    except ImportError:
        _warn("matplotlib not installed — skipping PNG render")
        return

    fig, axes = plt.subplots(1, 3, figsize=(18, 7))
    flagged = set(cross.get("rooms_only_in_pipeline", []))
    flagged_high = set(cross.get("llm_high_severity_room_ids", []))

    def _draw_model(ax, blob: dict[str, Any] | None, title: str, highlight: set[str]) -> None:
        ax.set_title(title)
        ax.set_aspect("equal")
        ax.invert_yaxis()  # source coordinates have y-down origin
        if blob is None:
            ax.text(0.5, 0.5, "(missing)", ha="center", va="center", transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])
            return
        for w in blob.get("walls", []) or []:
            s = w.get("start")
            e = w.get("end")
            if s and e:
                ax.plot([s[0], e[0]], [s[1], e[1]], color="#444", linewidth=0.6)
        for r in blob.get("rooms", []) or []:
            poly = r.get("polygon")
            if poly and len(poly) >= 3:
                rid = _id_of(r, "room_id", "id")
                color = "#d62728" if rid in highlight else "#1f77b4"
                alpha = 0.45 if rid in highlight else 0.18
                ax.add_patch(MplPoly(poly, closed=True, facecolor=color, alpha=alpha,
                                     edgecolor=color, linewidth=0.5))
        for o in blob.get("openings", []) or []:
            c = o.get("center")
            if c:
                ax.plot(c[0], c[1], marker="o", color="#2ca02c", markersize=3)

    _draw_model(axes[0], pipeline, "Pipeline", flagged)
    _draw_model(axes[1], cubicasa, "CubiCasa", set())

    # Third panel: LLM defects, drawn over a faded pipeline.
    _draw_model(axes[2], pipeline, "LLM defects (over pipeline)", flagged_high)
    if llm is not None:
        defects = llm.get("defects", []) or []
        # Index pipeline rooms by id for label placement.
        rooms_by_id: dict[str, dict[str, Any]] = {}
        for r in pipeline.get("rooms", []) or []:
            rid = _id_of(r, "room_id", "id")
            rooms_by_id[rid] = r
        for d in defects:
            if d.get("element_type") == "room":
                eid = str(d.get("element_id", ""))
                room = rooms_by_id.get(eid)
                if room is not None:
                    c = _centroid_of(room)
                    if c is not None:
                        sev = d.get("severity", "low")
                        color = {"high": "#d62728", "medium": "#ff7f0e", "low": "#bcbd22"}.get(sev, "#888")
                        axes[2].plot(c[0], c[1], marker="x", color=color, markersize=8, mew=2)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="compare_oracles",
        description="Build a 3-way comparison between the pipeline and its two oracles.",
    )
    p.add_argument("--pipeline", required=True, type=Path,
                   help="Pipeline run directory (must contain observed_model.json).")
    p.add_argument("--cubicasa", type=Path, default=None,
                   help="CubiCasa oracle run directory (must contain cubicasa_observed.json).")
    p.add_argument("--out", required=True, type=Path,
                   help="Output JSON path (e.g. runs/<run>/oracle_comparison.json).")
    p.add_argument("--min-match-distance-px", type=float, default=DEFAULT_MIN_MATCH_DISTANCE_PX,
                   help=f"Centroid distance threshold for matching pipeline elements to oracle elements (default: {DEFAULT_MIN_MATCH_DISTANCE_PX}).")
    p.add_argument("--png", action="store_true",
                   help="Also render a side-by-side PNG next to the output JSON.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    pipeline_run: Path = args.pipeline
    if not pipeline_run.is_dir():
        _die(f"pipeline run dir not found at {pipeline_run}", code=1)

    pipeline = load_pipeline(pipeline_run)
    cubicasa = load_cubicasa(args.cubicasa) if args.cubicasa is not None else None
    if args.cubicasa is None:
        _warn("no --cubicasa argument; skipping cubicasa column")
    llm = load_llm_diagnosis(pipeline_run)

    if cubicasa is None and llm is None:
        _die("nothing to compare — both cubicasa and LLM diagnosis are absent", code=1)

    counts: dict[str, Any] = {
        "pipeline": {
            "walls": count_collection(pipeline, "walls"),
            "rooms": count_collection(pipeline, "rooms"),
            "openings": count_collection(pipeline, "openings"),
        },
    }
    if cubicasa is not None:
        counts["cubicasa"] = {
            "walls": count_collection(cubicasa, "walls"),
            "rooms": count_collection(cubicasa, "rooms"),
            "openings": count_collection(cubicasa, "openings"),
        }
    if llm is not None:
        defects = llm.get("defects", []) or []
        counts["llm_defects_total"] = len(defects)
        counts["llm_defects_by_severity"] = llm_severity_breakdown(llm)

    deltas: dict[str, Any] = {}
    if cubicasa is not None:
        pipe = counts["pipeline"]
        cub = counts["cubicasa"]
        deltas = {
            "walls_pipeline_vs_cubicasa": _delta(pipe["walls"], cub["walls"]),
            "rooms_pipeline_vs_cubicasa": _delta(pipe["rooms"], cub["rooms"]),
            "openings_pipeline_vs_cubicasa": _delta(pipe["openings"], cub["openings"]),
        }

    cross: dict[str, Any] = {
        "llm_high_severity_room_ids": llm_high_severity_room_ids(llm),
        "rooms_only_in_pipeline": [],
        "openings_only_in_pipeline": [],
    }
    if cubicasa is not None:
        cross["rooms_only_in_pipeline"] = unmatched_centroids(
            pipeline.get("rooms") or [],
            cubicasa.get("rooms") or [],
            id_keys=("room_id", "id"),
            min_distance_px=args.min_match_distance_px,
        )
        cross["openings_only_in_pipeline"] = unmatched_centroids(
            pipeline.get("openings") or [],
            cubicasa.get("openings") or [],
            id_keys=("opening_id", "id"),
            min_distance_px=args.min_match_distance_px,
        )

    interpretation = build_interpretation(
        counts=counts,
        deltas=deltas,
        cross=cross,
        has_cubicasa=cubicasa is not None,
        has_llm=llm is not None,
    )

    output: dict[str, Any] = {
        "pipeline_run": pipeline_run.name,
        "cubicasa_run": args.cubicasa.name if args.cubicasa is not None else None,
        "llm_diagnosis_present": llm is not None,
        "min_match_distance_px": args.min_match_distance_px,
        "counts": counts,
        "deltas": deltas,
        "cross_signal": cross,
        "interpretation": interpretation,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"compare_oracles: wrote {args.out}")

    if args.png:
        png_path = args.out.with_suffix(".png")
        render_png(pipeline, cubicasa, llm, cross, png_path)
        if png_path.exists():
            print(f"compare_oracles: wrote {png_path}")

    print(f"compare_oracles: {interpretation}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
