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


def classify_walls(
    candidates: list[WallCandidate], coordinate_tolerance: float | None = None
) -> list[Wall]:
    if not candidates:
        return []

    if coordinate_tolerance is None:
        coordinate_tolerance = _infer_tolerance(candidates)

    # Stage 1: collapse redundant Hough detections of the same stroke.
    strokes = _consolidate_hough_duplicates(candidates, coordinate_tolerance)

    # Stage 2: pair parallel strokes that represent the two faces of the
    # same wall into a single centerline candidate.
    wall_candidates = _pair_merge_strokes(strokes)

    # Stage 3: assign stable wall ids and turn the candidates into Walls.
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
        return 2.0
    thicknesses.sort()
    median = thicknesses[len(thicknesses) // 2]
    return max(2.0, median)


def _perp_coord(candidate: WallCandidate, orientation: str) -> float:
    return candidate.start[1] if orientation == "horizontal" else candidate.start[0]


def _para_range(candidate: WallCandidate, orientation: str) -> tuple[float, float]:
    if orientation == "horizontal":
        return (min(candidate.start[0], candidate.end[0]), max(candidate.start[0], candidate.end[0]))
    return (min(candidate.start[1], candidate.end[1]), max(candidate.start[1], candidate.end[1]))


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
