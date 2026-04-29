"""Unit tests for classify.service._dedupe_collinear_overlapping.

Exercises the representative-anchored clustering that runs after the
perpendicular-cluster consolidation when the dedup activation gate
fires (``_dedup_activation_ratio(strokes) >= _DEDUP_ACTIVATION_RATIO``
inside ``classify_walls``). Its job is to collapse Hough twin
detections of the same physical stroke whose perpendicular offset
escaped the consolidation tolerance AND whose parallel ranges overlap
heavily.

The tests call the function directly so the activation gate does not
interfere with the invariants under test. End-to-end coverage of the
gate + dedup combo lives in ``tests/test_planta_74_regression.py``.
Complements ``tests/test_dedup.py`` (F3 adversarial cases covering
``dupla alvenaria`` survival, twin-detection bucket membership, and
the DedupReport contract) — the two files share no cases.
"""
from __future__ import annotations

from classify.service import (
    _DEDUP_OVERLAP_RATIO,
    _DEDUP_PERP_TOLERANCE,
    _dedupe_collinear_overlapping,
)
from model.types import DedupReport, WallCandidate


def _h(y: float, x0: float, x1: float, thickness: float = 3.0, page: int = 0) -> WallCandidate:
    return WallCandidate(
        page_index=page,
        start=(x0, y),
        end=(x1, y),
        thickness=thickness,
        source="test_h",
        confidence=1.0,
    )


def _v(x: float, y0: float, y1: float, thickness: float = 3.0, page: int = 0) -> WallCandidate:
    return WallCandidate(
        page_index=page,
        start=(x, y0),
        end=(x, y1),
        thickness=thickness,
        source="test_v",
        confidence=1.0,
    )


def _dedup(candidates: list[WallCandidate]) -> list[WallCandidate]:
    # Since the F1 refactor the function returns (kept, DedupReport).
    # These tests only care about the kept candidates; the report is
    # exercised separately in ``tests/test_dedup.py``.
    kept, _report = _dedupe_collinear_overlapping(candidates)
    return kept


def test_cluster_of_two_collapses_to_one_representative() -> None:
    # Two horizontal twin detections at y=100 and y=105 (perp spread 5,
    # well under the tolerance) with identical parallel extent. The
    # representative-anchored sweep collapses them into a single
    # centerline at the mean perpendicular coordinate.
    candidates = [
        _h(y=100.0, x0=100.0, x1=300.0),
        _h(y=105.0, x0=100.0, x1=300.0),
    ]
    result = _dedup(candidates)
    assert len(result) == 1, [(c.start, c.end) for c in result]
    survivor = result[0]
    assert survivor.start == (100.0, 102.5)
    assert survivor.end == (300.0, 102.5)


def test_cluster_of_three_collapses_when_spread_within_tolerance() -> None:
    # Three near-parallel twins at y=100, 105, 108: total perp spread
    # 8 px, under the tolerance. Representative-anchored sweep keeps
    # growing the cluster because each addition preserves the bounded
    # spread invariant ``max - min <= perp_tolerance``.
    candidates = [
        _h(y=100.0, x0=100.0, x1=300.0),
        _h(y=105.0, x0=100.0, x1=300.0),
        _h(y=108.0, x0=100.0, x1=300.0),
    ]
    result = _dedup(candidates)
    assert len(result) == 1, [(c.start, c.end) for c in result]
    survivor = result[0]
    expected_mean = round((100.0 + 105.0 + 108.0) / 3.0, 3)
    assert survivor.start[1] == expected_mean
    assert survivor.end[1] == expected_mean
    assert survivor.start[0] == 100.0 and survivor.end[0] == 300.0


def test_chain_exceeding_tolerance_splits_into_two_clusters() -> None:
    # F3 pathology guard: under the old union-find approach the chain
    # y=100, 115, 130 merged into a single cluster because each
    # consecutive pair fit inside the tolerance. Representative-anchored
    # sweep refuses this because the end-to-end spread would be 30 px,
    # which exceeds the 20 px tolerance. The sweep closes the first
    # cluster when adding y=130 would violate the bound.
    candidates = [
        _h(y=100.0, x0=100.0, x1=300.0),
        _h(y=115.0, x0=100.0, x1=300.0),
        _h(y=130.0, x0=100.0, x1=300.0),
    ]
    result = _dedup(candidates)
    assert len(result) >= 2, [(c.start, c.end) for c in result]


