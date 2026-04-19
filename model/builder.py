from __future__ import annotations

from model.types import ConnectivityReport, Junction, Room, SplitWall, junction_to_dict, room_to_dict, wall_to_dict


def build_observed_model(
    walls: list[SplitWall],
    junctions: list[Junction],
    rooms: list[Room],
    connectivity_report: ConnectivityReport,
    geometry_score: float,
    topology_score: float,
    room_score: float,
    warnings: list[str],
) -> dict:
    topology_quality = "poor"
    if topology_score >= 0.8:
        topology_quality = "good"
    elif topology_score >= 0.5:
        topology_quality = "fair"

    return {
        "schema_version": "2.0.0",
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
            "warnings": warnings,
            "connectivity": connectivity_report.to_dict(),
        },
    }
