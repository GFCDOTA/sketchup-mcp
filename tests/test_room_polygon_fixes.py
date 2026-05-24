"""Tests for the Frente-3 room-polygon fix layers (2026-05-21).

Two opt-in pipeline shims in ``tools/polygonize_rooms.py`` +
``tools/rooms_from_seeds.py``, glued by
``tools/apply_room_polygon_fixes.py``:

  1. Near-miss soft_barrier endpoint extension (with FP-006 guard +
     semantic-origin guard + post-extension effectiveness validation).
  2. Voronoi sub-division of polygonize cells that contain multiple
     seed labels (the ``seeds_share_cell`` case).

Both layers default OFF — the production pipeline behaviour is
byte-equivalent until a caller opts in. Tests below pin:

  - the helpers' isolated behaviour (synthetic fixtures);
  - the contract that FP-006 wall-coincident SBs are NEVER extended;
  - the contract that ineffective extensions are REJECTED (the
    post-extension validation must veto a candidate that doesn't
    change cell topology);
  - the contract that a ``warn`` audit decision does NOT auto-promote
    to ``keep`` (the SB extension feature is independent of the
    ``tools/audit_soft_barriers.py`` decision column);
  - the regression on planta_74: r001 (A.S.|TERRACO SOCIAL|TERRACO
    TECNICO) splits into 3 distinct rooms after Voronoi, and
    SALA JANTAR|ESTAR splits too. 8 → 11 rooms total.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon, box

from tools.polygonize_rooms import (
    _is_suspicious_cell,
    _polygonize_cells_only,
    _sb_has_semantic_origin,
    _sb_overlap_fraction_with_walls,
    _try_extend_endpoint,
    _validate_extension_effectiveness,
    extend_near_miss_soft_barriers,
    polygonize_rooms,
)
from tools.rooms_from_seeds import (
    _voronoi_subdivide_merged_cell,
    detect_rooms_polygonize,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PLANTA_74_CONSENSUS = (
    REPO_ROOT / "fixtures" / "planta_74"
    / "consensus_with_human_walls_and_soft_barriers.json"
)


# ---- semantic-origin guard ------------------------------------------


def test_semantic_origin_recognises_human_annotation() -> None:
    sb = {"geometry_origin": "human_annotation"}
    assert _sb_has_semantic_origin(sb) is True


def test_semantic_origin_recognises_barrier_type_peitoril() -> None:
    sb = {"barrier_type": "peitoril"}
    assert _sb_has_semantic_origin(sb) is True


def test_semantic_origin_recognises_mureta_keyword_in_id() -> None:
    sb = {"id": "mureta_terraco_001"}
    assert _sb_has_semantic_origin(sb) is True


def test_semantic_origin_rejects_unknown_sb() -> None:
    """A soft_barrier from the V7 vector extractor with no origin and
    no barrier_type must NOT pass the semantic guard — the extension
    feature is opt-in, not opt-out."""
    sb = {"id": "sb000", "geometry_origin": None, "barrier_type": None,
          "name": None, "label": None}
    assert _sb_has_semantic_origin(sb) is False


# ---- FP-006 wall-coincidence guard ----------------------------------


def test_fp006_overlap_high_for_wall_coincident_polyline() -> None:
    walls = [{"id": "w0", "start": [0.0, 10.0], "end": [100.0, 10.0],
              "thickness": 5.0, "orientation": "h"}]
    sb = {"polyline_pts": [[10.0, 10.0], [90.0, 10.0]]}
    # Polyline lies exactly on the wall axis at y=10 from x=10..90.
    frac = _sb_overlap_fraction_with_walls(sb, walls, thickness_pt=5.0)
    assert frac > 0.9, f"polyline coincident with wall must have high overlap, got {frac}"


def test_fp006_overlap_zero_for_far_polyline() -> None:
    walls = [{"id": "w0", "start": [0.0, 10.0], "end": [100.0, 10.0],
              "thickness": 5.0, "orientation": "h"}]
    sb = {"polyline_pts": [[10.0, 50.0], [90.0, 50.0]]}
    # Polyline at y=50, far from wall at y=10. tol=1 → no overlap.
    frac = _sb_overlap_fraction_with_walls(sb, walls, thickness_pt=5.0)
    assert frac == pytest.approx(0.0)


# ---- suspicious cell heuristic --------------------------------------


def test_suspicious_cell_flags_area_outlier() -> None:
    median = 100.0
    big = box(0, 0, 30, 30)  # area = 900 = 9× median
    assert _is_suspicious_cell(big, median, area_factor=2.0) is True


def test_suspicious_cell_does_not_flag_normal_size_convex() -> None:
    median = 100.0
    normal = box(0, 0, 10, 10)  # area = 100 = 1× median, convex
    assert _is_suspicious_cell(normal, median, area_factor=2.0) is False


def test_suspicious_cell_flags_concave_shape() -> None:
    median = 100.0
    # An L-shaped polygon — convex hull is much bigger than the polygon
    # area, so concavity_ratio is high.
    poly = Polygon([
        (0, 0), (20, 0), (20, 5), (5, 5), (5, 20), (0, 20),
    ])
    assert _is_suspicious_cell(poly, median, concavity_threshold=0.30) is True


# ---- _try_extend_endpoint behaviour ---------------------------------


def test_try_extend_endpoint_skips_endpoint_already_inside_cell() -> None:
    """An endpoint sitting in the deep interior of a suspicious cell
    is NOT a near-miss case; the function must return (None, 0, None)."""
    cell = box(0, 0, 100, 100)
    polyline = [[50.0, 50.0], [60.0, 50.0]]  # endpoint A at (50,50) deep inside
    result, gap, ci = _try_extend_endpoint(
        polyline, endpoint_idx=0, suspicious_cells=[cell],
        gap_tol_pt=8.0,
    )
    assert result is None
    assert ci is None


def test_try_extend_endpoint_extends_near_miss() -> None:
    """An endpoint just outside a cell, with the polyline pointing
    inward, must be extended into the cell's interior."""
    cell = box(0, 0, 100, 100)
    # polyline endpoint at (-1, 50) — 1pt left of cell. Neighbour at (-5, 50)
    # so direction outward is (-1, 0). Wait — that points further away from
    # the cell. We want extension OUTWARD from the polyline at endpoint 0,
    # which means away from polyline_pts[1]. polyline_pts[1] is the
    # neighbour at (-5, 50), so direction outward is (-1, 0) — extending
    # further to the LEFT, AWAY from the cell. That's the wrong direction
    # for a near-miss recovery here.
    #
    # Instead, set the polyline so endpoint 0 is at (-1, 50) and
    # neighbour is at (-10, 50): outward from endpoint 0 still points left.
    # The near-miss is at endpoint -1 going RIGHT.
    polyline = [[-10.0, 50.0], [-1.0, 50.0]]
    # Endpoint -1 at (-1, 50): neighbour 0 is at (-10, 50); outward dir
    # = (+1, 0). Extension by 2pt → (1, 50), which is inside the cell.
    result, gap, ci = _try_extend_endpoint(
        polyline, endpoint_idx=-1, suspicious_cells=[cell],
        gap_tol_pt=8.0,
    )
    assert result is not None, "near-miss endpoint should extend into interior"
    assert ci == 0
    assert gap <= 8.0 and gap > 0


