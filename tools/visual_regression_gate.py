#!/usr/bin/env python3
"""Visual-regression gate — PDF (ground truth) x BEFORE x AFTER.

A geometry change is only "improvement" if AFTER looks MORE like the PDF as a
WHOLE plan, not on one local metric. This tool builds the mandatory 3-way
montage (PDF | BEFORE | AFTER, for top and iso) and writes a verdict scaffold
with the hard FAIL checklist. A human/agent fills the verdict by LOOKING —
auto "looks like PDF" judgement is exactly what the vision oracle was proven
unable to do, so it is NOT trusted here.

Verdict must be IMPROVED / SAME / WORSE. If SAME or WORSE, the patch must be
reverted or adjusted immediately. pytest / counts / exit-0 are NOT evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

FAIL_CHECKLIST = [
    "doors disappear or become useless lines",
    "gray walls/blocks invade rooms",
    "colored floors leak / do not respect walls",
    "openings become less legible",
    "model is more blocky than the baseline",
    "plan is less recognizable vs the PDF",
]


def _label(draw, x, y, text, color):
    draw.rectangle([x, y, x + 8 * len(text) + 10, y + 20], fill=(255, 255, 255))
    draw.text((x + 4, y + 4), text, fill=color)


def build_montage(pdf_png: Path, before_top: Path, before_iso: Path,
                  after_top: Path, after_iso: Path, out_png: Path) -> None:
    from PIL import Image, ImageDraw
    def load(p): return Image.open(p).convert("RGB")
    pdf = load(pdf_png)
    bt, bi, at, ai = load(before_top), load(before_iso), load(after_top), load(after_iso)

    COLW = 520
    def fit(im):
        return im.resize((COLW, int(im.height * COLW / im.width)))
    pdf, bt, bi, at, ai = [fit(x) for x in (pdf, bt, bi, at, ai)]
    lab = 24
    rowh_iso = max(bi.height, ai.height, pdf.height)
    rowh_top = max(bt.height, at.height, pdf.height)
    pad = 8
    W = COLW * 3 + pad * 4
    H = lab + (lab + rowh_iso) + (lab + rowh_top) + pad * 4
    canvas = Image.new("RGB", (W, H), (235, 235, 235))
    d = ImageDraw.Draw(canvas)
    d.text((pad, 6), "VISUAL REGRESSION GATE — PDF (truth) | BEFORE | AFTER", fill=(0, 0, 0))

    y = lab + pad
    # ISO row
    cols = [("PDF", pdf, (0, 0, 0)), ("BEFORE", bi, (180, 0, 0)), ("AFTER", ai, (0, 110, 0))]
    for i, (name, im, col) in enumerate(cols):
        x = pad + i * (COLW + pad)
        d.text((x, y), f"{name} (iso/plan)", fill=col)
        canvas.paste(im, (x, y + lab))
    y += lab + rowh_iso + pad
    # TOP row
    cols = [("PDF", pdf, (0, 0, 0)), ("BEFORE", bt, (180, 0, 0)), ("AFTER", at, (0, 110, 0))]
    for i, (name, im, col) in enumerate(cols):
        x = pad + i * (COLW + pad)
        d.text((x, y), f"{name} (top)", fill=col)
        canvas.paste(im, (x, y + lab))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_png)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", default="planta_74")
    ap.add_argument("--pdf", type=Path)
    ap.add_argument("--before-top", type=Path)
    ap.add_argument("--before-iso", type=Path)
    ap.add_argument("--after-top", type=Path)
    ap.add_argument("--after-iso", type=Path)
    ap.add_argument("--label", default="change")
    args = ap.parse_args()

    runs = REPO_ROOT / "runs" / args.fixture
    pdf = args.pdf or (runs / "pdf_plan_region.png")
    bt = args.before_top or (runs / "before_top.png")
    bi = args.before_iso or (runs / "before_iso.png")
    at = args.after_top or (runs / "model_top.png")
    ai = args.after_iso or (runs / "model_iso.png")
    missing = [str(p) for p in (pdf, bt, bi, at, ai) if not p.exists()]
    if missing:
        print(f"[visual-gate] MISSING inputs: {missing}")
        return 2

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = REPO_ROOT / "artifacts" / "review" / args.fixture / f"visual_regression_{ts}"
    montage = out_dir / "montage_pdf_before_after.png"
    build_montage(pdf, bt, bi, at, ai, montage)

    verdict = [
        f"# Visual regression gate — {args.fixture} ({args.label})",
        f"\nGenerated: {ts}",
        f"\nMontage: `{montage.relative_to(REPO_ROOT)}`",
        "\n## Hard FAIL checklist (any True => WORSE)\n",
    ]
    for c in FAIL_CHECKLIST:
        verdict.append(f"- [ ] {c}")
    verdict += [
        "\n## Verdict (fill by LOOKING — not pytest/counts/exit-0)\n",
        "VERDICT: <IMPROVED | SAME | WORSE>",
        "REASON: <one line, whole-plan vs PDF>",
        "ACTION: <promote | revert | adjust>  (SAME or WORSE => revert/adjust now)",
    ]
    (out_dir / "verdict.md").write_text("\n".join(verdict) + "\n", encoding="utf-8")
    print(f"[visual-gate] montage: {montage.relative_to(REPO_ROOT)}")
    print(f"[visual-gate] verdict scaffold: {(out_dir / 'verdict.md').relative_to(REPO_ROOT)}")
    print("[visual-gate] LOOK at the montage and classify IMPROVED/SAME/WORSE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
