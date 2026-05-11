"""Apply human openings truth to a consensus_model.json.

Reworked 2026-05-11 per user mandate ("Não usar snap grande como
correção silenciosa"). The previous version silently snapped opening
centers up to ~70 pt onto host walls so consume_consensus.rb's carve
would fire. That hid the real fidelity question (does the user-painted
position correspond to an actual wall or an existing architectural
gap?) under a numeric correction.

New approach: classify each opening's hosting mode before applying.

Modes
-----
- ``cut_into_wall``: the opening center falls inside a continuous wall
  (wall axis range contains the center, within wall thickness on the
  cross axis). The opening will cause carving. A minor snap (≤ 8 pt)
  is allowed to align the center to the wall's centerline.
- ``existing_gap``: the opening center sits in a colinear gap between
  two wall fragments — i.e. the architectural opening is ALREADY drawn
  in the consensus as a wall discontinuity, the user's blob just names
  what it is (door/window/balcony). No carving needed; the wall_id
  references one of the bracketing fragments so consume_consensus.rb
  knows the orientation + thickness for door-leaf rendering.
- ``unhosted``: no wall nor gap plausibly matches the user's blob.
  Marked as FAIL by the structural gate; reviewer must paint a
  human-annotated wall or correct the blob position.

The applied opening records both ``original_center_pdf`` (where the
user painted) and ``adjusted_center_pdf`` (post-classification),
plus ``shift_pt`` so the gate can FAIL on excessive drift.

Companion: ``tools/extract_human_openings.py``,
``tools/structural_checks_human.py``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# Per-mode snap policy. cut_into_wall accepts very minor adjustments
# (a wall centerline is one pixel of paint thickness off the user's
# brushstroke). Anything more is a signal that the host detection is
# wrong or the user-paint location is questionable.
CUT_INTO_WALL_MAX_SNAP_PT = 8.0
# Shift thresholds applied to the user-paint -> adjusted-center delta:
# the GATE in structural_checks_human flags WARN above the first
# threshold and FAIL above the second. They are exposed here only as
# documentation; the gate enforces them.
SHIFT_WARN_PT = 8.0
SHIFT_FAIL_PT = 15.0


def _wall_bbox(w: dict, thickness: float) -> tuple[float, float, float, float]:
    """Return the wall's filled rectangle (x0, y0, x1, y1) in PDF pts."""
    sx, sy = float(w["start"][0]), float(w["start"][1])
    ex, ey = float(w["end"][0]), float(w["end"][1])
    half = thickness / 2.0
    if w.get("orientation") == "h":
        x0, x1 = min(sx, ex), max(sx, ex)
        return (x0, sy - half, x1, sy + half)
    else:
        y0, y1 = min(sy, ey), max(sy, ey)
        return (sx - half, y0, sx + half, y1)


def _find_cut_into_wall(center: list[float],
                         walls: list[dict],
                         thickness: float) -> tuple[dict | None, float]:
    """Find the wall whose filled rectangle contains the center.
    Returns (wall, shift_pt) where shift_pt is the snap distance to the
    wall's centerline (≤ thickness/2 by construction). Returns
    (None, inf) if no wall contains the center.
    """
    cx, cy = float(center[0]), float(center[1])
    best: dict | None = None
    best_shift = float("inf")
    for w in walls:
        wb = _wall_bbox(w, thickness)
        if wb[0] <= cx <= wb[2] and wb[1] <= cy <= wb[3]:
            # Distance to wall centerline (perpendicular to wall axis)
            if w.get("orientation") == "h":
                shift = abs(cy - float(w["start"][1]))
            else:
                shift = abs(cx - float(w["start"][0]))
            if shift < best_shift:
                best_shift = shift
                best = w
    return best, best_shift


