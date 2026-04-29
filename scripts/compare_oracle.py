"""3-way opening comparison: pipeline vs CubiCasa5K oracle vs GT.

Runs the pipeline's `match_openings` from `scripts/score_openings.py` in
three combinations and emits a markdown report.

Usage:
    python scripts/compare_oracle.py \\
        --pipeline runs/planta74/observed_model.json \\
        --oracle   runs/oracle_planta74/oracle_openings.json \\
        --gt       tests/fixtures/svg/planta_74m2_openings_gt.yaml \\
        --out      runs/3way_report.md

The report has:
    * Summary row per pair (TP / FP / FN / P / R / F1)
    * Per-opening list for each comparison
    * "Divergences" section: openings where pipeline and oracle *disagree*
      (one sees it, the other doesn't) — often the most informative clues.

The oracle JSON must follow the schema emitted by
`scripts/run_cubicasa_oracle.py` (openings are wrapped in a dict at key
"openings"). The pipeline JSON uses the standard `observed_model.json` shape.

Observational only: this script never writes to model/pipeline output.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# We reuse score_openings' matching logic. Keep this directory on the path
# when invoked via `python scripts/compare_oracle.py`.
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from score_openings import (  # noqa: E402  (after sys.path manipulation)
    DetOpening,
    GTOpening,
    MatchResult,
    load_gt,
    match_openings,
)


# ---------- data ingestion ----------


def _dets_from_openings_list(openings: list[dict[str, Any]]) -> list[DetOpening]:
    out: list[DetOpening] = []
    for item in openings:
        center = item.get("center") or [0.0, 0.0]
        out.append(
            DetOpening(
                opening_id=str(item.get("opening_id", f"det-{len(out) + 1}")),
                center=(float(center[0]), float(center[1])),
                width=float(item.get("width", 0.0)),
                orientation=str(item.get("orientation", "horizontal")),
                kind=str(item.get("kind", "door")),
            )
        )
    return out


def load_pipeline_detections(path: Path) -> list[DetOpening]:
    """Read openings out of `observed_model.json`."""
    model = json.loads(path.read_text(encoding="utf-8"))
    return _dets_from_openings_list(model.get("openings") or [])


def load_oracle_detections(path: Path) -> list[DetOpening]:
    """Read openings out of `oracle_openings.json`."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _dets_from_openings_list(payload.get("openings") or [])


def gts_as_dets(gts: list[GTOpening]) -> list[DetOpening]:
    """Adapter: GTOpening -> DetOpening so we can pair pipeline vs oracle
    using the same match_openings logic (where one side acts as "GT").
    """
    return [
        DetOpening(
            opening_id=gt.gt_id,
            center=gt.center,
            width=gt.width,
            orientation=gt.orientation,
            kind=gt.kind,
        )
        for gt in gts
    ]


def dets_as_gts(dets: list[DetOpening], prefix: str) -> list[GTOpening]:
    """Adapter for the inverse: use a det list as pseudo-GT so we can
    evaluate "how much does oracle agree with pipeline" symmetrically.
    """
    return [
        GTOpening(
            gt_id=f"{prefix}-{i+1}",
            center=d.center,
            width=d.width,
            orientation=d.orientation,
            kind=d.kind,
            notes="",
        )
        for i, d in enumerate(dets)
    ]


# ---------- comparison driver ----------


@dataclass(frozen=True)
class Comparison:
    label: str
    result: MatchResult
    n_a: int  # "dets" side
    n_b: int  # "gts" side


def run_all_pairs(
    pipeline_dets: list[DetOpening],
    oracle_dets: list[DetOpening],
    gt_openings: list[GTOpening],
    thickness: float,
    center_tol_mul: float,
    width_ratio_min: float,
    width_ratio_max: float,
) -> list[Comparison]:
    """Run three match_openings comparisons and return them."""
    common = dict(
        thickness=thickness,
        center_tol_mul=center_tol_mul,
        width_ratio_min=width_ratio_min,
        width_ratio_max=width_ratio_max,
    )

    r_pipeline_gt = match_openings(gt_openings, pipeline_dets, **common)
    r_oracle_gt = match_openings(gt_openings, oracle_dets, **common)

    # pipeline-vs-oracle: treat oracle as GT so we can reuse match_openings.
    r_pipeline_vs_oracle = match_openings(
        dets_as_gts(oracle_dets, prefix="oracle"), pipeline_dets, **common
    )

    return [
        Comparison("pipeline vs GT", r_pipeline_gt, len(pipeline_dets), len(gt_openings)),
        Comparison("oracle   vs GT", r_oracle_gt, len(oracle_dets), len(gt_openings)),
        Comparison("pipeline vs oracle", r_pipeline_vs_oracle, len(pipeline_dets), len(oracle_dets)),
    ]


