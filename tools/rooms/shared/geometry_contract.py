"""FP-048/T0.4: pure, reversible rigid transforms for cross-room component frames.

Cabinet uses local front +Y; wardrobe uses local front -Y. Switching those
uses a 180° rotation around Z, NOT a mirror: right handedness is preserved.
Synthetic examples are test geometry, never dimensions from a real apartment.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Sequence

from jsonschema import Draft202012Validator
from core.schemas import schema_path

ROOT = Path(__file__).resolve().parents[3]
_UNIT_TO_M = {"m": 1.0, "cm": 0.01, "mm": 0.001}


def _scalar_m(value: dict) -> float:
    return value["value"] * _UNIT_TO_M[value["unit"]]


def plan_transform(request: dict, *, root: Path = ROOT) -> dict:
    """Validate provenance and return an invertible rigid 4×4 mapping; no execution."""
    schema = json.loads(schema_path("shared_transform.v1.schema.json", root).read_text("utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(request), key=lambda e: str(e.path))
    if errors:
        return {"state": "BLOCKED_TRANSFORM_SCHEMA",
                "reason": "; ".join(f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors[:4]),
                "execution_authorized": False}
    pose = request["pose"]
    if any(not math.isfinite(float(v["value"])) for v in pose.values()):
        return {"state": "BLOCKED_TRANSFORM_NONFINITE", "execution_authorized": False}
    shift = [_scalar_m(pose[k]) for k in ("x", "y", "z")]
    if any(not math.isfinite(v) for v in shift):
        return {"state": "BLOCKED_TRANSFORM_NONFINITE", "execution_authorized": False}
    half_turn = 180 if request["source_front"] != request["target_front"] else 0
    angle_deg = float(pose["rotation_deg"]["value"]) + half_turn
    theta = math.radians(angle_deg)
    c, s = math.cos(theta), math.sin(theta)
    # Proper rotation (determinant +1) with full +Z invariance.
    r = [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]
    t = shift
    world = [[*r[i], t[i]] for i in range(3)] + [[0.0, 0.0, 0.0, 1.0]]
    inverse_r = [[r[j][i] for j in range(3)] for i in range(3)]
    inverse_t = [-sum(inverse_r[i][j] * t[j] for j in range(3)) for i in range(3)]
    inv = [[*inverse_r[i], inverse_t[i]] for i in range(3)] + [[0.0, 0.0, 0.0, 1.0]]
    return {"state": "PLAN_READY_NOT_EXECUTED",
            "source_front": request["source_front"], "target_front": request["target_front"],
            "angle_deg": angle_deg % 360.0, "matrix": world, "inverse_matrix": inv,
            "determinant": 1.0, "unit": "m", "execution_authorized": False}


def transform_point(matrix: Sequence[Sequence[float]], point: Sequence[float]) -> tuple[float, float, float]:
    if len(point) != 3 or any(not math.isfinite(float(v)) for v in point):
        raise ValueError("point must be three finite coordinates")
    if len(matrix) != 4 or any(len(row) != 4 for row in matrix):
        raise ValueError("matrix must be 4x4")
    return tuple(sum(matrix[i][j] * point[j] for j in range(3)) + matrix[i][3] for i in range(3))


def transform_direction(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> tuple[float, float, float]:
    """Direction/normal: only rotation; translation must never shift normal."""
    if len(vector) != 3 or any(not math.isfinite(float(v)) for v in vector):
        raise ValueError("vector must be three finite coordinates")
    if len(matrix) != 4 or any(len(row) != 4 for row in matrix):
        raise ValueError("matrix must be 4x4")
    return tuple(sum(matrix[i][j] * vector[j] for j in range(3)) for i in range(3))


def main() -> int:
    p = argparse.ArgumentParser(description="Pure transform plan; no SketchUp")
    p.add_argument("request", type=Path)
    args = p.parse_args()
    result = plan_transform(json.loads(args.request.read_text("utf-8")))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["state"] == "PLAN_READY_NOT_EXECUTED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
