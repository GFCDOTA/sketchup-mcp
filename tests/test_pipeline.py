from __future__ import annotations

from pathlib import Path

from model.pipeline import run_raster_pipeline
from tests.fixtures import blank_canvas, disconnected_walls, l_shape_room, simple_square, t_junction, two_rooms_shared_wall


def test_simple_square_detects_one_room(tmp_path: Path) -> None:
    result = run_raster_pipeline(simple_square(), output_dir=tmp_path / "square")
    assert len(result.rooms) == 1
    assert result.observed_model["metadata"]["rooms_detected"] == 1


def test_two_rooms_shared_wall_detects_two_rooms(tmp_path: Path) -> None:
    result = run_raster_pipeline(two_rooms_shared_wall(), output_dir=tmp_path / "two_rooms")
    assert len(result.rooms) == 2


def test_l_shape_is_valid_room(tmp_path: Path) -> None:
    result = run_raster_pipeline(l_shape_room(), output_dir=tmp_path / "l_shape")
    assert len(result.rooms) == 1
    assert result.rooms[0].area > 0


def test_t_junction_is_detected(tmp_path: Path) -> None:
    result = run_raster_pipeline(t_junction(), output_dir=tmp_path / "t_junction")
    assert any(junction.kind == "tee" for junction in result.junctions)


def test_disconnected_walls_keep_rooms_zero(tmp_path: Path) -> None:
    result = run_raster_pipeline(disconnected_walls(), output_dir=tmp_path / "disconnected")
    assert len(result.rooms) == 0
    # roi_fallback_used appears because the synthetic fixture is below
    # min_image_side (CLAUDE.md invariant #2: no silent fallback).
    assert result.observed_model["warnings"] == [
        "roi_fallback_used",
        "walls_disconnected",
        "rooms_not_detected",
    ]


def test_debug_artifacts_exist_even_when_no_geometry_is_found(tmp_path: Path) -> None:
    output_dir = tmp_path / "empty"
    result = run_raster_pipeline(blank_canvas(), output_dir=output_dir)
    assert result.observed_model["warnings"] == [
        "roi_fallback_used",
        "no_wall_candidates",
        "rooms_not_detected",
    ]
    assert (output_dir / "observed_model.json").exists()
    assert (output_dir / "debug_walls.svg").exists()
    assert (output_dir / "debug_junctions.svg").exists()
    assert (output_dir / "connectivity_report.json").exists()
