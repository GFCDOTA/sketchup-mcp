from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence

from model.pipeline import PipelineError, run_pdf_pipeline


def _print_summary(observed_model: dict, output_dir: Path) -> None:
    source = observed_model["source"]
    bounds_pages = observed_model["bounds"]["pages"]
    walls = observed_model["walls"]
    junctions = observed_model["junctions"]
    rooms = observed_model["rooms"]
    warnings = observed_model["warnings"]
    scores = observed_model["scores"]

    sha = source["sha256"]
    sha_display = (sha[:12] + "...") if sha else "n/a"

    print(f"run_id:    {observed_model['run_id']}")
    print(
        f"source:    type={source['source_type']} "
        f"filename={source['filename']} "
        f"pages={source['page_count']} "
        f"sha256={sha_display}"
    )
    print(f"walls:     {len(walls)}")
    per_page_walls = Counter(w["page_index"] for w in walls)
    for page_index in sorted(per_page_walls):
        print(f"  page {page_index}: {per_page_walls[page_index]}")
    print(f"junctions: {len(junctions)}")
    kinds = Counter(j["kind"] for j in junctions)
    for kind in sorted(kinds):
        print(f"  {kind}: {kinds[kind]}")
    print(f"rooms:     {len(rooms)}")
    for room in rooms:
        print(f"  {room['room_id']} area={room['area']:.1f}")
    print(
        "scores:    "
        f"geometry={scores['geometry']} "
        f"topology={scores['topology']} "
        f"rooms={scores['rooms']}"
    )
    print("bounds:")
    if not bounds_pages:
        print("  (no walls detected)")
    for page in bounds_pages:
        print(
            f"  page {page['page_index']}: "
            f"x=[{page['min_x']}, {page['max_x']}] "
            f"y=[{page['min_y']}, {page['max_y']}]"
        )
    print("warnings:")
    if not warnings:
        print("  (none)")
    for warning in warnings:
        print(f"  {warning}")
    print(f"artifacts: {output_dir}")


def cmd_extract(args: argparse.Namespace) -> int:
    pdf_path = Path(args.pdf)
    if not pdf_path.is_file():
        print(f"error: PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    output_dir = Path(args.out) if args.out else Path("runs") / pdf_path.stem
    try:
        result = run_pdf_pipeline(
            pdf_bytes=pdf_path.read_bytes(),
            filename=pdf_path.name,
            output_dir=output_dir,
        )
    except PipelineError as exc:
        print(f"error: pipeline failed: {exc}", file=sys.stderr)
        return 3

    _print_summary(result.observed_model, result.output_dir)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from api.app import app

    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plan-extract-v2",
        description="PDF plan extractor. Emits observed_model.json plus debug artifacts.",
    )
    subs = parser.add_subparsers(dest="command", required=True)

    p_extract = subs.add_parser(
        "extract",
        help="Run the pipeline on a PDF and write artifacts.",
        description="Run the pipeline on a PDF and write observed_model.json plus debug artifacts.",
    )
    p_extract.add_argument("pdf", help="Path to the input PDF.")
    p_extract.add_argument(
        "--out",
        default=None,
        help="Output directory. Default: runs/<pdf stem>.",
    )
    p_extract.set_defaults(func=cmd_extract)

    p_serve = subs.add_parser(
        "serve",
        help="Start the HTTP API.",
        description="Start the FastAPI server exposing POST /extract.",
    )
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