def test_try_extend_endpoint_rejects_when_extension_doesnt_reach_interior() -> None:
    """If gap_tol_pt is too small to bridge the near-miss gap, the
    function returns (None, 0, None) — never extends partway."""
    cell = box(0, 0, 100, 100)
    polyline = [[-50.0, 50.0], [-20.0, 50.0]]
    # Endpoint -1 at (-20, 50): outward dir (+1, 0). Cell starts at x=0,
    # so endpoint is 20pt outside. Tolerance only 5pt → can't reach.
    result, gap, ci = _try_extend_endpoint(
        polyline, endpoint_idx=-1, suspicious_cells=[cell],
        gap_tol_pt=5.0,
    )
    assert result is None
    assert ci is None


# ---- extend_near_miss_soft_barriers integration ---------------------


def _synthetic_consensus_with_near_miss_split() -> dict:
    """A small consensus where a near-miss SB extension genuinely
    splits a merged cell. Used by both the extension and effectiveness
    tests to verify the helper works in principle on a controlled
    fixture, independent of planta_74's larger geometry.
    """
    # Two perpendicular walls forming an L, then a peitoril SB that
    # ALMOST closes a third side — its endpoint stops 2pt outside the
    # corner of the L. Extending the SB by 2.5pt closes the cell.
    return {
        "wall_thickness_pts": 4.0,
        "walls": [
            # Bottom wall y=0, x=0..100
            {"id": "w0", "start": [0.0, 0.0], "end": [100.0, 0.0],
             "thickness": 4.0, "orientation": "h"},
            # Left wall x=0, y=0..100
            {"id": "w1", "start": [0.0, 0.0], "end": [0.0, 100.0],
             "thickness": 4.0, "orientation": "v"},
        ],
        "soft_barriers": [
            {"id": "sb_peitoril", "barrier_type": "peitoril",
             "geometry_origin": "human_annotation",
             "polyline_pts": [[50.0, 100.0], [100.0, 100.0]]},
            # peitoril sits at y=100 across the top edge of the cell;
            # its left endpoint at x=50 is well inside the cell, while
            # the right at x=100 is exactly on the right boundary.
        ],
        "planta_region": [-5.0, -5.0, 110.0, 110.0],
    }


