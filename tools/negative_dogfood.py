#!/usr/bin/env python3
"""FP-030 negative dogfood — prove the visual oracle discriminates a REAL defect.

The `ollama_vision` oracle returns PASS readily and has so far been shown to
FAIL only on *synthetic* fixtures (`fixtures/visual_oracle_negative/`). This
harness injects ONE deterministic, reproducible defect into the REAL
`planta_74` render — erasing a segment of the top exterior wall, i.e. a
"missing wall" gap — and asks the oracle to judge the clean render vs the
corrupted render.

Method (decided with GPT peer review, trigger final_fail_non_obvious_fix):
a first single-image probe saturated the oracle at FAIL even on the clean
baseline (the model is over-pessimistic / hallucinates without the full input
set), so the conclusive test mirrors PRODUCTION inputs:

  - Both runs send the same set the real pipeline sends: top + iso +
    side_by_side(PDF) + geometry context.
  - ONLY the top render (and the side-by-side built from it) is corrupted.
  - PRIMARY criterion: clean is PASS/WARN AND corrupted is rated strictly
    worse (top_level).
  - SECONDARY (predeclared) criterion: the corrupted run introduces a NEW
    localized missing-wall/gap finding (type + region) that the clean run
    does not.
  - If the clean baseline still FAILs, the result is INCONCLUSIVE (oracle not
    stable enough), NOT a pass. No verdict is ever fabricated.

Constraints honored: no SketchUp build, no geometry invention, no auto-fix.

Usage:
    python -m tools.negative_dogfood --fixture planta_74 \\
        --out artifacts/review/planta_74/negative_dogfood_<ts>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from tools.oracle_providers import OracleRequest, get_provider
from tools.run_skp_visual_review import _VERDICT_RANK

REPO_ROOT = Path(__file__).resolve().parent.parent

# Deterministic corruption recipe per fixture. Each rect was verified (via
# pixel probe + tests/test_negative_dogfood.py) to land on a dark wall band,
# and each ref_point on light background, so filling rect with the background
# color erases the wall -> a "missing wall" gap. rect = (x0, y0, x1, y1).
CORRUPTION_RECIPES: dict[str, dict] = {
    "planta_74": {
        "op": "erase_top_exterior_wall_segment",
        "defect_class": "missing_wall_continuation",
        "source_render": "planta_74_top.png",
        # re-pinned for the canonical_20260531 deterministic-camera render
        # (1600x1200): top perimeter wall band at y~200-224. center (700,212)
        # avg 94 (dark wall, 83% rect coverage); ref_point avg 193 (bg).
        "rect": (500, 200, 900, 224),
        "ref_point": (1300, 30),
    },
}

# Predeclared finding-level criterion (secondary). A finding counts as a
# "localized missing-wall / gap" defect if its type is a gap-class type AND it
# references the corrupted region (top/center) or describes a gap/opening.
_GAP_TYPES = {
    "missing_wall_continuation", "wall_stub", "missing_wall", "missing_enclosure",
    "floor_leak", "full_height_window_void", "global_visual_fail",
}
_REGION_KEYWORDS = ("top", "center", "centre", "upper", "middle")
_GAP_EVIDENCE_KEYWORDS = (
    "gap", "not fully enclosed", "missing", "not properly connected",
    "open ", "opening", "hole", "enclos", "incomplete", "disconnect",
)


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def corrupt_render(
    src_png: Path, out_png: Path, rect: tuple, ref_point: tuple,
) -> dict:
    """Erase ``rect`` by filling it with the color sampled at ``ref_point``.

    Deterministic: identical (src + rect + ref_point) -> identical output
    bytes. Returns metadata incl. before/after SHA-256.
    """
    from PIL import Image, ImageDraw

    with Image.open(src_png) as im:
        im = im.convert("RGB")
        w, h = im.size
        x0, y0, x1, y1 = rect
        if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
            raise ValueError(f"rect {rect} out of bounds for {w}x{h}")
        rx, ry = ref_point
        if not (0 <= rx < w and 0 <= ry < h):
            raise ValueError(f"ref_point {ref_point} out of bounds for {w}x{h}")
        fill = im.getpixel((rx, ry))
        ImageDraw.Draw(im).rectangle([x0, y0, x1 - 1, y1 - 1], fill=fill)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        im.save(out_png, format="PNG")

    return {
        "rect": list(rect),
        "ref_point": list(ref_point),
        "fill_rgb": list(fill),
        "image_size": [w, h],
        "src_sha256": _sha256(src_png),
        "out_sha256": _sha256(out_png),
    }


def discrimination_decision(clean_verdict: str, corrupted_verdict: str) -> dict:
    """Did the oracle rate the corrupted render WORSE than the clean one?"""
    cr = _VERDICT_RANK.get(clean_verdict, -1)
    kr = _VERDICT_RANK.get(corrupted_verdict, -1)
    return {
        "clean_verdict": clean_verdict,
        "corrupted_verdict": corrupted_verdict,
        "discriminated": kr > cr,
    }


def localized_gap_findings(normalized: dict | None) -> list[dict]:
    """Return findings that look like a localized missing-wall / gap defect.

    Predeclared (before running) so the secondary criterion is objective:
    type in _GAP_TYPES AND (location mentions the top/center region OR
    evidence describes a gap/opening/incomplete enclosure).
    """
    out: list[dict] = []
    for f in (normalized or {}).get("findings", []):
        if not isinstance(f, dict):
            continue
        t = (f.get("type") or "").lower()
        loc = (f.get("location") or "").lower()
        ev = (f.get("evidence") or "").lower()
        if t not in _GAP_TYPES:
            continue
        if any(k in loc for k in _REGION_KEYWORDS) or any(
            k in ev for k in _GAP_EVIDENCE_KEYWORDS
        ):
            out.append(f)
    return out


def _oracle_context(geom_path: Path) -> dict:
    """Same context shape the real pipeline sends (scalar-only stats)."""
    if not geom_path.exists():
        return {}
    rep = json.loads(geom_path.read_text(encoding="utf-8"))
    stats = rep.get("shell_stats_from_python", {})
    return {
        "gates_self_check": rep.get("gates_self_check", {}),
        "shell_stats_from_python": {
            k: v for k, v in stats.items() if not isinstance(v, (list, dict))
        },
    }


def _compose_sxs(pdf: Path, top: Path, iso: Path, out: Path) -> Path | None:
    try:
        from tools.compose_side_by_side import compose_to_file
        compose_to_file(pdf_path=pdf, top_path=top, iso_path=iso, out_path=out)
        return out if out.exists() else None
    except Exception as e:  # composer is best-effort; oracle still runs on 2 imgs
        print(f"[negative-dogfood] side_by_side compose failed: {e!r}")
        return None


def _run_oracle(images: list[Path], context: dict, out_dir: Path,
                model: str | None) -> dict:
    provider = get_provider("ollama_vision")
    if model:
        provider.model = model  # type: ignore[attr-defined]
    req = OracleRequest(
        prompt="Review these architectural floor-plan renders for fidelity defects.",
        image_paths=images,
        context=context,
        expected_schema={"schema_version": "visual_findings.v1"},
    )
    resp = provider.call(req, out_dir=out_dir)
    verdict = None
    if resp.status == "ok" and resp.normalized_findings:
        verdict = resp.normalized_findings.get("top_level_verdict")
    return {
        "status": resp.status,
        "detail": resp.detail,
        "verdict": verdict,
        "images": [p.name for p in images],
        "normalized": resp.normalized_findings,
    }


def run(fixture: str, out_dir: Path, model: str | None = None) -> dict:
    if fixture not in CORRUPTION_RECIPES:
        raise ValueError(
            f"no corruption recipe for fixture {fixture!r}; "
            f"have: {sorted(CORRUPTION_RECIPES)}"
        )
    recipe = CORRUPTION_RECIPES[fixture]
    art = REPO_ROOT / "artifacts" / fixture
    src_top = art / recipe["source_render"]
    src_iso = art / f"{fixture}_iso.png"
    geom = art / "geometry_report.json"
    pdf = REPO_ROOT / f"{fixture}.pdf"
    if not src_top.exists():
        raise FileNotFoundError(f"source render not found: {src_top}")

    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- build clean + corrupted production-parity image sets ----
    clean_top = out_dir / "clean_top.png"
    shutil.copy2(src_top, clean_top)
    iso_ok = src_iso.exists()
    clean_iso = out_dir / "clean_iso.png"
    if iso_ok:
        shutil.copy2(src_iso, clean_iso)

    corrupted_top = out_dir / "corrupted_top.png"
    corr_meta = corrupt_render(
        src_top, corrupted_top, tuple(recipe["rect"]), tuple(recipe["ref_point"]),
    )

    iso_for_sxs = clean_iso if iso_ok else clean_top
    clean_sxs = (
        _compose_sxs(pdf, clean_top, iso_for_sxs, out_dir / "clean_side_by_side.png")
        if pdf.exists() else None
    )
    corrupted_sxs = (
        _compose_sxs(pdf, corrupted_top, iso_for_sxs,
                     out_dir / "corrupted_side_by_side.png")
        if pdf.exists() else None
    )

    context = _oracle_context(geom)
    clean_imgs = [p for p in (clean_top, clean_iso if iso_ok else None, clean_sxs) if p]
    corrupted_imgs = [
        p for p in (corrupted_top, clean_iso if iso_ok else None, corrupted_sxs) if p
    ]

    clean_res = _run_oracle(clean_imgs, context, out_dir / "clean", model)
    corrupted_res = _run_oracle(corrupted_imgs, context, out_dir / "corrupted", model)

    # ---- A+B criteria ----
    conclusive = clean_res["status"] == "ok" and corrupted_res["status"] == "ok"
    clean_v, corr_v = clean_res["verdict"], corrupted_res["verdict"]
    top_decision = discrimination_decision(
        clean_v or clean_res["status"], corr_v or corrupted_res["status"],
    )
    clean_gaps = localized_gap_findings(clean_res["normalized"])
    corr_gaps = localized_gap_findings(corrupted_res["normalized"])

    primary = bool(
        conclusive
        and clean_v in ("PASS", "WARN", "WARN_documented")
        and top_decision["discriminated"]
    )
    secondary = bool(conclusive and len(corr_gaps) > len(clean_gaps))

    if not conclusive:
        result = "INCONCLUSIVE_ORACLE_ERROR"
    elif clean_v == "FAIL":
        result = "INCONCLUSIVE_CLEAN_SATURATED"
    elif primary or secondary:
        result = "DISCRIMINATED"
    else:
        result = "NOT_DISCRIMINATED"

    report = {
        "schema_version": "negative_dogfood.v2",
        "fixture": fixture,
        "timestamp": _now_utc_iso(),
        "method": "production-parity (top+iso+side_by_side+context); corrupt top only",
        "recipe": recipe,
        "corruption": corr_meta,
        "clean_oracle": clean_res,
        "corrupted_oracle": corrupted_res,
        "conclusive": conclusive,
        "criteria": {
            "primary_top_level": top_decision,
            "primary_pass": primary,
            "secondary_finding_level": {
                "clean_gap_findings": len(clean_gaps),
                "corrupted_gap_findings": len(corr_gaps),
                "new_localized_gap": secondary,
            },
        },
        "result": result,
    }
    (out_dir / "discrimination_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )

    blurb = {
        "DISCRIMINATED": (
            "> The oracle caught the injected missing-wall defect on the REAL "
            "fixture (worse top-level verdict and/or a new localized gap "
            "finding the clean run lacked)."
        ),
        "NOT_DISCRIMINATED": (
            "> Clean was acceptable but the oracle did NOT register the "
            "corrupted render as worse. Honest finding: on this defect the "
            "oracle is not discriminative. No verdict fabricated."
        ),
        "INCONCLUSIVE_CLEAN_SATURATED": (
            "> The oracle FAILed even the clean baseline, so it is not stable "
            "enough here to prove discrimination. Honest INCONCLUSIVE — not a "
            "pass. (Real finding about oracle robustness.)"
        ),
        "INCONCLUSIVE_ORACLE_ERROR": (
            "> The oracle did not return a usable verdict on one/both runs."
        ),
    }[result]

    summary = [
        f"# Negative dogfood — `{fixture}` (production-parity)",
        "",
        f"## Generated: {report['timestamp']}",
        "",
        f"**Defect injected:** `{recipe['op']}` ({recipe['defect_class']}) on "
        f"`{recipe['source_render']}`, rect={recipe['rect']} filled with "
        f"rgb={corr_meta['fill_rgb']}. Only the top render (and the "
        f"side-by-side built from it) is corrupted; iso + PDF + geometry "
        f"context are identical between runs.",
        "",
        "## Oracle verdicts (ollama_vision, full input set)",
        "",
        "| Render set | status | top_level | localized gap findings |",
        "|---|---|---|---|",
        f"| clean | `{clean_res['status']}` | `{clean_v}` | {len(clean_gaps)} |",
        f"| corrupted | `{corrupted_res['status']}` | `{corr_v}` | {len(corr_gaps)} |",
        "",
        f"## Result: **{result}**",
        "",
        f"- primary (top-level worse, clean not already FAIL): **{primary}**",
        f"- secondary (new localized gap finding): **{secondary}**",
        "",
        blurb,
        "",
        "## Evidence",
        "",
        "- `clean_top.png`, `corrupted_top.png`, `*_side_by_side.png`",
        "- `clean/`, `corrupted/` (oracle raw/normalized or request package)",
        "- `discrimination_report.json`",
    ]
    (out_dir / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixture", default="planta_74")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default=None, help="override ollama vision model")
    args = ap.parse_args()

    report = run(args.fixture, Path(args.out), model=args.model)
    c, k = report["clean_oracle"], report["corrupted_oracle"]
    print(f"[negative-dogfood] fixture={report['fixture']} result={report['result']}")
    print(
        f"[negative-dogfood] clean={c['verdict']}({c['status']}) "
        f"corrupted={k['verdict']}({k['status']}) "
        f"| primary={report['criteria']['primary_pass']} "
        f"secondary={report['criteria']['secondary_finding_level']['new_localized_gap']}"
    )
    print(f"[negative-dogfood] out={args.out}")
    return 0  # any honest outcome is a valid exit


if __name__ == "__main__":
    raise SystemExit(main())