def test_masonry_pair_above_perp_tolerance_is_preserved() -> None:
    # Two horizontal strokes 30 px apart in y: dupla alvenaria. Perp
    # spread 30 > tolerance 20, so the dedup pass MUST NOT fuse them.
    # The later pair-merge stage handles the masonry-pair case on its
    # own via gap analysis.
    candidates = [
        _h(y=100.0, x0=100.0, x1=300.0),
        _h(y=130.0, x0=100.0, x1=300.0),
    ]
    result = _dedup(candidates)
    assert len(result) == 2, [(c.start, c.end) for c in result]


def test_disjoint_parallel_pair_low_overlap_is_preserved() -> None:
    # Perp spread 2 px (well under tolerance) but disjoint parallel
    # extents. Dedup requires overlap >= 35 % of the shorter segment;
    # 0 % fails the check. The cluster never forms.
    candidates = [
        _h(y=100.0, x0=100.0, x1=200.0),  # length 100
        _h(y=102.0, x0=400.0, x1=600.0),  # length 200, no x overlap
    ]
    result = _dedup(candidates)
    assert len(result) == 2, [(c.start, c.end) for c in result]


def test_overlap_just_below_ratio_is_preserved() -> None:
    # Shorter length 100, overlap 30 (30 % < 35 %): NOT merged.
    candidates = [
        _h(y=100.0, x0=0.0, x1=100.0),    # length 100
        _h(y=104.0, x0=70.0, x1=270.0),   # length 200, overlap 30 on the shorter
    ]
    result = _dedup(candidates)
    assert len(result) == 2, [(c.start, c.end) for c in result]


def test_cluster_spans_full_parallel_extent_of_members() -> None:
    # The longest member is picked as the representative basis, but the
    # survivor endpoints cover the outer span across the entire cluster.
    # Shorter members that poke past the longest on either side must
    # NOT be clipped.
    candidates = [
        _h(y=100.0, x0=100.0, x1=500.0),  # seed, length 400
        _h(y=103.0, x0=50.0, x1=200.0),   # sticks out on the left
    ]
    result = _dedup(candidates)
    assert len(result) == 1, [(c.start, c.end) for c in result]
    survivor = result[0]
    assert survivor.start[0] == 50.0
    assert survivor.end[0] == 500.0


def test_cross_page_candidates_never_merge() -> None:
    # Geometrically identical candidates on different pages stay
    # isolated. Grouping keys off ``(page_index, orientation)``.
    candidates = [
        _h(y=100.0, x0=100.0, x1=300.0, page=0),
        _h(y=102.0, x0=100.0, x1=300.0, page=1),
    ]
    result = _dedup(candidates)
    assert len(result) == 2
    pages = {c.page_index for c in result}
    assert pages == {0, 1}


def test_different_orientations_never_merge() -> None:
    # H and V intersecting near the same point must not merge
    # regardless of proximity: grouping also keys off orientation.
    candidates = [
        _h(y=100.0, x0=100.0, x1=300.0),
        _v(x=200.0, y0=50.0, y1=150.0),
    ]
    result = _dedup(candidates)
    assert len(result) == 2


def test_merged_thickness_uses_max_across_cluster() -> None:
    # When twins report different thicknesses (Hough's distance-transform
    # sample can land on different stroke widths), the survivor keeps
    # the max so downstream stages see the widest estimate.
    candidates = [
        _h(y=100.0, x0=100.0, x1=300.0, thickness=3.0),
        _h(y=105.0, x0=100.0, x1=300.0, thickness=8.0),
    ]
    result = _dedup(candidates)
    assert len(result) == 1
    assert result[0].thickness == 8.0


