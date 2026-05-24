"""Side-by-side render: a user-painted floor plan vs the pipeline overlay.

Originally hardcoded ``C:/Users/felip_local/Documents/paredes.png`` and
``runs/proto/p9_v3_run/overlay_semantic.png``; refactored 2026-05-08 to
take CLI args so it can be ruff-checked and reused across machines.

Example::

    python render_sidebyside.py \
        --painted paredes.png \
        --overlay runs/proto/p9_v3_run/overlay_semantic.png \
        --output runs/proto/p9_v3_run/sidebyside.png

    # default crop matches the legacy invocation (apartment region of paredes.png):
    python render_sidebyside.py --painted paredes.png \
        --overlay runs/proto/p9_v3_run/overlay_semantic.png \
        --output runs/proto/p9_v3_run/sidebyside.png \
        --crop 80,120,1140,900

Optional ``--consensus`` lets the script log the pairing into the
PNG history manifest so the external validator microservice can
score it. Set ``--no-history`` (or env ``PNG_HISTORY_DISABLE``) to
skip that step.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _parse_crop(spec: str) -> tuple[int, int, int, int]:
    parts = [p.strip() for p in spec.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            f"--crop must be 'x1,y1,x2,y2' (4 ints), got: {spec!r}"
        )
    try:
        x1, y1, x2, y2 = (int(p) for p in parts)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"--crop values must be ints, got: {spec!r}"
        ) from e
    return x1, y1, x2, y2


def main(args: argparse.Namespace) -> int:
    painted = Path(args.painted)
    overlay = Path(args.overlay)
    out = Path(args.output)

    if not painted.exists():
        print(f"ERROR: --painted not found: {painted}", file=sys.stderr)
        return 2
    if not overlay.exists():
        print(f"ERROR: --overlay not found: {overlay}", file=sys.stderr)
        return 2

    a_full = Image.open(painted).convert("RGB")
    if args.crop is not None:
        a = a_full.crop(args.crop)
    else:
        a = a_full
    b = Image.open(overlay).convert("RGB")

    # normalise height
    h = args.height
    a2 = a.resize((int(a.width * h / a.height), h))
    b2 = b.resize((int(b.width * h / b.height), h))

    gap = args.gap
    canvas_w = a2.width + b2.width + gap
    canvas = Image.new("RGB", (canvas_w, h + 50), "white")
    canvas.paste(a2, (0, 50))
    canvas.paste(b2, (a2.width + gap, 50))

    d = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    d.text((10, 12), args.left_label, fill="black", font=font)
    d.text((a2.width + gap + 10, 12), args.right_label, fill="black", font=font)

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    print(f"wrote {out}  {canvas.size}")

    skip_history = args.no_history or os.environ.get("PNG_HISTORY_DISABLE")
    if not skip_history:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
            from png_history import register

            source: dict[str, Path] = {}
            if args.consensus is not None:
                source["consensus"] = Path(args.consensus)
            register(
                out,
                kind="sidebyside",
                source=source,
                generator="render_sidebyside.py",
                params={"size": list(canvas.size)},
            )
        except Exception as e:
            print(f"[png_history skipped] {e}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Render a side-by-side comparison of a user-painted floor plan "
            "and the pipeline's semantic overlay. Optionally records the "
            "pairing in the PNG history manifest."
        ),
    )
    p.add_argument(
        "--painted",
        required=True,
        help="Path to the user-painted reference PNG (left panel).",
    )
    p.add_argument(
        "--overlay",
        required=True,
        help=(
            "Path to the pipeline's semantic overlay PNG (right panel). "
            "Typically runs/proto/<run>/overlay_semantic.png."
        ),
    )
    p.add_argument(
        "--output",
        required=True,
        help="Output PNG path for the side-by-side render.",
    )
    p.add_argument(
        "--crop",
        type=_parse_crop,
        default=None,
        help=(
            "Optional crop (x1,y1,x2,y2 ints) applied to --painted before "
            "resizing. Use to strip legend/footer from a scanned plan. "
            "Legacy default for paredes.png was '80,120,1140,900'."
        ),
    )
    p.add_argument(
        "--height",
        type=int,
        default=700,
        help="Canvas row height (px) used to normalise both panels. Default: 700",
    )
    p.add_argument(
        "--gap",
        type=int,
        default=20,
        help="Horizontal gap (px) between the two panels. Default: 20",
    )
    p.add_argument(
        "--left-label",
        default="VOCE PINTOU",
        help="Banner above the painted panel. Default: 'VOCE PINTOU'.",
    )
    p.add_argument(
        "--right-label",
        default="PIPELINE EXTRAIU (rosa/azul=rooms detectados)",
        help="Banner above the pipeline overlay panel.",
    )
    p.add_argument(
        "--consensus",
        default=None,
        help=(
            "Optional path to observed_model.json for the run; "
            "logged in the PNG history manifest as the source consensus."
        ),
    )
    p.add_argument(
        "--no-history",
        action="store_true",
        help=(
            "Skip the PNG history manifest registration. "
            "Equivalent to setting PNG_HISTORY_DISABLE=1 in the environment."
        ),
    )
    return p


if __name__ == "__main__":
    sys.exit(main(build_parser().parse_args()))