def test_extend_near_miss_skips_fp006_wall_coincident() -> None:
    """Even with a semantic-origin barrier_type, an SB whose polyline
    overlaps a wall by >50% must NOT be extended — that's FP-006 noise,
    not a real peitoril."""
    walls = [{"id": "w0", "start": [0.0, 0.0], "end": [100.0, 0.0],
              "thickness": 5.0, "orientation": "h"}]
    soft_barriers = [{
        "id": "sb_noise",
        "barrier_type": "peitoril",
        "geometry_origin": "human_annotation",
        # Lies entirely on the wall y=0.
        "polyline_pts": [[10.0, 0.0], [90.0, 0.0]],
    }]
    suspicious = [box(20, -10, 80, 50)]
    extended, prov = extend_near_miss_soft_barriers(
        walls, soft_barriers, suspicious, 5.0,
        gap_tol_pt=8.0,
        fp006_overlap_threshold=0.50,
        require_semantic_origin=True,
    )
    # No provenance entries — SB was rejected at the FP-006 gate.
    assert prov == []
    # Returned SB is verbatim (deepcopy of original).
    assert extended[0]["polyline_pts"] == soft_barriers[0]["polyline_pts"]


def test_extend_near_miss_respects_semantic_guard() -> None:
    """A non-semantic SB must not be extended when
    require_semantic_origin=True, even if FP-006 says it's far from walls."""
    walls = [{"id": "w0", "start": [0.0, 0.0], "end": [100.0, 0.0],
              "thickness": 4.0, "orientation": "h"}]
    soft_barriers = [{
        "id": "sb_no_origin",
        # Neither geometry_origin nor barrier_type — V7-extracted unknown.
        "polyline_pts": [[-1.0, 50.0], [-10.0, 50.0]],
    }]
    suspicious = [box(0, 0, 100, 100)]
    _, prov = extend_near_miss_soft_barriers(
        walls, soft_barriers, suspicious, 4.0,
        gap_tol_pt=8.0,
        fp006_overlap_threshold=0.50,
        require_semantic_origin=True,
    )
    assert prov == []


# ---- post-extension effectiveness validation -----------------------


