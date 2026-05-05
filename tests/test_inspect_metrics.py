"""Tests for `tools.inspect_metrics` — fidelity signature extraction.

Uses synthetic JSON fixtures that mirror the real shape produced by
`tools/inspect_walls_report.rb` (see
`runs/skp_current_20260504T215920Z/inspect_report.json` for a real
example). No SU launch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.inspect_metrics import FidelityMetrics, compare


@pytest.fixture
def clean_report() -> dict:
    """Mirror of the post-fix planta_74 inspect output (2026-05-04)."""
    return {
        "default_faces_count": 0,
        "materials": [
            {"name": "wall_dark", "color": [78, 78, 78, 255]},
            {"name": "parapet",   "color": [130, 135, 140, 255]},
            *[{"name": f"room_r{i:03d}", "color": [200, 200, 200, 255]}
              for i in range(11)],
        ],
        "groups": [{"name": f"w{i:03d}", "layer": "walls"} for i in range(33)]
                  + [{"name": f"r{i}", "layer": "rooms"} for i in range(11)]
                  + [{"name": f"o{i}", "layer": "walls"} for i in range(12)]
                  + [{"name": f"p{i}", "layer": "parapets"} for i in range(8)],
        "wall_overlaps_top20": [],
        "components": [],
        "totals": {"faces": 395},
    }


@pytest.fixture
def stale_report() -> dict:
    """Mirror of the pre-fix planta_74 (2026-05-02 triplication state)."""
    return {
        "default_faces_count": 1140,
        "materials": [
            {"name": "wall_dark"},
            {"name": "wall_dark1"},   # triplication rename
            {"name": "wall_dark2"},
            {"name": "Sree_Hair"},    # template figure leak
            {"name": "Sree_Watch_1"},
            *[{"name": f"room_r{i}"} for i in range(11)],
        ],
        "groups": [{"name": f"w{i:03d}"} for i in range(99)],  # 33 × 3
        "wall_overlaps_top20": [
            {"left": "w002", "right": "w002"},
            {"left": "w002", "right": "w002"},
            {"left": "w031", "right": "w031"},
        ],
        "components": [{"name": "", "definition": "Sree"}],
        "totals": {"faces": 1855},
    }


def test_clean_report_is_clean(clean_report: dict) -> None:
    m = FidelityMetrics.from_dict(clean_report)
    assert m.is_clean() is True
    assert m.default_faces_count == 0
    assert m.materials_count == 13
    assert m.wall_overlaps_count == 0
    assert m.components_count == 0
    assert m.groups_count == 64
    assert m.faces_count == 395
    assert m.wall_dark_variant_count == 0
    assert m.sree_material_count == 0


def test_stale_report_is_not_clean(stale_report: dict) -> None:
    m = FidelityMetrics.from_dict(stale_report)
    assert m.is_clean() is False
    assert m.default_faces_count == 1140
    assert m.wall_dark_variant_count == 2  # wall_dark1, wall_dark2
    assert m.sree_material_count == 2      # Sree_Hair, Sree_Watch_1
    assert m.wall_overlaps_count == 3
    assert m.components_count == 1
    assert m.groups_count == 99            # triplication


def test_compare_surfaces_deltas(stale_report: dict, clean_report: dict) -> None:
    b = FidelityMetrics.from_dict(stale_report)
    a = FidelityMetrics.from_dict(clean_report)
    delta = compare(b, a)
    assert delta["default_faces_count"]["delta"] == -1140
    assert delta["wall_overlaps_count"]["delta"] == -3
    assert delta["components_count"]["delta"] == -1
    assert delta["wall_dark_variant_count"]["delta"] == -2
    assert delta["sree_material_count"]["delta"] == -2
    # ALL fields decrease or stay equal — no fidelity regression
    assert all(v["delta"] <= 0 for v in delta.values()), delta


def test_from_inspect_report_round_trips(
    tmp_path: Path, clean_report: dict
) -> None:
    p = tmp_path / "inspect_report.json"
    p.write_text(json.dumps(clean_report), encoding="utf-8")
    m = FidelityMetrics.from_inspect_report(p)
    assert m.is_clean() is True


def test_real_inspect_report_if_available() -> None:
    """If the live post-fix inspect lives on disk, parse it and assert clean."""
    repo = Path(__file__).resolve().parent.parent
    candidates = sorted(repo.glob("runs/skp_current_*/inspect_report.json"))
    if not candidates:
        pytest.skip("no live inspect_report.json under runs/skp_current_*")
    latest = candidates[-1]
    m = FidelityMetrics.from_inspect_report(latest)
    assert m.default_faces_count == 0, (
        f"{latest}: default_faces_count={m.default_faces_count} "
        f"-> whiteness regression!"
    )
    assert m.wall_overlaps_count == 0, (
        f"{latest}: wall_overlaps_count={m.wall_overlaps_count} "
        f"-> triplication regression!"
    )
    assert m.wall_dark_variant_count == 0, (
        f"{latest}: wall_dark variants={m.wall_dark_variant_count} "
        f"-> reset_model regression!"
    )
    assert m.sree_material_count == 0, (
        f"{latest}: Sree mats={m.sree_material_count} "
        f"-> template figure leak!"
    )