def _find_existing_gap(center: list[float],
                        opening_orientation: str,
                        opening_width_pts: float,
                        walls: list[dict],
                        thickness: float) -> tuple[dict | None, float, str]:
    """Look for two colinear walls bracketing the opening center.

    Returns (host_wall, shift_pt, gap_id). ``host_wall`` is the LEFT/LOWER
    bracket wall (the one with smaller axis coord). ``gap_id`` encodes
    the pair like ``"gap_w006_w007"``. shift_pt is the
    distance from center to the gap's CROSS-axis line (should be small
    if the user painted on the colinear axis).

    Returns (None, inf, "") if no plausible gap matches.

    Note: this is the LEGACY center-based path. The segment-based
    classifier in ``classify_opening_host_segment`` is preferred for
    real human annotations because the user paints a BBOX not a point;
    using the full segment catches matches the center alone misses.
    Kept here for synthetic-test backward compatibility.
    """
    cx, cy = float(center[0]), float(center[1])
    # Colinearity tolerance: the wall has thickness/2 on each side of
    # its centerline; allow paint anywhere within the wall's filled
    # rectangle as "on the colinear band". No global multiplier — the
    # evidence is the wall thickness itself.
    coll_tol = thickness * 0.6
    # Filter walls by orientation matching the opening
    same_ori = [w for w in walls
                 if w.get("orientation") == opening_orientation]
    if len(same_ori) < 2:
        return None, float("inf"), ""

    if opening_orientation == "h":
        # h walls: cross axis = y. Find walls whose y is close to cy.
        candidates = [w for w in same_ori
                       if abs(float(w["start"][1]) - cy) <= coll_tol]
        # Pair walls whose x-axis ranges bracket cx
        for i, wa in enumerate(candidates):
            wa_min, wa_max = sorted([wa["start"][0], wa["end"][0]])
            for wb in candidates[i + 1:]:
                wb_min, wb_max = sorted([wb["start"][0], wb["end"][0]])
                # wa is left of wb if wa_max < wb_min
                left, right = (wa, wb) if wa_max <= wb_min else (wb, wa)
                left_max = max(left["start"][0], left["end"][0])
                right_min = min(right["start"][0], right["end"][0])
                if left_max <= cx <= right_min:
                    # cx in the gap; check gap width matches opening
                    gap = right_min - left_max
                    if gap <= 0:
                        continue
                    # Accept any gap >= half opening width (the opening
                    # may slightly overshoot into the bracket walls).
                    if gap >= opening_width_pts * 0.5:
                        shift = abs(cy - float(left["start"][1]))
                        gap_id = f"gap_{left['id']}_{right['id']}"
                        return left, shift, gap_id
    else:  # v
        candidates = [w for w in same_ori
                       if abs(float(w["start"][0]) - cx) <= coll_tol]
        for i, wa in enumerate(candidates):
            wa_min, wa_max = sorted([wa["start"][1], wa["end"][1]])
            for wb in candidates[i + 1:]:
                wb_min, wb_max = sorted([wb["start"][1], wb["end"][1]])
                left, right = (wa, wb) if wa_max <= wb_min else (wb, wa)
                left_max = max(left["start"][1], left["end"][1])
                right_min = min(right["start"][1], right["end"][1])
                if left_max <= cy <= right_min:
                    gap = right_min - left_max
                    if gap <= 0:
                        continue
                    if gap >= opening_width_pts * 0.5:
                        shift = abs(cx - float(left["start"][0]))
                        gap_id = f"gap_{left['id']}_{right['id']}"
                        return left, shift, gap_id
    # Also accept "single wall is too short, but its CROSS coord matches
    # the user-paint; the opening simply lives past the wall's end". In
    # that case mode is still existing_gap with host = nearest wall and
    # gap_id = open-ended.
    if opening_orientation == "h":
        for w in same_ori:
            cross = float(w["start"][1])
            if abs(cross - cy) > coll_tol:
                continue
            axis_min, axis_max = sorted([w["start"][0], w["end"][0]])
            # cx is within opening_width/2 of an end -> bracketing the gap
            if axis_min - thickness <= cx <= axis_min:
                return w, abs(cross - cy), f"gap_before_{w['id']}"
            if axis_max <= cx <= axis_max + thickness:
                return w, abs(cross - cy), f"gap_after_{w['id']}"
    else:
        for w in same_ori:
            cross = float(w["start"][0])
            if abs(cross - cx) > coll_tol:
                continue
            axis_min, axis_max = sorted([w["start"][1], w["end"][1]])
            if axis_min - thickness <= cy <= axis_min:
                return w, abs(cross - cx), f"gap_before_{w['id']}"
            if axis_max <= cy <= axis_max + thickness:
                return w, abs(cross - cx), f"gap_after_{w['id']}"
    return None, float("inf"), ""


