"""Generate a live HTML dashboard with current F1 metrics across all plans.

Static, self-contained HTML page (inline CSS/SVG, no external deps) that
shows the current openings F1 score for every known plan plus an embedded
SVG visualization of walls + openings (TP green, FP red, FN orange-ring).

Complementary to ``runs/validation_summary.png`` but navigable: each plan
is a card in a 2-col grid, with a collapsible details block for the raw
metrics. Missing runs render as amber "not run yet" cards rather than
failing the whole build.

Usage:
    python scripts/generate_f1_dashboard.py --out docs/F1-DASHBOARD.html

Scoring is delegated to ``scripts/score_openings.match_openings`` — the
dashboard never reimplements scoring, only renders its output.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

# Make score_openings importable when this script is executed directly.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from score_openings import (  # noqa: E402  (intentional sys.path shim above)
    DetOpening,
    GTOpening,
    MatchResult,
    load_detections,
    load_gt,
    match_openings,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------- plan registry ----------

@dataclass(frozen=True)
class PlanSpec:
    name: str
    model_rel: str
    gt_rel: str
    subtitle: str


PLANS: list[PlanSpec] = [
    PlanSpec(
        name="planta_74m2",
        model_rel="runs/validation_p74/observed_model.json",
        gt_rel="tests/fixtures/svg/planta_74m2_openings_gt.yaml",
        subtitle="alpha GT (pipeline-derived, self-consistent)",
    ),
    PlanSpec(
        name="studio",
        model_rel="runs/synth_studio/observed_model.json",
        gt_rel="tests/fixtures/svg/synthetic/studio_openings_gt.yaml",
        subtitle="synthetic — 3 rooms",
    ),
    PlanSpec(
        name="2br",
        model_rel="runs/synth_2br/observed_model.json",
        gt_rel="tests/fixtures/svg/synthetic/2br_openings_gt.yaml",
        subtitle="synthetic — 2 bedrooms",
    ),
    PlanSpec(
        name="3br",
        model_rel="runs/synth_3br/observed_model.json",
        gt_rel="tests/fixtures/svg/synthetic/3br_openings_gt.yaml",
        subtitle="synthetic — 3 bedrooms",
    ),
    PlanSpec(
        name="lshape",
        model_rel="runs/synth_lshape/observed_model.json",
        gt_rel="tests/fixtures/svg/synthetic/lshape_openings_gt.yaml",
        subtitle="synthetic — L-shape",
    ),
    PlanSpec(
        name="tiny",
        model_rel="runs/synth_tiny/observed_model.json",
        gt_rel="tests/fixtures/svg/synthetic/tiny_openings_gt.yaml",
        subtitle="synthetic — 2 rooms (small plan, 400x300)",
    ),
    PlanSpec(
        name="large",
        model_rel="runs/synth_large/observed_model.json",
        gt_rel="tests/fixtures/svg/synthetic/large_openings_gt.yaml",
        subtitle="synthetic — 10 rooms (1000x800)",
    ),
    PlanSpec(
        name="multistory",
        model_rel="runs/synth_multistory/observed_model.json",
        gt_rel="tests/fixtures/svg/synthetic/multistory_openings_gt.yaml",
        subtitle="synthetic — two disconnected floors (800x1200)",
    ),
]


# ---------- per-plan scoring ----------

@dataclass
class PlanReport:
    spec: PlanSpec
    ok: bool
    reason: str = ""
    result: MatchResult | None = None
    walls: list[dict] | None = None
    dets: list[DetOpening] | None = None
    gts: list[GTOpening] | None = None
    thickness: float = 0.0


def score_plan(spec: PlanSpec, repo_root: Path) -> PlanReport:
    model_path = repo_root / spec.model_rel
    gt_path = repo_root / spec.gt_rel
    if not model_path.exists():
        return PlanReport(spec=spec, ok=False, reason=f"missing observed_model.json at {spec.model_rel}")
    if not gt_path.exists():
        return PlanReport(spec=spec, ok=False, reason=f"missing GT YAML at {spec.gt_rel}")
    try:
        thickness, gts = load_gt(gt_path)
        dets, walls = load_detections(model_path)
        result = match_openings(gts, dets, thickness=thickness)
    except Exception as exc:  # noqa: BLE001 — render-safe fallback
        return PlanReport(spec=spec, ok=False, reason=f"scoring failed: {type(exc).__name__}: {exc}")
    return PlanReport(
        spec=spec,
        ok=True,
        result=result,
        walls=walls,
        dets=dets,
        gts=gts,
        thickness=thickness,
    )


# ---------- SVG rendering ----------

_SVG_W = 560
_SVG_H = 340
_SVG_PAD = 18

_COLOR_WALL = "#8b949e"
_COLOR_TP = "#3fb950"
_COLOR_FP = "#f85149"
_COLOR_FN = "#d29922"
_COLOR_BG = "#0b0f14"


def _bounds_from_points(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _collect_points(report: PlanReport) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for wall in report.walls or []:
        s = wall.get("start") or [0.0, 0.0]
        e = wall.get("end") or [0.0, 0.0]
        pts.append((float(s[0]), float(s[1])))
        pts.append((float(e[0]), float(e[1])))
    if report.result is not None:
        for _gt, det in report.result.tp_pairs:
            pts.append(det.center)
        for det in report.result.fp:
            pts.append(det.center)
        for gt in report.result.fn:
            pts.append(gt.center)
    return pts


def render_plan_svg(report: PlanReport) -> str:
    """Return an inline <svg> string visualizing walls + openings.

    Walls are light gray. TP=green fill, FP=red fill, FN=orange ring at
    the missed GT position. The viewBox is scaled from the walls bbox
    with a small padding; the SVG preserves aspect ratio (meet).
    """
    pts = _collect_points(report)
    if not pts:
        return (
            f'<svg viewBox="0 0 {_SVG_W} {_SVG_H}" xmlns="http://www.w3.org/2000/svg" '
            f'preserveAspectRatio="xMidYMid meet">'
            f'<rect width="100%" height="100%" fill="{_COLOR_BG}"/>'
            f'<text x="50%" y="50%" text-anchor="middle" fill="#8b949e" font-size="14" '
            f'font-family="Segoe UI, sans-serif">(no walls)</text>'
            f"</svg>"
        )

    minx, miny, maxx, maxy = _bounds_from_points(pts)
    span_x = max(1.0, maxx - minx)
    span_y = max(1.0, maxy - miny)
    inner_w = _SVG_W - 2 * _SVG_PAD
    inner_h = _SVG_H - 2 * _SVG_PAD
    scale = min(inner_w / span_x, inner_h / span_y)
    draw_w = span_x * scale
    draw_h = span_y * scale
    tx = _SVG_PAD + (inner_w - draw_w) / 2
    ty = _SVG_PAD + (inner_h - draw_h) / 2

    def P(x: float, y: float) -> tuple[float, float]:
        return (tx + (x - minx) * scale, ty + (y - miny) * scale)

    parts: list[str] = []
    parts.append(
        f'<svg viewBox="0 0 {_SVG_W} {_SVG_H}" xmlns="http://www.w3.org/2000/svg" '
        f'preserveAspectRatio="xMidYMid meet">'
    )
    parts.append(f'<rect width="100%" height="100%" fill="{_COLOR_BG}"/>')

    # Walls
    for wall in report.walls or []:
        s = wall.get("start") or [0.0, 0.0]
        e = wall.get("end") or [0.0, 0.0]
        x1, y1 = P(float(s[0]), float(s[1]))
        x2, y2 = P(float(e[0]), float(e[1]))
        parts.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{_COLOR_WALL}" stroke-width="1.2" stroke-linecap="round"/>'
        )

    # Openings: TP, FP, FN — radius proportional to width, clamped to a sane
    # visual minimum so tiny openings stay clickable on-screen.
    result = report.result
    if result is not None:
        def draw_circle(center: tuple[float, float], width: float, fill: str | None, stroke: str | None) -> str:
            cx, cy = P(*center)
            rr = max(3.0, (float(width) / 2.0) * scale)
            attrs = f'cx="{cx:.2f}" cy="{cy:.2f}" r="{rr:.2f}"'
            fill_attr = f'fill="{fill}"' if fill else 'fill="none"'
            stroke_attr = (
                f'stroke="{stroke}" stroke-width="2"'
                if stroke
                else 'stroke="#e6edf3" stroke-width="1"'
            )
            return f'<circle {attrs} {fill_attr} {stroke_attr}/>'

        for _gt, det in result.tp_pairs:
            parts.append(draw_circle(det.center, det.width, fill=_COLOR_TP, stroke=None))
        for det in result.fp:
            parts.append(draw_circle(det.center, det.width, fill=_COLOR_FP, stroke=None))
        for gt in result.fn:
            # Orange ring only — no fill — so FN stands out against TPs.
            parts.append(draw_circle(gt.center, gt.width, fill=None, stroke=_COLOR_FN))

    parts.append("</svg>")
    return "".join(parts)


# ---------- HTML assembly ----------

def _f1_class(f1: float) -> str:
    if f1 >= 0.90:
        return "ok"
    if f1 >= 0.75:
        return "warn"
    return "bad"


def _f1_label(f1: float) -> str:
    if f1 >= 0.90:
        return "on target"
    if f1 >= 0.75:
        return "below target"
    return "regression"


def _plan_card_html(report: PlanReport) -> str:
    spec = report.spec
    name_html = escape(spec.name)
    subtitle_html = escape(spec.subtitle)

    if not report.ok:
        reason_html = escape(report.reason)
        return (
            f'<article class="plan-card missing">'
            f'<header class="card-head">'
            f'<div class="card-title">'
            f'<h2>{name_html}</h2>'
            f'<p class="sub">{subtitle_html}</p>'
            f'</div>'
            f'<span class="badge warn">not run yet</span>'
            f'</header>'
            f'<div class="empty">'
            f'<p>{reason_html}</p>'
            f'<p class="hint">Run the pipeline to populate this plan.</p>'
            f'</div>'
            f'</article>'
        )

    result = report.result
    assert result is not None
    f1 = result.f1
    cls = _f1_class(f1)
    metrics_text = (
        f"P={result.precision:.2f}  R={result.recall:.2f}  "
        f"TP={result.tp_count}  FP={result.fp_count}  FN={result.fn_count}"
    )
    svg_html = render_plan_svg(report)

    gt_count = len(report.gts or [])
    det_count = len(report.dets or [])

    return (
        f'<article class="plan-card">'
        f'<header class="card-head">'
        f'<div class="card-title">'
        f'<h2>{name_html}</h2>'
        f'<p class="sub">{subtitle_html}</p>'
        f'</div>'
        f'<div class="card-score">'
        f'<span class="badge {cls}">{f1:.3f}</span>'
        f'<span class="badge-sub">F1 · {_f1_label(f1)}</span>'
        f'</div>'
        f'</header>'
        f'<div class="metric-row">{escape(metrics_text)}</div>'
        f'<figure class="plan-svg">{svg_html}</figure>'
        f'<details>'
        f'<summary>Metrics detail</summary>'
        f'<dl class="kv">'
        f'<dt>Precision</dt><dd>{result.precision:.3f}</dd>'
        f'<dt>Recall</dt><dd>{result.recall:.3f}</dd>'
        f'<dt>F1</dt><dd>{result.f1:.3f}</dd>'
        f'<dt>TP</dt><dd>{result.tp_count}</dd>'
        f'<dt>FP</dt><dd>{result.fp_count}</dd>'
        f'<dt>FN</dt><dd>{result.fn_count}</dd>'
        f'<dt>GT openings</dt><dd>{gt_count}</dd>'
        f'<dt>Detections</dt><dd>{det_count}</dd>'
        f'<dt>Thickness</dt><dd>{report.thickness:.2f} px</dd>'
        f'<dt>Model</dt><dd><code>{escape(spec.model_rel)}</code></dd>'
        f'<dt>GT</dt><dd><code>{escape(spec.gt_rel)}</code></dd>'
        f'</dl>'
        f'</details>'
        f'</article>'
    )


def _summary_html(reports: list[PlanReport]) -> str:
    scored = [r for r in reports if r.ok and r.result is not None]
    skipped = [r for r in reports if not r.ok]
    total = len(reports)
    mean_f1 = (
        sum(r.result.f1 for r in scored) / len(scored)
        if scored
        else 0.0
    )
    passing = sum(1 for r in scored if r.result.f1 >= 0.90)
    mean_cls = _f1_class(mean_f1) if scored else "warn"

    return (
        f'<section class="summary">'
        f'<div class="stat"><span class="stat-label">mean F1</span>'
        f'<span class="stat-value f1-{mean_cls}">{mean_f1:.3f}</span></div>'
        f'<div class="stat"><span class="stat-label">passing (F1 ≥ 0.90)</span>'
        f'<span class="stat-value">{passing} / {len(scored)}</span></div>'
        f'<div class="stat"><span class="stat-label">total plans</span>'
        f'<span class="stat-value">{total}</span></div>'
        f'<div class="stat"><span class="stat-label">skipped</span>'
        f'<span class="stat-value">{len(skipped)}</span></div>'
        f'</section>'
    )


_CSS = """
:root {
  --bg: #0e1116;
  --bg-card: #161b22;
  --bg-elev: #1f242c;
  --border: #30363d;
  --text: #e6edf3;
  --text-mute: #8b949e;
  --accent: #58a6ff;
  --good: #3fb950;
  --bad: #f85149;
  --warn: #d29922;
  --code-bg: #0b0f14;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}
.wrap { max-width: 1280px; margin: 0 auto; padding: 40px 28px 96px; }

header.hero {
  border-bottom: 1px solid var(--border);
  padding-bottom: 24px;
  margin-bottom: 32px;
}
header.hero h1 {
  font-size: 34px;
  margin: 0 0 8px;
  letter-spacing: -0.02em;
}
header.hero .sub {
  color: var(--text-mute);
  font-size: 15px;
  margin: 0;
}
header.hero .meta {
  margin-top: 14px;
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  font-size: 12.5px;
  color: var(--text-mute);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
header.hero .meta code {
  background: var(--code-bg);
  padding: 2px 6px;
  border-radius: 3px;
  color: var(--accent);
}

section.summary {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin: 0 0 36px;
}
section.summary .stat {
  flex: 1 1 180px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 20px;
}
.stat-label {
  display: block;
  color: var(--text-mute);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 6px;
}
.stat-value {
  display: block;
  font-size: 26px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.f1-ok { color: var(--good); }
.f1-warn { color: var(--warn); }
.f1-bad { color: var(--bad); }

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}
@media (max-width: 960px) {
  .grid { grid-template-columns: 1fr; }
}

.plan-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.plan-card.missing { opacity: 0.85; border-style: dashed; }

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.card-title h2 {
  margin: 0;
  font-size: 20px;
  letter-spacing: -0.01em;
}
.card-title .sub {
  margin: 2px 0 0;
  color: var(--text-mute);
  font-size: 13px;
}
.card-score {
  text-align: right;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}
.badge {
  display: inline-block;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 22px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 8px;
  letter-spacing: -0.01em;
  line-height: 1;
}
.badge.ok   { background: rgba(63, 185, 80, 0.15);  color: var(--good); border: 1px solid rgba(63, 185, 80, 0.4); }
.badge.warn { background: rgba(210, 153, 34, 0.15); color: var(--warn); border: 1px solid rgba(210, 153, 34, 0.4); }
.badge.bad  { background: rgba(248, 81, 73, 0.15);  color: var(--bad);  border: 1px solid rgba(248, 81, 73, 0.4); }
.badge-sub {
  font-size: 11px;
  color: var(--text-mute);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.metric-row {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
  color: var(--text-mute);
  background: var(--code-bg);
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
}

figure.plan-svg {
  margin: 0;
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
figure.plan-svg svg {
  display: block;
  width: 100%;
  height: auto;
}

.empty {
  padding: 32px 16px;
  text-align: center;
  color: var(--text-mute);
  background: var(--code-bg);
  border: 1px dashed var(--border);
  border-radius: 8px;
}
.empty p { margin: 0; }
.empty p + p.hint {
  margin-top: 6px;
  font-size: 12px;
  font-style: italic;
}

details {
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0 14px;
}
details summary {
  cursor: pointer;
  padding: 10px 0;
  font-size: 13px;
  color: var(--text-mute);
  user-select: none;
}
details summary:hover { color: var(--accent); }
details[open] summary { border-bottom: 1px solid var(--border); margin-bottom: 10px; }
dl.kv {
  display: grid;
  grid-template-columns: 130px 1fr;
  gap: 4px 16px;
  font-size: 13px;
  margin: 0 0 12px;
}
dl.kv dt { color: var(--text-mute); }
dl.kv dd { margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
dl.kv code {
  background: var(--code-bg);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
  color: var(--accent);
}

footer.foot {
  margin-top: 48px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
  color: var(--text-mute);
  font-size: 12.5px;
}
footer.foot code {
  background: var(--code-bg);
  padding: 1px 6px;
  border-radius: 3px;
  color: var(--accent);
  font-size: 12px;
}
.legend {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin: 10px 0 0;
}
.legend .li { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; }
.swatch {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: inline-block;
}
.swatch.wall { border-radius: 2px; background: #8b949e; height: 2px; width: 18px; }
.swatch.tp   { background: #3fb950; }
.swatch.fp   { background: #f85149; }
.swatch.fn   { background: transparent; border: 2px solid #d29922; }
""".strip()


def build_html(reports: list[PlanReport], generated_at: datetime) -> str:
    cards = "\n".join(_plan_card_html(r) for r in reports)
    summary = _summary_html(reports)
    stamp = generated_at.strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>F1 Dashboard — openings-refine</title>
<style>
{_CSS}
</style>
</head>
<body>
<div class="wrap">

<header class="hero">
  <h1>F1 Dashboard</h1>
  <p class="sub">Openings detection — precision / recall / F1 across all known plans.</p>
  <div class="meta">
    <span>Generated: <code>{escape(stamp)}</code></span>
    <span>Scorer: <code>scripts/score_openings.py</code></span>
    <span>Branch: <code>feat/svg-ingest-openings-refine</code></span>
    <span>Target: <code>F1 &ge; 0.90</code></span>
  </div>
</header>

{summary}

<div class="grid">
{cards}
</div>

<footer class="foot">
  <p>Generated by <code>scripts/generate_f1_dashboard.py</code> from the openings-refine harness.</p>
  <div class="legend">
    <span class="li"><span class="swatch wall"></span>walls</span>
    <span class="li"><span class="swatch tp"></span>TP (matched)</span>
    <span class="li"><span class="swatch fp"></span>FP (false positive)</span>
    <span class="li"><span class="swatch fn"></span>FN (missed GT)</span>
  </div>
</footer>

</div>
</body>
</html>
"""


# ---------- public entry ----------

def generate_dashboard(
    out: Path,
    repo_root: Path | None = None,
    plans: list[PlanSpec] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Score every plan and write the HTML dashboard to ``out``.

    Returns a small summary dict with keys: ``total``, ``scored``,
    ``skipped``, ``mean_f1``, ``passing``, ``out_path``, ``size_bytes``.
    """
    root = repo_root or REPO_ROOT
    plan_list = plans or PLANS
    reports = [score_plan(p, root) for p in plan_list]
    html = build_html(reports, now or datetime.now())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    scored = [r for r in reports if r.ok and r.result is not None]
    mean_f1 = sum(r.result.f1 for r in scored) / len(scored) if scored else 0.0
    passing = sum(1 for r in scored if r.result.f1 >= 0.90)
    return {
        "total": len(reports),
        "scored": len(scored),
        "skipped": len(reports) - len(scored),
        "mean_f1": mean_f1,
        "passing": passing,
        "out_path": str(out),
        "size_bytes": out.stat().st_size,
        "reports": [
            {
                "name": r.spec.name,
                "ok": r.ok,
                "reason": r.reason,
                "f1": (r.result.f1 if (r.ok and r.result is not None) else None),
                "tp": (r.result.tp_count if (r.ok and r.result is not None) else None),
                "fp": (r.result.fp_count if (r.ok and r.result is not None) else None),
                "fn": (r.result.fn_count if (r.ok and r.result is not None) else None),
            }
            for r in reports
        ],
    }


# ---------- CLI ----------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate F1 dashboard HTML for all plans.")
    parser.add_argument("--out", required=True, type=Path,
                        help="output HTML file (e.g. docs/F1-DASHBOARD.html)")
    args = parser.parse_args(argv)

    info = generate_dashboard(args.out)
    print(
        f"wrote {info['out_path']} "
        f"({info['size_bytes']} bytes, "
        f"scored {info['scored']}/{info['total']}, "
        f"mean F1 = {info['mean_f1']:.3f}, "
        f"passing {info['passing']}/{info['scored']})"
    )
    for entry in info["reports"]:
        if entry["ok"]:
            print(
                f"  {entry['name']}: F1={entry['f1']:.3f} "
                f"TP={entry['tp']} FP={entry['fp']} FN={entry['fn']}"
            )
        else:
            print(f"  {entry['name']}: SKIPPED — {entry['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
