from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np

from classify.service import classify_walls
from debug.overlay import write_audited_overlay
from debug.service import write_debug_artifacts
from extract.service import extract_from_raster
from ingest.service import IngestError, IngestedDocument, ingest_pdf
from ingest.svg_service import IngestSvgError, IngestedSvgDocument, ingest_svg
from model.builder import build_observed_model, compute_bounds
from model.types import ConnectivityReport, DedupReport, Junction, Room, SplitWall, Wall, WallCandidate
from openings.pruning import (
    dedup_collinear_openings,
    filter_min_width_openings,
    postfilter_roomless_openings,
    prune_orphan_openings,
)
from openings.service import detect_openings
from roi.service import RoiResult, crop_image_to_bbox, detect_architectural_roi
from topology.main_component_filter import select_main_component
from topology.service import build_topology


class PipelineError(RuntimeError):
    pass


@dataclass(frozen=True)
class PipelineResult:
    observed_model: dict
    output_dir: Path
    candidates: list[WallCandidate]
    split_walls: list[SplitWall]
    junctions: list[Junction]
    rooms: list[Room]
    connectivity_report: ConnectivityReport


def run_pdf_pipeline(
    pdf_bytes: bytes,
    filename: str,
    output_dir: Path,
    peitoris: list[dict] | None = None,
) -> PipelineResult:
    try:
        document = ingest_pdf(pdf_bytes=pdf_bytes, filename=filename)
    except IngestError as exc:
        raise PipelineError(str(exc)) from exc
    candidates, roi_results = _extract_with_roi_from_document(document)
    source = _build_pdf_source(pdf_bytes=pdf_bytes, filename=filename, document=document)
    return _run_pipeline(
        candidates=candidates,
        output_dir=output_dir,
        source=source,
        roi_results=roi_results,
        peitoris=peitoris,
    )


def run_svg_pipeline(
    svg_bytes: bytes,
    filename: str,
    output_dir: Path,
    peitoris: list[dict] | None = None,
) -> PipelineResult:
    try:
        document = ingest_svg(svg_bytes=svg_bytes, filename=filename)
    except IngestSvgError as exc:
        raise PipelineError(str(exc)) from exc
    source = _build_svg_source(svg_bytes=svg_bytes, filename=filename, document=document)
    return _run_pipeline_from_walls(
        walls=document.walls,
        wall_thickness=document.stroke_width_median,
        output_dir=output_dir,
        source=source,
        peitoris=peitoris,
    )


def run_raster_pipeline(image: np.ndarray, output_dir: Path) -> PipelineResult:
    candidates, roi_result = _extract_with_roi_from_raster(image, page_index=0)
    source = {
        "filename": None,
        "source_type": "raster",
        "page_count": 1,
        "sha256": None,
    }
    return _run_pipeline(
        candidates=candidates,
        output_dir=output_dir,
        source=source,
        roi_results=[roi_result],
    )


def _extract_with_roi_from_document(document: IngestedDocument):
    all_candidates: list[WallCandidate] = []
    roi_results: list[RoiResult] = []
    for page in document.pages:
        candidates, roi = _extract_with_roi_from_raster(page.image, page_index=page.index)
        all_candidates.extend(candidates)
        roi_results.append(roi)
    return all_candidates, roi_results


def _extract_with_roi_from_raster(image: np.ndarray, page_index: int):
    # Heuristica: se o input ja vem limpo (poucos pixels escuros = planta
    # pre-processada/anotada), pula ROI pra nao perder paredes que ele
    # trataria como "fora da regiao principal".
    import cv2 as _cv2
    _gray = image if image.ndim == 2 else _cv2.cvtColor(image, _cv2.COLOR_BGR2GRAY)
    dark_pct = (_gray < 200).sum() / _gray.size
    if dark_pct < 0.03:
        candidates = extract_from_raster(image=image, page_index=page_index)
        return candidates, RoiResult(applied=False, bbox=None, fallback_reason="clean_input_skip_roi")
    roi = detect_architectural_roi(image)
    if not roi.applied or roi.bbox is None:
        candidates = extract_from_raster(image=image, page_index=page_index)
        return candidates, roi
    cropped = crop_image_to_bbox(image, roi.bbox)
    raw = extract_from_raster(image=cropped, page_index=page_index)
    dx, dy = roi.bbox[0], roi.bbox[1]
    translated = [
        WallCandidate(
            page_index=c.page_index,
            start=(c.start[0] + dx, c.start[1] + dy),
            end=(c.end[0] + dx, c.end[1] + dy),
            thickness=c.thickness,
            source=c.source,
            confidence=c.confidence,
        )
        for c in raw
    ]
    return translated, roi