def _opening_segment(opening: dict) -> tuple[str, float, float, float]:
    """Derive the architectural SEGMENT covered by the painted blob.

    For an h opening with bbox [x0, y0, x1, y1]:
        returns ("h", x0, x1, (y0+y1)/2)   # axis [x0..x1] at cross_y
    For a v opening:
        returns ("v", y0, y1, (x0+x1)/2)   # axis [y0..y1] at cross_x

    Falls back to a degenerate segment of width = opening_width_pts
    centered on center_pts when bbox is absent.
    """
    orient = opening.get("orientation", "h")
    bbox = opening.get("bbox_pts")
    if bbox and len(bbox) == 4:
        x0, y0, x1, y1 = [float(v) for v in bbox]
        if orient == "h":
            return ("h", min(x0, x1), max(x0, x1), (y0 + y1) / 2.0)
        return ("v", min(y0, y1), max(y0, y1), (x0 + x1) / 2.0)
    # Fallback from center + width
    c = opening.get("center_pts") or opening.get("center") or [0.0, 0.0]
    w = float(opening.get("opening_width_pts", 0))
    if orient == "h":
        return ("h", float(c[0]) - w / 2, float(c[0]) + w / 2, float(c[1]))
    return ("v", float(c[1]) - w / 2, float(c[1]) + w / 2, float(c[0]))


def _wall_axis_range(w: dict) -> tuple[float, float, float, str]:
    """Return (axis_min, axis_max, cross, orientation) for a wall."""
    sx, sy = float(w["start"][0]), float(w["start"][1])
    ex, ey = float(w["end"][0]), float(w["end"][1])
    if w.get("orientation") == "h":
        return (min(sx, ex), max(sx, ex), sy, "h")
    return (min(sy, ey), max(sy, ey), sx, "v")


def _nearest_candidates(opening: dict,
                         walls: list[dict],
                         thickness: float,
                         top_n: int = 3) -> list[dict]:
    """Diagnose: list the N nearest walls + colinear-gap candidates
    that COULD host this opening, sorted by a composite distance.
    Used in unhosted reports.
    """
    orient, axis_lo, axis_hi, cross = _opening_segment(opening)
    cands: list[dict] = []
    # Same-orientation walls
    for w in walls:
        if w.get("orientation") != orient:
            continue
        a0, a1, wcross, _ = _wall_axis_range(w)
        cross_diff = abs(wcross - cross)
        # Axis overlap of opening segment vs wall axis range
        overlap = max(0.0, min(a1, axis_hi) - max(a0, axis_lo))
        cands.append({
            "kind": "wall",
            "wall_id": w["id"],
            "wall_axis_range": [round(a0, 3), round(a1, 3)],
            "wall_cross": round(wcross, 3),
            "cross_diff": round(cross_diff, 3),
            "axis_overlap_pts": round(overlap, 3),
            "score": round(cross_diff + max(0, axis_lo - a1) + max(0, a0 - axis_hi), 3),
        })
    # Sort walls by score (lower = closer)
    cands.sort(key=lambda c: c["score"])
    nearest_walls = cands[:top_n]

    # Same-orientation wall pairs (gaps)
    gap_cands: list[dict] = []
    same_ori = [w for w in walls if w.get("orientation") == orient]
    for i, wa in enumerate(same_ori):
        for wb in same_ori[i + 1:]:
            a0, a1, ca, _ = _wall_axis_range(wa)
            b0, b1, cb, _ = _wall_axis_range(wb)
            # Same cross-axis within thickness
            cross_diff_a = abs(ca - cross)
            cross_diff_b = abs(cb - cross)
            cross_diff = (cross_diff_a + cross_diff_b) / 2
            if abs(ca - cb) > thickness * 0.6:
                continue  # not colinear
            # Gap range
            if a1 <= b0:
                gap_lo, gap_hi = a1, b0
            elif b1 <= a0:
                gap_lo, gap_hi = b1, a0
            else:
                continue  # walls overlap, no gap
            gap = gap_hi - gap_lo
            if gap <= 0:
                continue
            # Opening segment overlap with gap
            seg_overlap = max(0.0, min(gap_hi, axis_hi) - max(gap_lo, axis_lo))
            gap_cands.append({
                "kind": "gap",
                "gap_id": f"gap_{wa['id']}_{wb['id']}",
                "walls": [wa["id"], wb["id"]],
                "gap_axis_range": [round(gap_lo, 3), round(gap_hi, 3)],
                "gap_width_pts": round(gap, 3),
                "cross_diff": round(cross_diff, 3),
                "seg_overlap_pts": round(seg_overlap, 3),
                "score": round(cross_diff
                                + max(0, axis_lo - gap_hi)
                                + max(0, gap_lo - axis_hi), 3),
            })
    gap_cands.sort(key=lambda c: c["score"])
    nearest_gaps = gap_cands[:top_n]
    return nearest_walls + nearest_gaps


