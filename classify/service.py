from __future__ import annotations

from model.types import DedupCluster, DedupReport, Wall, WallCandidate


# Pair-merge heuristics. A wall drawn in a plan is typically two parallel
# strokes with the wall's true thickness as the gap between them. These
# parameters filter out stroke duplicates (gap too small) and pairings
# across unrelated walls (gap too large) before clustering.
_PAIR_MIN_GAP = 4.0
_PAIR_MAX_GAP = 100.0
_PAIR_MIN_OVERLAP_RATIO = 0.7
_HACHURA_CHAIN_LENGTH = 3
_HACHURA_GAP_VARIANCE = 0.35

# Text-baseline filter: paragraph text (NOTAS, LEGENDA, footers) registers
# as 3+ parallel strokes with near-uniform perpendicular spacing that share
# a common parallel extent. Same signature for hachura / floor pattern
# inside rooms. Architectural walls never form such chains: even a
# double-line pair is only 2 strokes, not 3+.
_TEXT_CHAIN_MIN_GAP = 4.0
# Bumped after ROI crop landed: inside the planta crop, the residual
# noise is mostly floor hachura with 30-60 px spacing that escaped the
# previous 30 px ceiling. ROI itself protects walls outside the planta
# region, so a wider chain window is safe to use here.
_TEXT_CHAIN_MAX_GAP = 60.0
_TEXT_CHAIN_MIN_LENGTH = 3
_TEXT_GAP_VARIANCE = 0.35
_TEXT_MIN_OVERLAP = 20.0

# Orientation-dominance filter: a genuine floor plan keeps horizontal and
# vertical strokes roughly balanced at small scales, because each wall
# meets perpendicular walls. Text blocks, hachura, and pure label rows
# produce cells where one orientation dominates heavily. Drop the
# dominant-orientation short strokes in any such cell. Long strokes are
# preserved because a single structural wall can span a cell without
# requiring a perpendicular partner inside that cell.
_IMBALANCE_CELL_SIZES = (120.0, 240.0)
_IMBALANCE_MIN_TOTAL = 4
_IMBALANCE_RATIO = 3.0
_IMBALANCE_MAX_STROKE_LENGTH = 100.0
# When one orientation dominates the cell by _IMBALANCE_EXTREME_RATIO or
# more, the region is treated as non-architectural (paragraph text block,
# legend hatching, footer). Even long strokes there are noise: a real
# floor plan would mix orientations that densely.
_IMBALANCE_EXTREME_RATIO = 5.0

# Aspect-ratio filter: a real architectural wall is much longer than it is
# thick. A stroke whose length / thickness ratio is below this threshold is
# a glyph fragment, a tick mark, or other residual noise with the shape of
# a blob, not a wall.
_MIN_ASPECT_RATIO = 2.0

# Collinear-overlap dedup: after the per-orientation cluster consolidation,
# HoughLinesP can still emit twin detections of the SAME physical stroke
# whose perpendicular coordinates differ by more than the consolidation
# tolerance (typically thick-lined walls drawn at scale 2x, where the
# interior sampling step misses a single tolerance bucket). Those survivors
# still overlap heavily in the parallel direction, so a second dedup pass
# that explicitly checks 1D overlap collapses them without needing to
# relax the earlier perpendicular tolerance (which would risk fusing
# unrelated walls).
# Perp tolerance and overlap ratio calibrated empirically after F1.
#
# History:
# - Original union-find approach (F2): tolerance 10, overlap 0.35, but
#   union-find allowed transitive chains → super-clusters with
#   perp_spread up to 151 px (completely fusing unrelated walls).
# - F1 switched to representative-anchored clustering with
#   perp_spread <= tolerance enforced as a hard bound. At tolerance=10
#   the new algorithm was too conservative (dedup merged only 22 of
#   220 candidates on planta_74 vs 169 before), inflating rooms from
#   16 to 54.
# - Bumping tolerance to 20 lets the algorithm absorb twin chains on
#   thick-line raster (2x scale doubles perp jitter) while keeping
#   dupla alvenaria (perpendicular separation >= 25 px, well above
#   tolerance) unharmed. Overlap stayed at 0.35 to avoid admitting
#   collinear segments that barely touch.
_DEDUP_PERP_TOLERANCE = 20.0
_DEDUP_OVERLAP_RATIO = 0.35
# perp_spread at or below this value is treated as Hough twin detection
# (sub-pixel jitter on the same physical stroke); above it, the cluster
# is more plausibly a collinear split that slipped through the earlier
# consolidation. The report uses this boundary to annotate clusters so
# a reviewer can audit whether each merge has the expected geometric
# signature.
_TWIN_DETECTION_PERP_PX = 5.0
# Fraction of candidates that must have at least one collinear-overlap
# partner within perp_tolerance to trigger the dedup pass. This
# replaces the old raw-count gate (len(candidates) > 200) because the
# raw count couples behaviour to canvas size, not geometry. Clean
# inputs like p12_red.pdf observe ~0 pair ratio; noisy inputs like
# planta_74.pdf observe >> 0.05. Calibrated empirically against the
# four baseline runs; see F1 commit message for the measured values.
_DEDUP_ACTIVATION_RATIO = 0.05