def _run_pipeline(
    candidates: list[WallCandidate],
    output_dir: Path,
    source: dict,
    roi_results: list[RoiResult],
    peitoris: list[dict] | None = None,
) -> PipelineResult:
    dedup_report_sink: list[DedupReport] = []
    walls = classify_walls(candidates, dedup_report_sink=dedup_report_sink)
    dedup_report = dedup_report_sink[0] if dedup_report_sink else None
    walls, openings = detect_openings(walls, peitoris=peitoris)
    room_topology_sink: list = []
    snapshot_hash_sink: list[str] = []
    split_walls, junctions, rooms, connectivity_report = build_topology(
        walls,
        room_topology_report_sink=room_topology_sink,
        snapshot_hash_sink=snapshot_hash_sink,
    )
    room_topology_report = room_topology_sink[0] if room_topology_sink else None
    topology_snapshot_sha256 = snapshot_hash_sink[0] if snapshot_hash_sink else None
    warnings = _build_warnings(
        candidates=candidates,
        walls=walls,
        split_walls=split_walls,
        rooms=rooms,
        connectivity_report=connectivity_report,
        roi_results=roi_results,
    )
    run_id = uuid4().hex
    bounds = compute_bounds(split_walls)
    observed_model = build_observed_model(
        walls=split_walls,
        junctions=junctions,
        rooms=rooms,
        connectivity_report=connectivity_report,
        geometry_score=_geometry_score(candidates, walls),
        topology_score=_topology_score(split_walls, connectivity_report),
        room_score=_room_score(rooms, connectivity_report),
        warnings=warnings,
        run_id=run_id,
        source=source,
        bounds=bounds,
        roi=[r.to_dict() for r in roi_results],
    )
    observed_model["openings"] = [o.to_dict() for o in openings]
    observed_model["peitoris"] = peitoris or []
    if topology_snapshot_sha256 is not None:
        observed_model.setdefault("metadata", {})["topology_snapshot_sha256"] = topology_snapshot_sha256

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "observed_model.json").write_text(
        json.dumps(observed_model, indent=2),
        encoding="utf-8",
    )
    if dedup_report is not None:
        (output_dir / "dedup_report.json").write_text(
            json.dumps(dedup_report.to_dict(), indent=2),
            encoding="utf-8",
        )
    if room_topology_report is not None:
        (output_dir / "room_topology_check.json").write_text(
            json.dumps(room_topology_report.to_dict(), indent=2),
            encoding="utf-8",
        )
    write_debug_artifacts(
        output_dir=output_dir,
        walls=split_walls,
        junctions=junctions,
        connectivity_report=connectivity_report,
    )
    try:
        write_audited_overlay(observed_model, output_dir / "overlay_audited.png")
    except Exception as exc:  # render issues must not fail the pipeline
        (output_dir / "overlay_audited.error.txt").write_text(
            f"{type(exc).__name__}: {exc}\n", encoding="utf-8"
        )

    return PipelineResult(
        observed_model=observed_model,
        output_dir=output_dir,
        candidates=candidates,
        split_walls=split_walls,
        junctions=junctions,
        rooms=rooms,
        connectivity_report=connectivity_report,
    )


def _build_pdf_source(pdf_bytes: bytes, filename: str, document: IngestedDocument) -> dict:
    return {
        "filename": filename,
        "source_type": "pdf",
        "page_count": len(document.pages),
        "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
    }


def _build_svg_source(svg_bytes: bytes, filename: str, document: IngestedSvgDocument) -> dict:
    return {
        "filename": filename,
        "source_type": "svg",
        "page_count": 1,
        "sha256": hashlib.sha256(svg_bytes).hexdigest(),
        "viewbox_width": document.viewbox_width,
        "viewbox_height": document.viewbox_height,
        "stroke_width_median": document.stroke_width_median,
        "stroke_width_samples": document.stroke_width_samples,
    }