def find_divergences(
    pipeline_dets: list[DetOpening],
    oracle_dets: list[DetOpening],
    thickness: float,
    center_tol_mul: float,
    width_ratio_min: float,
    width_ratio_max: float,
) -> tuple[list[DetOpening], list[DetOpening]]:
    """Openings that pipeline sees but oracle doesn't, and vice versa.

    Both lists are useful debug signals: pipeline-only = possible FPs (the
    pipeline is hallucinating a door that CubiCasa doesn't confirm) or
    possible oracle misses; oracle-only = possible pipeline misses or
    oracle false alarms.
    """
    common = dict(
        thickness=thickness,
        center_tol_mul=center_tol_mul,
        width_ratio_min=width_ratio_min,
        width_ratio_max=width_ratio_max,
    )

    # Pipeline-only: pipeline dets not matched by any oracle det.
    r1 = match_openings(dets_as_gts(oracle_dets, "oracle"), pipeline_dets, **common)
    pipeline_only = list(r1.fp)

    # Oracle-only: oracle dets not matched by any pipeline det.
    r2 = match_openings(dets_as_gts(pipeline_dets, "pipeline"), oracle_dets, **common)
    oracle_only = list(r2.fp)

    return pipeline_only, oracle_only


# ---------- markdown rendering ----------


def _fmt_center(c: tuple[float, float]) -> str:
    return f"({c[0]:.1f}, {c[1]:.1f})"


def render_markdown(
    pipeline_path: Path,
    oracle_path: Path,
    gt_path: Path,
    thickness: float,
    center_tol_mul: float,
    comps: list[Comparison],
    pipeline_only: list[DetOpening],
    oracle_only: list[DetOpening],
) -> str:
    lines: list[str] = []
    center_tol = thickness * center_tol_mul

    lines.append("# 3-way opening comparison")
    lines.append("")
    lines.append("| Input | Path |")
    lines.append("|---|---|")
    lines.append(f"| pipeline | `{pipeline_path}` |")
    lines.append(f"| oracle | `{oracle_path}` |")
    lines.append(f"| GT | `{gt_path}` |")
    lines.append("")
    lines.append(
        f"Matching parameters: thickness = `{thickness}`, "
        f"center_tol = `{center_tol:.2f}px` "
        f"(= thickness * {center_tol_mul})."
    )
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Comparison | n(A) | n(B) | TP | FP | FN | P | R | F1 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for c in comps:
        r = c.result
        lines.append(
            f"| {c.label} | {c.n_a} | {c.n_b} | {r.tp_count} | "
            f"{r.fp_count} | {r.fn_count} | {r.precision:.3f} | "
            f"{r.recall:.3f} | **{r.f1:.3f}** |"
        )
    lines.append("")
    lines.append(
        "`n(A)` = size of the detections side; `n(B)` = size of the "
        "reference side (GT or the other detector). TP/FP/FN are from the "
        "detections-side perspective."
    )
    lines.append("")

    # Per-comparison detail
    for c in comps:
        r = c.result
        lines.append(f"## {c.label}")
        lines.append("")

        if r.fp:
            lines.append(f"### FP ({len(r.fp)}) — detections without a reference match")
            lines.append("")
            lines.append("| id | center | width | orientation | kind |")
            lines.append("|---|---|---|---|---|")
            for det in r.fp:
                lines.append(
                    f"| `{det.opening_id}` | {_fmt_center(det.center)} | "
                    f"{det.width:.1f} | {det.orientation} | {det.kind} |"
                )
            lines.append("")

        if r.fn:
            lines.append(f"### FN ({len(r.fn)}) — reference entries with no matching detection")
            lines.append("")
            lines.append("| id | center | width | orientation | kind | notes |")
            lines.append("|---|---|---|---|---|---|")
            for gt in r.fn:
                notes = gt.notes.replace("|", "/") if gt.notes else ""
                lines.append(
                    f"| `{gt.gt_id}` | {_fmt_center(gt.center)} | "
                    f"{gt.width:.1f} | {gt.orientation} | {gt.kind} | {notes} |"
                )
            lines.append("")

        if not r.fp and not r.fn:
            lines.append("_Perfect match on this pair._")
            lines.append("")

    # Divergences
    lines.append("## Divergences (pipeline <-> oracle)")
    lines.append("")
    lines.append(
        "These are openings seen by one detector but not the other. Often "
        "the richest debugging signal: a pipeline-only detection near a "
        "corner may be a geometric false positive; an oracle-only detection "
        "on a real door may be a pipeline miss."
    )
    lines.append("")

    if pipeline_only:
        lines.append(f"### Pipeline-only ({len(pipeline_only)})")
        lines.append("")
        lines.append("| id | center | width | orientation | kind |")
        lines.append("|---|---|---|---|---|")
        for det in pipeline_only:
            lines.append(
                f"| `{det.opening_id}` | {_fmt_center(det.center)} | "
                f"{det.width:.1f} | {det.orientation} | {det.kind} |"
            )
        lines.append("")
    else:
        lines.append("_No pipeline-only openings (everything pipeline sees, oracle also sees)._")
        lines.append("")

    if oracle_only:
        lines.append(f"### Oracle-only ({len(oracle_only)})")
        lines.append("")
        lines.append("| id | center | width | orientation | kind |")
        lines.append("|---|---|---|---|---|")
        for det in oracle_only:
            lines.append(
                f"| `{det.opening_id}` | {_fmt_center(det.center)} | "
                f"{det.width:.1f} | {det.orientation} | {det.kind} |"
            )
        lines.append("")
    else:
        lines.append("_No oracle-only openings (everything oracle sees, pipeline also sees)._")
        lines.append("")

    return "\n".join(lines)


