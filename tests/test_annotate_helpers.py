"""Tests for scripts/annotate_openings_helper.py and scripts/render_f1_diff_png.py.

Both scripts are thin visualization layers — the tests only verify
that ``main()`` runs end-to-end on a mock ``observed_model.json`` and
writes the expected artifacts (PNG non-empty, YAML parseable).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


def _mock_model() -> dict:
    """Small-but-plausible observed model (2 rooms, 4 openings)."""
    walls = [
        # outer rectangle 0..300 x 0..200
        {"start": [0.0, 0.0], "end": [300.0, 0.0], "thickness": 6.25},
        {"start": [300.0, 0.0], "end": [300.0, 200.0], "thickness": 6.25},
        {"start": [300.0, 200.0], "end": [0.0, 200.0], "thickness": 6.25},
        {"start": [0.0, 200.0], "end": [0.0, 0.0], "thickness": 6.25},
        # internal divider
        {"start": [150.0, 0.0], "end": [150.0, 200.0], "thickness": 6.25},
    ]
    openings = [
        {"opening_id": "opening-1", "center": [50.0, 0.0], "width": 36.0,
         "orientation": "horizontal", "kind": "door"},
        {"opening_id": "opening-2", "center": [150.0, 100.0], "width": 60.0,
         "orientation": "vertical", "kind": "passage"},
        {"opening_id": "opening-3", "center": [220.0, 200.0], "width": 40.0,
         "orientation": "horizontal", "kind": "window"},
        # near opening-3 to test label-offset rotation
        {"opening_id": "opening-4", "center": [260.0, 200.0], "width": 30.0,
         "orientation": "horizontal", "kind": "door"},
    ]
    return {
        "schema_version": "1.0.0",
        "source": {
            "filename": "mock_plan.svg",
            "source_type": "svg",
            "stroke_width_median": 6.25,
        },
        "walls": walls,
        "openings": openings,
    }


def _mock_gt() -> dict:
    """Ground truth with 3 real openings (one FP -> drop opening-4,
    one FN -> new bath window not in detections)."""
    return {
        "meta": {
            "source": "mock_plan.svg",
            "thickness": 6.25,
            "annotator": "test",
        },
        "openings": [
            {"id": "entrance", "center": [50.0, 0.0], "width": 36.0,
             "orientation": "horizontal", "kind": "door",
             "notes": "porta entrada"},
            {"id": "living_passage", "center": [150.0, 100.0], "width": 60.0,
             "orientation": "vertical", "kind": "passage",
             "notes": "abertura sala/cozinha"},
            {"id": "bath_window", "center": [80.0, 200.0], "width": 40.0,
             "orientation": "horizontal", "kind": "window",
             "notes": "janela banheiro — nao detectada"},
        ],
    }


def test_annotate_helper_runs_on_sample_model(tmp_path: Path) -> None:
    from scripts import annotate_openings_helper as helper

    model = _mock_model()
    model_path = tmp_path / "observed_model.json"
    model_path.write_text(json.dumps(model), encoding="utf-8")

    png_path = tmp_path / "annotation_helper.png"
    rc = helper.main([
        "--model", str(model_path),
        "--out", str(png_path),
    ])
    assert rc == 0

    # PNG created and non-trivial
    assert png_path.exists()
    size = png_path.stat().st_size
    assert size > 10_000, f"PNG suspiciously small: {size} bytes"

    # YAML template created next to PNG
    tmpl_path = tmp_path / "annotation_template.yaml"
    assert tmpl_path.exists()
    data = yaml.safe_load(tmpl_path.read_text(encoding="utf-8"))
    assert data["meta"]["source"] == "mock_plan.svg"
    assert data["meta"]["thickness"] == pytest.approx(6.25)
    assert isinstance(data["openings"], list)
    assert len(data["openings"]) == 4  # all detections pre-filled
    # first entry preserves detection data
    first = data["openings"][0]
    assert first["id"] == "opening-1"
    assert first["center"] == [pytest.approx(50.0), pytest.approx(0.0)]
    assert first["width"] == pytest.approx(36.0)
    assert first["orientation"] == "horizontal"
    assert first["kind"] == "door"


def test_render_f1_diff_runs(tmp_path: Path) -> None:
    from scripts import render_f1_diff_png as differ

    model = _mock_model()
    gt = _mock_gt()

    model_path = tmp_path / "observed_model.json"
    gt_path = tmp_path / "gt.yaml"
    model_path.write_text(json.dumps(model), encoding="utf-8")
    gt_path.write_text(yaml.safe_dump(gt, sort_keys=False), encoding="utf-8")

    out_path = tmp_path / "f1_diff.png"
    rc = differ.main([
        "--model", str(model_path),
        "--gt", str(gt_path),
        "--out", str(out_path),
    ])
    assert rc == 0

    assert out_path.exists()
    size = out_path.stat().st_size
    assert size > 10_000, f"PNG suspiciously small: {size} bytes"