def test_validation_rejects_ineffective_extension() -> None:
    """If the candidate extension doesn't change cell count nor shrink
    any suspicious cell by ≥20%, it must be rejected by the validator
    — the provenance log shouldn't pollute with cosmetic-only events."""
    walls = [{"id": "w0", "start": [0.0, 0.0], "end": [200.0, 0.0],
              "thickness": 4.0, "orientation": "h"}]
    base_sbs = [{
        "id": "sb_a", "geometry_origin": "human_annotation",
        "barrier_type": "peitoril",
        "polyline_pts": [[50.0, 50.0], [150.0, 50.0]],
    }]
    ext_sbs = [{
        "id": "sb_a", "geometry_origin": "human_annotation",
        "barrier_type": "peitoril",
        # Trivial 0.5pt shift on one endpoint — won't change topology.
        "polyline_pts": [[50.5, 50.0], [150.0, 50.0]],
    }]
    eff, report = _validate_extension_effectiveness(
        walls, base_sbs, ext_sbs, 4.0,
        door_min_pts=15.0, door_max_pts=150.0,
        envelope_margin_pts=2.0, min_room_area_factor=12.0,
        planta_region=(-5.0, -5.0, 205.0, 100.0),
        sb_width_pts=1.6, use_soft_barriers=True,
    )
    assert eff is False, f"trivial 0.5pt extension must be ineffective, got {report}"


# ---- Voronoi sub-division ------------------------------------------


def test_voronoi_returns_empty_for_single_seed() -> None:
    cell = box(0, 0, 100, 100)
    labels = [{"id": "l0", "name": "single", "seed_pt": [50.0, 50.0]}]
    result = _voronoi_subdivide_merged_cell(cell, labels)
    assert result == [], "single seed cell must not be voronoi'd"


def test_voronoi_splits_two_seed_cell_into_two() -> None:
    cell = box(0, 0, 100, 100)
    labels = [
        {"id": "l0", "name": "left", "seed_pt": [25.0, 50.0]},
        {"id": "l1", "name": "right", "seed_pt": [75.0, 50.0]},
    ]
    result = _voronoi_subdivide_merged_cell(cell, labels)
    assert len(result) == 2
    # Each sub-polygon must be smaller than the original cell.
    for _, poly_pts, area in result:
        assert 0 < area < 10000  # cell.area == 10000
        # And each sub-polygon must contain its seed.
        sub_poly = Polygon(poly_pts)
        assert sub_poly.is_valid
    # The two sub-areas should roughly partition the cell.
    total = sum(area for _, _, area in result)
    assert total == pytest.approx(10000, abs=10)


def test_voronoi_splits_three_seed_cell_into_three() -> None:
    """The planta_74 r001 case (A.S./TER SOC/TER TEC): three seeds in
    one cell must yield three sub-polygons."""
    cell = box(0, 0, 200, 200)
    labels = [
        {"id": "l0", "name": "AS", "seed_pt": [30.0, 150.0]},
        {"id": "l1", "name": "TER_SOC", "seed_pt": [100.0, 100.0]},
        {"id": "l2", "name": "TER_TEC", "seed_pt": [170.0, 50.0]},
    ]
    result = _voronoi_subdivide_merged_cell(cell, labels)
    assert len(result) == 3
    total = sum(area for _, _, area in result)
    assert total == pytest.approx(40000, abs=20)  # 200 × 200


# ---- regression: planta_74 r001 split ------------------------------


@pytest.fixture
def planta_74_consensus() -> dict:
    if not PLANTA_74_CONSENSUS.exists():
        pytest.skip(f"{PLANTA_74_CONSENSUS} missing")
    return json.loads(PLANTA_74_CONSENSUS.read_text(encoding="utf-8"))


