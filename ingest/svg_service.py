"""SVG ingest service: parse PDF-converted SVG bytes into Wall objects.

Contract
--------
`ingest_svg(svg_bytes, filename)` returns an `IngestedSvgDocument` containing
axis-aligned wall segments extracted from a single-page architectural SVG.

Filtering rules (validated in the v5 PoC):
  * Only paths whose style declares ``stroke: #000`` or ``#000000``.
  * Only paths whose ``stroke-width`` is in the inclusive range ``[6.0, 6.5]``.
  * Paths whose ``d`` attribute contains any SVG curve command
    (``C/S/Q/T/A`` upper or lower case) are rejected wholesale, even if they
    also contain straight segments.
  * Only axis-aligned segments survive; diagonals are dropped using
    ``COLLINEAR_TOL`` as the tolerance.
  * Nested SVG ``transform`` attributes are composed by matrix multiplication
    before each segment is projected to document coordinates.

Failure modes raise ``IngestSvgError``:
  * Invalid XML.
  * Missing or malformed ``viewBox``.
  * Zero axis-aligned wall paths after filtering.

The service performs no logging, no printing, no network I/O and no file
writes. ``stroke_width_samples`` is returned so the caller can log observed
stroke widths if desired.
"""
from __future__ import annotations

import re
import statistics
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from model.types import Wall


COLLINEAR_TOL = 3.0
_STROKE_WIDTH_MIN = 6.0
_STROKE_WIDTH_MAX = 6.5
_STROKE_COLORS = ("#000000", "#000")

_TOK_RE = re.compile(r"[A-Za-z]|-?\d*\.?\d+(?:[eE][-+]?\d+)?")
_CURVE_RE = re.compile(r"[CScSQqTtAa]")
_TRANSFORM_RE = re.compile(r"(matrix|scale|translate|rotate)\s*\(([^)]*)\)")


class IngestSvgError(RuntimeError):
    """Raised when an SVG cannot be ingested into a wall document."""


@dataclass(frozen=True)
class IngestedSvgDocument:
    filename: str
    viewbox_width: float
    viewbox_height: float
    walls: list[Wall]
    stroke_width_median: float
    stroke_width_samples: list[float] = field(default_factory=list)


def _parse_transform(s: str | None) -> np.ndarray:
    if not s:
        return np.eye(3)
    M = np.eye(3)
    for fn, args in _TRANSFORM_RE.findall(s):
        nums = [float(x) for x in re.split(r"[,\s]+", args.strip()) if x]
        T = np.eye(3)
        if fn == "matrix":
            a, b, c, d, e, f = nums
            T = np.array([[a, c, e], [b, d, f], [0, 0, 1]], dtype=float)
        elif fn == "scale":
            sx = nums[0]
            sy = nums[1] if len(nums) > 1 else sx
            T = np.diag([sx, sy, 1.0])
        elif fn == "translate":
            tx = nums[0]
            ty = nums[1] if len(nums) > 1 else 0.0
            T = np.array([[1, 0, tx], [0, 1, ty], [0, 0, 1]], dtype=float)
        elif fn == "rotate":
            a = np.deg2rad(nums[0])
            c, s_ = np.cos(a), np.sin(a)
            T = np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1]], dtype=float)
        # parent-first composition: children inherit ancestor frame
        M = M @ T
    return M


