"""FP-033 — deterministic fix handlers: `finding_type -> handler -> FixResult`.

The hands of the closed correction loop. Every handler is:

- **pure on its inputs** — takes a working copy (`FixContext`), returns a
  `FixResult`; it NEVER writes to disk and NEVER mutates `fixtures/` (Hard Rule
  #3: promoting a corrected consensus to the pinned fixture stays a gated,
  human/NOC step — the loop persists candidates to its own --out dir).
- **source-supported** — only removes/relocates what the consensus/brain already
  declares; never invents a wall, an opening or a furniture module.
- **idempotent** — applying twice yields the same state; a second application
  reports `changed=False`.

Registry contract (spec §Algorithm): a finding routed DETERMINISTIC_AUTOFIX whose
type has NO registered handler is NOT silently "fixed" — `apply()` returns
`ok=False` and the loop escalates it to NEEDS_FELIPE. Honest by construction.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from tools.furniture_overlap_gate import (
    AREA_MIN_M2, EXCLUDE, FRAC_MIN, M2IN, Z_EPS_IN, _is_embedded, _module_geom,
)


@dataclass
class FixContext:
    """Working state a handler may read/patch. The loop owns the deep copy —
    handlers may mutate `consensus`/`boxes` freely (it is never the input)."""
    consensus: dict | None = None
    boxes: list[dict] | None = None          # furniture boxes for the room in scope
    room_poly: list[tuple[float, float]] | None = None  # optional room polygon (same unit as boxes)


@dataclass
class FixResult:
    ok: bool
    finding_type: str
    action: str = ""            # what was done, one line, for the cycle log
    detail: str = ""
    changed: bool = False       # False on idempotent re-apply / nothing-to-do
    source_supported: bool = True
    reverted_keys: list = field(default_factory=list)  # ids touched (audit trail)


# --- wall_overlap: drop the duplicate wall (consensus-level) -----------------


def _walls_hosting(consensus: dict) -> set:
    """Wall ids referenced as host by any opening — dropping one would orphan
    the opening, so hosts are protected."""
    return {
        o.get("wall_id") for o in consensus.get("openings", [])
        if o.get("wall_id")
    }


def _span_len(w: dict) -> float:
    return abs(w["end"][0] - w["start"][0]) + abs(w["end"][1] - w["start"][1])


def fix_wall_overlap(ctx: FixContext, finding: dict) -> FixResult:
    """Deduplicate collinear overlapping wall pairs found by
    `wall_overlap_audit`. Keep the wall that hosts openings; if neither hosts,
    keep the longer span (more information), tie-broken by id (stable). If BOTH
    host openings, dropping either would orphan openings -> escalate (ok=False).
    """
    from tools.wall_overlap_audit import audit_wall_overlaps

    t = "wall_overlap"
    if not isinstance(ctx.consensus, dict):
        return FixResult(False, t, detail="no consensus in context")

    rep = audit_wall_overlaps(ctx.consensus)
    pairs = rep.get("overlaps", [])
    if not pairs:
        return FixResult(True, t, action="no overlapping walls (idempotent no-op)",
                         changed=False)

    hosts = _walls_hosting(ctx.consensus)
    by_id = {w.get("id"): w for w in ctx.consensus.get("walls", [])}
    to_drop: list[str] = []
    for p in sorted(pairs, key=lambda x: (str(x["wall_a"]), str(x["wall_b"]))):
        a_id, b_id = p["wall_a"], p["wall_b"]
        a_host, b_host = a_id in hosts, b_id in hosts
        if a_host and b_host:
            return FixResult(
                False, t, source_supported=False,
                detail=f"both {a_id} and {b_id} host openings — dedup would "
                       f"orphan openings; escalating (needs merge, not drop)",
            )
        if a_host:
            drop = b_id
        elif b_host:
            drop = a_id
        else:
            wa, wb = by_id.get(a_id), by_id.get(b_id)
            if wa is None or wb is None:
                continue
            la, lb = _span_len(wa), _span_len(wb)
            # keep longer span; tie -> keep smaller id (stable)
            if la > lb:
                drop = b_id
            elif lb > la:
                drop = a_id
            else:
                drop = max(str(a_id), str(b_id))
        if drop not in to_drop:
            to_drop.append(drop)

    if not to_drop:
        return FixResult(True, t, action="no droppable duplicate", changed=False)

    ctx.consensus["walls"] = [
        w for w in ctx.consensus["walls"] if w.get("id") not in set(to_drop)
    ]
    return FixResult(
        True, t, changed=True, reverted_keys=list(to_drop),
        action=f"dropped duplicate wall(s): {', '.join(map(str, to_drop))}",
        detail="kept the opening-hosting / longer-span wall of each pair",
    )


# --- furniture_overlap: minimal deterministic nudge on module boxes ----------


def _overlapping_module_pairs(boxes: list[dict]) -> list[tuple[str, str, float]]:
    """Same criteria as `furniture_overlap_gate.overlap_gate` (shared constants):
    z-ranges cross AND intersection >= AREA_MIN_M2 AND >= FRAC_MIN of the smaller
    footprint. Returns sorted (mod_a, mod_b, frac)."""
    geoms = {m: g for m, g in _module_geom(boxes or []).items()
             if not any(e in m.lower() for e in EXCLUDE)}
    mods = sorted(geoms)
    out = []
    for i in range(len(mods)):
        for j in range(i + 1, len(mods)):
            if _is_embedded(mods[i], mods[j]):  # parity with the gate: embutido legítimo
                continue
            pa, za0, za1 = geoms[mods[i]]
            pb, zb0, zb1 = geoms[mods[j]]
            if min(za1, zb1) - max(za0, zb0) <= Z_EPS_IN:
                continue
            inter = pa.intersection(pb).area / (M2IN * M2IN)
            if inter < AREA_MIN_M2:
                continue
            amin = min(pa.area, pb.area) / (M2IN * M2IN)
            frac = inter / amin if amin else 0.0
            if frac >= FRAC_MIN:
                out.append((mods[i], mods[j], frac))
    return out


def _translate_module(boxes: list[dict], module: str, dx: float, dy: float) -> None:
    for b in boxes:
        if str(b.get("module", b.get("kind", "movel"))) != module:
            continue
        b["corners"] = [[c[0] + dx, c[1] + dy] for c in b["corners"]]


def _inside(poly_pts, boxes: list[dict], module: str) -> bool:
    """All corners of the module inside the room polygon (with 1in slack)."""
    if not poly_pts:
        return True
    from shapely.geometry import Point, Polygon
    poly = Polygon(poly_pts).buffer(1.0)
    for b in boxes:
        if str(b.get("module", b.get("kind", "movel"))) != module:
            continue
        for c in b["corners"]:
            if not poly.contains(Point(c[0], c[1])):
                return False
    return True


_MAX_NUDGE_PASSES = 5  # deterministic cap; unresolved after this -> escalate


def fix_furniture_overlap(ctx: FixContext, finding: dict) -> FixResult:
    """Resolve móvel-sobre-móvel by nudging the SMALLER module along the axis of
    minimal displacement, away from the larger one. Deterministic (sorted pairs,
    fixed tie-breaks), capped at _MAX_NUDGE_PASSES. If the nudge would push the
    module outside the room polygon (when provided) in both directions of both
    axes, escalates honestly instead of forcing.
    """
    t = "furniture_overlap"
    if not ctx.boxes:
        return FixResult(False, t, detail="no boxes in context")

    moved: list[str] = []
    for _ in range(_MAX_NUDGE_PASSES):
        pairs = _overlapping_module_pairs(ctx.boxes)
        if not pairs:
            break
        mod_a, mod_b, _frac = pairs[0]           # deterministic: first sorted pair
        geoms = _module_geom(ctx.boxes)
        pa, pb = geoms[mod_a][0], geoms[mod_b][0]
        mover = mod_a if pa.area <= pb.area else mod_b
        other = mod_b if mover == mod_a else mod_a
        inter = geoms[mover][0].intersection(geoms[other][0])
        if inter.is_empty:
            break
        ix0, iy0, ix1, iy1 = inter.bounds
        ox, oy = ix1 - ix0, iy1 - iy0            # overlap extents
        mc = geoms[mover][0].centroid
        oc = geoms[other][0].centroid
        # candidate nudges: min-extent axis first, away from the other module;
        # then its opposite; then the other axis both ways. 0.5in clearance.
        def _cands():
            sx = 1.0 if mc.x >= oc.x else -1.0
            sy = 1.0 if mc.y >= oc.y else -1.0
            x_move = ((ox + 0.5) * sx, 0.0)
            y_move = (0.0, (oy + 0.5) * sy)
            first = [x_move, y_move] if ox <= oy else [y_move, x_move]
            return first + [(-first[0][0], -first[0][1]),
                            (-first[1][0], -first[1][1])]

        applied = False
        for dx, dy in _cands():
            trial = copy.deepcopy(ctx.boxes)
            _translate_module(trial, mover, dx, dy)
            if not _inside(ctx.room_poly, trial, mover):
                continue
            still = [p for p in _overlapping_module_pairs(trial)
                     if {p[0], p[1]} == {mover, other}]
            if still:
                continue
            ctx.boxes[:] = trial
            moved.append(f"{mover} ({dx:+.1f},{dy:+.1f})in")
            applied = True
            break
        if not applied:
            return FixResult(
                False, t, source_supported=False,
                detail=f"no in-room nudge resolves {mover}×{other} — escalating "
                       f"(re-layout needed, not a nudge)",
            )

    remaining = _overlapping_module_pairs(ctx.boxes)
    if remaining:
        return FixResult(False, t,
                         detail=f"{len(remaining)} overlap(s) left after "
                                f"{_MAX_NUDGE_PASSES} passes — escalating")
    if not moved:
        return FixResult(True, t, action="no furniture overlap (idempotent no-op)",
                         changed=False)
    return FixResult(True, t, changed=True, reverted_keys=moved,
                     action=f"nudged: {'; '.join(moved)}",
                     detail="minimal-displacement nudge, room-bounded")


# --- registry ----------------------------------------------------------------


HANDLERS = {
    "wall_overlap": fix_wall_overlap,
    "furniture_overlap": fix_furniture_overlap,
}


def has_handler(finding_type: str) -> bool:
    return str(finding_type or "").strip().lower() in HANDLERS


def apply(ctx: FixContext, finding: dict) -> FixResult:
    """Dispatch a finding to its handler. No handler registered -> ok=False so
    the loop escalates (never pretends to have fixed)."""
    t = str((finding or {}).get("type") or "").strip().lower()
    handler = HANDLERS.get(t)
    if handler is None:
        return FixResult(False, t or "?",
                         detail=f"no deterministic handler registered for {t!r}")
    return handler(ctx, finding)