def test_merged_confidence_uses_min_across_cluster() -> None:
    # Confidence is the most conservative across the cluster: the
    # merged candidate is only as trustworthy as its weakest member.
    a = _h(y=100.0, x0=100.0, x1=300.0)
    b = WallCandidate(
        page_index=0,
        start=(100.0, 105.0),
        end=(300.0, 105.0),
        thickness=3.0,
        source="test_h",
        confidence=0.4,
    )
    result = _dedup([a, b])
    assert len(result) == 1
    assert result[0].confidence == 0.4


def test_perp_diff_at_boundary_tolerance_still_merges() -> None:
    # Perp spread exactly equal to ``_DEDUP_PERP_TOLERANCE`` still
    # satisfies the ``<=`` predicate inside the sweep, so the pair
    # merges.
    candidates = [
        _h(y=100.0, x0=100.0, x1=300.0),
        _h(y=100.0 + _DEDUP_PERP_TOLERANCE, x0=100.0, x1=300.0),
    ]
    result = _dedup(candidates)
    assert len(result) == 1


def test_overlap_at_boundary_ratio_merges() -> None:
    # overlap / shorter == ``_DEDUP_OVERLAP_RATIO`` exactly: the
    # predicate uses ``>=``, so the pair merges. Shorter length 100,
    # need overlap >= 35.
    candidates = [
        _h(y=100.0, x0=0.0, x1=100.0),      # shorter, length 100
        _h(y=104.0, x0=65.0, x1=265.0),     # overlap [65, 100] = 35
    ]
    result = _dedup(candidates)
    assert len(result) == 1, [(c.start, c.end) for c in result]


def test_vertical_cluster_behaves_symmetrically() -> None:
    # Same behaviour for vertical twins: perp diff is along x,
    # parallel range along y.
    candidates = [
        _v(x=100.0, y0=200.0, y1=600.0),
        _v(x=105.0, y0=200.0, y1=600.0),
    ]
    result = _dedup(candidates)
    assert len(result) == 1
    survivor = result[0]
    assert survivor.start == (102.5, 200.0)
    assert survivor.end == (102.5, 600.0)


def test_empty_input_returns_empty_with_report() -> None:
    # Empty input still produces a valid DedupReport so downstream
    # callers that plumb the sink get consistent records.
    kept, report = _dedupe_collinear_overlapping([])
    assert kept == []
    assert isinstance(report, DedupReport)
    assert report.candidate_count_before == 0
    assert report.kept_count == 0
    assert report.merged_count == 0
    assert report.clusters == []


def test_single_candidate_passes_through_unchanged() -> None:
    only = _h(y=100.0, x0=100.0, x1=300.0)
    kept, report = _dedupe_collinear_overlapping([only])
    assert kept == [only]
    assert report.merged_count == 0
    assert report.kept_count == 1


def test_mixed_cluster_and_isolated_preserves_isolated() -> None:
    # Two twins that merge + one far-away stroke that must survive.
    # Proves the keep-mask / replacement bookkeeping preserves the
    # candidates outside the cluster regardless of input order.
    candidates = [
        _h(y=100.0, x0=100.0, x1=300.0),
        _h(y=105.0, x0=100.0, x1=300.0),
        _h(y=500.0, x0=50.0, x1=250.0),  # isolated row, survives alone
    ]
    result = _dedup(candidates)
    assert len(result) == 2, [(c.start, c.end) for c in result]
    ys = sorted(round(c.start[1], 3) for c in result)
    assert ys == [102.5, 500.0]


def test_dedup_report_bounds_perp_spread_by_tolerance() -> None:
    # Contract introduced by the F1 refactor: every emitted cluster
    # must have ``perp_spread_px <= _DEDUP_PERP_TOLERANCE``. Under the
    # old union-find this could be violated by transitive chains.
    candidates = [
        _h(y=100.0, x0=0.0, x1=300.0),
        _h(y=110.0, x0=0.0, x1=300.0),
        _h(y=118.0, x0=0.0, x1=300.0),
    ]
    kept, report = _dedupe_collinear_overlapping(candidates)
    assert report.triggered is True
    for cluster in report.clusters:
        assert cluster.perp_spread_px <= _DEDUP_PERP_TOLERANCE, cluster
    assert report.kept_count == len(kept)