def classify_opening_host_segment(opening: dict,
                                    walls: list[dict],
                                    thickness: float,
                                    *,
                                    cross_tol_factor: float = 1.5,
                                    min_axis_overlap_frac: float = 0.5
                                    ) -> dict:
    """Segment-based host classifier (preferred over center-only).

    Derives the opening's architectural segment from its bbox and
    compares it to wall geometry:

    1. cut_into_wall — a SINGLE same-orientation wall whose filled
       rectangle COVERS the opening's segment. Requires:
       a. cross-axis distance ≤ thickness * cross_tol_factor.
          cross_tol_factor = 1.5 by design — wall half-width (0.5)
          + paint-precision allowance (1.0) = the maximum
          perpendicular distance an honest user-paint can land from
          the wall centerline. This EQUALS the gate's WARN threshold
          (shift_pt > 8 ≈ thickness * 1.5 on planta_74), so anything
          the classifier accepts is still inspected by the gate.
       b. axis overlap of opening segment vs wall axis range ≥
          min_axis_overlap_frac (default 0.5) of opening length.

    2. existing_gap — a PAIR of colinear same-orientation walls
       whose CROSS axes are within thickness * cross_tol_factor AND
       whose axis gap contains the opening segment with overlap ≥
       min_axis_overlap_frac.

    3. unhosted — neither matches. Returns nearest candidates for
       diagnostic (cause classification A-F per the audit protocol).

    Returns a dict with the same shape as classify_opening_host plus:
        "nearest_candidates": [...]  (for unhosted, 3 walls + 3 gaps)
        "evidence": {...}            (for matched, what passed)
    """
    orient, axis_lo, axis_hi, cross = _opening_segment(opening)
    seg_len = max(axis_hi - axis_lo, 0.001)
    center_axis = (axis_lo + axis_hi) / 2.0
    if orient == "h":
        center = [center_axis, cross]
    else:
        center = [cross, center_axis]

    cross_tol = thickness * cross_tol_factor
    # 1) cut_into_wall — single wall covering segment
    same_ori = [w for w in walls if w.get("orientation") == orient]
    best_wall: dict | None = None
    best_axis_overlap = 0.0
    best_cross_diff = float("inf")
    for w in same_ori:
        a0, a1, wcross, _ = _wall_axis_range(w)
        cd = abs(wcross - cross)
        if cd > cross_tol:
            continue
        overlap = max(0.0, min(a1, axis_hi) - max(a0, axis_lo))
        if overlap / seg_len < min_axis_overlap_frac:
            continue
        # Prefer wall with most overlap; tie-break by cross_diff
        if overlap > best_axis_overlap or (
            overlap == best_axis_overlap and cd < best_cross_diff
        ):
            best_wall = w
            best_axis_overlap = overlap
            best_cross_diff = cd
    if best_wall:
        # Adjust opening center to lie on the wall's centerline
        a0, a1, wcross, _ = _wall_axis_range(best_wall)
        if orient == "h":
            adjusted = [center_axis, wcross]
        else:
            adjusted = [wcross, center_axis]
        shift = ((adjusted[0] - center[0]) ** 2
                 + (adjusted[1] - center[1]) ** 2) ** 0.5
        return {
            "mode": "cut_into_wall",
            "host_wall_id": best_wall["id"],
            "gap_id": None,
            "original_center_pdf": list(center),
            "adjusted_center_pdf": adjusted,
            "shift_pt": round(shift, 3),
            "carved": True,
            "drawn": True,
            "evidence": {
                "axis_overlap_pts": round(best_axis_overlap, 3),
                "axis_overlap_frac": round(best_axis_overlap / seg_len, 3),
                "cross_diff_pts": round(best_cross_diff, 3),
                "cross_tol_pts": round(cross_tol, 3),
            },
        }

    # 2) existing_gap — colinear pair bracketing segment.
    # gap_tol = distance between the 2 bracket walls' own cross axes
    # (NOT distance from opening). Two walls are colinear if their own
    # cross coords match within thickness*0.6 (less than a full wall
    # thickness — they're truly on the same row).
    gap_tol = thickness * 0.6
    best_pair = None
    best_seg_overlap = 0.0
    best_cross_pair = float("inf")
    for i, wa in enumerate(same_ori):
        a0, a1, ca, _ = _wall_axis_range(wa)
        if abs(ca - cross) > cross_tol:
            continue
        for wb in same_ori[i + 1:]:
            b0, b1, cb, _ = _wall_axis_range(wb)
            if abs(cb - cross) > cross_tol:
                continue
            if abs(ca - cb) > gap_tol:
                continue
            # Determine gap
            if a1 <= b0:
                gap_lo, gap_hi = a1, b0
                left, right = wa, wb
            elif b1 <= a0:
                gap_lo, gap_hi = b1, a0
                left, right = wb, wa
            else:
                continue
            gap = gap_hi - gap_lo
            if gap <= 0:
                continue
            seg_overlap = max(0.0, min(gap_hi, axis_hi) - max(gap_lo, axis_lo))
            if seg_overlap / seg_len < min_axis_overlap_frac:
                continue
            cross_pair = (abs(ca - cross) + abs(cb - cross)) / 2
            if seg_overlap > best_seg_overlap or (
                seg_overlap == best_seg_overlap and cross_pair < best_cross_pair
            ):
                best_pair = (left, right, gap_lo, gap_hi)
                best_seg_overlap = seg_overlap
                best_cross_pair = cross_pair
    if best_pair:
        left, right, gap_lo, gap_hi = best_pair
        a0, a1, wcross, _ = _wall_axis_range(left)
        if orient == "h":
            adjusted = [center_axis, wcross]
        else:
            adjusted = [wcross, center_axis]
        shift = ((adjusted[0] - center[0]) ** 2
                 + (adjusted[1] - center[1]) ** 2) ** 0.5
        return {
            "mode": "existing_gap",
            "host_wall_id": left["id"],
            "gap_id": f"gap_{left['id']}_{right['id']}",
            "original_center_pdf": list(center),
            "adjusted_center_pdf": adjusted,
            "shift_pt": round(shift, 3),
            "carved": False,
            "drawn": True,
            "evidence": {
                "seg_overlap_pts": round(best_seg_overlap, 3),
                "seg_overlap_frac": round(best_seg_overlap / seg_len, 3),
                "gap_width_pts": round(gap_hi - gap_lo, 3),
                "cross_pair_avg_pts": round(best_cross_pair, 3),
                "cross_tol_pts": round(cross_tol, 3),
            },
        }

    # 3) unhosted — emit diagnostic
    nearest = _nearest_candidates(opening, walls, thickness, top_n=3)
    return {
        "mode": "unhosted",
        "host_wall_id": None,
        "gap_id": None,
        "original_center_pdf": list(center),
        "adjusted_center_pdf": list(center),
        "shift_pt": 0.0,
        "carved": False,
        "drawn": False,
        "evidence": {
            "cross_tol_pts": round(cross_tol, 3),
            "min_axis_overlap_frac": min_axis_overlap_frac,
        },
        "nearest_candidates": nearest,
    }


