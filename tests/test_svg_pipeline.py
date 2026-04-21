from __future__ import annotations

from pathlib import Path

import pytest

from model.pipeline import run_svg_pipeline


FIXTURE = Path(__file__).parent / "fixtures" / "svg" / "minimal_room.svg"


def test_pipeline_on_minimal_room(tmp_path: Path) -> None:
    svg_bytes = FIXTURE.read_bytes()
    result = run_svg_pipeline(svg_bytes, "minimal_room.svg", tmp_path)

    assert result.observed_model["source"]["source_type"] == "svg"
    assert result.observed_model["source"]["filename"] == "minimal_room.svg"
    # 4 real walls; detector may add a bridge across the door gap.
    assert len(result.split_walls) >= 4

    assert (tmp_path / "observed_model.json").exists()
    assert (tmp_path / "debug_walls.svg").exists()
    assert (tmp_path / "debug_junctions.svg").exists()
    assert (tmp_path / "connectivity_report.json").exists()


def test_wall_interior_filter_preserves_real_room(tmp_path: Path) -> None:
    svg_bytes = FIXTURE.read_bytes()
    result = run_svg_pipeline(svg_bytes, "minimal_room.svg", tmp_path)

    # The single room must survive the is_wall_interior sliver filter.
    assert len(result.rooms) == 1

    # Interior of the rectangle is (190-10) * (90-10) = 180 * 80 = 14400 user-units^2,
    # minus whatever the door bridge trims. Tolerant approx per spec.
    expected_area = 180.0 * 80.0
    assert result.rooms[0].area == pytest.approx(expected_area, rel=0.2)


def test_observed_model_has_svg_metadata(tmp_path: Path) -> None:
    svg_bytes = FIXTURE.read_bytes()
    result = run_svg_pipeline(svg_bytes, "minimal_room.svg", tmp_path)

    source = result.observed_model["source"]
    for key in ("source_type", "sha256", "viewbox_width", "viewbox_height", "stroke_width_median"):
        assert key in source, f"missing {key} in source metadata"

    assert source["source_type"] == "svg"
    assert source["stroke_width_median"] == pytest.approx(6.25)
