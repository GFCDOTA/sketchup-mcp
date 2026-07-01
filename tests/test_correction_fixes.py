"""FP-033 — correction_fixes unit tests (pure, no SU/network)."""
from __future__ import annotations

import copy

from tools import correction_fixes as cfx
from tools.correction_fixes import FixContext
from tools.furniture_overlap_gate import overlap_gate  # noqa: F401  (parity import)


# --- synthetic consensus (wall dedup) ---------------------------------------


def _dup_wall_consensus(*, host_on: str | None = "w1") -> dict:
    """Two collinear vertical walls 1.5pt apart, 80pt span overlap (thick=5.4 ->
    ctol=6.48, movl=10.8 => flagged). Opening optionally hosted on one."""
    con = {
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "w1", "start": [100.0, 0.0], "end": [100.0, 100.0]},
            {"id": "w2", "start": [101.5, 10.0], "end": [101.5, 90.0]},
            {"id": "w3", "start": [0.0, 0.0], "end": [50.0, 0.0]},  # unrelated
        ],
        "openings": [],
    }
    if host_on:
        con["openings"].append(
            {"id": "d1", "wall_id": host_on, "center": [100.0, 50.0]})
    return con


def _overlap_finding():
    return {"type": "wall_overlap", "severity": "FAIL",
            "source": "deterministic", "evidence": "dup"}


def test_wall_dedup_keeps_host_drops_duplicate():
    ctx = FixContext(consensus=_dup_wall_consensus(host_on="w1"))
    fr = cfx.fix_wall_overlap(ctx, _overlap_finding())
    assert fr.ok and fr.changed
    ids = {w["id"] for w in ctx.consensus["walls"]}
    assert ids == {"w1", "w3"}          # host kept, duplicate dropped
    assert "w2" in fr.reverted_keys


def test_wall_dedup_keeps_longer_span_when_no_host():
    ctx = FixContext(consensus=_dup_wall_consensus(host_on=None))
    fr = cfx.fix_wall_overlap(ctx, _overlap_finding())
    assert fr.ok and fr.changed
    ids = {w["id"] for w in ctx.consensus["walls"]}
    assert ids == {"w1", "w3"}          # w1 span 100 > w2 span 80


def test_wall_dedup_escalates_when_both_host():
    con = _dup_wall_consensus(host_on="w1")
    con["openings"].append({"id": "d2", "wall_id": "w2", "center": [101.5, 40.0]})
    ctx = FixContext(consensus=con)
    before = copy.deepcopy(con)
    fr = cfx.fix_wall_overlap(ctx, _overlap_finding())
    assert not fr.ok                    # honest escalation, no drop
    assert not fr.source_supported
    assert ctx.consensus == before      # nothing touched


def test_wall_dedup_is_idempotent():
    ctx = FixContext(consensus=_dup_wall_consensus(host_on="w1"))
    fr1 = cfx.fix_wall_overlap(ctx, _overlap_finding())
    assert fr1.ok and fr1.changed
    state_after_first = copy.deepcopy(ctx.consensus)
    fr2 = cfx.fix_wall_overlap(ctx, _overlap_finding())
    assert fr2.ok and not fr2.changed   # second apply = no-op
    assert ctx.consensus == state_after_first


def test_wall_dedup_never_invents_walls():
    ctx = FixContext(consensus=_dup_wall_consensus(host_on="w1"))
    n_before = len(ctx.consensus["walls"])
    cfx.fix_wall_overlap(ctx, _overlap_finding())
    assert len(ctx.consensus["walls"]) < n_before   # only removes, never adds


# --- synthetic boxes (furniture nudge) ---------------------------------------


def _box(module: str, x0: float, y0: float, w: float, d: float,
         z0: float = 0.0, h: float = 30.0) -> dict:
    return {"module": module, "kind": module, "z0_in": z0, "h_in": h,
            "corners": [[x0, y0], [x0 + w, y0], [x0 + w, y0 + d], [x0, y0 + d]]}


def _overlapping_boxes() -> list[dict]:
    # sofa 40x20 @ (0,0); mesa 24x24 overlapping its right edge (20x20in^2
    # intersection = 400in^2 >> AREA_MIN, frac 400/576 = 0.69 >> FRAC_MIN)
    return [_box("sofa", 0, 0, 40, 20), _box("mesa", 20, 0, 24, 24)]


_BIG_ROOM = [(-100.0, -100.0), (300.0, -100.0), (300.0, 300.0), (-100.0, 300.0)]


def _furn_finding():
    return {"type": "furniture_overlap", "severity": "FAIL",
            "source": "deterministic", "evidence": "sofa × mesa"}


def test_nudge_resolves_overlap():
    ctx = FixContext(boxes=_overlapping_boxes(), room_poly=_BIG_ROOM)
    assert cfx._overlapping_module_pairs(ctx.boxes)          # sanity: overlapping
    fr = cfx.fix_furniture_overlap(ctx, _furn_finding())
    assert fr.ok and fr.changed, fr.detail
    assert cfx._overlapping_module_pairs(ctx.boxes) == []    # resolved


def test_nudge_is_idempotent():
    ctx = FixContext(boxes=_overlapping_boxes(), room_poly=_BIG_ROOM)
    cfx.fix_furniture_overlap(ctx, _furn_finding())
    state = copy.deepcopy(ctx.boxes)
    fr2 = cfx.fix_furniture_overlap(ctx, _furn_finding())
    assert fr2.ok and not fr2.changed
    assert ctx.boxes == state


def test_nudge_escalates_when_room_too_tight():
    # room barely fits the two boxes overlapped — no in-room nudge resolves
    tight = [(-1.0, -1.0), (45.0, -1.0), (45.0, 25.0), (-1.0, 25.0)]
    ctx = FixContext(boxes=_overlapping_boxes(), room_poly=tight)
    fr = cfx.fix_furniture_overlap(ctx, _furn_finding())
    assert not fr.ok                     # honest: re-layout needed, not a nudge
    assert not fr.source_supported


def test_nudge_moves_smaller_module_only():
    boxes = _overlapping_boxes()
    sofa_before = copy.deepcopy(
        [b for b in boxes if b["module"] == "sofa"][0]["corners"])
    ctx = FixContext(boxes=boxes, room_poly=_BIG_ROOM)
    fr = cfx.fix_furniture_overlap(ctx, _furn_finding())
    assert fr.ok
    sofa_after = [b for b in ctx.boxes if b["module"] == "sofa"][0]["corners"]
    assert sofa_after == sofa_before     # bigger module untouched; mesa moved
    assert any("mesa" in m for m in fr.reverted_keys)


def test_embedded_pairs_not_treated_as_overlap():
    # cuba dentro da bancada = legítimo (paridade com o gate)
    boxes = [_box("bancada", 0, 0, 60, 24), _box("cuba", 10, 5, 15, 12, z0=30, h=8)]
    boxes[0]["h_in"] = 36.0
    assert cfx._overlapping_module_pairs(boxes) == []
    ctx = FixContext(boxes=boxes)
    fr = cfx.fix_furniture_overlap(ctx, _furn_finding())
    assert fr.ok and not fr.changed


# --- registry dispatch --------------------------------------------------------


def test_apply_unknown_type_refuses_honestly():
    fr = cfx.apply(FixContext(), {"type": "floating_door"})
    assert not fr.ok
    assert "no deterministic handler" in fr.detail


def test_has_handler_matches_registry():
    assert cfx.has_handler("wall_overlap")
    assert cfx.has_handler("furniture_overlap")
    assert not cfx.has_handler("appearance_verdict")
    assert not cfx.has_handler("")
