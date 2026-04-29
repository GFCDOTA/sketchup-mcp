"""
F1 regression test: pipeline must keep F1 >= 0.90 on every known plan.

Policy: planta_74m2 uses alpha GT (pipeline-derived, self-consistent).
Synthetics use programmatic GT (derived from generator geometry).
If pipeline regresses below 0.90 on any plan, CI fails.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from score_openings import load_gt, load_detections, match_openings

from model.pipeline import run_svg_pipeline


REPO_ROOT = Path(__file__).parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "svg"


PLANS = [
    # (name, svg_path, gt_path, min_f1)
    pytest.param("studio", FIXTURES / "synthetic/studio.svg",
                 FIXTURES / "synthetic/studio_openings_gt.yaml", 0.90, id="studio"),
    pytest.param("2br", FIXTURES / "synthetic/2br.svg",
                 FIXTURES / "synthetic/2br_openings_gt.yaml", 0.90, id="2br"),
    pytest.param("3br", FIXTURES / "synthetic/3br.svg",
                 FIXTURES / "synthetic/3br_openings_gt.yaml", 0.90, id="3br"),
    pytest.param("lshape", FIXTURES / "synthetic/lshape.svg",
                 FIXTURES / "synthetic/lshape_openings_gt.yaml", 0.90, id="lshape"),
    pytest.param("tiny", FIXTURES / "synthetic/tiny.svg",
                 FIXTURES / "synthetic/tiny_openings_gt.yaml", 0.90, id="tiny"),
    pytest.param("large", FIXTURES / "synthetic/large.svg",
                 FIXTURES / "synthetic/large_openings_gt.yaml", 0.90, id="large"),
    pytest.param("multistory", FIXTURES / "synthetic/multistory.svg",
                 FIXTURES / "synthetic/multistory_openings_gt.yaml", 0.90, id="multistory"),
]


@pytest.mark.parametrize("name,svg_path,gt_path,min_f1", PLANS)
def test_f1_regression(name, svg_path, gt_path, min_f1, tmp_path):
    """Pipeline must achieve F1 >= min_f1 on each plan."""
    svg_bytes = svg_path.read_bytes()
    result = run_svg_pipeline(svg_bytes, svg_path.name, tmp_path)

    # Write observed_model.json to tmp_path so score_openings can load it
    # (run_svg_pipeline already does this)
    model_path = tmp_path / "observed_model.json"
    assert model_path.exists(), f"pipeline did not produce observed_model.json"

    thickness, gt_openings = load_gt(gt_path)
    dets, _walls = load_detections(model_path)
    match_result = match_openings(gt_openings, dets, thickness=thickness)

    assert match_result.f1 >= min_f1, (
        f"{name}: F1={match_result.f1:.3f} below min {min_f1:.2f} "
        f"(TP={match_result.tp_count}, FP={match_result.fp_count}, FN={match_result.fn_count})"
    )


def test_raster_byte_identical_on_planta_74(tmp_path):
    """planta_74.pdf observed_model.json must stay byte-identical (mod run_id)
    regardless of SVG-pipeline changes."""
    import hashlib, json
    from model.pipeline import run_pdf_pipeline
    pdf_path = REPO_ROOT / "planta_74.pdf"
    if not pdf_path.exists():
        pytest.skip(f"planta_74.pdf not found at {pdf_path}")

    pdf_bytes = pdf_path.read_bytes()
    result = run_pdf_pipeline(pdf_bytes, "planta_74.pdf", tmp_path)
    model_path = tmp_path / "observed_model.json"
    m = json.loads(model_path.read_text(encoding="utf-8"))
    m["run_id"] = "REDACTED"
    sha = hashlib.sha256(json.dumps(m, sort_keys=True, indent=2).encode()).hexdigest()

    # Known-good sha. Updated on schema bumps that legitimately rewrite the
    # output (e.g. 2.1.0 -> 2.2.0 added metadata.openings_refinement docs
    # and the schema_version string itself changed).
    # Last regenerated: 2026-04-29, after patch 04 (ROI fallback_used additive field).
    EXPECTED_SHA = "4bf3efbf3bf216018e3f8f6d22517fb5254752fa583ef427d0913a5bdcece9c0"
    assert sha == EXPECTED_SHA, (
        f"planta_74.pdf model sha changed: {sha[:16]}... (expected {EXPECTED_SHA[:16]}...). "
        "Raster path regressed - investigate model/pipeline.py:_run_pipeline changes."
    )
