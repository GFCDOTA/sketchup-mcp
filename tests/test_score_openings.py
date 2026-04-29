"""Tests for scripts/score_openings.py.

Covers:
  - perfect match (F1=1.0)
  - all FP (no GT)
  - all FN (no detection)
  - width mismatch rejects a match
  - center too far rejects a match
  - orientation mismatch rejects a match
  - mixed scenario (partial match, combined FP/FN)
  - YAML parsing from tmp_path
  - FN output carries the GT `notes` field
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make scripts/ importable
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from score_openings import (  # noqa: E402
    DetOpening,
    GTOpening,
    format_report,
    load_gt,
    match_openings,
)


def _det(
    opening_id: str,
    center: tuple[float, float],
    width: float = 50.0,
    orientation: str = "horizontal",
    kind: str = "door",
) -> DetOpening:
    return DetOpening(
        opening_id=opening_id,
        center=center,
        width=width,
        orientation=orientation,
        kind=kind,
    )


def _gt(
    gt_id: str,
    center: tuple[float, float],
    width: float = 50.0,
    orientation: str = "horizontal",
    kind: str = "door",
    notes: str = "",
) -> GTOpening:
    return GTOpening(
        gt_id=gt_id,
        center=center,
        width=width,
        orientation=orientation,
        kind=kind,
        notes=notes,
    )


def test_perfect_match() -> None:
    gts = [
        _gt("a", (100.0, 100.0), width=50.0),
        _gt("b", (200.0, 100.0), width=40.0),
        _gt("c", (100.0, 200.0), width=60.0, orientation="vertical"),
    ]
    dets = [
        _det("opening-1", (100.0, 100.0), width=50.0),
        _det("opening-2", (200.0, 100.0), width=40.0),
        _det("opening-3", (100.0, 200.0), width=60.0, orientation="vertical"),
    ]
    r = match_openings(gts, dets, thickness=6.25)
    assert r.tp_count == 3
    assert r.fp_count == 0
    assert r.fn_count == 0
    assert r.precision == pytest.approx(1.0)
    assert r.recall == pytest.approx(1.0)
    assert r.f1 == pytest.approx(1.0)


def test_all_false_positives() -> None:
    gts: list[GTOpening] = []
    dets = [
        _det("opening-1", (100.0, 100.0)),
        _det("opening-2", (200.0, 100.0)),
        _det("opening-3", (100.0, 200.0)),
    ]
    r = match_openings(gts, dets, thickness=6.25)
    assert r.tp_count == 0
    assert r.fp_count == 3
    assert r.fn_count == 0
    assert r.precision == pytest.approx(0.0)
    # recall denom=0 -> 0
    assert r.recall == pytest.approx(0.0)
    assert r.f1 == pytest.approx(0.0)


def test_all_false_negatives() -> None:
    gts = [
        _gt("a", (100.0, 100.0)),
        _gt("b", (200.0, 100.0)),
        _gt("c", (100.0, 200.0)),
    ]
    dets: list[DetOpening] = []
    r = match_openings(gts, dets, thickness=6.25)
    assert r.tp_count == 0
    assert r.fp_count == 0
    assert r.fn_count == 3
    assert r.precision == pytest.approx(0.0)
    assert r.recall == pytest.approx(0.0)
    assert r.f1 == pytest.approx(0.0)


def test_width_mismatch_rejects_match() -> None:
    """Same center/orientation but width 10 vs 30 (ratio 3.0 > 2.0): no match."""
    gts = [_gt("a", (100.0, 100.0), width=10.0)]
    dets = [_det("opening-1", (100.0, 100.0), width=30.0)]
    r = match_openings(gts, dets, thickness=6.25)
    assert r.tp_count == 0
    assert r.fp_count == 1
    assert r.fn_count == 1


def test_center_too_far_rejects_match() -> None:
    """Centers 20 px apart, thickness=6.25 -> tol=12.5. No match."""
    gts = [_gt("a", (100.0, 100.0), width=50.0)]
    dets = [_det("opening-1", (120.0, 100.0), width=50.0)]
    r = match_openings(gts, dets, thickness=6.25)
    assert r.tp_count == 0
    assert r.fp_count == 1
    assert r.fn_count == 1


def test_orientation_mismatch_rejects_match() -> None:
    gts = [_gt("a", (100.0, 100.0), width=50.0, orientation="horizontal")]
    dets = [_det("opening-1", (100.0, 100.0), width=50.0, orientation="vertical")]
    r = match_openings(gts, dets, thickness=6.25)
    assert r.tp_count == 0
    assert r.fp_count == 1
    assert r.fn_count == 1


def test_mixed_scenario() -> None:
    """GT=4, DET=5. 3 match, 1 GT unmatched (FN), 2 DET unmatched (FP).

    Expected:
      P = 3 / (3 + 2) = 0.6
      R = 3 / (3 + 1) = 0.75
      F1 = 2*0.6*0.75 / (0.6 + 0.75) = 0.9 / 1.35 ~= 0.6667
    """
    gts = [
        _gt("a", (100.0, 100.0), width=50.0),
        _gt("b", (200.0, 100.0), width=50.0),
        _gt("c", (300.0, 100.0), width=50.0),
        # FN: no detection near this one
        _gt("d", (900.0, 900.0), width=50.0),
    ]
    dets = [
        _det("opening-1", (100.0, 100.0), width=50.0),                 # matches a
        _det("opening-2", (200.0, 100.0), width=50.0),                 # matches b
        _det("opening-3", (300.0, 100.0), width=50.0),                 # matches c
        _det("opening-4", (500.0, 500.0), width=50.0),                 # FP
        _det("opening-5", (600.0, 600.0), width=50.0),                 # FP
    ]
    r = match_openings(gts, dets, thickness=6.25)
    assert r.tp_count == 3
    assert r.fp_count == 2
    assert r.fn_count == 1
    assert r.precision == pytest.approx(0.6)
    assert r.recall == pytest.approx(0.75)
    assert r.f1 == pytest.approx(0.6666666667, rel=1e-4)


def test_yaml_parsing(tmp_path: Path) -> None:
    gt_path = tmp_path / "gt.yaml"
    gt_path.write_text(
        """meta:
  source: "planta_74m2.svg"
  thickness: 6.25
  annotator: "felipe"
