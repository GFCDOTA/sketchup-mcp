from __future__ import annotations

from dataclasses import asdict, dataclass


Point = tuple[float, float]


@dataclass(frozen=True)
class WallCandidate:
    page_index: int
    start: Point
    end: Point
    thickness: float
    source: str
    confidence: float


@dataclass(frozen=True)
class Wall:
    wall_id: str
    page_index: int
    start: Point
    end: Point
    thickness: float
    orientation: str
    source: str
    confidence: float


@dataclass(frozen=True)
class SplitWall:
    wall_id: str
    parent_wall_id: str
    page_index: int
    start: Point
    end: Point
    thickness: float
    orientation: str
    source: str
    confidence: float

    @property
    def length(self) -> float:
        return abs(self.end[0] - self.start[0]) + abs(self.end[1] - self.start[1])


@dataclass(frozen=True)
class Junction:
    junction_id: str
    point: Point
    degree: int
    kind: str


@dataclass(frozen=True)
class Room:
    room_id: str
    polygon: list[Point]
    area: float
    centroid: Point


@dataclass(frozen=True)
class ConnectivityReport:
    node_count: int
    edge_count: int
    component_count: int
    component_sizes: list[int]
    largest_component_ratio: float
    rooms_detected: int
    page_count: int = 1
    max_components_within_page: int = 0
    min_intra_page_connectivity_ratio: float = 0.0
    orphan_component_count: int = 0
    orphan_node_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def wall_to_dict(wall: Wall | SplitWall) -> dict:
    payload = asdict(wall)
    payload["start"] = list(wall.start)
    payload["end"] = list(wall.end)
    return payload


def junction_to_dict(junction: Junction) -> dict:
    payload = asdict(junction)
    payload["point"] = list(junction.point)
    return payload


def room_to_dict(room: Room) -> dict:
    payload = asdict(room)
    payload["polygon"] = [list(point) for point in room.polygon]
    payload["centroid"] = list(room.centroid)
    return payload