def classify_walls(
    candidates: list[WallCandidate],
    coordinate_tolerance: float | None = None,
    *,
    dedup_report_sink: list | None = None,
) -> list[Wall]:
    """Classify wall candidates into Wall objects.

    ``dedup_report_sink`` is an optional out-parameter. When provided
    (empty list), exactly one ``DedupReport`` is appended — useful for
    callers that want to audit what the collinear dedup stage did
    without changing the return type. Tests that don't pass it keep
    working unchanged.
    """
    if not candidates:
        if dedup_report_sink is not None:
            dedup_report_sink.append(
                DedupReport(
                    triggered=False,
                    candidate_count_before=0,
                    kept_count=0,
                    merged_count=0,
                    clusters=[],
                )
            )
        return []

    if coordinate_tolerance is None:
        coordinate_tolerance = _infer_tolerance(candidates)

    # Stage 1: collapse redundant Hough detections of the same stroke.
    strokes = _consolidate_hough_duplicates(candidates, coordinate_tolerance)

    # Stage 1b: second dedup pass that clusters collinear strokes whose
    # perpendicular separation is small (<= _DEDUP_PERP_TOLERANCE) AND
    # whose parallel ranges overlap by >= _DEDUP_OVERLAP_RATIO of the
    # shorter segment. Catches Hough twin detections that escaped the
    # earlier tolerance-based consolidation.
    #
    # Gate now derives from geometry (what fraction of the candidates
    # has a collinear-overlap partner) rather than raw count, so
    # behaviour is scale-invariant: a large clean plan with 400
    # candidates but no overlap will skip, and a small noisy plan with
    # 120 candidates where half have partners will activate.
    strokes_before_dedup = len(strokes)
    gate_active = _dedup_activation_ratio(strokes) >= _DEDUP_ACTIVATION_RATIO
    if gate_active:
        strokes, dedup_report = _dedupe_collinear_overlapping(strokes)
    else:
        dedup_report = DedupReport(
            triggered=False,
            candidate_count_before=strokes_before_dedup,
            kept_count=strokes_before_dedup,
            merged_count=0,
            clusters=[],
        )
    if dedup_report_sink is not None:
        dedup_report_sink.append(dedup_report)

    # Filtros de ruido (text baselines + orientation imbalance) so fazem
    # sentido em planta real bagunsada. Quando o input ja vem limpo
    # (poucas centenas de candidatos), eles matam paredes legitimas.
    if len(strokes) > 200:
        strokes = _remove_text_baselines(strokes)
        strokes = _drop_orientation_imbalanced(strokes)

    # Stage 4: drop strokes whose length / thickness ratio is too low to be
    # a wall (blob-shaped glyph fragments and tick marks).
    strokes = _drop_low_aspect_strokes(strokes)

    # Stage 5: pair parallel strokes que representam as 2 faces de uma
    # wall double-line. Quando input ja vem limpo (single-stroke walls),
    # esse merge causa falsos positivos e mata walls de banheiros pequenos.
    if len(strokes) > 200:
        wall_candidates = _pair_merge_strokes(strokes)
    else:
        wall_candidates = list(strokes)

    # Stage 6: aspect check again, because pair-merge can synthesise a
    # centerline whose thickness (= the pair gap) is close to its length.
    # Real walls are long compared to their thickness even after pairing.
    wall_candidates = _drop_low_aspect_strokes(wall_candidates)

    # Stage 7: assign stable wall ids and turn the candidates into Walls.
    return _candidates_to_walls(wall_candidates)