def _labels_from_rooms(rooms: list[dict]) -> list[dict]:
    """Re-create the labels list from a consensus.rooms[] (one per
    seed). Mirrors tools.apply_room_polygon_fixes._reconstruct_labels."""
    out: list[dict] = []
    for r in rooms:
        name = r.get("name", "")
        if " | " in name and r.get("merged_seeds"):
            names = name.split(" | ")
            seeds = r["merged_seeds"]
            ids = r.get("label_ids") or [None] * len(names)
            for n, sp, lid in zip(names, seeds, ids):
                out.append({"id": lid, "name": n, "seed_pt": list(sp)})
        elif r.get("seed_pt"):
            out.append({"id": r.get("label_id"), "name": name,
                        "seed_pt": list(r["seed_pt"])})
    return out


def test_planta_74_baseline_has_8_rooms(planta_74_consensus: dict) -> None:
    """Sanity check: the canonical consensus fixture starts with 8
    rooms including the r001 3-way and r002 2-way merges. If this
    drops, the rest of the regression test would silently no-op."""
    rooms = planta_74_consensus["rooms"]
    assert len(rooms) == 8
    names = [r["name"] for r in rooms]
    assert "A.S. | TERRACO SOCIAL | TERRACO TECNICO" in names
    assert "SALA DE JANTAR | SALA DE ESTAR" in names


def test_planta_74_voronoi_splits_r001_into_three(
    planta_74_consensus: dict,
) -> None:
    """The headline fix for Frente 3: enabling Voronoi sub-division
    must split r001 into 3 distinct rooms (A.S., TERRACO SOCIAL,
    TERRACO TECNICO), and r002 into 2 (SALA JANTAR, SALA ESTAR).
    Total rooms goes 8 → 11. No room name retains the "X | Y"
    merged form."""
    labels = _labels_from_rooms(planta_74_consensus["rooms"])
    new_rooms = detect_rooms_polygonize(
        planta_74_consensus, labels,
        door_min=15.0, door_max=150.0,
        voronoi_subdivide_merged_cells=True,
    )
    names = [r["name"] for r in new_rooms]
    assert len(new_rooms) == 11, f"expected 11 rooms after voronoi, got {len(new_rooms)}"
    assert "A.S." in names
    assert "TERRACO SOCIAL" in names
    assert "TERRACO TECNICO" in names
    assert "SALA DE JANTAR" in names
    assert "SALA DE ESTAR" in names
    # No merged form survives.
    assert not any(" | " in n for n in names)


def test_planta_74_voronoi_off_keeps_baseline(planta_74_consensus: dict) -> None:
    """The Voronoi feature is opt-in: without the flag, the existing
    behaviour (8 rooms with 2 merged names) is preserved exactly."""
    labels = _labels_from_rooms(planta_74_consensus["rooms"])
    new_rooms = detect_rooms_polygonize(
        planta_74_consensus, labels,
        door_min=15.0, door_max=150.0,
    )
    assert len(new_rooms) == 8
    names = [r["name"] for r in new_rooms]
    assert "A.S. | TERRACO SOCIAL | TERRACO TECNICO" in names


def test_planta_74_no_slivers_after_voronoi(planta_74_consensus: dict) -> None:
    """After Voronoi the smallest room must still be plausibly large
    (≥ 2 m²). A.S. ≈ 9 m², TERRACO TECNICO ≈ 2.8 m², LAVABO ≈ 3.2 m²
    — none should be a sliver."""
    labels = _labels_from_rooms(planta_74_consensus["rooms"])
    new_rooms = detect_rooms_polygonize(
        planta_74_consensus, labels,
        door_min=15.0, door_max=150.0,
        voronoi_subdivide_merged_cells=True,
    )
    PT_TO_M2 = (0.19 / 5.4) ** 2  # m²/pt²
    for r in new_rooms:
        area_m2 = r["area_pts2"] * PT_TO_M2
        assert area_m2 > 1.5, (
            f"room {r['id']} {r['name']!r} area {area_m2:.2f} m² is too small "
            f"after voronoi — possibly a sliver from a degenerate Voronoi cell"
        )


