#!/usr/bin/env python3
"""Shared primitives for the deterministic gates.

`kitchen_wall_regression_gate`, `wall_exact_match_gate` and
`position_fidelity_gate` each carried a byte-identical copy of the
point-to-segment distance (under three different names: `_dist_pt_seg`,
`_d_pt_seg`, `_pt_dist_to_seg_m`) and the same UTF-8-BOM-tolerant JSON loader.

One definition, used by all (DRY): a fix or tweak to the gate coverage geometry
now happens in exactly one place instead of drifting across three files.
"""
from __future__ import annotations

import json
import math
from pathlib import Path


def pt_seg_dist(px: float, py: float,
                ax: float, ay: float, bx: float, by: float) -> float:
    """Euclidean distance from point (px, py) to segment (ax, ay)-(bx, by).

    The projection is clamped to the segment (t in [0, 1]); a zero-length
    segment degenerates to point-to-point distance. Units are whatever the
    inputs are in — callers needing metres multiply by their pt_to_m scale.
    """
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def load_json(path: str | Path) -> dict:
    """Read a JSON file tolerating a UTF-8 BOM (utf-8-sig)."""
    return json.loads(Path(path).read_text("utf-8-sig"))