def _consolidate_hough_duplicates(
    candidates: list[WallCandidate], tolerance: float
) -> list[WallCandidate]:
    by_page: dict[int, list[WallCandidate]] = {}
    for candidate in candidates:
        by_page.setdefault(candidate.page_index, []).append(candidate)

    strokes: list[WallCandidate] = []
    for page_index in sorted(by_page):
        page_items = by_page[page_index]
        by_orientation: dict[str, list[WallCandidate]] = {"horizontal": [], "vertical": []}
        for candidate in page_items:
            by_orientation[_orientation(candidate)].append(candidate)

        for orientation, items in by_orientation.items():
            if not items:
                continue
            clusters = _cluster_by_perpendicular(items, orientation, tolerance)
            for cluster in clusters:
                for merged in _merge_collinear_segments(cluster, orientation, tolerance):
                    strokes.append(
                        WallCandidate(
                            page_index=page_index,
                            start=merged.start,
                            end=merged.end,
                            thickness=merged.thickness,
                            source=merged.source,
                            confidence=merged.confidence,
                        )
                    )
    return strokes


def _dedup_activation_ratio(
    candidates: list[WallCandidate],
    perp_tolerance: float = _DEDUP_PERP_TOLERANCE,
    overlap_ratio: float = _DEDUP_OVERLAP_RATIO,
) -> float:
    """Cheap sweep that returns the fraction of candidates that have
    at least one collinear-overlap partner within ``perp_tolerance``
    and parallel overlap >= ``overlap_ratio`` of the shorter segment.

    Used as the dedup activation gate: geometry-anchored, scale-
    invariant, replaces the old raw-count threshold.
    """
    if len(candidates) < 2:
        return 0.0

    by_group: dict[tuple[int, str], list[WallCandidate]] = {}
    for candidate in candidates:
        orientation = _orientation(candidate)
        by_group.setdefault((candidate.page_index, orientation), []).append(
            candidate
        )

    paired = 0
    for (_, orientation), items in by_group.items():
        if len(items) < 2:
            continue
        ordered = sorted(items, key=lambda c: _perp_coord(c, orientation))
        # Precompute ranges to avoid redundant work.
        ranges = [_para_range(c, orientation) for c in ordered]
        perps = [_perp_coord(c, orientation) for c in ordered]
        has_partner = [False] * len(ordered)
        for i in range(len(ordered)):
            if has_partner[i]:
                continue
            ri = ranges[i]
            li = ri[1] - ri[0]
            for j in range(i + 1, len(ordered)):
                if perps[j] - perps[i] > perp_tolerance:
                    break
                rj = ranges[j]
                lj = rj[1] - rj[0]
                shorter = min(li, lj)
                if shorter <= 0:
                    continue
                overlap = max(0.0, min(ri[1], rj[1]) - max(ri[0], rj[0]))
                if overlap / shorter >= overlap_ratio:
                    has_partner[i] = True
                    has_partner[j] = True
                    break
        paired += sum(1 for flag in has_partner if flag)
    return paired / len(candidates)


