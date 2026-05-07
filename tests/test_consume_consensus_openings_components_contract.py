"""Contract test: consume_consensus.rb renders door leaves + window
panels for door_arc / wall_gap openings.

The Ruby exporter consumes openings and emits visible swing/glass
geometry beyond the carved opening. It reads exactly these fields:

* For door_arc openings (after carving):
  - ``geometry_origin == 'svg_arc'`` OR ``kind_v5 == 'door_arc'``
  - ``wall_id``, ``center``, ``opening_width_pts``, ``id``
  - ``hinge`` (``'left'`` or ``'right'``) — swing direction

* For wall_gap openings (window panels):
  - ``geometry_origin == 'wall_gap'``
  - same field set as passage_marker (already covered by sibling test)

This file does NOT invoke SketchUp. It validates source-grep contract:
the Ruby consumer references each field above, and the Python producer
emits each field. If a future refactor breaks either side, this test
fails before the regression ships.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONSUMER_RB = REPO_ROOT / "tools" / "consume_consensus.rb"


def _consumer_source() -> str:
    return CONSUMER_RB.read_text(encoding="utf-8")


# ---------- Door leaf contract ----------

def test_consumer_defines_door_leaf_function():
    src = _consumer_source()
    assert re.search(r"def\s+add_door_leaf\b", src), (
        "consume_consensus.rb missing add_door_leaf — door_arc openings "
        "would render as carved gaps with no visible swing panel."
    )


def test_consumer_reads_hinge_field():
    src = _consumer_source()
    assert "'hinge'" in src or '"hinge"' in src, (
        "consume_consensus.rb no longer reads opening['hinge']; door "
        "leaves cannot pick swing direction."
    )


def test_consumer_branches_on_room_context_kinds():
    """Caminho B: Ruby reads kind_v5 set by
    classify_openings_by_room_context and routes to the corresponding
    renderer. Each kind below MUST appear as a branch target so a
    typo / missing branch in the case-when fails the contract."""
    src = _consumer_source()
    for kind in ("interior_door", "interior_passage",
                  "window", "glazed_balcony"):
        # The kind appears either as a string literal in a `when`
        # branch, a comparison, or as the body of the legacy mapping.
        pattern = rf"['\"]({kind})['\"]"
        assert re.search(pattern, src), (
            f"consume_consensus.rb does not reference kind_v5='{kind}'; "
            f"openings with this kind will not render."
        )


def test_consumer_back_compat_legacy_v5_kinds():
    """Older consensus files (pre-room-context) emit door_arc /
    open_passage. The Ruby exporter must map these to the new kinds
    or render nothing. Either way, the legacy strings must still
    appear in the source as case-arm targets."""
    src = _consumer_source()
    for legacy in ("door_arc", "open_passage"):
        pattern = rf"['\"]({legacy})['\"]"
        assert re.search(pattern, src), (
            f"consume_consensus.rb dropped legacy V5 kind '{legacy}' "
            f"compatibility; older consensus files would silently "
            f"render nothing."
        )


def test_consumer_uses_doors_layer():
    src = _consumer_source()
    assert "'doors'" in src or '"doors"' in src, (
        "consume_consensus.rb missing 'doors' layer; door leaves would "
        "land on the default layer and become unidentifiable."
    )


def test_consumer_door_geometry_constants_defined():
    src = _consumer_source()
    for const in ("DOOR_HEIGHT_M", "DOOR_THICK_M", "DOOR_SWING_DEG",
                  "DOOR_RGB"):
        assert const in src, (
            f"consume_consensus.rb missing constant {const}; geometry "
            f"would silently regress."
        )


# ---------- Window panel contract ----------

def test_consumer_defines_window_panel_function():
    src = _consumer_source()
    assert re.search(r"def\s+add_window_panel\b", src), (
        "consume_consensus.rb missing add_window_panel — wall_gap "
        "openings would render as floor markers only, no glazing."
    )


def test_consumer_branches_on_wall_gap_for_window():
    src = _consumer_source()
    # Must call add_window_panel under the wall_gap geometry_origin
    # branch (in addition to add_passage_marker)
    assert "add_window_panel" in src, (
        "consume_consensus.rb does not invoke add_window_panel; "
        "wall_gap openings would skip glazing."
    )


def test_consumer_uses_windows_layer():
    src = _consumer_source()
    assert "'windows'" in src or '"windows"' in src, (
        "consume_consensus.rb missing 'windows' layer; window groups "
        "would land on the default layer and become unidentifiable."
    )


def test_consumer_window_geometry_constants_defined():
    src = _consumer_source()
    for const in ("WINDOW_SILL_M", "WINDOW_HEAD_M", "GLASS_RGB",
                  "GLASS_ALPHA", "LINTEL_RGB"):
        assert const in src, (
            f"consume_consensus.rb missing constant {const}; window "
            f"geometry would silently regress."
        )


def test_consumer_window_emits_three_band_assembly():
    """window_sill + window_glass + window_lintel must each be emitted.
    A change that drops e.g. the lintel band would silently regress
    the visual without changing counts."""
    src = _consumer_source()
    for tag in ("window_sill_", "window_glass_", "window_lintel_"):
        assert tag in src, (
            f"consume_consensus.rb missing emit of '{tag}'; window "
            f"3-band assembly is incomplete."
        )


def test_consumer_passage_marker_still_emitted():
    """Caminho A: window_panel is ADDITIVE to passage_marker. Both
    must coexist so designers can re-classify wall_gaps that should
    have been passages, not windows."""
    src = _consumer_source()
    assert "add_passage_marker" in src, (
        "consume_consensus.rb dropped passage_marker; window_panel "
        "should be additive, not replacement."
    )
