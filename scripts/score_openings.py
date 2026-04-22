"""Score openings detected by the pipeline against a YAML ground truth.

Reports precision / recall / F1, plus lists of false positives and false
negatives. Optionally renders a diff PNG with TP/FP/FN color-coded over
the walls of the observed model.

Matching strategy: greedy by center distance. For each GT opening we
pick the closest detection that satisfies all gates:
  - same orientation
  - center distance <= thickness * center_tol_mul  (default 2.0)
  - width ratio within [width_ratio_min, width_ratio_max]  (default 0.5 - 2.0)

A detection can only match one GT opening. GT without a match is a FN,
detection without a match is a FP.

Usage:
    python scripts/score_openings.py \\
        --model runs/<name>/observed_model.json \\
        --gt    tests/fixtures/.../planta_74m2_openings_gt.yaml \\
        [--diff-png runs/<name>/f1_diff.png] \\
        [--center-tol-mul 2.0] \\
        [--width-ratio-min 0.5] \\
        [--width-ratio-max 2.0]

Ground truth YAML schema:
    meta:
      source: "planta_74m2.svg"
      thickness: 6.25
      annotator: "..."
    openings:
      - id: entrance
        center: [200.0, 215.0]
        width: 46.0
        orientation: horizontal
        kind: door
        notes: "porta de entrada"

Observational only: never writes to the pipeline output, never mutates
walls/openings. Pure comparison tool.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


# ---------- data classes ----------

@dataclass(frozen=True)
class GTOpening:
    gt_id: str
    center: tuple[float, float]
    width: float
    orientation: str
    kind: str
    notes: str


@dataclass(frozen=True)
class DetOpening:
    opening_id: str
    center: tuple[float, float]
    width: float
    orientation: str
    kind: str


@dataclass(frozen=True)
class MatchResult:
    tp_pairs: list[tuple[GTOpening, DetOpening]]
    fp: list[DetOpening]
    fn: list[GTOpening]

    @property
    def tp_count(self) -> int:
        return len(self.tp_pairs)

    @property
    def fp_count(self) -> int:
        return len(self.fp)

    @property
    def fn_count(self) -> int:
        return len(self.fn)

    @property
    def precision(self) -> float:
        denom = self.tp_count + self.fp_count
        return self.tp_count / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp_count + self.fn_count
        return self.tp_count / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


# ---------- IO ----------

def load_gt(path: Path) -> tuple[float, list[GTOpening]]:
    """Load GT YAML. Returns (thickness, openings).

    thickness defaults to 6.25 if meta.thickness is missing.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    meta = data.get("meta") or {}
    thickness = float(meta.get("thickness", 6.25))
    raw = data.get("openings") or []
    out: list[GTOpening] = []
    for item in raw:
        center = item.get("center") or [0.0, 0.0]
        out.append(GTOpening(
            gt_id=str(item.get("id", f"gt-{len(out) + 1}")),
            center=(float(center[0]), float(center[1])),
            width=float(item.get("width", 0.0)),
            orientation=str(item.get("orientation", "horizontal")),
            kind=str(item.get("kind", "door")),
            notes=str(item.get("notes", "")),
        ))
    return thickness, out


def load_detections(path: Path) -> tuple[list[DetOpening], list[dict]]:
    """Load detections from observed_model.json. Returns (openings, walls).

    walls are kept as raw dicts for rendering.
    """
    model = json.loads(path.read_text(encoding="utf-8"))
    raw_ops = model.get("openings") or []
    out: list[DetOpening] = []
    for item in raw_ops:
        center = item.get("center") or [0.0, 0.0]
        out.append(DetOpening(
            opening_id=str(item.get("opening_id", f"det-{len(out) + 1}")),
            center=(float(center[0]), float(center[1])),
            width=float(item.get("width", 0.0)),
            orientation=str(item.get("orientation", "horizontal")),
            kind=str(item.get("kind", "door")),
        ))
    walls = list(model.get("walls") or [])
    return out, walls


# ---------- matching ----------

def _center_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return math.sqrt(dx * dx + dy * dy)


