from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np

from classify.service import classify_walls
from debug.service import write_debug_artifacts
from extract.service import extract_from_document, extract_from_raster
from ingest.service import IngestError, IngestedDocument, ingest_pdf
from model.builder import build_observed_model, compute_bounds
from model.types import ConnectivityReport, Junction, Room, SplitWall, WallCandidate
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


def run_pdf_pipeline(pdf_bytes: bytes, filename: str, output_dir: Path) -> PipelineResult:
    try:
        document = ingest_pdf(pdf_bytes=pdf_bytes, filename=filename)
    except IngestError as exc:
        raise PipelineError(str(exc)) from exc
    candidates = extract_from_document(document)
    source = _build_pdf_source(pdf_bytes=pdf_bytes, filename=filename, document=document)
    return _run_pipeline(candidates=candidates, output_dir=output_dir, source=source)


def run_raster_pipeline(image: np.ndarray, output_dir: Path) -> PipelineResult:
    candidates = extract_from_raster(image=image)
    source = {
        "filename": None,
        "source_type": "raster",
        "page_count": 1,
        "sha256": None,
    }
    return _run_pipeline(candidates=candidates, output_dir=output_dir, source=source)


def _run_pipeline(
    candidates: list[WallCandidate], output_dir: Path, source: dict
) -> PipelineResult:
    walls = classify_walls(candidates)
    split_walls, junctions, rooms, connectivity_report = build_topology(walls)
    warnings = _build_warnings(candidates, walls, split_walls, rooms, connectivity_report)
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
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "observed_model.json").write_text(
        json.dumps(observed_model, indent=2),
        encoding="utf-8",
    )
    write_debug_artifacts(
        output_dir=output_dir,
        walls=split_walls,
        junctions=junctions,
        connectivity_report=connectivity_report,
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


def _build_warnings(
    candidates: list[WallCandidate],
    walls: list,
    split_walls: list[SplitWall],
    rooms: list[Room],
    connectivity_report: ConnectivityReport,
) -> list[str]:
    warnings: list[str] = []
    if not candidates:
        warnings.append("no_wall_candidates")
    if candidates and not walls:
        warnings.append("all_candidates_filtered")
    if split_walls and connectivity_report.max_components_within_page > 1:
        warnings.append("walls_disconnected")
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