def classify_opening_host(opening: dict,
                           walls: list[dict],
                           thickness: float) -> dict:
    """Classify the hosting mode of a single human-annotated opening.

    Returns a dict:
        {
          "mode": "cut_into_wall" | "existing_gap" | "unhosted",
          "host_wall_id": str | None,
          "gap_id": str | None,
          "original_center_pdf": [x, y],
          "adjusted_center_pdf": [x, y],
          "shift_pt": float,
          "carved": bool,        # cut_into_wall=True, others=False
          "drawn": bool,         # cut_into_wall/existing_gap=True, unhosted=False
        }
    """
    center = list(opening.get("center_pts", [0.0, 0.0]))
    orientation = opening.get("orientation", "h")
    width = float(opening.get("opening_width_pts", 0))

    # 1) cut_into_wall — opening center lies inside a wall rectangle
    wall, perp = _find_cut_into_wall(center, walls, thickness)
    if wall:
        # Snap center to wall centerline (perpendicular). Only minor —
        # the wall is by definition within thickness/2 of center.
        if wall.get("orientation") == "h":
            adjusted = [center[0], float(wall["start"][1])]
        else:
            adjusted = [float(wall["start"][0]), center[1]]
        shift = ((adjusted[0] - center[0]) ** 2
                 + (adjusted[1] - center[1]) ** 2) ** 0.5
        return {
            "mode": "cut_into_wall",
            "host_wall_id": wall["id"],
            "gap_id": None,
            "original_center_pdf": center,
            "adjusted_center_pdf": adjusted,
            "shift_pt": round(shift, 3),
            "carved": True,
            "drawn": True,
        }

    # 2) existing_gap — colinear walls bracket the user-paint position
    host, perp_gap, gap_id = _find_existing_gap(
        center, orientation, width, walls, thickness
    )
    if host:
        # Adjust center only on the CROSS axis to land on the colinear
        # band. AXIS coord stays where the user painted (the door/window
        # lives in the gap at that position).
        if host.get("orientation") == "h":
            adjusted = [center[0], float(host["start"][1])]
        else:
            adjusted = [float(host["start"][0]), center[1]]
        shift = ((adjusted[0] - center[0]) ** 2
                 + (adjusted[1] - center[1]) ** 2) ** 0.5
        return {
            "mode": "existing_gap",
            "host_wall_id": host["id"],
            "gap_id": gap_id,
            "original_center_pdf": center,
            "adjusted_center_pdf": adjusted,
            "shift_pt": round(shift, 3),
            "carved": False,
            "drawn": True,
        }

    # 3) unhosted
    return {
        "mode": "unhosted",
        "host_wall_id": None,
        "gap_id": None,
        "original_center_pdf": center,
        "adjusted_center_pdf": list(center),
        "shift_pt": 0.0,
        "carved": False,
        "drawn": False,
    }


