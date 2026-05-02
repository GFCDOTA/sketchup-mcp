from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


class ExtractError(Exception):
    """Raised when the extract_plan tool cannot complete."""


async def extract_plan(pdf_path: str, out_dir: str | None = None) -> dict[str, Any]:
    """Run the floor-plan extraction pipeline on a PDF or SVG.

    Args:
        pdf_path: Path to a ``.pdf`` or ``.svg`` input. Absolute or relative
            (relative resolves against the server's current working directory,
            which is normally the repository root when launched via the
            ``sketchup-mcp-server`` console script with ``cwd`` set in
            ``mcp.json``).
        out_dir: Optional output directory. Defaults to ``runs/<stem>/``
            relative to CWD, mirroring the behaviour of ``main.py extract``.

    Returns:
        Dict with two top-level keys:
            * ``observed_model``: the full ObservedModel JSON (schema 2.x)
            * ``artifacts``: paths (str) to the files the pipeline wrote
    """
    source_path = _resolve_input_path(pdf_path)
    suffix = source_path.suffix.lower()
    if suffix not in (".pdf", ".svg"):
        raise ExtractError(f"unsupported input extension: {suffix} (expected .pdf or .svg)")

    output_dir = _resolve_output_dir(out_dir, source_path.stem)
    payload = source_path.read_bytes()

    result = await asyncio.to_thread(
        _run_pipeline_sync, suffix, payload, source_path.name, output_dir
    )
    return _build_response(result)


def _resolve_input_path(pdf_path: str) -> Path:
    p = Path(pdf_path).expanduser()
    if not p.is_absolute():
        p = p.resolve()
    if not p.is_file():
        raise ExtractError(f"input not found: {p}")
    return p


def _resolve_output_dir(out_dir: str | None, stem: str) -> Path:
    if out_dir is None:
        return Path("runs") / stem
    p = Path(out_dir).expanduser()
    if not p.is_absolute():
        p = p.resolve()
    return p


def _run_pipeline_sync(suffix: str, payload: bytes, filename: str, output_dir: Path):
    # Lazy import: keeps `mcp.list_tools` cold-start under ~1s by deferring
    # the heavy opencv/shapely/networkx import chain until extract_plan runs.
    from model.pipeline import PipelineError, run_pdf_pipeline, run_svg_pipeline

    try:
        if suffix == ".svg":
            return run_svg_pipeline(svg_bytes=payload, filename=filename, output_dir=output_dir)
        return run_pdf_pipeline(pdf_bytes=payload, filename=filename, output_dir=output_dir)
    except PipelineError as exc:
        raise ExtractError(f"pipeline failed: {exc}") from exc


def _build_response(result) -> dict[str, Any]:
    output_dir: Path = result.output_dir
    artifacts: dict[str, str | None] = {"run_dir": str(output_dir)}
    for key, name in (
        ("observed_model_json", "observed_model.json"),
        ("walls_svg", "debug_walls.svg"),
        ("junctions_svg", "debug_junctions.svg"),
        ("connectivity_report", "connectivity_report.json"),
        ("overlay_audited_png", "overlay_audited.png"),
        ("dedup_report", "dedup_report.json"),
        ("room_topology_check", "room_topology_check.json"),
    ):
        path = output_dir / name
        artifacts[key] = str(path) if path.exists() else None
    return {
        "observed_model": result.observed_model,
        "artifacts": artifacts,
    }
