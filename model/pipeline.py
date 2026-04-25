from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np

from classify.service import classify_walls
from debug.service import write_debug_artifacts
from extract.service import extract_from_raster
from ingest.service import IngestError, IngestedDocument, RasterPage, ingest_pdf
from model.builder import build_observed_model, compute_bounds
from model.types import ConnectivityReport, Junction, Room, SplitWall, WallCandidate
from openings.service import detect_openings
from peitoris.service import detect_peitoris
from preprocess import apply_preprocessing, preprocess_warning_for
from roi.service import RoiResult, crop_image_to_bbox, detect_architectural_roi
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
    source_image: np.ndarray | None = None,
    preprocess: dict | None = None,
) -> PipelineResult:
    """Roda o pipeline completo a partir de um PDF.

    `peitoris`: override manual (legado pNN_peitoris.json). Se None E
    `source_image` for fornecida (PNG colorido original), detecta
    peitoris automaticamente via `peitoris.service.detect_peitoris`.
    Se ambos forem None, observed_model.peitoris fica `[]`.

    `preprocess`: configuracao opcional de pre-processamento por pagina,
    aplicada APOS rasterizacao e ANTES da extracao. Ex:
    ``{"mode": "color_mask", "color": "auto"}`` extrai canal cromatico
    dominante (vermelho/preto/...) e injeta um warning explicito
    `preprocess_color_mask_applied` no observed_model. ``None`` mantem o
    comportamento default (sem alteracao do raster). Ver `preprocess/`.
    """
    try:
        document = ingest_pdf(pdf_bytes=pdf_bytes, filename=filename)
    except IngestError as exc:
        raise PipelineError(str(exc)) from exc
    document = _apply_preprocess_to_document(document, preprocess)
    candidates, roi_results = _extract_with_roi_from_document(document)
    source = _build_pdf_source(pdf_bytes=pdf_bytes, filename=filename, document=document)
    if peitoris is None and source_image is not None:
        peitoris = detect_peitoris(source_image, page_index=0)
    return _run_pipeline(
        candidates=candidates,
        output_dir=output_dir,
        source=source,
        roi_results=roi_results,
        peitoris=peitoris,
        preprocess=preprocess,
    )


def run_raster_pipeline(
    image: np.ndarray,
    output_dir: Path,
    peitoris: list[dict] | None = None,
    auto_detect_peitoris: bool = False,
    preprocess: dict | None = None,
) -> PipelineResult:
    """Roda o pipeline a partir de um raster ja em memoria.

    `auto_detect_peitoris`: se True E `peitoris` for None, roda o
    detector automatico em cima da imagem (deve ser colorida).
    `preprocess`: ver docstring de :func:`run_pdf_pipeline`.
    """
    if preprocess is not None:
        image = apply_preprocessing(image, preprocess)
    candidates, roi_result = _extract_with_roi_from_raster(image, page_index=0)
    source = {
        "filename": None,
        "source_type": "raster",
        "page_count": 1,
        "sha256": None,
    }
    if peitoris is None and auto_detect_peitoris:
        peitoris = detect_peitoris(image, page_index=0)
    return _run_pipeline(
        candidates=candidates,
        output_dir=output_dir,
        source=source,
        roi_results=[roi_result],
        peitoris=peitoris,
        preprocess=preprocess,
    )


def _apply_preprocess_to_document(
    document: IngestedDocument,
    preprocess: dict | None,
) -> IngestedDocument:
    """Return a new IngestedDocument with each page image preprocessed.

    No-op (returns ``document`` as-is) when ``preprocess`` is None.
    """
    if preprocess is None:
        return document
    new_pages: list[RasterPage] = []
    for page in document.pages:
        new_image = apply_preprocessing(page.image, preprocess)
        new_image = np.ascontiguousarray(new_image)
        new_pages.append(
            RasterPage(
                index=page.index,
                image=new_image,
                width=int(new_image.shape[1]),
                height=int(new_image.shape[0]),
            )
        )
    return IngestedDocument(source_name=document.source_name, pages=new_pages)


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
    preprocess: dict | None = None,
) -> PipelineResult:
    walls = classify_walls(candidates)
    walls, openings = detect_openings(walls, peitoris=peitoris)
    split_walls, junctions, rooms, connectivity_report = build_topology(walls)
    warnings = _build_warnings(
        candidates=candidates,
        walls=walls,
        split_walls=split_walls,
        rooms=rooms,
        connectivity_report=connectivity_report,
        roi_results=roi_results,
        preprocess=preprocess,
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
    roi_results: list[RoiResult],
    preprocess: dict | None = None,
) -> list[str]:
    warnings: list[str] = []
    # INVARIANT: preprocessing is never silent. If applied, the warning is
    # the FIRST entry so downstream consumers cannot miss it.
    if preprocess is not None and preprocess.get("mode"):
        warnings.append(preprocess_warning_for(preprocess["mode"]))
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