def _dedupe_collinear_overlapping(
    candidates: list[WallCandidate],
    perp_tolerance: float = _DEDUP_PERP_TOLERANCE,
    overlap_ratio: float = _DEDUP_OVERLAP_RATIO,
) -> tuple[list[WallCandidate], DedupReport]:
    """Representative-anchored clustering of collinear candidates.

    Replaces the previous union-find approach, which allowed transitive
    chains to produce clusters whose total perpendicular spread far
    exceeded ``perp_tolerance``: the F3 audit observed clusters on
    planta_74.pdf with 56 members and ``perp_spread_px`` of 151 — the
    old algorithm was fusing walls three orders of magnitude apart
    perpendicularly just because each consecutive pair fell inside the
    tolerance.

    The new algorithm enforces a bounded spread per cluster:

    - Within each ``(page, orientation)`` group, sort by perpendicular
      coordinate.
    - Sweep with an open cluster: the first unprocessed candidate seeds
      the cluster and supplies the initial parallel range.
    - Each subsequent candidate joins the cluster iff
      ``cluster_max_perp - cluster_min_perp <= perp_tolerance`` after
      inclusion AND its overlap with the running seed (the longest
      segment seen so far) is >= ``overlap_ratio`` of the shorter
      segment.
    - Otherwise the cluster closes and the candidate seeds a new one.

    The representative is the bbox union of cluster members at the mean
    perpendicular coordinate, as before. The dedup report now carries
    clusters whose ``perp_spread_px`` is guaranteed <= perp_tolerance.

    Two candidates may still be merged even when they don't overlap
    each other directly, provided both overlap the seed; this preserves
    the transitivity needed for Hough sub-pixel jitter while refusing
    the pathological chain case.
    """
    if not candidates:
        return list(candidates), DedupReport(
            triggered=True,
            candidate_count_before=0,
            kept_count=0,
            merged_count=0,
            clusters=[],
        )

    by_group: dict[tuple[int, str], list[tuple[int, WallCandidate]]] = {}
    for idx, candidate in enumerate(candidates):
        orientation = _orientation(candidate)
        by_group.setdefault((candidate.page_index, orientation), []).append(
            (idx, candidate)
        )

    keep_mask = [True] * len(candidates)
    replacements: dict[int, WallCandidate] = {}
    clusters_report: list[DedupCluster] = []
    cluster_id_counter = 0

    for (page_index, orientation), items in by_group.items():
        if len(items) < 2:
            continue
        ordered = sorted(items, key=lambda pair: _perp_coord(pair[1], orientation))

        # Sweep with an "open cluster" whose spread is bounded by
        # perp_tolerance. When a candidate would violate the bound or
        # fails overlap with the cluster seed, the current cluster is
        # closed (emitted if it has >=2 members) and the candidate
        # starts a new one.
        open_cluster: list[tuple[int, WallCandidate]] = []
        open_min_perp = 0.0
        open_max_perp = 0.0
        open_min_overlap = 1.0
        seed_range: tuple[float, float] = (0.0, 0.0)
        seed_length = 0.0

        def _emit_cluster(cluster: list[tuple[int, WallCandidate]], min_overlap: float) -> None:
            nonlocal cluster_id_counter
            if len(cluster) < 2:
                return
            spans = [_para_range(pair[1], orientation) for pair in cluster]
            perps = [_perp_coord(pair[1], orientation) for pair in cluster]
            span_start = min(s[0] for s in spans)
            span_end = max(s[1] for s in spans)
            mean_perp = sum(perps) / len(cluster)
            max_thickness = max(pair[1].thickness for pair in cluster)
            perp_spread = max(perps) - min(perps)
            merge_reason = (
                "twin_detection" if perp_spread <= _TWIN_DETECTION_PERP_PX
                else "collinear_split"
            )
            clusters_report.append(
                DedupCluster(
                    cluster_id=cluster_id_counter,
                    page_index=page_index,
                    orientation=orientation,
                    member_count=len(cluster),
                    perp_spread_px=round(perp_spread, 3),
                    min_parallel_overlap_ratio=round(min_overlap, 3),
                    merge_reason=merge_reason,
                )
            )
            cluster_id_counter += 1

            # Representative = longest member by parallel extent; we
            # preserve its original index to write the merged
            # WallCandidate back into its slot.
            representative = max(
                cluster,
                key=lambda pair: _para_range(pair[1], orientation)[1]
                - _para_range(pair[1], orientation)[0],
            )
            rep_original_idx, rep_candidate = representative

            if orientation == "horizontal":
                new_start = (round(span_start, 3), round(mean_perp, 3))
                new_end = (round(span_end, 3), round(mean_perp, 3))
            else:
                new_start = (round(mean_perp, 3), round(span_start, 3))
                new_end = (round(mean_perp, 3), round(span_end, 3))

            merged = WallCandidate(
                page_index=page_index,
                start=new_start,
                end=new_end,
                thickness=round(max_thickness, 3),
                source=rep_candidate.source,
                confidence=min(pair[1].confidence for pair in cluster),
            )
            replacements[rep_original_idx] = merged
            for pair in cluster:
                if pair[0] != rep_original_idx:
                    keep_mask[pair[0]] = False

        for pair in ordered:
            _idx, candidate = pair
            p = _perp_coord(candidate, orientation)
            r = _para_range(candidate, orientation)
            length = r[1] - r[0]

            if not open_cluster:
                open_cluster = [pair]
                open_min_perp = p
                open_max_perp = p
                open_min_overlap = 1.0
                seed_range = r
                seed_length = length
                continue

            new_min = min(open_min_perp, p)
            new_max = max(open_max_perp, p)
            spread_ok = (new_max - new_min) <= perp_tolerance

            shorter = min(seed_length, length)
            overlap_abs = max(0.0, min(seed_range[1], r[1]) - max(seed_range[0], r[0]))
            overlap_ok = shorter > 0 and (overlap_abs / shorter) >= overlap_ratio

            if spread_ok and overlap_ok:
                open_cluster.append(pair)
                open_min_perp = new_min
                open_max_perp = new_max
                open_min_overlap = min(open_min_overlap, overlap_abs / shorter)
                # Let a longer segment become the new seed; this keeps
                # the overlap gate anchored on the most informative
                # member of the cluster as it grows.
                if length > seed_length:
                    seed_range = r
                    seed_length = length
            else:
                _emit_cluster(open_cluster, open_min_overlap)
                open_cluster = [pair]
                open_min_perp = p
                open_max_perp = p
                open_min_overlap = 1.0
                seed_range = r
                seed_length = length

        _emit_cluster(open_cluster, open_min_overlap)

    out: list[WallCandidate] = []
    for idx, candidate in enumerate(candidates):
        if not keep_mask[idx]:
            continue
        out.append(replacements.get(idx, candidate))
    report = DedupReport(
        triggered=True,
        candidate_count_before=len(candidates),
        kept_count=len(out),
        merged_count=len(candidates) - len(out),
        clusters=clusters_report,
    )
    return out, report