def match_openings(
    gts: list[GTOpening],
    dets: list[DetOpening],
    thickness: float,
    center_tol_mul: float = 2.0,
    width_ratio_min: float = 0.5,
    width_ratio_max: float = 2.0,
) -> MatchResult:
    """Greedy match: for each GT, pick the closest detection passing gates.

    A detection can only be matched once. Unmatched GTs become FN, unmatched
    detections become FP.
    """
    center_tol = thickness * center_tol_mul
    used_det: set[int] = set()
    tp_pairs: list[tuple[GTOpening, DetOpening]] = []
    fn: list[GTOpening] = []

    for gt in gts:
        best_idx: int | None = None
        best_dist = float("inf")
        for i, det in enumerate(dets):
            if i in used_det:
                continue
            if det.orientation != gt.orientation:
                continue
            dist = _center_distance(det.center, gt.center)
            if dist > center_tol:
                continue
            if gt.width <= 0:
                continue
            ratio = det.width / gt.width
            if ratio < width_ratio_min or ratio > width_ratio_max:
                continue
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        if best_idx is None:
            fn.append(gt)
        else:
            used_det.add(best_idx)
            tp_pairs.append((gt, dets[best_idx]))

    fp = [det for i, det in enumerate(dets) if i not in used_det]
    return MatchResult(tp_pairs=tp_pairs, fp=fp, fn=fn)


# ---------- reporting ----------

def _fmt_center(c: tuple[float, float]) -> str:
    return f"({c[0]:.1f}, {c[1]:.1f})"


def format_report(
    result: MatchResult,
    model_path: Path,
    gt_path: Path,
    thickness: float,
    center_tol_mul: float,
    det_count: int,
    gt_count: int,
) -> str:
    lines: list[str] = []
    center_tol = thickness * center_tol_mul
    lines.append("=== Score openings ===")
    lines.append(f"model: {model_path} ({det_count} detections)")
    lines.append(f"gt:    {gt_path} ({gt_count} ground truth)")
    lines.append(f"thickness: {thickness}, center_tol: {center_tol:.2f} px")
    lines.append("")
    lines.append("Matching (greedy by center distance):")
    lines.append(f"  TP: {result.tp_count}")
    lines.append(f"  FP: {result.fp_count}")
    lines.append(f"  FN: {result.fn_count}")
    lines.append("")
    lines.append(f"Precision: {result.precision:.3f}")
    lines.append(f"Recall:    {result.recall:.3f}")
    f1_mark = "OK" if result.f1 >= 0.90 else "below target"
    lines.append(f"F1:        {result.f1:.3f}    (target >= 0.90 {f1_mark})")
    lines.append("")

    lines.append("=== FP (pipeline detected, not in GT) ===")
    if not result.fp:
        lines.append("  (none)")
    else:
        for det in result.fp:
            lines.append(
                f"  {det.opening_id}: center={_fmt_center(det.center)} "
                f"w={det.width:.1f} orientation={det.orientation}"
            )
    lines.append("")

    lines.append("=== FN (GT not matched by pipeline) ===")
    if not result.fn:
        lines.append("  (none)")
    else:
        for gt in result.fn:
            notes = f' notes="{gt.notes}"' if gt.notes else ""
            lines.append(
                f"  {gt.gt_id}: center={_fmt_center(gt.center)} "
                f"w={gt.width:.1f} orientation={gt.orientation}{notes}"
            )
    return "\n".join(lines)


# ---------- rendering ----------