openings:
  - id: entrance
    center: [200.0, 215.0]
    width: 46.0
    orientation: horizontal
    kind: door
    notes: "porta de entrada"
  - id: suite_window
    center: [240.0, 280.0]
    width: 40.0
    orientation: horizontal
    kind: window
    notes: "janela suite"
""",
        encoding="utf-8",
    )
    thickness, gts = load_gt(gt_path)
    assert thickness == pytest.approx(6.25)
    assert len(gts) == 2
    assert gts[0].gt_id == "entrance"
    assert gts[0].center == (200.0, 215.0)
    assert gts[0].width == pytest.approx(46.0)
    assert gts[0].orientation == "horizontal"
    assert gts[0].kind == "door"
    assert gts[0].notes == "porta de entrada"
    assert gts[1].gt_id == "suite_window"
    assert gts[1].kind == "window"


def test_reports_notes_in_fn_output() -> None:
    gts = [
        _gt("suite_window", (240.0, 280.0), width=40.0,
            orientation="horizontal", notes="janela suite"),
    ]
    dets: list[DetOpening] = []
    r = match_openings(gts, dets, thickness=6.25)
    report = format_report(
        result=r,
        model_path=Path("m.json"),
        gt_path=Path("gt.yaml"),
        thickness=6.25,
        center_tol_mul=2.0,
        det_count=0,
        gt_count=1,
    )
    assert "suite_window" in report
    assert 'notes="janela suite"' in report
