from __future__ import annotations

from model.types import (
    ConnectivityReport,
    Junction,
    Room,
    SplitWall,
    junction_to_dict,
    room_to_dict,
    wall_to_dict,
)


SCHEMA_VERSION = "2.1.0"


def build_observed_model(
    walls: list[SplitWall],
    junctions: list[Junction],
    rooms: list[Room],
    connectivity_report: ConnectivityReport,
    geometry_score: float,
    topology_score: float,
    room_score: float,
    warnings: list[str],
    run_id: str,
    source: dict,
    bounds: dict,
) -> dict:
    topology_quality = "poor"
    if topology_score >= 0.8:
        topology_quality = "good"
    elif topology_score >= 0.5:
        topology_quality = "fair"

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "source": source,
        "bounds": bounds,
        "walls": [wall_to_dict(wall) for wall in walls],
        "junctions": [junction_to_dict(junction) for junction in junctions],
        "rooms": [room_to_dict(room) for room in rooms],
        "scores": {
            "geometry": round(geometry_score, 4),
            "topology": round(topology_score, 4),
            "rooms": round(room_score, 4),
        },
        "metadata": {
            "rooms_detected": len(rooms),
            "topology_quality": topology_quality,
            "connectivity": connectivity_report.to_dict(),
            "warnings": warnings,
        },
        "warnings": warnings,
    }


def compute_bounds(walls: list[SplitWall]) -> dict:
    by_page: dict[int, list[SplitWall]] = {}
    for wall in walls:
        by_page.setdefault(wall.page_index, []).append(wall)

    pages: list[dict] = []
    for page_index in sorted(by_page):
        page_walls = by_page[page_index]
        xs = [coord for wall in page_walls for coord in (wall.start[0], wall.end[0])]
        ys = [coord for wall in page_walls for coord in (wall.start[1], wall.end[1])]
        pages.append(
            {
                "page_index": page_index,
                "min_x": round(min(xs), 3),
                "min_y": round(min(ys), 3),
                "max_x": round(max(xs), 3),
                "max_y": round(max(ys), 3),
            }
        )
    return {"pages": pages}
