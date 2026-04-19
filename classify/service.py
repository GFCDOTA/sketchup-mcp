from __future__ import annotations

from model.types import Wall, WallCandidate


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


def classify_walls(
    candidates: list[WallCandidate], coordinate_tolerance: float | None = None
) -> list[Wall]:
    if not candidates:
        return []

    if coordinate_tolerance is None:
        coordinate_tolerance = _infer_tolerance(candidates)

    # Stage 1: collapse redundant Hough detections of the same stroke.
    strokes = _consolidate_hough_duplicates(candidates, coordinate_tolerance)

    # Stage 2: drop text baselines / repeating decorative patterns. Chains of
    # 3+ parallel strokes at near-uniform perpendicular spacing that share a
    # significant parallel extent are the signature of paragraph text or
    # hachura, not architectural walls.
    strokes = _remove_text_baselines(strokes)

    # Stage 3: drop orientation-dominated short strokes in regions where one
    # orientation overwhelms the other. Catches residual hachura patterns
    # and label text that survived the chain-based filter.
    strokes = _drop_orientation_imbalanced(strokes)

    # Stage 4: drop strokes whose length / thickness ratio is too low to be
    # a wall (blob-shaped glyph fragments and tick marks).
    strokes = _drop_low_aspect_strokes(strokes)

    # Stage 5: pair parallel strokes that represent the two faces of the
    # same wall into a single centerline candidate.
    wall_candidates = _pair_merge_strokes(strokes)

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
