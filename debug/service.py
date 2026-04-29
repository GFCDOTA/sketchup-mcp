from __future__ import annotations

import json
from pathlib import Path

from model.types import ConnectivityReport, Junction, SplitWall


def write_debug_artifacts(
    output_dir: Path,
    walls: list[SplitWall],
    junctions: list[Junction],
    connectivity_report: ConnectivityReport,
) -> None:
    bounds = _compute_bounds(walls, junctions)
    (output_dir / "debug_walls.svg").write_text(_render_walls_svg(walls, bounds), encoding="utf-8")
    (output_dir / "debug_junctions.svg").write_text(
        _render_junctions_svg(walls, junctions, bounds), encoding="utf-8"
    )
    (output_dir / "connectivity_report.json").write_text(
        json.dumps(connectivity_report.to_dict(), indent=2),
        encoding="utf-8",
    )


def _compute_bounds(walls: list[SplitWall], junctions: list[Junction]) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for wall in walls:
        xs.extend([wall.start[0], wall.end[0]])
        ys.extend([wall.start[1], wall.end[1]])
    for junction in junctions:
        xs.append(junction.point[0])
        ys.append(junction.point[1])
    if not xs or not ys:
        return (0.0, 0.0, 100.0, 100.0)
    margin = 20.0
    return (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)


def _render_walls_svg(walls: list[SplitWall], bounds: tuple[float, float, float, float]) -> str:
    min_x, min_y, max_x, max_y = bounds
    width = max(100.0, max_x - min_x)
    height = max(100.0, max_y - min_y)
    lines = []
    for wall in walls:
        lines.append(
            "<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='#0f172a' stroke-width='{stroke}' />".format(
                x1=wall.start[0] - min_x,
                y1=wall.start[1] - min_y,
                x2=wall.end[0] - min_x,
                y2=wall.end[1] - min_y,
                stroke=max(1.0, wall.thickness / 2.0),
            )
        )
    return _svg_document(width=width, height=height, body="\n".join(lines))


def _render_junctions_svg(
    walls: list[SplitWall],
    junctions: list[Junction],
    bounds: tuple[float, float, float, float],
) -> str:
    min_x, min_y, max_x, max_y = bounds
    width = max(100.0, max_x - min_x)
    height = max(100.0, max_y - min_y)
    body: list[str] = []
    for wall in walls:
        body.append(
            "<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='#cbd5e1' stroke-width='2' />".format(
                x1=wall.start[0] - min_x,
                y1=wall.start[1] - min_y,
                x2=wall.end[0] - min_x,
                y2=wall.end[1] - min_y,
            )
        )
    for junction in junctions:
        color = "#ef4444" if junction.degree >= 3 else "#2563eb"
        body.append(
            "<circle cx='{cx}' cy='{cy}' r='4' fill='{fill}' />".format(
                cx=junction.point[0] - min_x,
                cy=junction.point[1] - min_y,
                fill=color,
            )
        )
    return _svg_document(width=width, height=height, body="\n".join(body))


def _svg_document(width: float, height: float, body: str) -> str:
    return (
        "<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
        "<rect width='100%' height='100%' fill='#ffffff' />"
        "{body}"
        "</svg>"
    ).format(width=width, height=height, body=body)
