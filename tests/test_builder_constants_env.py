"""Contract test for DIFF-006 — builder architectural heights are ENV-overridable
with the planta_74 (BR residential norm) values as DEFAULTS.

build_plan_shell_skp.rb runs inside SketchUp (no Ruby interpreter in CI), so this
is a TEXT contract, not a runtime one. It exists to:
  1. PIN the defaults — changing any height alters the canonical planta_74 SKP
     (built/approved in d48798d), so a future edit that drifts them fails here.
  2. PROVE each height reads ENV['<NAME>'] — the per-plant override that
     generalize_any_plant §1 needs (a 2nd plant sets ENV; planta_74 leaves it unset).
Runtime confirmation that the build still produces an identical SKP = a SketchUp
build on the human's machine (cannot run headless here).
"""
from __future__ import annotations

import re
from pathlib import Path

RB = Path(__file__).resolve().parents[1] / "tools" / "build_plan_shell_skp.rb"

# height constant -> pinned default (BR residential norm). These are the values
# that built the approved planta_74; do NOT change without a VISUAL_REVIEW.
HEIGHTS = {
    "WALL_HEIGHT_M": "2.70",
    "PARAPET_HEIGHT_M": "1.10",
    "DOOR_HEIGHT_M": "2.10",
    "WINDOW_SILL_M": "1.10",
    "WINDOW_HEAD_M": "2.30",
}


def _rhs(src: str, name: str) -> str:
    """The right-hand side of `NAME = ...` (the definition line, not NAME_IN)."""
    m = re.search(rf"^{name}\s*=\s*(.+)$", src, re.MULTILINE)
    assert m, f"{name} assignment not found in build_plan_shell_skp.rb"
    return m.group(1)


def test_heights_are_env_overridable_with_pinned_defaults():
    src = RB.read_text("utf-8")
    for name, default in HEIGHTS.items():
        rhs = _rhs(src, name)
        assert f"ENV['{name}']" in rhs, f"{name} must read ENV['{name}'] (per-plant override)"
        assert default in rhs, f"{name} default must stay {default} (planta_74 unchanged)"


def test_pt_to_m_anchor_still_env_overridable():
    # the pre-existing anchor whose pattern the heights mirror — regression guard
    rhs = _rhs(RB.read_text("utf-8"), "PT_TO_M")
    assert "ENV['PT_TO_M']" in rhs and "0.19" in rhs


def test_inch_constants_still_derive_from_metres():
    # *_IN must keep deriving from *_M (not be hardcoded) so an ENV override of the
    # metre value actually propagates into the extruded geometry
    src = RB.read_text("utf-8")
    for base in ("WALL_HEIGHT", "PARAPET_HEIGHT", "DOOR_HEIGHT", "WINDOW_SILL", "WINDOW_HEAD"):
        assert f"{base}_M * M_TO_IN" in _rhs(src, f"{base}_IN"), \
            f"{base}_IN must derive from {base}_M"
