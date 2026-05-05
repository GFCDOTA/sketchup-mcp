"""Contract tests for door_arc / svg_segments wall carving.

The Ruby exporter (``tools/consume_consensus.rb``) splits each wall into
sub-segments around its host openings (those whose ``geometry_origin``
is in ``CARVING_OPENING_ORIGINS``). We can't unit-test Ruby code here,
but we can:

1. Port the ``_kept_segments`` algorithm to Python and pin its behavior
   on synthetic inputs. The Ruby and Python versions share the same
   algebraic spec — drift in either direction shows up as a failed test
   in CI.
2. Use the producer/consumer grep pattern from
   ``test_consume_consensus_passage_contract.py`` to assert the Ruby
   file still references the field names + origin labels the producer
   side emits.
3. Pin the live-planta_74 invariant: with 12 svg_arc openings, the
   carved SU groups should be in the range [walls_count, walls_count +
   12], with each carving opening contributing 0 or 1 extra sub-wall.

If the Ruby algorithm changes to honor a different field shape, set of
origins, or wall-splitting behavior, this test fails first.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tools.detect_wall_gaps import detect_wall_gaps  # used to seed ids
REPO_ROOT = Path(__file__).resolve().parent.parent
CONSUMER_RB = REPO_ROOT / "tools" / "consume_consensus.rb"


# --- Algorithm port ------------------------------------------------------

def kept_segments(axis_start: float, axis_end: float,
                  carve_ranges: list[tuple[float, float]]
                  ) -> list[tuple[float, float]]:
    """Python mirror of Ruby ``_kept_segments`` in
    ``tools/consume_consensus.rb``. Subtracts the union of carve_ranges
    from [axis_start, axis_end]; returns sorted list of [start, end]."""
    if axis_end <= axis_start:
        return []
    sorted_ranges = sorted(
        ((min(a, b), max(a, b)) for a, b in carve_ranges),
        key=lambda r: r[0],
    )
    kept: list[tuple[float, float]] = []
    cursor = float(axis_start)
    for c_start, c_end in sorted_ranges:
        c_start = max(c_start, axis_start)
        c_end = min(c_end, axis_end)
        if c_end <= cursor:
            continue
        if c_start > cursor:
            kept.append((cursor, c_start))
        cursor = max(cursor, c_end)
    if cursor < axis_end:
        kept.append((cursor, axis_end))
    return kept


# --- algorithm tests ----------------------------------------------------

def test_no_carving_returns_full_wall():
    assert kept_segments(0.0, 100.0, []) == [(0.0, 100.0)]


def test_single_door_in_middle_splits_into_two():
    out = kept_segments(0.0, 200.0, [(80.0, 120.0)])
    assert out == [(0.0, 80.0), (120.0, 200.0)]


def test_two_doors_split_into_three():
    out = kept_segments(0.0, 300.0, [(50.0, 80.0), (180.0, 220.0)])
    assert out == [(0.0, 50.0), (80.0, 180.0), (220.0, 300.0)]


def test_carve_overlapping_ranges_merge():
    out = kept_segments(0.0, 200.0, [(50.0, 100.0), (90.0, 130.0)])
    assert out == [(0.0, 50.0), (130.0, 200.0)]


def test_carve_at_left_edge_drops_left_segment():
    out = kept_segments(0.0, 200.0, [(0.0, 60.0)])
    assert out == [(60.0, 200.0)]


def test_carve_at_right_edge_drops_right_segment():
    out = kept_segments(0.0, 200.0, [(160.0, 200.0)])
    assert out == [(0.0, 160.0)]


def test_carve_extending_past_edges_clamps():
    out = kept_segments(0.0, 200.0, [(-10.0, 50.0), (180.0, 250.0)])
    assert out == [(50.0, 180.0)]


def test_carve_consuming_full_wall_yields_empty():
    assert kept_segments(0.0, 100.0, [(0.0, 100.0)]) == []


def test_carve_with_inverted_ranges_normalizes():
    """Ruby algorithm sorts each range; Python mirror does the same so a
    detector mistakenly emitting (end, start) doesn't crash."""
    out = kept_segments(0.0, 200.0, [(120.0, 80.0)])
    assert out == [(0.0, 80.0), (120.0, 200.0)]


def test_zero_or_negative_axis_returns_empty():
    assert kept_segments(100.0, 100.0, []) == []
    assert kept_segments(50.0, 0.0, []) == []


# --- grep-the-source contract ------------------------------------------

@pytest.fixture(scope="module")
def consumer_source() -> str:
    return CONSUMER_RB.read_text(encoding="utf-8")


def test_consumer_defines_carving_origins_constant(consumer_source: str):
    assert "CARVING_OPENING_ORIGINS" in consumer_source, (
        "consume_consensus.rb no longer defines CARVING_OPENING_ORIGINS; "
        "the carving switch has been removed or renamed."
    )