def _parse_style(s: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not s:
        return out
    for part in s.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _parse_d(d: str) -> list[tuple[np.ndarray, np.ndarray]]:
    toks = _TOK_RE.findall(d)
    segs: list[tuple[np.ndarray, np.ndarray]] = []
    cur = np.zeros(2)
    start = np.zeros(2)
    cmd: str | None = None
    i = 0

    def readnums(k: int, i: int) -> tuple[list[float] | None, int]:
        nums: list[float] = []
        while len(nums) < k and i < len(toks):
            try:
                nums.append(float(toks[i]))
                i += 1
            except ValueError:
                return None, i
        if len(nums) < k:
            return None, i
        return nums, i

    while i < len(toks):
        t = toks[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t
            i += 1
            continue
        if cmd is None:
            break
        rel = cmd.islower()
        op = cmd.upper()
        if op == "M":
            nums, i = readnums(2, i)
            if nums is None:
                break
            nxt = np.array(nums)
            cur = cur + nxt if rel else nxt
            start = cur.copy()
            # SVG spec: coordinate pairs that follow an M/m are implicit line-to
            cmd = "l" if rel else "L"
        elif op == "L":
            nums, i = readnums(2, i)
            if nums is None:
                break
            nxt = np.array(nums)
            end = cur + nxt if rel else nxt
            segs.append((cur.copy(), end.copy()))
            cur = end
        elif op == "H":
            nums, i = readnums(1, i)
            if nums is None:
                break
            end = cur.copy()
            end[0] = (cur[0] + nums[0]) if rel else nums[0]
            segs.append((cur.copy(), end.copy()))
            cur = end
        elif op == "V":
            nums, i = readnums(1, i)
            if nums is None:
                break
            end = cur.copy()
            end[1] = (cur[1] + nums[0]) if rel else nums[0]
            segs.append((cur.copy(), end.copy()))
            cur = end
        elif op == "Z":
            if not np.allclose(cur, start):
                segs.append((cur.copy(), start.copy()))
            cur = start.copy()
        else:
            # curve commands: consume the argcount, do not emit a segment.
            # Whole path will still be rejected upstream by _CURVE_RE anyway.
            argcount = {"C": 6, "S": 4, "Q": 4, "T": 2, "A": 7}.get(op, 0)
            nums, i = readnums(argcount, i)
            if nums is None:
                break
            end_rel = np.array(nums[-2:])
            end = cur + end_rel if rel else end_rel
            cur = end
    return segs


def _walk(
    elem: ET.Element,
    parent_M: np.ndarray,
    acc: list[tuple[np.ndarray, dict[str, str], list[tuple[np.ndarray, np.ndarray]], str]],
) -> None:
    T = _parse_transform(elem.get("transform"))
    M = parent_M @ T
    tag = elem.tag.split("}")[-1]
    if tag == "path":
        raw_d = elem.get("d") or ""
        acc.append((M, _parse_style(elem.get("style")), _parse_d(raw_d), raw_d))
    for child in elem:
        _walk(child, M, acc)


def _collect_samples(values: Iterable[float], limit: int = 20) -> list[float]:
    seen: list[float] = []
    for v in values:
        if v not in seen:
            seen.append(v)
            if len(seen) >= limit:
                break
    return seen


def ingest_svg(svg_bytes: bytes, filename: str) -> IngestedSvgDocument:
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError as exc:
        raise IngestSvgError(f"invalid XML in {filename!r}: {exc}") from exc

    vb_raw = root.get("viewBox", "")
    vb_parts = vb_raw.split()
    if len(vb_parts) != 4:
        raise IngestSvgError(
            f"missing or malformed viewBox in {filename!r}: got {vb_raw!r}"
        )
    try:
        vb_w = float(vb_parts[2])
        vb_h = float(vb_parts[3])
    except ValueError as exc:
        raise IngestSvgError(
            f"non-numeric viewBox dimensions in {filename!r}: {vb_raw!r}"
        ) from exc

    acc: list[tuple[np.ndarray, dict[str, str], list[tuple[np.ndarray, np.ndarray]], str]] = []
    _walk(root, np.eye(3), acc)

    walls: list[Wall] = []
    stroke_width_stream: list[float] = []
    seg_id = 1
    for M, style, segs, raw_d in acc:
        stroke = style.get("stroke", "").lower()
        try:
            sw = float(style.get("stroke-width", "0"))
        except ValueError:
            sw = 0.0
        if stroke not in _STROKE_COLORS:
            continue
        if not (_STROKE_WIDTH_MIN <= sw <= _STROKE_WIDTH_MAX):
            continue
        # reject paths with any curve command, even mixed with straight segments
        if _CURVE_RE.search(raw_d):
            continue
        stroke_width_stream.append(sw)
        for p0, p1 in segs:
            A = M @ np.array([p0[0], p0[1], 1.0])
            B = M @ np.array([p1[0], p1[1], 1.0])
            ax, ay = float(A[0]), float(A[1])
            bx, by = float(B[0]), float(B[1])
            if ax == bx and ay == by:
                continue
            dx = abs(ax - bx)
            dy = abs(ay - by)
            if dy < COLLINEAR_TOL and dx >= COLLINEAR_TOL:
                y_mid = (ay + by) / 2
                walls.append(Wall(
                    wall_id=f"wall-{seg_id}", page_index=0,
                    start=(ax, y_mid), end=(bx, y_mid),
                    thickness=sw, orientation="horizontal",
                    source="svg", confidence=1.0,
                ))
                seg_id += 1
            elif dx < COLLINEAR_TOL and dy >= COLLINEAR_TOL:
                x_mid = (ax + bx) / 2
                walls.append(Wall(
                    wall_id=f"wall-{seg_id}", page_index=0,
                    start=(x_mid, ay), end=(x_mid, by),
                    thickness=sw, orientation="vertical",
                    source="svg", confidence=1.0,
                ))
                seg_id += 1

    if not walls:
        raise IngestSvgError(
            f"no axis-aligned wall paths found in {filename!r}"
        )

    thicknesses = [w.thickness for w in walls]
    stroke_width_median = float(statistics.median(thicknesses))
    stroke_width_samples = _collect_samples(stroke_width_stream)

    return IngestedSvgDocument(
        filename=filename,
        viewbox_width=vb_w,
        viewbox_height=vb_h,
        walls=walls,
        stroke_width_median=stroke_width_median,
        stroke_width_samples=stroke_width_samples,
    )
