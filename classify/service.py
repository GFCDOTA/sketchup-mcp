from __future__ import annotations

from collections import defaultdict

from model.types import Wall, WallCandidate


def classify_walls(candidates: list[WallCandidate], coordinate_tolerance: float = 2.0) -> list[Wall]:
    grouped: dict[tuple[int, str, int], list[WallCandidate]] = defaultdict(list)
    for candidate in candidates:
        orientation = _orientation(candidate)
        fixed_coord = (
            candidate.start[1] if orientation == "horizontal" else candidate.start[0]
        )
        grouped[(candidate.page_index, orientation, int(round(fixed_coord / coordinate_tolerance)))].append(candidate)

    walls: list[Wall] = []
    counter = 1
    for (_, orientation, _), batch in grouped.items():
        merged = _merge_candidates(batch, orientation=orientation, tolerance=coordinate_tolerance)
        for candidate in merged:
            walls.append(
                Wall(
                    wall_id=f"wall-{counter}",
                    page_index=candidate.page_index,
                    start=candidate.start,
                    end=candidate.end,
                    thickness=candidate.thickness,
                    orientation=orientation,
                    source=candidate.source,
                    confidence=candidate.confidence,
                )
            )
            counter += 1
    return walls


def _orientation(candidate: WallCandidate) -> str:
    if abs(candidate.start[1] - candidate.end[1]) <= abs(candidate.start[0] - candidate.end[0]):
        return "horizontal"
    return "vertical"


def _merge_candidates(
    candidates: list[WallCandidate], orientation: str, tolerance: float
) -> list[WallCandidate]:
    if not candidates:
        return []

    if orientation == "horizontal":
        ordered = sorted(candidates, key=lambda item: (item.start[0], item.end[0]))
    else:
        ordered = sorted(candidates, key=lambda item: (item.start[1], item.end[1]))

    merged: list[WallCandidate] = []
    current = ordered[0]

    for candidate in ordered[1:]:
        if _can_merge(current, candidate, orientation=orientation, tolerance=tolerance):
            current = _merge_pair(current, candidate, orientation=orientation)
        else:
            merged.append(current)
            current = candidate

    merged.append(current)
    return merged


def _can_merge(a: WallCandidate, b: WallCandidate, orientation: str, tolerance: float) -> bool:
    if orientation == "horizontal":
        same_axis = abs(a.start[1] - b.start[1]) <= tolerance
        gap = b.start[0] - a.end[0]
    else:
        same_axis = abs(a.start[0] - b.start[0]) <= tolerance
        gap = b.start[1] - a.end[1]
    thickness_gap = abs(a.thickness - b.thickness) <= max(a.thickness, b.thickness, tolerance)
    return same_axis and thickness_gap and gap <= max(a.thickness, b.thickness, tolerance)


def _merge_pair(a: WallCandidate, b: WallCandidate, orientation: str) -> WallCandidate:
    if orientation == "horizontal":
        start = (min(a.start[0], b.start[0]), (a.start[1] + b.start[1]) / 2.0)
        end = (max(a.end[0], b.end[0]), (a.end[1] + b.end[1]) / 2.0)
    else:
        start = ((a.start[0] + b.start[0]) / 2.0, min(a.start[1], b.start[1]))
        end = ((a.end[0] + b.end[0]) / 2.0, max(a.end[1], b.end[1]))
    return WallCandidate(
        page_index=a.page_index,
        start=start,
        end=end,
        thickness=max(a.thickness, b.thickness),
        source=a.source,
        confidence=min(a.confidence, b.confidence),
    )