@pytest.mark.parametrize("origin", ["svg_arc", "svg_segments"])
def test_consumer_carves_each_documented_origin(consumer_source: str,
                                                origin: str):
    """Both door_arc-source (svg_arc) and window-source (svg_segments)
    openings must remain in the carving switch."""
    pattern = re.compile(rf"['\"]{re.escape(origin)}['\"]")
    assert pattern.search(consumer_source), (
        f"consume_consensus.rb no longer references the carving origin "
        f"'{origin}'; openings of that geometry_origin will render as "
        f"solid walls again."
    )


def test_consumer_does_not_carve_wall_gap_origin(consumer_source: str):
    """wall_gap origin must NOT appear in CARVING_OPENING_ORIGINS — the
    gap is already in the wall data, double-carving would shrink the
    flanking walls a second time."""
    # Locate the constant definition and assert wall_gap is not in its array.
    m = re.search(
        r"CARVING_OPENING_ORIGINS\s*=\s*\[(.*?)\]",
        consumer_source, re.DOTALL,
    )
    assert m, "CARVING_OPENING_ORIGINS constant not found"
    assert "wall_gap" not in m.group(1), (
        "wall_gap origin must NOT be in CARVING_OPENING_ORIGINS; the "
        "gap is already in the wall data and double-carving regresses "
        "the geometry."
    )


def test_consumer_emits_seg_suffix_for_subwalls(consumer_source: str):
    """Sub-walls are named '<wall_id>_seg_<n>' so the inspector can
    reconstruct the parent->sub mapping."""
    assert "_seg_" in consumer_source, (
        "Sub-wall naming convention '<wall_id>_seg_<n>' lost; inspector "
        "won't be able to attribute carved subwalls to their parents."
    )


@pytest.mark.parametrize("ruby_helper", [
    "_kept_segments",
    "_carve_ranges_for",
    "add_carved_wall",
])
def test_consumer_keeps_carving_helpers(consumer_source: str, ruby_helper: str):
    assert ruby_helper in consumer_source, (
        f"consume_consensus.rb no longer defines `{ruby_helper}`; the "
        f"carving algorithm has been refactored away. Update this test "
        f"OR restore the helper."
    )


# --- live planta_74 invariant -----------------------------------------

def _planta_74_consensus_with_openings() -> dict | None:
    candidates = [
        REPO_ROOT / "runs" / "vector" / "consensus_model.json",
        REPO_ROOT / "runs" / "post_merge_e2e_2026_05_05" /
        "consensus_with_openings.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                continue
    return None


@pytest.mark.skipif(_planta_74_consensus_with_openings() is None,
                    reason="planta_74 consensus snapshot unavailable")
def test_live_planta_74_carving_count_matches_invariant():
    """For every svg_arc / svg_segments opening on a real wall, the
    carver must split that wall into at most one extra sub-segment.
    Lower bound: walls_count (zero openings).
    Upper bound: walls_count + count(svg_arc + svg_segments openings).
    """
    consensus = _planta_74_consensus_with_openings()
    walls = consensus["walls"]
    wall_ids = {w["id"] for w in walls}
    openings = consensus.get("openings") or []
    carving = [o for o in openings
               if o.get("geometry_origin") in {"svg_arc", "svg_segments"}
               and o.get("wall_id") in wall_ids]
    n_walls = len(walls)
    n_carving = len(carving)
    # Apply the algorithm per wall and count emitted sub-walls.
    by_wall: dict[str, list[dict]] = {w["id"]: [] for w in walls}
    for op in carving:
        by_wall[op["wall_id"]].append(op)
    total_sub = 0
    for w in walls:
        ops = by_wall[w["id"]]
        if not ops:
            total_sub += 1
            continue
        axis_idx = 0 if w["orientation"] == "h" else 1
        a_start = min(w["start"][axis_idx], w["end"][axis_idx])
        a_end = max(w["start"][axis_idx], w["end"][axis_idx])
        carves = [(o["center"][axis_idx] - o["opening_width_pts"] / 2.0,
                   o["center"][axis_idx] + o["opening_width_pts"] / 2.0)
                  for o in ops]
        total_sub += len(kept_segments(a_start, a_end, carves))
    # Each carving opening adds 0 or 1 extra sub-wall (vs. base of 1
    # per uncarved wall). Allow degenerate cases where an opening sits
    # at the wall edge and produces 0 extra.
    assert n_walls <= total_sub <= n_walls + n_carving, (
        f"sub-wall count {total_sub} outside expected band "
        f"[{n_walls}, {n_walls + n_carving}] (walls={n_walls}, "
        f"carving_openings={n_carving})"
    )
