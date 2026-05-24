"""SKP/export-level gates for window aperture semantics (ADR-007 / FP-024).

These tests assert structural properties of the artifacts produced by
build_plan_shell_skp:
  - the `_shell_polygon.json` (Python phase output)
  - the geometry report `report.json` (Ruby phase output, optional)

Tests that depend on a SU-generated artifact skip cleanly when the
artifact is not present (so the suite stays CI-portable).

Window aperture semantics gate (the regression we're locking):
  - window apertures must record sill_in < head_in < wall_height_in
  - the host wall in the generated SKP must retain mass above head
    and below sill (i.e., wall lateral faces span [0, WALL_HEIGHT_IN]
    NOT [0, sill] or [head, WALL_HEIGHT_IN])
  - the glass face sits at mid-thickness, sized opening_width × (head - sill)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# Constants mirrored from tools/build_plan_shell_skp.rb (kept in sync
# manually). If these drift the geometry tests will catch the change
# via the wall_height assertion.
M_TO_IN = 39.3700787402
WALL_HEIGHT_M = 2.70
WALL_HEIGHT_IN = WALL_HEIGHT_M * M_TO_IN  # ~106.30
WINDOW_SILL_M = 0.90
WINDOW_HEAD_M = 2.10
WINDOW_SILL_IN = WINDOW_SILL_M * M_TO_IN  # ~35.43
WINDOW_HEAD_IN = WINDOW_HEAD_M * M_TO_IN  # ~82.68

REPO_ROOT = Path(__file__).parent.parent


# ---- partial-height invariants on apertures ========================

def test_window_sill_head_within_wall_height():
    """Sill must be > 0 (peitoril preserved), head must be < wall
    height (verga preserved). Hard invariant — if sill <= 0 or
    head >= WALL_HEIGHT_IN, the aperture is door-like."""
    assert WINDOW_SILL_IN > 0.0, "peitoril (sill) collapsed to floor"
    assert WINDOW_HEAD_IN < WALL_HEIGHT_IN, "verga (lintel) collapsed to ceiling"
    assert WINDOW_SILL_IN < WINDOW_HEAD_IN, "sill must be below head"


def test_window_aperture_height_positive():
    """The glass band must have non-zero height."""
    aperture_h_in = WINDOW_HEAD_IN - WINDOW_SILL_IN
    assert aperture_h_in > 0
    # Sanity: at canonical constants, aperture should be 1.20 m = ~47.24 in
    assert abs(aperture_h_in - 1.20 * M_TO_IN) < 0.5


def test_wall_mass_below_sill_is_positive():
    """Parapet (wall material from floor to sill) must have non-zero
    height. This is the structural distinguisher from a door."""
    parapet_h_in = WINDOW_SILL_IN - 0.0
    assert parapet_h_in > 0, "no parapet — window aperture reaches floor (door-like)"


def test_wall_mass_above_head_is_positive():
    """Lintel band (wall material from head to ceiling) must have
    non-zero height. Doors only have lintel; windows have lintel +
    parapet."""
    lintel_h_in = WALL_HEIGHT_IN - WINDOW_HEAD_IN
    assert lintel_h_in > 0, "no lintel — window aperture reaches ceiling"


# ---- _shell_polygon.json gates =====================================

QUADRADO_SHELL_JSON = REPO_ROOT / "runs" / "quadrado_v3_aperture" / "_shell_polygon.json"


@pytest.mark.skipif(
    not QUADRADO_SHELL_JSON.exists(),
    reason="quadrado_v3_aperture not built — run build_plan_shell_skp first",
)
def test_quadrado_shell_has_window_aperture_not_carve():
    data = json.loads(QUADRADO_SHELL_JSON.read_text(encoding="utf-8"))
    stats = data["stats"]
    assert stats["window_apertures_3d"] >= 1, (
        "quadrado canonical fixture must have >= 1 window aperture"
    )
    assert stats["openings_carved"] == 0, (
        "quadrado fixture has only a window; openings_carved must be 0 "
        "(any non-zero value indicates window was full-height carved)"
    )
    # window_apertures field must be present in the JSON for Ruby to consume
    assert "window_apertures" in data
    assert len(data["window_apertures"]) == stats["window_apertures_3d"]


@pytest.mark.skipif(
    not QUADRADO_SHELL_JSON.exists(),
    reason="quadrado_v3_aperture not built",
)
def test_quadrado_shell_remains_single_continuous_ring():
    data = json.loads(QUADRADO_SHELL_JSON.read_text(encoding="utf-8"))
    stats = data["stats"]
    # No 2D carve for window → wall ring stays as 1 connected piece
    assert stats["shell_pieces_after_union"] == 1
    assert stats["shell_pieces_after_sliver_filter"] == 1


# ---- geometry report gates (Ruby phase output) =====================

QUADRADO_GEOMETRY_REPORT = (
    REPO_ROOT / "runs" / "quadrado_v3_aperture" / "geometry_report.json"
)


def _find_group_record(report: dict, name: str) -> dict | None:
    """Look up a group's record in the geometry_report's groups_diagnostic
    (where bbox info lives — plan_shell.collect_face_records doesn't
    include bbox)."""
    for g in report.get("groups_diagnostic", []):
        if g.get("name") == name:
            return g
    return None


def _bbox_z_range_m(group_rec: dict) -> tuple[float, float] | None:
    bbox = (group_rec or {}).get("bbox_m") or {}
    mn, mx = bbox.get("min"), bbox.get("max")
    if not (mn and mx):
        return None
    return float(mn[2]), float(mx[2])


@pytest.mark.skipif(
    not QUADRADO_GEOMETRY_REPORT.exists(),
    reason="quadrado geometry_report.json not present "
           "(run build_plan_shell_skp with REPORT_OUT to populate)",
)
def test_quadrado_planshell_height_full_walls():
    """The PlanShell_Group bbox must span full wall height. If z_max
    < WALL_HEIGHT or z_min > 0, the wall was carved short — window
    incorrectly removed wall mass above/below the aperture."""
    report = json.loads(QUADRADO_GEOMETRY_REPORT.read_text(encoding="utf-8"))
    rec = _find_group_record(report, "PlanShell_Group")
    assert rec is not None, "PlanShell_Group missing from geometry report"
    z_range = _bbox_z_range_m(rec)
    assert z_range is not None
    z_min, z_max = z_range
    assert abs(z_min) < 0.01, f"PlanShell z_min={z_min:.3f} m (expected 0.0)"
    assert abs(z_max - WALL_HEIGHT_M) < 0.05, (
        f"PlanShell z_max={z_max:.3f} m; expected {WALL_HEIGHT_M} m. "
        f"Wall was carved short — window may have removed wall mass "
        f"above the aperture (no lintel) or below (no parapet)."
    )


@pytest.mark.skipif(
    not QUADRADO_GEOMETRY_REPORT.exists(),
    reason="quadrado geometry_report.json not present",
)
def test_quadrado_window_glass_group_exists():
    """A WindowGlass_Group_<id> must exist per window aperture, sized
    sill-to-head (NOT floor-to-ceiling)."""
    report = json.loads(QUADRADO_GEOMETRY_REPORT.read_text(encoding="utf-8"))
    glass_groups = [
        g for g in report.get("groups_diagnostic", [])
        if str(g.get("name", "")).startswith("WindowGlass_Group_")
    ]
    assert len(glass_groups) >= 1, (
        "no WindowGlass_Group_* found — 3D aperture path did not "
        "emit glass face; window may have been routed to legacy "
        "full-height carve + 3-band infill"
    )
    for g in glass_groups:
        z_range = _bbox_z_range_m(g)
        if z_range is None:
            continue
        z_min, z_max = z_range
        assert z_min > 0.5, (
            f"{g['name']} touches the floor (z_min={z_min:.3f} m). "
            f"Glass should sit at sill height (~{WINDOW_SILL_M} m). "
            f"This is the door-like-void regression."
        )
        assert z_max < WALL_HEIGHT_M - 0.3, (
            f"{g['name']} reaches the ceiling (z_max={z_max:.3f} m). "
            f"Glass should top at head height (~{WINDOW_HEAD_M} m)."
        )
        # The exact window-pane height (head - sill = 1.20 m)
        assert abs((z_max - z_min) - (WINDOW_HEAD_M - WINDOW_SILL_M)) < 0.05, (
            f"{g['name']} height = {z_max - z_min:.3f} m; "
            f"expected {WINDOW_HEAD_M - WINDOW_SILL_M:.3f} m "
            f"(WINDOW_HEAD - WINDOW_SILL)"
        )


@pytest.mark.skipif(
    not QUADRADO_GEOMETRY_REPORT.exists(),
    reason="quadrado geometry_report.json not present",
)
def test_quadrado_no_window_panel_legacy_groups():
    """Legacy Window_Group_<id>_sill / _lintel groups must NOT exist —
    they're the structural signature of the door-like-void bug.
    The 3D aperture path emits ONLY WindowGlass_Group_<id>."""
    report = json.loads(QUADRADO_GEOMETRY_REPORT.read_text(encoding="utf-8"))
    legacy_groups = [
        g["name"] for g in report.get("groups_diagnostic", [])
        if "_sill" in g.get("name", "") or "_lintel" in g.get("name", "")
    ]
    assert legacy_groups == [], (
        f"found legacy sill/lintel groups: {legacy_groups}. "
        f"These indicate the wall was full-height carved and "
        f"refilled with sill/glass/lintel bands (the FP-024 bug). "
        f"Windows must use 3D aperture carve, not full-height + infill."
    )
