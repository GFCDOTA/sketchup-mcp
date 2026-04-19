from __future__ import annotations

from model.types import Wall, WallCandidate


def classify_walls(
    candidates: list[WallCandidate], coordinate_tolerance: float | None = None
) -> list[Wall]:
    if not candidates:
        return []

    if coordinate_tolerance is None:
        coordinate_tolerance = _infer_tolerance(candidates)

    by_page: dict[int, list[WallCandidate]] = {}
    for candidate in candidates:
        by_page.setdefault(candidate.page_index, []).append(candidate)

    walls: list[Wall] = []
    counter = 1
    for page_index in sorted(by_page):
        page_items = by_page[page_index]
        by_orientation: dict[str, list[WallCandidate]] = {"horizontal": [], "vertical": []}
        for candidate in page_items:
            by_orientation[_orientation(candidate)].append(candidate)

        for orientation, items in by_orientation.items():
            if not items:
                continue
            clusters = _cluster_by_perpendicular(items, orientation, coordinate_tolerance)
            for cluster in clusters:
                for merged in _merge_collinear_segments(cluster, orientation, coordinate_tolerance):
                    walls.append(
                        Wall(
                            wall_id=f"wall-{counter}",
                            page_index=page_index,
                            start=merged.start,
                            end=merged.end,
                            thickness=merged.thickness,
                            orientation=orientation,
                            source=merged.source,
                            confidence=merged.confidence,
                        )
                    )
                    counter += 1
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
