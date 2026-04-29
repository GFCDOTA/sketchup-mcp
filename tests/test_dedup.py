"""Adversarial tests for _dedupe_collinear_overlapping.

These exercise the boundary conditions that matter semantically:
- perp_tolerance must not collapse dupla alvenaria (20+ px separation)
- overlap_ratio must not collapse co-linear segments that barely touch
- union-find must give transitive closure (3+ twins collapse together)
- Hough twin detections (perp_spread near 0) must collapse

They also sanity-check the DedupReport contract: clusters survive with
the perp_spread and min_parallel_overlap_ratio expected by reviewers.
"""
from __future__ import annotations

from classify.service import _dedupe_collinear_overlapping
from model.types import DedupReport, WallCandidate


def _h(
    page: int,
    y: float,
    x0: float,
    x1: float,
    thickness: float = 3.0,
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
    page: int,
    x: float,
    y0: float,
    y1: float,
    thickness: float = 3.0,
) -> WallCandidate:
    return WallCandidate(
        page_index=page,
        start=(x, y0),
        end=(x, y1),
        thickness=thickness,
        source="test_v",
        confidence=1.0,
    )


def test_preserves_dupla_alvenaria() -> None:
    # Two horizontal walls with perp_spread = 22 px and full parallel
    # overlap: the signature of dupla alvenaria (double masonry). They
    # are NOT Hough twins of the same stroke; collapsing them would
    # erase the second face of the wall assembly.
    candidates = [
        _h(page=0, y=100, x0=10, x1=200, thickness=5.0),
        _h(page=0, y=122, x0=10, x1=200, thickness=5.0),
    ]
    kept, report = _dedupe_collinear_overlapping(candidates)
    assert len(kept) == 2, "dupla alvenaria must survive: perp=22 > tolerance=10"
    assert isinstance(report, DedupReport)
    assert report.triggered is True
    assert report.merged_count == 0
    assert report.clusters == []


def test_merges_twin_detection() -> None:
    # Two horizontal walls with perp_spread = 6 px and ~47 / 100 = 47%
    # overlap (above 35%). perp is over the 5 px twin-detection boundary
    # but still inside the 10 px tolerance — a Hough twin that slipped
    # through the earlier consolidation bucket. MUST merge into one
    # centerline whose span covers the union.
    candidates = [
        _h(page=0, y=50, x0=10, x1=110, thickness=3.0),
        _h(page=0, y=56, x0=63, x1=160, thickness=3.0),
    ]
    kept, report = _dedupe_collinear_overlapping(candidates)
    assert len(kept) == 1, [(k.start, k.end) for k in kept]
    assert report.merged_count == 1
    assert len(report.clusters) == 1
    cluster = report.clusters[0]
    assert cluster.member_count == 2
    assert cluster.orientation == "horizontal"
    assert 5.0 < cluster.perp_spread_px <= 10.0
    # min overlap ratio should roughly be 47 / 97 (shorter segment is 97 px).
    assert 0.35 <= cluster.min_parallel_overlap_ratio <= 1.0
    assert cluster.merge_reason == "collinear_split"
    # Representative should span the union.
    rep = kept[0]
    assert rep.start[0] == 10 and rep.end[0] == 160
    # Mean perp is (50 + 56) / 2.
    assert rep.start[1] == 53.0 and rep.end[1] == 53.0


def test_transitive_union_find_three_twins() -> None:
    # Three horizontal candidates at y = 50, 54, 58. Pairwise perps are
    # 4 and 4 (both under tolerance). Each consecutive pair overlaps at
    # 100% on the shared x span. Union-find must collapse all three into
    # a single cluster, even though y=50 and y=58 are 8 px apart (still
    # inside tolerance=10 directly, but the test also covers the case
    # where transitivity is what binds them).
    candidates = [
        _h(page=0, y=50, x0=0, x1=200, thickness=3.0),
        _h(page=0, y=54, x0=0, x1=200, thickness=3.0),
        _h(page=0, y=58, x0=0, x1=200, thickness=3.0),
    ]
    kept, report = _dedupe_collinear_overlapping(candidates)
    assert len(kept) == 1
    assert report.merged_count == 2
    assert len(report.clusters) == 1
    cluster = report.clusters[0]
    assert cluster.member_count == 3
    # Spread is 8 px (over the twin-detection boundary = 5), so the
    # reviewer should see this flagged as collinear_split in the report.
    assert cluster.perp_spread_px == 8.0
    assert cluster.merge_reason == "collinear_split"
    # Representative perp is mean = 54.
    assert kept[0].start[1] == 54.0


def test_rejects_insufficient_overlap() -> None:
    # perp_spread = 5 px (at the twin-detection boundary, inside
    # tolerance), but the parallel overlap is only 30 px out of a
    # shorter 100 px segment = 30%, below the 35% threshold. The pair
    # MUST survive as two separate candidates; the dedup stage is not
    # supposed to paper over genuinely disjoint co-linear detections.
    candidates = [
        _h(page=0, y=40, x0=0, x1=100, thickness=3.0),
        _h(page=0, y=45, x0=70, x1=200, thickness=3.0),
    ]
    kept, report = _dedupe_collinear_overlapping(candidates)
    assert len(kept) == 2, "overlap ratio 0.3 is below threshold 0.35"
    assert report.merged_count == 0
    assert report.clusters == []


def test_report_records_page_and_orientation() -> None:
    # Sanity: with mixed orientations and pages, the report correctly
    # attributes each cluster back to its (page, orientation) group.
    candidates = [
        # Page 0, horizontal twin pair — will merge.
        _h(page=0, y=50, x0=0, x1=100, thickness=3.0),
        _h(page=0, y=53, x0=0, x1=100, thickness=3.0),
        # Page 1, vertical twin pair — will merge.
        _v(page=1, x=200, y0=0, y1=100, thickness=3.0),
        _v(page=1, x=203, y0=0, y1=100, thickness=3.0),
    ]
    kept, report = _dedupe_collinear_overlapping(candidates)
    assert len(kept) == 2
    assert report.merged_count == 2
    assert len(report.clusters) == 2
    pages = {c.page_index for c in report.clusters}
    orientations = {c.orientation for c in report.clusters}
    assert pages == {0, 1}
    assert orientations == {"horizontal", "vertical"}


def test_empty_input_returns_empty_triggered_report() -> None:
    kept, report = _dedupe_collinear_overlapping([])
    assert kept == []
    assert report.triggered is True
    assert report.candidate_count_before == 0
    assert report.kept_count == 0
    assert report.merged_count == 0
    assert report.clusters == []