def render_diff_png(
    out_path: Path,
    walls: list[dict],
    result: MatchResult,
) -> None:
    """Render walls in gray + openings colored by class (TP green, FP red,
    FN orange). Small legend top-right with counts.
    """
    # Imported lazily so core logic stays testable without PIL at import time.
    from PIL import Image, ImageDraw, ImageFont

    # Determine bounds from walls + all opening centers (GT + det)
    all_pts: list[tuple[float, float]] = []
    for w in walls:
        s = w.get("start") or [0, 0]
        e = w.get("end") or [0, 0]
        all_pts.append((float(s[0]), float(s[1])))
        all_pts.append((float(e[0]), float(e[1])))
    for gt, det in result.tp_pairs:
        all_pts.append(gt.center)
        all_pts.append(det.center)
    for det in result.fp:
        all_pts.append(det.center)
    for gt in result.fn:
        all_pts.append(gt.center)

    if not all_pts:
        # Empty canvas fallback
        Image.new("RGB", (400, 200), (22, 27, 34)).save(out_path, "PNG")
        return

    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)

    canvas_w, canvas_h = 1200, 800
    pad = 40
    legend_w = 220
    plan_w = canvas_w - legend_w - pad * 2
    plan_h = canvas_h - pad * 2
    span_x = max(1.0, maxx - minx)
    span_y = max(1.0, maxy - miny)
    scale = min(plan_w / span_x, plan_h / span_y)
    draw_w = span_x * scale
    draw_h = span_y * scale
    tx = pad + (plan_w - draw_w) / 2
    ty = pad + (plan_h - draw_h) / 2

    def P(x: float, y: float) -> tuple[int, int]:
        return (int(tx + (x - minx) * scale), int(ty + (y - miny) * scale))

    img = Image.new("RGB", (canvas_w, canvas_h), (22, 27, 34))
    draw = ImageDraw.Draw(img)

    # Walls
    for w in walls:
        s = w.get("start") or [0, 0]
        e = w.get("end") or [0, 0]
        draw.line([P(float(s[0]), float(s[1])), P(float(e[0]), float(e[1]))],
                  fill=(140, 140, 140), width=1)

    color_tp = (63, 185, 80)      # green
    color_fp = (248, 81, 73)      # red
    color_fn = (255, 165, 0)      # orange

    def circle(center: tuple[float, float], width: float, fill: tuple[int, int, int]) -> None:
        cx, cy = P(*center)
        rr = max(4, int((width / 2) * scale))
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                     fill=fill, outline=(230, 237, 243))

    for gt, det in result.tp_pairs:
        circle(det.center, det.width, color_tp)
    for det in result.fp:
        circle(det.center, det.width, color_fp)
    for gt in result.fn:
        circle(gt.center, gt.width, color_fn)

    # Legend
    font = _load_font(16)
    font_title = _load_font(20)
    lx = canvas_w - legend_w - pad // 2
    ly = pad
    draw.rectangle([lx, ly, lx + legend_w, ly + 170],
                   fill=(31, 36, 44), outline=(48, 54, 61), width=2)
    draw.text((lx + 12, ly + 10), "f1_diff", font=font_title, fill=(230, 237, 243))

    def legend_row(idx: int, color: tuple[int, int, int], label: str, count: int) -> None:
        row_y = ly + 48 + idx * 32
        draw.ellipse([lx + 14, row_y, lx + 34, row_y + 20], fill=color,
                     outline=(230, 237, 243))
        draw.text((lx + 44, row_y + 2), f"{label}: {count}", font=font,
                  fill=(230, 237, 243))

    legend_row(0, color_tp, "TP", result.tp_count)
    legend_row(1, color_fp, "FP", result.fp_count)
    legend_row(2, color_fn, "FN", result.fn_count)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")


def _load_font(size: int):
    from PIL import ImageFont
    for candidate in (
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                pass
    return ImageFont.load_default()


# ---------- CLI ----------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True, type=Path,
                        help="path to observed_model.json")
    parser.add_argument("--gt", required=True, type=Path,
                        help="path to ground-truth YAML")
    parser.add_argument("--diff-png", type=Path, default=None,
                        help="optional output PNG with TP/FP/FN overlay")
    parser.add_argument("--center-tol-mul", type=float, default=2.0,
                        help="center distance tolerance as multiple of thickness")
    parser.add_argument("--width-ratio-min", type=float, default=0.5,
                        help="minimum det_width / gt_width ratio")
    parser.add_argument("--width-ratio-max", type=float, default=2.0,
                        help="maximum det_width / gt_width ratio")
    args = parser.parse_args(argv)

    thickness, gts = load_gt(args.gt)
    dets, walls = load_detections(args.model)

    result = match_openings(
        gts=gts,
        dets=dets,
        thickness=thickness,
        center_tol_mul=args.center_tol_mul,
        width_ratio_min=args.width_ratio_min,
        width_ratio_max=args.width_ratio_max,
    )

    report = format_report(
        result=result,
        model_path=args.model,
        gt_path=args.gt,
        thickness=thickness,
        center_tol_mul=args.center_tol_mul,
        det_count=len(dets),
        gt_count=len(gts),
    )
    print(report)

    if args.diff_png is not None:
        render_diff_png(args.diff_png, walls, result)
        print(f"\nwrote diff PNG: {args.diff_png}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
