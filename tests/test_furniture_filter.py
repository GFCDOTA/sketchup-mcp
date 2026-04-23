"""Adversarial tests for the F12 semantic furniture / legend filter.

The filter operates on ``WallCandidate`` inputs inside
``classify.service._filter_furniture_components``. Two signatures are
tested: small orphan connected components (furniture / pictograms) and
dense parallel short-stroke clusters (hachura). Real architectural
walls, long isolated walls, and walls participating in a larger
connected graph must all be preserved.

Integration coverage also runs the real ``p12_red.pdf`` and
``planta_74.pdf`` samples to pin the filter against regressions on the
calibrated baselines.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from classify.service import (
    _FURNITURE_ACTIVATION_MIN_COUNT,
    _filter_furniture_components,
)
from model.types import WallCandidate


def _h(
    x0: float,
    x1: float,
    y: float,
    *,
    page: int = 0,
    thickness: float = 2.0,
) -> WallCandidate:
    return WallCandidate(
        page_index=page,
        start=(x0, y),
        end=(x1, y),
        thickness=thickness,
        source="test_h",
        confidence=1.0,
    )


def _v(
    y0: float,
    y1: float,
    x: float,
    *,
    page: int = 0,
    thickness: float = 2.0,
) -> WallCandidate:
    return WallCandidate(
        page_index=page,
        start=(x, y0),
        end=(x, y1),
        thickness=thickness,
        source="test_v",
        confidence=1.0,
    )


def test_small_orphan_component_is_filtered() -> None:
    # Three connected walls forming a tiny U (bbox 50x50 < 80px) with no
    # connection to anything else. Classic furniture pictogram silhouette.
    furniture = [
        _h(x0=100, x1=150, y=100),   # top of U
        _v(y0=100, y1=150, x=100),   # left side
        _v(y0=100, y1=150, x=150),   # right side
    ]
    kept = _filter_furniture_components(furniture)
    assert kept == [], [(c.start, c.end) for c in kept]


def test_large_orphan_single_wall_is_kept() -> None:
    # A single isolated long wall (e.g. external boundary) that nothing
    # else touches. Must survive: it's not a "compact" component and it
    # alone should not be misclassified as furniture regardless of how
    # isolated it is.
    lonely = [_h(x0=10, x1=410, y=50)]  # 400px long
    kept = _filter_furniture_components(lonely)
    assert kept == lonely


def test_dense_parallel_strokes_are_filtered() -> None:
    # Eight short horizontal strokes at 3px vertical spacing, each 20px
    # long — decorative hachura (legend fill, floor pattern). Window
    # width 50px easily catches them all. Pass 2 must drop every short
    # stroke inside the window.
    hachura = [_h(x0=10, x1=30, y=100 + k * 3) for k in range(8)]
    kept = _filter_furniture_components(hachura)
    assert kept == [], [(c.start, c.end) for c in kept]


def test_p12_no_false_positive_furniture() -> None:
    # Integration pin: p12_red.pdf pipeline must not lose any wall to
    # this filter, AND the topology snapshot hash must match the F11
    # baseline. If this regresses, the filter's activation gate is too
    # loose or its diagonal threshold is too permissive.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from model.pipeline import run_pdf_pipeline

    root = Path(__file__).resolve().parents[1]
    pdf_path = root / "runs" / "proto" / "p12_red.pdf"
    peitoris_path = root / "runs" / "proto" / "p12_peitoris.json"
    if not pdf_path.exists() or not peitoris_path.exists():
        pytest.skip("p12_red.pdf fixtures not present")

    out_dir = root / "runs" / "_tmp_f12_p12_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    peitoris = json.loads(peitoris_path.read_text(encoding="utf-8"))
    run_pdf_pipeline(
        pdf_bytes=pdf_path.read_bytes(),
        filename="p12_red.pdf",
        output_dir=out_dir,
        peitoris=peitoris,
    )
    obs = json.loads((out_dir / "observed_model.json").read_text(encoding="utf-8"))
    expected_hash = (
        "39b4138f4fd5613ed897824657b0329445d2eb332a6a1d810da75933ba4b5ce3"
    )
    assert obs["metadata"]["topology_snapshot_sha256"] == expected_hash
    assert len(obs["walls"]) == 33
    # F6 dedup absorbs room-17 (3-vertex sliver) into its largest
    # neighbour, taking p12 from 19 to 18 legitimate rooms. The
    # topology hash stays frozen because walls/junctions are unchanged.
    assert len(obs["rooms"]) == 18


def test_planta_74_orphan_count_drops() -> None:
    # Integration pin: planta_74.pdf pipeline reports orphan_node_count
    # of at most 1 after F12. Baseline on the branch already hits 0
    # because the upstream dedup chain is strong; F12 must not regress
    # this (i.e. it must not orphan previously-connected walls by
    # dropping architectural strokes).
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from model.pipeline import run_pdf_pipeline

    root = Path(__file__).resolve().parents[1]
    pdf_path = root / "planta_74.pdf"
    if not pdf_path.exists():
        pytest.skip("planta_74.pdf fixture not present")

    out_dir = root / "runs" / "_tmp_f12_planta_74_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_pdf_pipeline(
        pdf_bytes=pdf_path.read_bytes(),
        filename="planta_74.pdf",
        output_dir=out_dir,
        peitoris=None,
    )
    connectivity = json.loads(
        (out_dir / "connectivity_report.json").read_text(encoding="utf-8")
    )
    assert connectivity["orphan_node_count"] <= 1, connectivity


def test_connected_large_wall_not_filtered() -> None:
    # Short architectural walls can exist (e.g. bathroom jambs), but
    # they always live in a larger connected graph. Here, a 40px wall
    # segment participates in an 8-member connected component spanning
    # over 300px; Pass 1 ignores this because member count exceeds
    # _FURNITURE_ORPHAN_MAX_MEMBERS, and Pass 2 ignores it because no
    # dense parallels surround it. The short wall must survive.
    architectural = [
        # Outer square roughly 300x300
        _h(x0=0, x1=300, y=0),
        _h(x0=0, x1=300, y=300),
        _v(y0=0, y1=300, x=0),
        _v(y0=0, y1=300, x=300),
        # Internal short walls forming room subdivisions, all endpoint-
        # connected to the outer walls.
        _v(y0=0, y1=40, x=150),         # 40px short wall - connected at top
        _h(x0=150, x1=190, y=40),       # connected at (150,40)
        _v(y0=40, y1=80, x=190),        # connected at (190,40)
        _h(x0=150, x1=190, y=80),       # closes an inner polygon
    ]
    kept = _filter_furniture_components(architectural)
    # All 8 stay: the short 40px vertical at x=150 must survive.
    assert len(kept) == 8, [(c.start, c.end) for c in kept]
    # And specifically the short wall.
    assert any(
        c.start == (150.0, 0.0) and c.end == (150.0, 40.0) for c in kept
    )


def test_activation_gate_constant_is_reasonable() -> None:
    # Guard: the activation gate must stay above typical clean-input
    # candidate counts (p12-style inputs end up around 40 candidates at
    # the F12 stage). If someone drops the gate too low, clean inputs
    # would enter the filter and could regress the p12 snapshot hash.
    assert _FURNITURE_ACTIVATION_MIN_COUNT >= 100
