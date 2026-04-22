"""Tests for scripts/generate_synthetic_plans.py.

The generator is the source of truth for four synthetic fixtures:
``studio.svg``, ``2br.svg``, ``3br.svg``, ``lshape.svg``. These tests
verify the generator itself (parse-ability, viewBox, GT schema) and
the end-to-end SVG pipeline's ability to ingest each fixture.

They intentionally do *not* assert on the exact number of detected
rooms/openings. That is the job of downstream scoring (see
``scripts/score_openings.py`` and friends). The point here is:

1. the generator produces legal SVG + YAML, and
2. the pipeline runs to completion without exception on every layout.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from ingest.svg_service import ingest_svg
from model.pipeline import run_svg_pipeline
from scripts.generate_synthetic_plans import (
    LAYOUTS,
    _apply_openings,
    generate_all,
    layout_studio,
    walls_to_svg,
    write_gt_yaml,
)


LAYOUT_NAMES = [name for name, _ in LAYOUTS]


@pytest.fixture(scope="module")
def synthetic_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("synthetic")
    generate_all(out)
    return out


def test_studio_generates_valid_svg(synthetic_dir: Path) -> None:
    svg_path = synthetic_dir / "studio.svg"
    assert svg_path.exists(), "studio.svg was not written"
    root = ET.fromstring(svg_path.read_bytes())
    # Namespace-agnostic tag check: "<ns>}svg" after strip.
    assert root.tag.split("}")[-1] == "svg"
    paths = [el for el in root.iter() if el.tag.split("}")[-1] == "path"]
    assert len(paths) > 4, (
        f"studio.svg has too few paths ({len(paths)}); expected > 4"
    )


def test_studio_gt_openings_count(synthetic_dir: Path) -> None:
    gt_path = synthetic_dir / "studio_openings_gt.yaml"
    data = yaml.safe_load(gt_path.read_text(encoding="utf-8"))
    openings = data["openings"]
    # Studio GT has 3 openings after dropping kitchen_opening (a virtual
    # passage without a colinear wall, not detectable by gap-based detector).
    assert len(openings) == 3, (
        f"studio GT should have 3 openings, got {len(openings)}"
    )
    ids = [o["id"] for o in openings]
    assert len(ids) == len(set(ids)), f"duplicate ids in studio GT: {ids}"
    # All required schema keys must be present.
    required = {"id", "center", "width", "orientation", "kind"}
    for o in openings:
        missing = required - set(o.keys())
        assert not missing, f"opening {o.get('id')!r} missing keys: {missing}"
        assert o["orientation"] in ("horizontal", "vertical")
        assert o["kind"] in ("door", "window", "passage")
        assert isinstance(o["center"], list) and len(o["center"]) == 2


@pytest.mark.parametrize("name", LAYOUT_NAMES)
def test_all_layouts_have_viewbox(synthetic_dir: Path, name: str) -> None:
    svg_path = synthetic_dir / f"{name}.svg"
    root = ET.fromstring(svg_path.read_bytes())
    assert root.get("viewBox") == "0 0 800 600", (
        f"{name}.svg has wrong viewBox: {root.get('viewBox')!r}"
    )


@pytest.mark.parametrize("name", LAYOUT_NAMES)
def test_generated_svg_ingests_cleanly(
    synthetic_dir: Path, tmp_path: Path, name: str
) -> None:
    svg_path = synthetic_dir / f"{name}.svg"
    svg_bytes = svg_path.read_bytes()
    # Phase 1: pure parser must return walls.
    document = ingest_svg(svg_bytes, f"{name}.svg")
    assert document.walls, f"no walls parsed from {name}.svg"
    assert document.stroke_width_median == pytest.approx(6.25)
    # Phase 2: full pipeline must run without PipelineError.
    run_dir = tmp_path / name
    result = run_svg_pipeline(svg_bytes, f"{name}.svg", run_dir)
    assert result.observed_model["source"]["filename"] == f"{name}.svg"
    # Pipeline artifacts are always written, even when no rooms are found.
    assert (run_dir / "observed_model.json").exists()
    assert (run_dir / "debug_walls.svg").exists()


def test_generate_all_layouts_returns_expected_counts(tmp_path: Path) -> None:
    summary = generate_all(tmp_path)
    by_name = {name: (n_walls, n_openings) for name, n_walls, n_openings in summary}
    # Opening counts are locked to the spec.
    # studio dropped to 3 after removing kitchen_opening (virtual passage).
    assert by_name["studio"][1] == 3
    assert by_name["2br"][1] == 8
    assert by_name["3br"][1] == 12
    assert by_name["lshape"][1] == 8
    # Wall counts after cutting are bounded below by the base geometry.
    for name, (n_walls, _) in by_name.items():
        assert n_walls > 4, f"{name} has too few walls ({n_walls}) after cuts"


def test_apply_openings_preserves_total_wall_extent_when_cut_interior() -> None:
    walls, openings = layout_studio()
    cut = _apply_openings(walls, openings)
    # Sum of wall lengths should drop by exactly the combined width of
    # openings that landed strictly inside a wall (not corner-clipped).
    original_length = sum(w.length for w in walls)
    cut_length = sum(w.length for w in cut)
    # Studio has 3 openings after removing kitchen_opening:
    #   - main_entrance (50) interior gap on top wall
    #   - bathroom_door (50) interior gap on vertical divider
    #   - window_bedroom (70) interior gap on top wall (moved to 640 so
    #     it no longer clips the corner)
    interior_gaps = 50.0 + 50.0 + 70.0
    removed = interior_gaps
    assert cut_length == pytest.approx(original_length - removed, abs=0.5)
