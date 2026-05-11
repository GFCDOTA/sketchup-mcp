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
    """
    cx, cy = float(center[0]), float(center[1])
    # Colinearity tolerance: how far the user-paint cross-axis can be
    # from a candidate wall row. thickness*1.5 = the brush-paint width
    # plus auto-calibrate drift typical of a 1999x1307 -> 595x842 map
    # (empirical: cross-axis diffs of 4-7 pt observed on planta_74).
    # Tighter values miss legitimate gap matches; looser values over-
    # match neighbouring wall rows.
    coll_tol = thickness * 1.5
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
                              mode: str = "replace") -> dict:
    """Return a new consensus dict with human openings applied + host
    classification stamped. Does NOT mutate the input dicts.
    """
    out = dict(consensus)
    walls = out.get("walls", [])
    thickness = float(out.get("wall_thickness_pts", 5.4))

    human_openings: list[dict] = []
    host_log: list[dict] = []
    for i, src in enumerate(truth.get("openings", [])):
        oid = f"h_o{i:03d}"
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
        host_log.append({
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
        })

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
