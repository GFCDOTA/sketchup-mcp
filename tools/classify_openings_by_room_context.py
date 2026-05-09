"""Classify openings by their adjacent rooms — caminho B.

The vector detector emits geometric openings (svg_arc, svg_segments,
wall_gap) with no notion of WHAT they connect. The previous V5
classifier (`classify_opening_kind.py`) used purely geometric features
and gave coarse labels (door_arc / open_passage / glazed_balcony /
window). For planta_74 it produced 12 door_arcs (with ghost duplicates
of width 2.15 m = arc-radius mis-measured as width) and 3
open_passages all rendered uniformly.

This module replaces that with room-context classification:

1. For each wall, find which rooms (if any) it borders on each side.
   Probe a point thickness/2 + epsilon on each cross-axis side, find
   the room polygon containing it.
2. For each opening on that wall, look up the two adjacent rooms.
3. Apply rules based on (room_a_kind, room_b_kind, width_m):

   | room_a   | room_b   | width    | kind                 |
   |----------|----------|----------|----------------------|
   | indoor   | indoor   | < 1.2 m  | interior_door        |
   | indoor   | indoor   | 1.2-2.5  | interior_passage     |
   | indoor   | open_air | < 1.5 m  | window               |
   | indoor   | open_air | 1.5-3.5  | glazed_balcony       |
   | indoor   | None     | < 1.5 m  | window               |
   | indoor   | None     | 1.5-3.5  | glazed_balcony       |

   Anything outside these ranges is dropped (almost always an arc
   whose radius was mis-measured as the chord).

4. Dedup pass: openings on the same wall with centers within
   `dedup_distance_pt` are clustered. Within each cluster, keep the
   one whose context_kind is non-None AND whose width fits the rule
   most snugly. Others are dropped.

After this pass, ``opening['kind_v5']`` becomes one of:
``interior_door | interior_passage | window | glazed_balcony``.
``opening['kind_v5_reason']`` records the adjacency.

Schema-additive: ``geometry_origin`` is preserved (Ruby exporter still
keys carving on it). ``hinge`` is preserved.

This module does NOT invoke SketchUp, does NOT change room/wall data,
and is a pure read-modify-write over ``consensus['openings']``.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ---- Constants ----

# Thresholds (PDF points). Calibrated for planta_74 PT_TO_M = 0.19/5.4.
PT_TO_M_DEFAULT = 0.19 / 5.4
DEDUP_DISTANCE_PT = 30.0

# Width ranges (meters). Slightly generous to absorb scale noise.
INTERIOR_DOOR_MAX_M = 1.20
INTERIOR_PASSAGE_MIN_M = 1.20
INTERIOR_PASSAGE_MAX_M = 2.50
WINDOW_MAX_M = 1.50
GLAZED_BALCONY_MIN_M = 1.50
GLAZED_BALCONY_MAX_M = 3.50

# Substrings (uppercase) that mark a room as open-air. The flanking
# wall to such a room behaves like an exterior wall: glazed instead
# of solid.
OPEN_AIR_LABEL_SUBSTRINGS = (
    "TERRACO", "TERRAÇO", "SACADA", "VARANDA",
)

# Substrings that mark a room as private (bedrooms, bathrooms). Walls
# between two private rooms are ALWAYS partitioned by a door —
# real apartments do not have open passages between SUITE/BANHO/
# LAVABO/QUARTO. So if the classifier sees two private rooms the
# door range is widened (up to PRIVATE_PAIR_DOOR_MAX_M) and any
# wider opening is dropped (= detector noise).
PRIVATE_ROOM_LABEL_SUBSTRINGS = (
    "SUITE", "SUÍTE", "QUARTO", "DORMITORIO", "DORMITÓRIO",
    "BANHO", "BANHEIRO", "LAVABO", "WC",
)
PRIVATE_PAIR_DOOR_MAX_M = 1.50  # widened range for private<->private


def is_open_air_room(name: Optional[str]) -> bool:
    if not name:
        return False
    upper = name.upper()
    return any(s in upper for s in OPEN_AIR_LABEL_SUBSTRINGS)


def is_private_room(name: Optional[str]) -> bool:
    if not name:
        return False
    upper = name.upper()
    return any(s in upper for s in PRIVATE_ROOM_LABEL_SUBSTRINGS)


# ---- Geometry helpers ----

def _point_in_polygon(pt: tuple[float, float],
                      polygon: list[list[float]]) -> bool:
    """Ray casting. polygon is a list of [x,y] vertices."""
    x, y = pt
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]
        if ((yi > y) != (yj > y)):
            # Avoid division by zero with epsilon
            x_intersect = (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
            if x < x_intersect:
                inside = not inside
        j = i
    return inside


def _find_room_containing_polygon(pt: tuple[float, float],
                                    rooms: list[dict]) -> Optional[dict]:
    for r in rooms:
        polygon = r.get("polygon_pts")
        if polygon and _point_in_polygon(pt, polygon):
            return r
    return None


def _find_room_by_nearest_seed(pt: tuple[float, float],
                                 rooms: list[dict],
                                 max_distance_pt: float = 400.0,
                                 ) -> Optional[dict]:
    """Robust lookup that does NOT rely on polygon quality. For each
    probe, returns the room whose ``seed_pt`` (label centroid) is
    closest, provided it's within max_distance_pt. Polygons in
    ``rooms_from_seeds`` output occasionally overlap or have holes;
    seeds are placed at the OCR'd label, so they're stable anchors.
    """
    px, py = pt
    best = None
    best_d = float("inf")
    for r in rooms:
        seed = r.get("seed_pt")
        if not seed or len(seed) < 2:
            continue
        sx, sy = seed[0], seed[1]
        d = math.hypot(px - sx, py - sy)
        if d < best_d:
            best_d = d
            best = r
    if best is None or best_d > max_distance_pt:
        return None
    return best


def _find_room_for_probe(pt: tuple[float, float],
                          rooms: list[dict]) -> Optional[dict]:
    """Hybrid: try polygon containment first (precise when it works);
    fall back to nearest seed (robust against polygon defects)."""
    poly_hit = _find_room_containing_polygon(pt, rooms)
    if poly_hit is not None:
        return poly_hit
    return _find_room_by_nearest_seed(pt, rooms)


def find_rooms_flanking_wall(wall: dict, rooms: list[dict],
                              thickness_pt: float,
                              opening_center: Optional[list] = None,
                              ) -> tuple[Optional[dict], Optional[dict]]:
    """Return (room_minus, room_plus) — rooms touching each cross-axis
    side of the wall.

    Uses the hybrid polygon+nearest-seed lookup. If both probes return
    the SAME room (geometrically impossible for a real partition), we
    fall back to nearest-seed exclusively for both probes — this
    handles the case where a single room polygon overlaps both sides
    of an interior wall.
    """
    sx, sy = wall["start"]
    ex, ey = wall["end"]
    if opening_center is not None and len(opening_center) >= 2:
        if wall["orientation"] == "h":
            mx, my = float(opening_center[0]), (sy + ey) / 2.0
        else:
            mx, my = (sx + ex) / 2.0, float(opening_center[1])
    else:
        mx, my = (sx + ex) / 2.0, (sy + ey) / 2.0

    eps = thickness_pt * 0.6 + 1.0
    if wall["orientation"] == "h":
        probe_minus = (mx, my - eps)
        probe_plus = (mx, my + eps)
    else:
        probe_minus = (mx - eps, my)
        probe_plus = (mx + eps, my)

    rm = _find_room_for_probe(probe_minus, rooms)
    rp = _find_room_for_probe(probe_plus, rooms)
    if rm is not None and rp is not None and rm.get("id") == rp.get("id"):
        # Self-adjacent: polygon error. Disambiguate via nearest-seed
        # using each probe directly, then exclude the polygon-hit room
        # from one of them so we get 2 different rooms.
        seeds_minus = _find_room_by_nearest_seed(probe_minus, rooms)
        seeds_plus = _find_room_by_nearest_seed(probe_plus, rooms)
        if seeds_minus and seeds_plus and \
                seeds_minus.get("id") != seeds_plus.get("id"):
            return seeds_minus, seeds_plus
        # Still self-adjacent: pick second-nearest for one side
        return _disambiguate_self_adjacent(probe_minus, probe_plus, rooms)
    return rm, rp


def _disambiguate_self_adjacent(probe_minus: tuple,
                                  probe_plus: tuple,
                                  rooms: list[dict]) -> tuple:
    """Last-resort: nearest seed for each probe, but force them to be
    different rooms. Returns the closest pair of distinct rooms."""
    def k_nearest(pt, k=3):
        scored = []
        for r in rooms:
            seed = r.get("seed_pt")
            if not seed:
                continue
            d = math.hypot(pt[0] - seed[0], pt[1] - seed[1])
            scored.append((d, r))
        scored.sort(key=lambda x: x[0])
        return scored[:k]

    near_minus = k_nearest(probe_minus, k=3)
    near_plus = k_nearest(probe_plus, k=3)
    if not near_minus or not near_plus:
        return (None, None)
    # Try every (minus, plus) pair, keep first with distinct room ids
    for d1, rm in near_minus:
        for d2, rp in near_plus:
            if rm.get("id") != rp.get("id"):
                return rm, rp
    return near_minus[0][1], None


# ---- Classification ----

def _classify_pair(room_a: Optional[dict], room_b: Optional[dict],
                    width_m: float) -> Optional[str]:
    """Apply the room-context rules. Returns a kind_v5 value or None
    (drop). See module docstring for the rule table."""
    a_open = is_open_air_room(room_a["name"]) if room_a else False
    b_open = is_open_air_room(room_b["name"]) if room_b else False
    a_indoor = room_a is not None and not a_open
    b_indoor = room_b is not None and not b_open
    a_private = is_private_room(room_a["name"]) if room_a else False
    b_private = is_private_room(room_b["name"]) if room_b else False

    # Both indoor closed rooms
    if a_indoor and b_indoor:
        # Two private rooms (suite/banho/quarto/lavabo): force door
        # classification with widened range. Real apartments never
        # have open passages here. Anything > PRIVATE_PAIR_DOOR_MAX_M
        # is detector noise.
        if a_private and b_private:
            if width_m <= PRIVATE_PAIR_DOOR_MAX_M:
                return "interior_door"
            return None
        if width_m < INTERIOR_DOOR_MAX_M:
            return "interior_door"
        if INTERIOR_PASSAGE_MIN_M <= width_m <= INTERIOR_PASSAGE_MAX_M:
            return "interior_passage"
        return None

    # One indoor + (open_air OR exterior None)
    if a_indoor or b_indoor:
        if width_m < WINDOW_MAX_M:
            return "window"
        if GLAZED_BALCONY_MIN_M <= width_m <= GLAZED_BALCONY_MAX_M:
            return "glazed_balcony"
        return None

    # Both open_air or both exterior — drop, soft_barriers handles parapets
    return None


def _width_fit_score(kind: str, width_m: float) -> float:
    """Lower = better fit. Used to pick a representative when a cluster
    has multiple valid candidates (e.g., svg_arc gives both corda and
    raio — corda is the real width and fits the kind range tighter)."""
    if kind == "interior_door":
        target = 0.90
    elif kind == "interior_passage":
        target = 1.80
    elif kind == "window":
        target = 1.10
    elif kind == "glazed_balcony":
        target = 2.20
    else:
        target = width_m
    return abs(width_m - target)


# ---- Confidence + hypotheses + evidence ----

KIND_TARGETS_M = {
    "interior_door":     (0.90, 0.50),  # (target_m, half-window for full credit)
    "interior_passage":  (1.80, 0.70),
    "window":            (1.10, 0.50),
    "glazed_balcony":    (2.20, 1.00),
}


def _width_fit_credit(kind: str, width_m: float) -> float:
    """0.0 .. 1.0 — how snugly width matches the canonical target for
    this kind. 1.0 at target, decays linearly to 0.0 at +/- half-window."""
    target, half = KIND_TARGETS_M.get(kind, (width_m, 0.5))
    delta = abs(width_m - target)
    if delta <= 0:
        return 1.0
    if delta >= half:
        return 0.0
    return 1.0 - (delta / half)


def _adjacency_plausibility(room_a_name: str | None,
                              room_b_name: str | None,
                              kind: str) -> float:
    """0.0 .. 1.0 — how architecturally plausible is this kind given
    the two adjacent rooms. Heuristic and conservative; meant to
    penalise weird pairings (e.g., COZINHA <-> SUITE 02 wide passage).

    No hard rules here — just bumps a confidence floor up when the
    pairing is canonical (private<->private = door; sala<->jantar =
    passage; sala<->terraco = glazed_balcony).
    """
    if not room_a_name or not room_b_name:
        # Indoor-to-exterior is fine for window / glazed_balcony
        if kind in ("window", "glazed_balcony"):
            return 1.0
        return 0.4
    a = room_a_name.upper()
    b = room_b_name.upper()
    a_priv = is_private_room(a)
    b_priv = is_private_room(b)
    a_open = is_open_air_room(a)
    b_open = is_open_air_room(b)

    if kind == "interior_door":
        if a_priv and b_priv:
            return 1.0  # canonical
        if a_priv != b_priv:
            return 0.85  # private<->public, plausible
        return 0.7

    if kind == "interior_passage":
        if a_priv and b_priv:
            return 0.0   # NEVER — private rooms only get doors
        if not a_priv and not b_priv and not a_open and not b_open:
            return 1.0   # sala<->jantar canonical
        return 0.6

    if kind == "window":
        if a_open or b_open:
            return 1.0
        return 0.5

    if kind == "glazed_balcony":
        if a_open or b_open:
            return 1.0
        return 0.4

    return 0.5


def _compute_confidence_and_hypotheses(opening: dict,
                                          room_a: dict | None,
                                          room_b: dict | None,
                                          width_m: float,
                                          selected_kind: str | None,
                                          ) -> tuple[float, list[dict]]:
    """Return (confidence, hypotheses).

    confidence in [0.0, 1.0] is a weighted sum of:
      - rooms_evidence  (0.30 weight) — both rooms identified > one > none
      - width_fit       (0.40 weight) — how snugly the width matches kind
      - adjacency_plaus (0.30 weight) — pairing makes architectural sense
    """
    rooms_populated = (
        (1 if room_a is not None else 0)
        + (1 if room_b is not None else 0)
    )
    rooms_evidence = {0: 0.0, 1: 0.5, 2: 1.0}[rooms_populated]

    if selected_kind is None:
        # No kind picked at all — confidence is 0; alternates list
        # exhaustively from the 4 known kinds with low prob each.
        return 0.0, [
            {"kind": k, "prob": 0.0, "reason": "rule rejected"}
            for k in KIND_TARGETS_M
        ]

    width_fit = _width_fit_credit(selected_kind, width_m)
    a_name = room_a["name"] if room_a else None
    b_name = room_b["name"] if room_b else None
    adj_plaus = _adjacency_plausibility(a_name, b_name, selected_kind)

    confidence = (
        0.30 * rooms_evidence
        + 0.40 * width_fit
        + 0.30 * adj_plaus
    )
    confidence = max(0.0, min(1.0, confidence))

    # Build hypotheses: selected kind first (with computed conf),
    # then alternates with the same confidence formula but the OTHER
    # kinds. This lets an auditor or downstream tool see which other
    # interpretations are nearly as plausible.
    candidates = []
    for k in KIND_TARGETS_M:
        if k == selected_kind:
            prob = confidence
            reason = (
                f"width {width_m:.2f}m fits target "
                f"{KIND_TARGETS_M[k][0]:.2f}m; rooms "
                f"{a_name or '-'} <-> {b_name or '-'}"
            )
        else:
            wf = _width_fit_credit(k, width_m)
            ap = _adjacency_plausibility(a_name, b_name, k)
            prob = max(0.0, min(1.0,
                0.30 * rooms_evidence + 0.40 * wf + 0.30 * ap,
            ))
            reason = f"width fit={wf:.2f}, adjacency plausibility={ap:.2f}"
        candidates.append({"kind": k, "prob": round(prob, 3),
                            "reason": reason})
    candidates.sort(key=lambda c: c["prob"], reverse=True)
    return round(confidence, 3), candidates


def _build_evidence(opening: dict, wall: dict | None,
                     room_a: dict | None, room_b: dict | None,
                     pt_to_m: float) -> dict:
    return {
        "wall_id": opening.get("wall_id"),
        "wall_orientation": (wall.get("orientation") if wall else None),
        "room_left": room_a["name"] if room_a else None,
        "room_right": room_b["name"] if room_b else None,
        "room_left_id": room_a["id"] if room_a else None,
        "room_right_id": room_b["id"] if room_b else None,
        "width_m": round(
            float(opening.get("opening_width_pts", 0.0)) * pt_to_m, 3,
        ),
        "width_pts": float(opening.get("opening_width_pts", 0.0)),
        "geometry_origin": opening.get("geometry_origin"),
        "chord_recovered": "opening_width_pts_legacy" in opening,
    }


# ---- Dedup ----

def _cluster_openings_by_proximity(openings: list[dict],
                                    threshold_pt: float
                                    ) -> list[list[dict]]:
    """Greedy single-link clustering on opening centers. Openings whose
    centers are within `threshold_pt` go into the same cluster.

    Assumes `openings` already share a wall_id (caller filters by wall).
    """
    clusters: list[list[dict]] = []
    for op in openings:
        cx, cy = op.get("center", [0.0, 0.0])
        placed = False
        for c in clusters:
            for member in c:
                mx, my = member.get("center", [0.0, 0.0])
                if math.hypot(cx - mx, cy - my) <= threshold_pt:
                    c.append(op)
                    placed = True
                    break
            if placed:
                break
        if not placed:
            clusters.append([op])
    return clusters


def _pick_best_in_cluster(cluster: list[dict],
                           pt_to_m: float) -> Optional[dict]:
    """Among a cluster, pick the best-grounded opening.

    Ranking (lower = better):
      1. Both rooms populated > one room populated > no rooms.
         (Adjacency we could verify on both sides is more trustworthy.)
      2. context_kind preference: interior_door < interior_passage
         < window < glazed_balcony. (When two candidates are otherwise
         equal, a door interpretation beats a balcony — small openings
         in a partition wall are far more common than full glazing.)
      3. width_fit_score for the candidate's kind (lower = tighter fit).

    Returns None if no opening in the cluster has a valid context_kind.
    """
    valid = [op for op in cluster if op.get("context_kind") is not None]
    if not valid:
        return None

    kind_priority = {
        "interior_door":     0,
        "interior_passage":  1,
        "window":            2,
        "glazed_balcony":    3,
    }

    def _key(op: dict) -> tuple:
        rooms_populated = (
            (op.get("room_left_id") is not None) +
            (op.get("room_right_id") is not None)
        )
        # rooms_populated 2 > 1 > 0 -> negative for ascending sort
        kind = op.get("context_kind") or ""
        prio = kind_priority.get(kind, 99)
        width_m = float(op.get("opening_width_pts", 0.0)) * pt_to_m
        fit = _width_fit_score(kind, width_m)
        return (-rooms_populated, prio, fit)

    return min(valid, key=_key)


# ---- Width recovery from arc bbox ----

def _recover_chord_width_pt(opening: dict,
                              wall: Optional[dict]) -> Optional[float]:
    """For svg_arc openings, the legacy ``opening_width_pts`` uses
    ``max(bbox_w, bbox_h)`` which equals the SWING DEPTH (radius)
    when the door is wider on one bbox axis than the other. The real
    chord (= the door panel width) is the bbox dimension ALIGNED with
    the wall axis: for a horizontal wall use bbox_w (x-span), for a
    vertical wall use bbox_h (y-span).

    Returns the recovered width in PDF points, or None if data
    insufficient (in which case caller falls back to opening_width_pts).
    """
    if opening.get("geometry_origin") != "svg_arc":
        return None
    bbox = opening.get("arc_bbox_pts")
    if not bbox or len(bbox) < 4 or wall is None:
        return None
    bbox_w = float(bbox[2]) - float(bbox[0])  # x-span
    bbox_h = float(bbox[3]) - float(bbox[1])  # y-span
    if wall.get("orientation") == "h":
        return bbox_w
    return bbox_h


# ---- Public API ----

def classify_openings_by_room_context(consensus: dict,
                                       pt_to_m: float = PT_TO_M_DEFAULT,
                                       dedup_distance_pt: float = DEDUP_DISTANCE_PT,
                                       ambiguity_policy: object = None,
                                       ) -> dict:
    """Read-modify-write classification. Returns the same dict, with
    ``consensus['openings']`` filtered + each remaining opening's
    ``kind_v5`` rewritten to the context-derived value.

    Stage 1 (PR feature/coherence-audit): every kept opening also gets
    a Stage-1 contract of uncertainty:

        opening['confidence']  : float in [0.0, 1.0]
        opening['decision']    : 'clean' | 'debug' | 'ask' | 'drop'
        opening['hypotheses']  : list of {kind, prob, reason}
        opening['evidence']    : structured features used for the call

    Pass ``ambiguity_policy`` (an AmbiguityPolicy from
    assumptions_loader) to apply a custom decision routing; otherwise
    a conservative default (drop<0.20, ask<0.50, debug<0.75, clean>=0.75)
    is used. Geometry/SKP are NOT touched.
    """
    rooms = consensus.get("rooms") or []
    walls = consensus.get("walls") or []
    walls_by_id = {w["id"]: w for w in walls if w.get("id")}
    thickness_pt = float(consensus.get("wall_thickness_pts", 5.4))

    openings = consensus.get("openings") or []

    # First pass: per-opening adjacency + tentative kind
    for op in openings:
        wall = walls_by_id.get(op.get("wall_id"))
        if wall is None:
            op["context_kind"] = None
            continue
        rl, rr = find_rooms_flanking_wall(
            wall, rooms, thickness_pt,
            opening_center=op.get("center"),
        )
        op["room_left_id"] = rl["id"] if rl else None
        op["room_right_id"] = rr["id"] if rr else None
        op["room_left_name"] = rl["name"] if rl else None
        op["room_right_name"] = rr["name"] if rr else None
        # Recover the wall-aligned chord width for svg_arc openings.
        # The legacy field uses max(bbox_w, bbox_h) which is the swing
        # depth, not the chord. Stash both: corrected width drives
        # classification + Ruby rendering, original is preserved for
        # backward compat / debugging.
        chord_pt = _recover_chord_width_pt(op, wall)
        if chord_pt is not None and chord_pt > 0:
            op["opening_width_pts_legacy"] = op.get("opening_width_pts")
            op["opening_width_pts"] = chord_pt
        width_m = float(op.get("opening_width_pts", 0.0)) * pt_to_m
        op["context_kind"] = _classify_pair(rl, rr, width_m)

    # Second pass: dedup per wall_id by center proximity
    by_wall: dict = defaultdict(list)
    for op in openings:
        by_wall[op.get("wall_id")].append(op)

    keep: list[dict] = []
    drop_count = 0
    drop_reasons: list[str] = []
    for wid, ops in by_wall.items():
        clusters = _cluster_openings_by_proximity(ops, dedup_distance_pt)
        for cluster in clusters:
            best = _pick_best_in_cluster(cluster, pt_to_m)
            if best is None:
                drop_count += len(cluster)
                drop_reasons.extend([
                    f"{op.get('id', '?')}: no valid context_kind"
                    for op in cluster
                ])
                continue
            keep.append(best)
            for op in cluster:
                if op is not best:
                    drop_count += 1
                    drop_reasons.append(
                        f"{op.get('id', '?')}: dedup_dropped (kept "
                        f"{best.get('id','?')} on wall {wid})"
                    )

    # Resolve ambiguity policy (Stage 1: routing, no geometry change)
    if ambiguity_policy is None:
        try:
            # Lazy import to keep this module standalone
            from tools.assumptions_loader import AmbiguityPolicy
            ambiguity_policy = AmbiguityPolicy()
        except Exception:
            ambiguity_policy = None

    # Apply: rewrite kind_v5 + reason + Stage-1 uncertainty contract
    decision_counts: dict = defaultdict(int)
    for op in keep:
        ctx = op.pop("context_kind", None)
        op["kind_v5"] = ctx
        op["kind_v5_reason"] = (
            f"room_context: {op.get('room_left_name','-')} "
            f"<-> {op.get('room_right_name','-')}"
        )
        # --- Stage-1 contract ---
        wall = walls_by_id.get(op.get("wall_id"))
        room_a = next(
            (r for r in rooms if r["id"] == op.get("room_left_id")),
            None,
        )
        room_b = next(
            (r for r in rooms if r["id"] == op.get("room_right_id")),
            None,
        )
        width_m = float(op.get("opening_width_pts", 0.0)) * pt_to_m
        confidence, hypotheses = _compute_confidence_and_hypotheses(
            op, room_a, room_b, width_m, ctx,
        )
        op["confidence"] = confidence
        op["hypotheses"] = hypotheses
        op["evidence"] = _build_evidence(op, wall, room_a, room_b, pt_to_m)
        if ambiguity_policy is not None:
            op["decision"] = ambiguity_policy.decide(confidence)
        else:
            op["decision"] = (
                "clean" if confidence >= 0.75
                else "debug" if confidence >= 0.50
                else "ask" if confidence >= 0.20
                else "drop"
            )
        decision_counts[op["decision"]] += 1

    # Update consensus
    consensus["openings"] = keep
    md = consensus.setdefault("metadata", {})
    md["openings_room_context_classifier"] = {
        "kept": len(keep),
        "dropped": drop_count,
        "dedup_distance_pt": dedup_distance_pt,
        "pt_to_m": pt_to_m,
        "decisions": dict(decision_counts),
    }
    return consensus


# ---- CLI ----

def _main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Classify openings by adjacent room context "
                    "(caminho B, replaces V5 geometric classifier).",
    )
    p.add_argument("consensus", type=Path,
                   help="path to consensus_with_rooms.json (must have "
                        "rooms[].polygon_pts populated)")
    p.add_argument("--out", type=Path, default=None,
                   help="output path (default: overwrite input)")
    p.add_argument("--pt-to-m", type=float, default=PT_TO_M_DEFAULT,
                   help=f"PDF pt -> meters (default: {PT_TO_M_DEFAULT})")
    p.add_argument("--dedup-distance-pt", type=float,
                   default=DEDUP_DISTANCE_PT,
                   help=f"cluster threshold in pt (default: "
                        f"{DEDUP_DISTANCE_PT})")
    args = p.parse_args(argv)

    data = json.loads(args.consensus.read_text(encoding="utf-8"))
    classify_openings_by_room_context(
        data,
        pt_to_m=args.pt_to_m,
        dedup_distance_pt=args.dedup_distance_pt,
    )

    out = args.out or args.consensus
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")

    md = data["metadata"]["openings_room_context_classifier"]
    print(f"[room-context] kept={md['kept']} dropped={md['dropped']}")
    counts: dict = defaultdict(int)
    for op in data["openings"]:
        counts[op.get("kind_v5", "?")] += 1
    for k, v in sorted(counts.items()):
        print(f"  {k:<20} {v}")
    print(f"[wrote] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