def apply_truth_to_consensus(consensus: dict,
                              truth: dict,
                              mode: str = "replace",
                              classifier: str = "segment") -> dict:
    """Return a new consensus dict with human openings applied + host
    classification stamped. Does NOT mutate the input dicts.

    ``classifier`` selects ``"segment"`` (default; uses the painted
    bbox as a full axis segment) or ``"center"`` (legacy; uses only
    the bbox center, prone to missing matches when paint is slightly
    off the wall row).
    """
    out = dict(consensus)
    walls = out.get("walls", [])
    thickness = float(out.get("wall_thickness_pts", 5.4))

    human_openings: list[dict] = []
    host_log: list[dict] = []
    for i, src in enumerate(truth.get("openings", [])):
        oid = f"h_o{i:03d}"
        if classifier == "segment":
            hosting = classify_opening_host_segment(src, walls, thickness)
        else:
            hosting = classify_opening_host(src, walls, thickness)
        adjusted = hosting["adjusted_center_pdf"]
        wall_id = hosting["host_wall_id"]
        hinge_side = src.get("hinge_side", "left")
        kind = src["kind"]
        op = {
            "id": oid,
            "kind": "door" if kind == "interior_door" else (
                "window" if kind in ("window", "glazed_balcony") else "door"
            ),
            "kind_v5": kind,
            "kind_v5_reason": "human_annotation_truth_file",
            "geometry_origin": "human_annotation",
            "confidence": 1.0,
            "decision": "clean",
            "required": True,
            "wall_id": wall_id,
            "center": list(adjusted),
            "opening_width_pts": float(src.get("opening_width_pts", 0)),
            "hinge_side": hinge_side,
            "host_mode": hosting["mode"],
            "human_annotation": {
                "source_image": truth.get("source_image"),
                "bbox_px": src.get("bbox_px"),
                "bbox_pts": src.get("bbox_pts"),
                "color": src.get("color"),
                "original_center_pdf": hosting["original_center_pdf"],
                "adjusted_center_pdf": hosting["adjusted_center_pdf"],
                "shift_pt": hosting["shift_pt"],
                "gap_id": hosting["gap_id"],
                "carved_predicted": hosting["carved"],
                "drawn_predicted": hosting["drawn"],
            },
        }
        # Preserve any wall_id the extractor wrote if classifier returns
        # None but extractor had a nearest-wall match (informational only).
        if wall_id is None and src.get("wall_id"):
            op["wall_id"] = src["wall_id"]
            op["human_annotation"]["extractor_wall_id"] = src["wall_id"]
        human_openings.append(op)
        host_entry = {
            "opening_id": oid,
            "kind": kind,
            "mode": hosting["mode"],
            "host_wall_id": hosting["host_wall_id"],
            "gap_id": hosting["gap_id"],
            "shift_pt": hosting["shift_pt"],
            "carved_predicted": hosting["carved"],
            "drawn_predicted": hosting["drawn"],
            "original_center_pdf": hosting["original_center_pdf"],
            "adjusted_center_pdf": hosting["adjusted_center_pdf"],
        }
        if "evidence" in hosting:
            host_entry["evidence"] = hosting["evidence"]
        if "nearest_candidates" in hosting:
            host_entry["nearest_candidates"] = hosting["nearest_candidates"]
        host_log.append(host_entry)

    if mode == "replace":
        out["openings"] = human_openings
    elif mode == "merge":
        existing = list(out.get("openings", []))
        kept = []
        for ex in existing:
            ex_c = ex.get("center") or ex.get("center_pts")
            if not ex_c:
                kept.append(ex)
                continue
            cx, cy = float(ex_c[0]), float(ex_c[1])
            collides = False
            for ho in human_openings:
                hc = ho["center"]
                if abs(cx - hc[0]) <= 25.0 and abs(cy - hc[1]) <= 25.0:
                    collides = True
                    break
            if not collides:
                kept.append(ex)
        out["openings"] = human_openings + kept
    else:
        raise ValueError(f"unknown mode: {mode}")

    # Metadata stamp
    md = dict(out.get("metadata", {}))
    md["human_openings_truth"] = {
        "applied": True,
        "mode": mode,
        "n_openings_applied": len(human_openings),
        "source_truth": truth.get("source_image"),
        "required_counts": truth.get("required_counts"),
        "explicit_constraints_count": len(truth.get("explicit_constraints", [])),
        "host_log": host_log,
        "host_summary": {
            "cut_into_wall": sum(1 for h in host_log if h["mode"] == "cut_into_wall"),
            "existing_gap": sum(1 for h in host_log if h["mode"] == "existing_gap"),
            "unhosted": sum(1 for h in host_log if h["mode"] == "unhosted"),
        },
    }
    out["metadata"] = md
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--mode", choices=["replace", "merge"], default="replace",
                    help="'replace' (default): wipe consensus.openings and "
                         "write only human openings. 'merge': keep "
                         "existing non-colliding openings plus human ones.")
    args = ap.parse_args()

    consensus = json.loads(args.consensus.read_text())
    truth = json.loads(args.truth.read_text())
    out = apply_truth_to_consensus(consensus, truth, mode=args.mode)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))

    md = out["metadata"]["human_openings_truth"]
    print(f"[apply] mode={md['mode']} "
          f"openings_applied={md['n_openings_applied']} -> {args.out}")
    print(f"  host_summary: {md['host_summary']}")
    print()
    print(f"  {'id':>6} {'kind':>15} {'mode':>14} {'host':>12} "
          f"{'shift_pt':>9} {'carve':>6} {'drawn':>6}")
    for h in md["host_log"]:
        host = h["host_wall_id"] or h["gap_id"] or "-"
        print(f"  {h['opening_id']:>6} {h['kind']:>15} {h['mode']:>14} "
              f"{host:>12} {h['shift_pt']:>9.2f} "
              f"{str(h['carved_predicted']):>6} "
              f"{str(h['drawn_predicted']):>6}")
    # Required-counts summary
    actual: dict[str, int] = {}
    for op in out["openings"]:
        if op.get("geometry_origin") == "human_annotation":
            k = op.get("kind_v5") or op.get("kind")
            actual[k] = actual.get(k, 0) + 1
    req = truth.get("required_counts", {}) or {}
    print()
    print("  required vs actual:")
    for kind in sorted(set(list(req.keys()) + list(actual.keys()))):
        r = req.get(kind, 0)
        a = actual.get(kind, 0)
        status = "OK" if a >= r else "FAIL"
        print(f"    {kind:18}: actual={a}, required={r} [{status}]")


if __name__ == "__main__":
    main()