# ---------- CLI ----------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pipeline", required=True, type=Path,
                        help="observed_model.json from the pipeline.")
    parser.add_argument("--oracle", required=True, type=Path,
                        help="oracle_openings.json from run_cubicasa_oracle.py.")
    parser.add_argument("--gt", required=True, type=Path,
                        help="Ground-truth YAML (same format as score_openings.py).")
    parser.add_argument("--out", required=True, type=Path,
                        help="Output markdown report path.")
    parser.add_argument("--center-tol-mul", type=float, default=2.0,
                        help="Center distance tolerance as multiple of thickness.")
    parser.add_argument("--width-ratio-min", type=float, default=0.5,
                        help="Minimum det_width / gt_width ratio for a match.")
    parser.add_argument("--width-ratio-max", type=float, default=2.0,
                        help="Maximum det_width / gt_width ratio for a match.")
    args = parser.parse_args(argv)

    thickness, gt_openings = load_gt(args.gt)
    pipeline_dets = load_pipeline_detections(args.pipeline)
    oracle_dets = load_oracle_detections(args.oracle)

    comps = run_all_pairs(
        pipeline_dets=pipeline_dets,
        oracle_dets=oracle_dets,
        gt_openings=gt_openings,
        thickness=thickness,
        center_tol_mul=args.center_tol_mul,
        width_ratio_min=args.width_ratio_min,
        width_ratio_max=args.width_ratio_max,
    )

    pipeline_only, oracle_only = find_divergences(
        pipeline_dets=pipeline_dets,
        oracle_dets=oracle_dets,
        thickness=thickness,
        center_tol_mul=args.center_tol_mul,
        width_ratio_min=args.width_ratio_min,
        width_ratio_max=args.width_ratio_max,
    )

    report = render_markdown(
        pipeline_path=args.pipeline,
        oracle_path=args.oracle,
        gt_path=args.gt,
        thickness=thickness,
        center_tol_mul=args.center_tol_mul,
        comps=comps,
        pipeline_only=pipeline_only,
        oracle_only=oracle_only,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"wrote {args.out}")
    print()
    # One-line summary per pair for the terminal too.
    for c in comps:
        r = c.result
        print(
            f"  {c.label}: F1={r.f1:.3f}  "
            f"(TP={r.tp_count} FP={r.fp_count} FN={r.fn_count})"
        )
    print(f"  divergences: pipeline-only={len(pipeline_only)}, "
          f"oracle-only={len(oracle_only)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