def _run_pipeline_from_walls(
    walls: list[Wall],
    wall_thickness: float,
    output_dir: Path,
    source: dict,
    peitoris: list[dict] | None = None,
) -> PipelineResult:
    walls, openings = detect_openings(walls, peitoris=peitoris, wall_thickness=wall_thickness)
    walls, main_component_report = select_main_component(
        walls, snap_tolerance=wall_thickness / 2
    )
    openings, prune_report = prune_orphan_openings(openings, walls)
    openings, min_width_report = filter_min_width_openings(openings, wall_thickness)
    openings, dedup_report = dedup_collinear_openings(openings, wall_thickness)
    room_topology_sink: list = []
    snapshot_hash_sink: list[str] = []
    split_walls, junctions, rooms, connectivity_report = build_topology(
        walls,
        room_topology_report_sink=room_topology_sink,
        snapshot_hash_sink=snapshot_hash_sink,
        filter_wall_interior=True,
        wall_thickness=wall_thickness,
    )
    openings, roomless_report = postfilter_roomless_openings(
        openings, rooms, wall_thickness
    )
    room_topology_report = room_topology_sink[0] if room_topology_sink else None
    topology_snapshot_sha256 = snapshot_hash_sink[0] if snapshot_hash_sink else None
    warnings: list[str] = []
    if not walls:
        warnings.append("no_walls")
    if split_walls and connectivity_report.max_components_within_page > 1:
        warnings.append("walls_disconnected")
    if split_walls and connectivity_report.orphan_component_count >= 5:
        warnings.append("many_orphan_components")
    if not rooms:
        warnings.append("rooms_not_detected")

    run_id = uuid4().hex
    bounds = compute_bounds(split_walls)
    observed_model = build_observed_model(
        walls=split_walls,
        junctions=junctions,
        rooms=rooms,
        connectivity_report=connectivity_report,
        geometry_score=1.0 if walls else 0.0,
        topology_score=_topology_score(split_walls, connectivity_report),
        room_score=_room_score(rooms, connectivity_report),
        warnings=warnings,
        run_id=run_id,
        source=source,
        bounds=bounds,
        roi=[],
    )
    observed_model["openings"] = [o.to_dict() for o in openings]
    observed_model["peitoris"] = peitoris or []
    observed_model.setdefault("metadata", {})["main_component"] = dict(main_component_report)
    observed_model["metadata"]["openings_refinement"] = {
        "prune_orphan": prune_report.to_dict(),
        "min_width": min_width_report.to_dict(),
        "dedup_collinear": dedup_report.to_dict(),
        "postfilter_roomless": roomless_report.to_dict(),
    }
    if topology_snapshot_sha256 is not None:
        observed_model["metadata"]["topology_snapshot_sha256"] = topology_snapshot_sha256

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "observed_model.json").write_text(
        json.dumps(observed_model, indent=2),
        encoding="utf-8",
    )
    if room_topology_report is not None:
        (output_dir / "room_topology_check.json").write_text(
            json.dumps(room_topology_report.to_dict(), indent=2),
            encoding="utf-8",
        )
    write_debug_artifacts(
        output_dir=output_dir,
        walls=split_walls,
        junctions=junctions,
        connectivity_report=connectivity_report,
    )
    try:
        write_audited_overlay(observed_model, output_dir / "overlay_audited.png")
    except Exception as exc:
        (output_dir / "overlay_audited.error.txt").write_text(
            f"{type(exc).__name__}: {exc}\n", encoding="utf-8"
        )

    return PipelineResult(
        observed_model=observed_model,
        output_dir=output_dir,
        candidates=[],
        split_walls=split_walls,
        junctions=junctions,
        rooms=rooms,
        connectivity_report=connectivity_report,
    )


def _build_warnings(
    candidates: list[WallCandidate],
    walls: list,
    split_walls: list[SplitWall],
    rooms: list[Room],
    connectivity_report: ConnectivityReport,
    roi_results: list[RoiResult],
) -> list[str]:
    warnings: list[str] = []
    if any(not r.applied for r in roi_results):
        warnings.append("roi_fallback_used")
    if not candidates:
        warnings.append("no_wall_candidates")
    if candidates and not walls:
        warnings.append("all_candidates_filtered")
    if split_walls and connectivity_report.max_components_within_page > 1:
        warnings.append("walls_disconnected")
    if split_walls and connectivity_report.orphan_component_count >= 5:
        warnings.append("many_orphan_components")
    if not rooms:
        warnings.append("rooms_not_detected")
    return warnings


def _geometry_score(candidates: list[WallCandidate], walls: list) -> float:
    if not candidates:
        return 0.0
    return min(1.0, len(walls) / len(candidates))


def _topology_score(split_walls: list[SplitWall], connectivity_report: ConnectivityReport) -> float:
    if not split_walls:
        return 0.0
    component_penalty = 1.0 / max(1, connectivity_report.max_components_within_page or 1)
    intra_page_ratio = connectivity_report.min_intra_page_connectivity_ratio
    return min(1.0, round((intra_page_ratio + component_penalty) / 2.0, 4))


def _room_score(rooms: list[Room], connectivity_report: ConnectivityReport) -> float:
    if not rooms:
        return 0.0
    density = len(rooms) / max(1, connectivity_report.edge_count)
    return min(1.0, round(0.5 + density, 4))