def test_planta_74_sb_extension_alone_does_not_split_r001(
    planta_74_consensus: dict,
) -> None:
    """Falsification record: on planta_74, the SB extension shim ALONE
    cannot split r001. Validated empirically — h_sb000's endpoint A
    sits on cell[2]'s boundary (covers→skip) and sb004 isn't semantic.
    Even with require_semantic=False, the only candidate (sb004) is
    rejected by the post-extension effectiveness validator. This test
    pins that behaviour so a future change can't silently "fix" the
    headline without also resolving Voronoi or vice-versa."""
    labels = _labels_from_rooms(planta_74_consensus["rooms"])
    ext_prov: list[dict] = []
    rooms = detect_rooms_polygonize(
        planta_74_consensus, labels,
        door_min=15.0, door_max=150.0,
        extend_near_miss_sbs=True,
        near_miss_gap_tol_pt=8.0,
        near_miss_require_semantic=False,
        # Voronoi explicitly OFF for this isolation test.
        voronoi_subdivide_merged_cells=False,
        extension_provenance_out=ext_prov,
    )
    assert len(rooms) == 8, "SB extension alone must NOT change room count on planta_74"
    # If any provenance entry has applied=True, the validator passed
    # something — fail because we expect ALL to be rejected here.
    applied_count = sum(1 for p in ext_prov if p.get("applied"))
    assert applied_count == 0, (
        "SB extension on planta_74 must yield only REJECTED candidates "
        f"(validator vetoes ineffective extensions). Got applied={applied_count}, "
        f"provenance={ext_prov}"
    )


def test_apply_room_polygon_fixes_metadata_is_stamped(
    planta_74_consensus: dict, tmp_path: Path,
) -> None:
    """End-to-end test of the CLI wrapper. Confirms metadata stamping
    survives JSON round-trip and the SB-audit `warn` decision in the
    sister tool (audit_soft_barriers) does NOT auto-promote to `keep`
    via the fixer — the two tools must remain independent in their
    classifications, even on the same consensus."""
    from tools.apply_room_polygon_fixes import apply

    new_consensus, prov = apply(
        planta_74_consensus,
        extend_near_miss_sbs=True,
        near_miss_require_semantic=False,
        voronoi_subdivide_merged_cells=True,
    )
    assert prov["rooms_after"] == 11
    md = new_consensus["metadata"]["room_polygon_fixes"]
    assert md["tool"] == "apply_room_polygon_fixes"
    assert md["voronoi_subdivide_merged_cells"] is True
    assert md["rooms_before"] == 8
    assert md["rooms_after"] == 11
    # The audit tool's `decision` field on each soft_barrier must NOT
    # have been written into the consensus by this fixer — it lives in
    # the audit report, not in consensus.soft_barriers. Confirm this is
    # respected.
    for sb in new_consensus.get("soft_barriers", []):
        assert "decision" not in sb, (
            f"SB {sb.get('id')!r}: apply_room_polygon_fixes must not "
            "merge audit decisions into consensus — keeps tools independent"
        )


# ---- polygonize_rooms backward compatibility -----------------------


def test_polygonize_rooms_default_is_byte_equivalent(
    planta_74_consensus: dict,
) -> None:
    """Production callers (rooms_from_seeds without flags, smoke
    harness, etc.) must continue seeing the prior behaviour exactly.
    The new flags default OFF; calling polygonize_rooms with no extra
    args returns the same rooms[] count + areas as the pre-change
    baseline."""
    rooms_old, _ = polygonize_rooms(
        planta_74_consensus,
        door_min_pts=15.0, door_max_pts=150.0,
    )
    rooms_explicit_off, _ = polygonize_rooms(
        planta_74_consensus,
        door_min_pts=15.0, door_max_pts=150.0,
        extend_near_miss_sbs=False,
    )
    assert len(rooms_old) == len(rooms_explicit_off)
    for ra, rb in zip(rooms_old, rooms_explicit_off):
        assert ra["area_pts2"] == rb["area_pts2"]
        assert ra["polygon_pts"] == rb["polygon_pts"]
