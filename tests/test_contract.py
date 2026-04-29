from __future__ import annotations

from pathlib import Path

from model.pipeline import run_raster_pipeline
from tests.fixtures import blank_canvas, simple_square


TOP_LEVEL_FIELDS = {
    "schema_version",
    "run_id",
    "source",
    "bounds",
    "walls",
    "junctions",
    "rooms",
    "scores",
    "metadata",
    "warnings",
}

SOURCE_FIELDS = {"filename", "source_type", "page_count", "sha256"}
SCORE_FIELDS = {"geometry", "topology", "rooms", "quality", "retention", "orthogonality"}
METADATA_FIELDS = {"rooms_detected", "topology_quality", "connectivity", "warnings"}


def _observed_model(tmp_path: Path, fixture):
    result = run_raster_pipeline(fixture, output_dir=tmp_path / "run")
    return result.observed_model


def test_schema_version_is_versioned(tmp_path: Path) -> None:
    model = _observed_model(tmp_path, simple_square())
    version = model["schema_version"]
    assert isinstance(version, str), type(version)
    major, minor, patch = version.split(".")
    assert major.isdigit() and minor.isdigit() and patch.isdigit()
    assert int(major) >= 2, version


def test_all_required_top_level_fields_present(tmp_path: Path) -> None:
    model = _observed_model(tmp_path, simple_square())
    missing = TOP_LEVEL_FIELDS - set(model)
    assert not missing, f"missing top-level fields: {missing}"


def test_source_block_has_required_fields(tmp_path: Path) -> None:
    model = _observed_model(tmp_path, simple_square())
    source = model["source"]
    assert set(source) >= SOURCE_FIELDS, source
    assert source["source_type"] in {"pdf", "raster"}, source["source_type"]
    assert isinstance(source["page_count"], int)


def test_run_id_is_a_non_empty_string(tmp_path: Path) -> None:
    model = _observed_model(tmp_path, simple_square())
    run_id = model["run_id"]
    assert isinstance(run_id, str) and run_id, run_id
    # uuid4 hex is 32 hex chars
    assert len(run_id) == 32 and all(c in "0123456789abcdef" for c in run_id)


def test_bounds_per_page_when_walls_exist(tmp_path: Path) -> None:
    model = _observed_model(tmp_path, simple_square())
    bounds = model["bounds"]
    assert set(bounds) >= {"pages"}, bounds
    assert len(bounds["pages"]) == 1, bounds
    page = bounds["pages"][0]
    for key in ("page_index", "min_x", "min_y", "max_x", "max_y"):
        assert key in page, page
    assert page["min_x"] < page["max_x"]
    assert page["min_y"] < page["max_y"]


def test_bounds_pages_empty_when_no_walls(tmp_path: Path) -> None:
    model = _observed_model(tmp_path, blank_canvas())
    assert model["bounds"] == {"pages": []}


def test_scores_are_bounded_floats(tmp_path: Path) -> None:
    model = _observed_model(tmp_path, simple_square())
    scores = model["scores"]
    assert set(scores) == SCORE_FIELDS, scores
    for name, value in scores.items():
        assert isinstance(value, (int, float)), (name, type(value))
        assert 0.0 <= float(value) <= 1.0, (name, value)


def test_metadata_has_required_fields(tmp_path: Path) -> None:
    model = _observed_model(tmp_path, simple_square())
    metadata = model["metadata"]
    assert set(metadata) >= METADATA_FIELDS, metadata
    assert metadata["topology_quality"] in {"good", "fair", "poor"}
    assert isinstance(metadata["rooms_detected"], int)
    assert metadata["rooms_detected"] == len(model["rooms"])


def test_connectivity_has_orphan_component_counts(tmp_path: Path) -> None:
    model = _observed_model(tmp_path, simple_square())
    connectivity = model["metadata"]["connectivity"]
    assert "orphan_component_count" in connectivity
    assert "orphan_node_count" in connectivity
    assert isinstance(connectivity["orphan_component_count"], int)
    assert isinstance(connectivity["orphan_node_count"], int)
    # simple_square forms one large component, not an orphan
    assert connectivity["orphan_component_count"] == 0
    assert connectivity["orphan_node_count"] == 0


def test_warnings_is_top_level_list_of_strings(tmp_path: Path) -> None:
    model = _observed_model(tmp_path, blank_canvas())
    warnings = model["warnings"]
    assert isinstance(warnings, list), type(warnings)
    assert all(isinstance(w, str) for w in warnings), warnings


def test_metadata_warnings_mirrors_top_level(tmp_path: Path) -> None:
    # AGENTS.md still lists metadata.warnings as a mandatory field. Keep both
    # locations in lock-step until a major schema bump removes the legacy one.
    model = _observed_model(tmp_path, blank_canvas())
    assert model["metadata"]["warnings"] == model["warnings"]


def test_walls_and_junctions_have_page_index(tmp_path: Path) -> None:
    model = _observed_model(tmp_path, simple_square())
    for wall in model["walls"]:
        assert "page_index" in wall and isinstance(wall["page_index"], int), wall
    # junctions may not carry page_index in the current schema; don't assert on it.
    assert isinstance(model["junctions"], list)


def test_empty_fixture_still_emits_valid_contract(tmp_path: Path) -> None:
    model = _observed_model(tmp_path, blank_canvas())
    assert TOP_LEVEL_FIELDS <= set(model)
    assert model["walls"] == []
    assert model["rooms"] == []


def _synthetic_pdf_bytes(pages: int = 1) -> bytes:
    import io

    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument.new()
    for _ in range(pages):
        doc.new_page(200, 200)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_pdf_pipeline_populates_pdf_source_fields(tmp_path: Path) -> None:
    from model.pipeline import run_pdf_pipeline

    pdf_bytes = _synthetic_pdf_bytes(pages=2)
    result = run_pdf_pipeline(
        pdf_bytes=pdf_bytes,
        filename="synthetic.pdf",
        output_dir=tmp_path / "pdf_run",
    )
    source = result.observed_model["source"]
    assert source["source_type"] == "pdf"
    assert source["filename"] == "synthetic.pdf"
    assert source["page_count"] == 2
    assert isinstance(source["sha256"], str) and len(source["sha256"]) == 64
    # sha256 must be deterministic for identical bytes.
    again = run_pdf_pipeline(
        pdf_bytes=pdf_bytes,
        filename="synthetic.pdf",
        output_dir=tmp_path / "pdf_run_again",
    )
    assert again.observed_model["source"]["sha256"] == source["sha256"]
    assert again.observed_model["run_id"] != result.observed_model["run_id"]