def _candidates_to_walls(candidates: list[WallCandidate]) -> list[Wall]:
    walls: list[Wall] = []
    for counter, candidate in enumerate(candidates, start=1):
        walls.append(
            Wall(
                wall_id=f"wall-{counter}",
                page_index=candidate.page_index,
                start=candidate.start,
                end=candidate.end,
                thickness=candidate.thickness,
                orientation=_orientation(candidate),
                source=candidate.source,
                confidence=candidate.confidence,
            )
        )
    return walls


def _orientation(candidate: WallCandidate) -> str:
    horizontal_span = abs(candidate.end[0] - candidate.start[0])
    vertical_span = abs(candidate.end[1] - candidate.start[1])
    return "horizontal" if horizontal_span >= vertical_span else "vertical"


def _infer_tolerance(candidates: list[WallCandidate]) -> float:
    thicknesses = [c.thickness for c in candidates if c.thickness > 0]
    if not thicknesses:
        return 4.0
    thicknesses.sort()
    median = thicknesses[len(thicknesses) // 2]
    # Floor at 4 px so Hough's twin detections of the top and bottom of a
    # single thick stroke (common on text baselines rendered at 2x scale)
    # always collapse into one candidate at consolidation time.
    return max(4.0, median)


def _perp_coord(candidate: WallCandidate, orientation: str) -> float:
    return candidate.start[1] if orientation == "horizontal" else candidate.start[0]


def _para_range(candidate: WallCandidate, orientation: str) -> tuple[float, float]:
    if orientation == "horizontal":
        return (min(candidate.start[0], candidate.end[0]), max(candidate.start[0], candidate.end[0]))
    return (min(candidate.start[1], candidate.end[1]), max(candidate.start[1], candidate.end[1]))


def _remove_text_baselines(strokes: list[WallCandidate]) -> list[WallCandidate]:
    """Drop chains of 3+ parallel strokes with near-uniform perpendicular
    spacing and at least _TEXT_MIN_OVERLAP px of pairwise parallel overlap
    between consecutive members.

    Paragraph text (NOTAS, LEGENDA, footers) renders as baseline strokes
    stacked at the line height, with consecutive lines overlapping in
    column even when widths differ due to wrapping. Decorative hachura
    shares the same signature. Real walls never form chains this long.
    """
    if not strokes:
        return list(strokes)

    by_group: dict[tuple[int, str], list[WallCandidate]] = {}
    for stroke in strokes:
        orientation = _orientation(stroke)
        by_group.setdefault((stroke.page_index, orientation), []).append(stroke)

    kept: list[WallCandidate] = []
    for (_, orientation), items in by_group.items():
        ordered = sorted(items, key=lambda c: _perp_coord(c, orientation))
        n = len(ordered)
        drop: set[int] = set()

        start = 0
        while start < n - (_TEXT_CHAIN_MIN_LENGTH - 1):
            chain_end = start + 1
            while chain_end < n:
                gap = _perp_coord(ordered[chain_end], orientation) - _perp_coord(
                    ordered[chain_end - 1], orientation
                )
                if gap < _TEXT_CHAIN_MIN_GAP or gap > _TEXT_CHAIN_MAX_GAP:
                    break
                if chain_end - start >= 2:
                    gaps = [
                        _perp_coord(ordered[k + 1], orientation)
                        - _perp_coord(ordered[k], orientation)
                        for k in range(start, chain_end)
                    ]
                    mean_gap = sum(gaps) / len(gaps)
                    if mean_gap <= 0:
                        break
                    if any(
                        abs(g - mean_gap) / mean_gap > _TEXT_GAP_VARIANCE for g in gaps
                    ):
                        break
                chain_end += 1

            chain_len = chain_end - start
            if chain_len >= _TEXT_CHAIN_MIN_LENGTH:
                pairwise_ok = True
                for k in range(start, chain_end - 1):
                    a_range = _para_range(ordered[k], orientation)
                    b_range = _para_range(ordered[k + 1], orientation)
                    pair_overlap = max(
                        0.0, min(a_range[1], b_range[1]) - max(a_range[0], b_range[0])
                    )
                    if pair_overlap < _TEXT_MIN_OVERLAP:
                        pairwise_ok = False
                        break
                if pairwise_ok:
                    for k in range(start, chain_end):
                        drop.add(k)
                    start = chain_end
                    continue
            start += 1

        for idx, stroke in enumerate(ordered):
            if idx not in drop:
                kept.append(stroke)

    return kept


def _drop_orientation_imbalanced(strokes: list[WallCandidate]) -> list[WallCandidate]:
    """Drop strokes whose orientation dominates their local cell.

    The page is tiled at every scale in _IMBALANCE_CELL_SIZES. A stroke is
    dropped if, at ANY scale, the cell containing its midpoint holds at
    least _IMBALANCE_MIN_TOTAL strokes and the stroke's orientation
    exceeds _IMBALANCE_RATIO x the other. Short strokes (len <
    _IMBALANCE_MAX_STROKE_LENGTH) fall under a moderate rule; all strokes,
    including long ones, are dropped when the cell shows extreme
    dominance (>= _IMBALANCE_EXTREME_RATIO).

    Multi-scale catches both small label clusters (120 px) and paragraph
    blocks that span several cells (240 px). Architectural walls mix
    orientations at these scales, so real walls are preserved.
    """
    if not strokes:
        return list(strokes)

    by_page: dict[int, list[WallCandidate]] = {}
    for stroke in strokes:
        by_page.setdefault(stroke.page_index, []).append(stroke)

    kept: list[WallCandidate] = []
    for items in by_page.values():
        orientations = [_orientation(s) for s in items]
        lengths = [
            abs(s.end[0] - s.start[0]) + abs(s.end[1] - s.start[1]) for s in items
        ]
        midpoints_xy = [
            ((s.start[0] + s.end[0]) / 2.0, (s.start[1] + s.end[1]) / 2.0)
            for s in items
        ]

        drop: set[int] = set()
        for cell_size in _IMBALANCE_CELL_SIZES:
            keys = [(int(mx // cell_size), int(my // cell_size)) for mx, my in midpoints_xy]
            cells_h: dict[tuple[int, int], int] = {}
            cells_v: dict[tuple[int, int], int] = {}
            for orientation, key in zip(orientations, keys):
                if orientation == "horizontal":
                    cells_h[key] = cells_h.get(key, 0) + 1
                else:
                    cells_v[key] = cells_v.get(key, 0) + 1

            imbalanced_h: set[tuple[int, int]] = set()
            imbalanced_v: set[tuple[int, int]] = set()
            extreme_h: set[tuple[int, int]] = set()
            extreme_v: set[tuple[int, int]] = set()
            for key in set(cells_h) | set(cells_v):
                h = cells_h.get(key, 0)
                v = cells_v.get(key, 0)
                if h + v < _IMBALANCE_MIN_TOTAL:
                    continue
                if h >= _IMBALANCE_EXTREME_RATIO * max(1, v):
                    extreme_h.add(key)
                    imbalanced_h.add(key)
                elif h >= _IMBALANCE_RATIO * max(1, v):
                    imbalanced_h.add(key)
                elif v >= _IMBALANCE_EXTREME_RATIO * max(1, h):
                    extreme_v.add(key)
                    imbalanced_v.add(key)
                elif v >= _IMBALANCE_RATIO * max(1, h):
                    imbalanced_v.add(key)

            for idx, (orientation, key, length) in enumerate(zip(orientations, keys, lengths)):
                if idx in drop:
                    continue
                if orientation == "horizontal" and key in extreme_h:
                    drop.add(idx)
                    continue
                if orientation == "vertical" and key in extreme_v:
                    drop.add(idx)
                    continue
                if length < _IMBALANCE_MAX_STROKE_LENGTH:
                    if orientation == "horizontal" and key in imbalanced_h:
                        drop.add(idx)
                    elif orientation == "vertical" and key in imbalanced_v:
                        drop.add(idx)

        for idx, stroke in enumerate(items):
            if idx not in drop:
                kept.append(stroke)

    return kept


def _drop_low_aspect_strokes(strokes: list[WallCandidate]) -> list[WallCandidate]:
    """Remove strokes whose length / thickness ratio is below
    _MIN_ASPECT_RATIO.

    A legitimate wall stroke is elongated: its length is many times its
    thickness. Residual glyph fragments, tick marks, and noise clusters
    that survived earlier filters tend to have near-square bounding
    boxes (aspect around 1). Strokes with thickness == 0 are left in
    place because the ratio is undefined; downstream stages can decide.
    """
    kept: list[WallCandidate] = []
    for stroke in strokes:
        if stroke.thickness <= 0:
            kept.append(stroke)
            continue
        length = abs(stroke.end[0] - stroke.start[0]) + abs(stroke.end[1] - stroke.start[1])
        if length >= _MIN_ASPECT_RATIO * stroke.thickness:
            kept.append(stroke)
    return kept


def _pair_merge_strokes(candidates: list[WallCandidate]) -> list[WallCandidate]:
    """Combine pairs of parallel strokes that represent the two faces of a
    single wall into one centerline candidate whose thickness equals the
    gap between the strokes.

    A candidate is considered the pair of its immediate perpendicular
    neighbour when the gap falls in [_PAIR_MIN_GAP, _PAIR_MAX_GAP] and at
    least _PAIR_MIN_OVERLAP_RATIO of the shorter segment overlaps the
    longer one in the parallel direction.

    Hachura / repeating parallel patterns (3+ collinear strokes with
    near-uniform spacing) are never paired: every candidate in such a
    chain passes through unchanged so the caller can still observe the
    raw linework.
    """
    if not candidates:
        return list(candidates)

    by_group: dict[tuple[int, str], list[WallCandidate]] = {}
    for candidate in candidates:
        orientation = _orientation(candidate)
        by_group.setdefault((candidate.page_index, orientation), []).append(candidate)

    merged: list[WallCandidate] = []
    for (page_index, orientation), items in by_group.items():
        ordered = sorted(items, key=lambda c: _perp_coord(c, orientation))
        hachura = _detect_hachura_indices(ordered, orientation)

        used: set[int] = set()
        for i in range(len(ordered) - 1):
            if i in used or i in hachura or (i + 1) in used or (i + 1) in hachura:
                continue
            a = ordered[i]
            b = ordered[i + 1]
            gap = _perp_coord(b, orientation) - _perp_coord(a, orientation)
            if gap < _PAIR_MIN_GAP or gap > _PAIR_MAX_GAP:
                continue
            a_range = _para_range(a, orientation)
            b_range = _para_range(b, orientation)
            overlap_start = max(a_range[0], b_range[0])
            overlap_end = min(a_range[1], b_range[1])
            overlap = max(0.0, overlap_end - overlap_start)
            max_len = max(a_range[1] - a_range[0], b_range[1] - b_range[0])
            # overlap must be large relative to the LONGER stroke. Using max
            # prevents pairing a short stroke with a much longer one that
            # merely happens to be parallel (e.g., the two opposite edges of
            # an L-shape fixture would otherwise look like a wall pair).
            if max_len <= 0 or overlap / max_len < _PAIR_MIN_OVERLAP_RATIO:
                continue

            used.add(i)
            used.add(i + 1)
            merged.append(
                _build_centerline(a, b, page_index, orientation, gap, overlap_start, overlap_end)
            )

        for index, candidate in enumerate(ordered):
            if index not in used:
                merged.append(candidate)
    return merged


def _detect_hachura_indices(
    ordered: list[WallCandidate], orientation: str
) -> set[int]:
    n = len(ordered)
    if n < _HACHURA_CHAIN_LENGTH:
        return set()
    hachura: set[int] = set()
    for start in range(n - _HACHURA_CHAIN_LENGTH + 1):
        window = ordered[start : start + _HACHURA_CHAIN_LENGTH]
        gaps = [
            _perp_coord(window[k + 1], orientation) - _perp_coord(window[k], orientation)
            for k in range(_HACHURA_CHAIN_LENGTH - 1)
        ]
        if any(g < _PAIR_MIN_GAP or g > _PAIR_MAX_GAP for g in gaps):
            continue
        mean_gap = sum(gaps) / len(gaps)
        if mean_gap <= 0:
            continue
        if all(abs(g - mean_gap) / mean_gap <= _HACHURA_GAP_VARIANCE for g in gaps):
            for offset in range(_HACHURA_CHAIN_LENGTH):
                hachura.add(start + offset)
    return hachura


def _build_centerline(
    a: WallCandidate,
    b: WallCandidate,
    page_index: int,
    orientation: str,
    gap: float,
    overlap_start: float,
    overlap_end: float,
) -> WallCandidate:
    mean_perp = (_perp_coord(a, orientation) + _perp_coord(b, orientation)) / 2.0
    if orientation == "horizontal":
        start = (round(overlap_start, 3), round(mean_perp, 3))
        end = (round(overlap_end, 3), round(mean_perp, 3))
    else:
        start = (round(mean_perp, 3), round(overlap_start, 3))
        end = (round(mean_perp, 3), round(overlap_end, 3))
    return WallCandidate(
        page_index=page_index,
        start=start,
        end=end,
        thickness=round(gap, 3),
        source=f"paired_{orientation}",
        confidence=min(a.confidence, b.confidence),
    )


def _cluster_by_perpendicular(
    items: list[WallCandidate], orientation: str, tolerance: float
) -> list[list[WallCandidate]]:
    ordered = sorted(items, key=lambda c: _perp_coord(c, orientation))
    clusters: list[list[WallCandidate]] = []
    current: list[WallCandidate] = [ordered[0]]
    current_mean = _perp_coord(ordered[0], orientation)
    for candidate in ordered[1:]:
        coord = _perp_coord(candidate, orientation)
        if abs(coord - current_mean) <= tolerance:
            current.append(candidate)
            current_mean = sum(_perp_coord(c, orientation) for c in current) / len(current)
        else:
            clusters.append(current)
            current = [candidate]
            current_mean = coord
    clusters.append(current)
    return clusters


def _merge_collinear_segments(
    cluster: list[WallCandidate], orientation: str, tolerance: float
) -> list[WallCandidate]:
    mean_perp = sum(_perp_coord(c, orientation) for c in cluster) / len(cluster)
    max_thickness = max(c.thickness for c in cluster)
    confidence = min(c.confidence for c in cluster)
    source = cluster[0].source
    page_index = cluster[0].page_index

    ranges = sorted((_para_range(c, orientation) for c in cluster), key=lambda r: r[0])
    merged_ranges: list[tuple[float, float]] = []
    cur_start, cur_end = ranges[0]
    for start, end in ranges[1:]:
        if start <= cur_end + tolerance:
            cur_end = max(cur_end, end)
        else:
            merged_ranges.append((cur_start, cur_end))
            cur_start, cur_end = start, end
    merged_ranges.append((cur_start, cur_end))

    merged: list[WallCandidate] = []
    for start, end in merged_ranges:
        if orientation == "horizontal":
            p1 = (round(start, 3), round(mean_perp, 3))
            p2 = (round(end, 3), round(mean_perp, 3))
        else:
            p1 = (round(mean_perp, 3), round(start, 3))
            p2 = (round(mean_perp, 3), round(end, 3))
        merged.append(
            WallCandidate(
                page_index=page_index,
                start=p1,
                end=p2,
                thickness=max_thickness,
                source=source,
                confidence=confidence,
            )
        )
    return merged
