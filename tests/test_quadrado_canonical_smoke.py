"""Quadrado canonical success-reference smoke gate.

This is **the** regression test for the quadrado canonical fixture.
It encodes the success state described in `docs/specs/quadrado_demo_spec.md`
and re-validated by ADR-007 + LL-016 (window aperture semantics) +
LL-017 + FP-025 (wall shell canonicalisation).

Two test tiers, both Python-only (no SU dependency):

1. **Python pre-extrude tier** — run `build_shell_polygon` on the
   versioned consensus and assert the polygon contract:
   - single connected piece
   - outer ring = canonical 4 vertices at canonical positions
   - inner room hole = canonical 4 vertices
   - all edges axis-aligned
   - exactly 1 window aperture routed to the 3D carve path
   - 0 openings_carved (window MUST NOT be 2D full-height carved)
   - 0 slivers, 0 redundant verts (shell is canonical out of the gate)

2. **Geometry-report tier** — compare against the versioned
   reference report at
   `docs/specs/_assets/quadrado_canonical_geometry_report.json`.
   Asserts:
   - PlanShell_Group bbox z spans [0, WALL_HEIGHT_M]
   - WindowGlass_Group_<id> exists, sized [WINDOW_SILL_M, WINDOW_HEAD_M]
   - NO legacy Window_Group_*_sill or _lintel groups

The reference report is the **success ground truth**. It is checked
into git deliberately — any change to it must be justified in the
PR body (it means the pipeline output changed in a way that
re-defines "correct").

**Promotion to CI gate:** when ready, add to
`.github/workflows/ci.yml` matrix; the gate is already
CI-portable (no SU launch required).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.build_plan_shell_skp import build_shell_polygon

REPO_ROOT = Path(__file__).parent.parent
CANONICAL_CONSENSUS = REPO_ROOT / "fixtures" / "quadrado" / "consensus_with_window.json"
CANONICAL_GEOM_REPORT = REPO_ROOT / "docs" / "specs" / "_assets" / "quadrado_canonical_geometry_report.json"
CANONICAL_SHELL_JSON = REPO_ROOT / "docs" / "specs" / "_assets" / "quadrado_canonical_shell_polygon.json"

# Constants mirrored from tools/build_plan_shell_skp.rb.
M_TO_IN = 39.3700787402
WALL_HEIGHT_M = 2.70
WINDOW_SILL_M = 0.90
WINDOW_HEAD_M = 2.10


def _ring_vertex_count(coords) -> int:
    pts = list(coords)
    if len(pts) >= 2 and pts[0] == pts[-1]:
        return len(pts) - 1
    return len(pts)


# ---- 1. Python pre-extrude tier =====================================

@pytest.fixture(scope="module")
def consensus() -> dict:
    return json.loads(CANONICAL_CONSENSUS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def shell(consensus):
    return build_shell_polygon(consensus)


def test_canonical_consensus_fixture_exists():
    """The versioned input must be checked in. If it goes missing,
    the canonical success reference is broken."""
    assert CANONICAL_CONSENSUS.exists(), (
        f"canonical input missing: {CANONICAL_CONSENSUS}. "
        f"The quadrado success reference depends on this file being "
        f"in git. If it was moved, update tests/test_quadrado_canonical_smoke.py."
    )


def test_canonical_consensus_declares_exactly_one_window(consensus):
    windows = [o for o in consensus.get("openings", [])
               if o.get("kind_v5") == "window"]
    assert len(windows) == 1, (
        f"expected exactly 1 window in the canonical input; got {len(windows)}. "
        f"If you intentionally added more, update this gate."
    )


def test_shell_is_single_connected_piece(shell):
    polys, stats = shell
    assert len(polys) == 1, (
        f"canonical quadrado must produce 1 shell piece; got {len(polys)}. "
        f"More pieces = the wall ring got fragmented (FP-025-style)."
    )


def test_outer_ring_is_canonical_4_vertex_rectangle(shell):
    polys, _ = shell
    n = _ring_vertex_count(polys[0].exterior.coords)
    assert n == 4, (
        f"outer ring has {n} vertices; canonical = 4. "
        f"FP-025 signature (corner notches)."
    )


def test_inner_hole_is_canonical_4_vertex_rectangle(shell):
    polys, _ = shell
    assert len(polys[0].interiors) == 1
    n = _ring_vertex_count(polys[0].interiors[0].coords)
    assert n == 4, f"inner hole has {n} vertices; canonical = 4."


def test_outer_corners_at_canonical_positions(shell):
    """The 4m × 4m room with thickness 5.4 pt produces these exact
    outer corners. Hardcoded because they're the ground truth."""
    polys, _ = shell
    coords = {(round(x, 3), round(y, 3))
              for x, y in list(polys[0].exterior.coords)[:-1]}
    expected = {(97.3, 97.3), (216.384, 97.3),
                (216.384, 216.384), (97.3, 216.384)}
    assert coords == expected, (
        f"outer corners drifted: {coords} != canonical {expected}"
    )


def test_all_edges_axis_aligned(shell):
    polys, _ = shell
    coords = list(polys[0].exterior.coords)
    for (x0, y0), (x1, y1) in zip(coords[:-1], coords[1:]):
        is_h = abs(y1 - y0) < 1e-6
        is_v = abs(x1 - x0) < 1e-6
        assert is_h or is_v, (
            f"non-axis-aligned edge: ({x0}, {y0}) -> ({x1}, {y1}). "
            f"Axis-aligned input must produce axis-aligned output."
        )


def test_window_routed_to_3d_aperture_not_2d_carve(shell):
    """ADR-007 / LL-016: windows are 3D post-extrude apertures.
    Hard gate: openings_carved MUST equal 0, window_apertures_3d == 1."""
    _, stats = shell
    assert stats["openings_carved"] == 0, (
        f"openings_carved={stats['openings_carved']}; canonical = 0. "
        f"The window was 2D full-height carved — FP-024 regression."
    )
    assert stats["window_apertures_3d"] == 1, (
        f"window_apertures_3d={stats['window_apertures_3d']}; expected 1."
    )


def test_no_slivers_no_redundant_vertices(shell):
    """LL-017: the canonicalisation must produce a clean polygon."""
    _, stats = shell
    assert stats["slivers_removed"] == 0
    assert stats["redundant_vertices_dropped"] == 0, (
        f"redundant_vertices_dropped={stats['redundant_vertices_dropped']}; "
        f"expected 0 (wall extension alone produces canonical union for "
        f"the quadrado fixture)"
    )


def test_total_shell_area_matches_canonical(shell):
    """The area is determined by the wall geometry. A drift here means
    the wall_footprint or the extension changed."""
    _, stats = shell
    expected_area = 2455.6
    actual = stats["total_shell_area_pts2"]
    assert abs(actual - expected_area) < 1.0, (
        f"shell area = {actual:.2f}; canonical = {expected_area:.2f}. "
        f"Drift indicates wall_footprint geometry changed."
    )


# ---- 2. Geometry-report tier (reference comparison) ================

@pytest.mark.skipif(
    not CANONICAL_GEOM_REPORT.exists(),
    reason="canonical geometry report not committed",
)
def test_reference_geometry_report_planshell_full_height():
    report = json.loads(CANONICAL_GEOM_REPORT.read_text(encoding="utf-8"))
    plan_shell = None
    for g in report.get("groups_diagnostic", []):
        if g.get("name") == "PlanShell_Group":
            plan_shell = g
            break
    assert plan_shell is not None, "PlanShell_Group missing from canonical report"
    bb = plan_shell.get("bbox_m", {})
    z_min = bb["min"][2]
    z_max = bb["max"][2]
    assert abs(z_min) < 0.01, f"PlanShell z_min={z_min:.3f} (expected 0)"
    assert abs(z_max - WALL_HEIGHT_M) < 0.05, (
        f"PlanShell z_max={z_max:.3f} m (expected {WALL_HEIGHT_M})"
    )


@pytest.mark.skipif(
    not CANONICAL_GEOM_REPORT.exists(),
    reason="canonical geometry report not committed",
)
def test_reference_geometry_report_window_glass_at_sill_to_head():
    report = json.loads(CANONICAL_GEOM_REPORT.read_text(encoding="utf-8"))
    glass = [g for g in report.get("groups_diagnostic", [])
             if str(g.get("name", "")).startswith("WindowGlass_Group_")]
    assert len(glass) == 1, (
        f"expected exactly 1 WindowGlass group; got {len(glass)}"
    )
    bb = glass[0].get("bbox_m", {})
    z_min, z_max = bb["min"][2], bb["max"][2]
    assert abs(z_min - WINDOW_SILL_M) < 0.05, (
        f"glass z_min={z_min:.3f} m; expected {WINDOW_SILL_M} (sill)"
    )
    assert abs(z_max - WINDOW_HEAD_M) < 0.05, (
        f"glass z_max={z_max:.3f} m; expected {WINDOW_HEAD_M} (head)"
    )


@pytest.mark.skipif(
    not CANONICAL_GEOM_REPORT.exists(),
    reason="canonical geometry report not committed",
)
def test_reference_geometry_report_no_legacy_window_panel_groups():
    """Window_Group_*_sill or _lintel are the FP-024 signature.
    They must never appear in a healthy build."""
    report = json.loads(CANONICAL_GEOM_REPORT.read_text(encoding="utf-8"))
    legacy = [g["name"] for g in report.get("groups_diagnostic", [])
              if "_sill" in g.get("name", "") or "_lintel" in g.get("name", "")]
    assert legacy == [], (
        f"FP-024 legacy groups found: {legacy}. "
        f"The 3D aperture path emits ONLY WindowGlass_Group_<id>, "
        f"never sill/lintel sub-volumes."
    )


# ---- 3. Reference shell polygon (the success snapshot) ============

@pytest.mark.skipif(
    not CANONICAL_SHELL_JSON.exists(),
    reason="canonical shell polygon not committed",
)
def test_reference_shell_polygon_matches_live_build(consensus):
    """The committed _shell_polygon.json reference must agree with
    the live build output (modulo runtime metadata like absolute
    paths). If you intentionally change the geometry, regenerate
    the reference with:

        python -c "
        import json
        from pathlib import Path
        from tools.build_plan_shell_skp import build_shell_polygon, serialize_polygons
        c = json.loads(Path('fixtures/quadrado/consensus_with_window.json').read_text())
        polys, stats = build_shell_polygon(c)
        out = serialize_polygons(polys, c, stats)
        Path('docs/specs/_assets/quadrado_canonical_shell_polygon.json').write_text(
            json.dumps(out, indent=2)
        )
        "
    """
    ref = json.loads(CANONICAL_SHELL_JSON.read_text(encoding="utf-8"))
    polys, stats = build_shell_polygon(consensus)
    # Compare the structural fields that matter for success.
    ref_stats = ref["stats"]
    for field in [
        "input_walls", "openings_carved", "window_apertures_3d",
        "shell_pieces_after_sliver_filter", "slivers_removed",
        "redundant_vertices_dropped",
    ]:
        assert stats[field] == ref_stats[field], (
            f"stats.{field} drift: live={stats[field]} ref={ref_stats[field]}"
        )
    # Polygon piece count + outer/inner vertex counts.
    assert len(polys) == len(ref["polygons"]), "piece count drift"
    for live, ref_p in zip(polys, ref["polygons"]):
        live_outer = _ring_vertex_count(live.exterior.coords)
        ref_outer = len(ref_p["outer"])
        assert live_outer == ref_outer, (
            f"outer vertex drift: live={live_outer} ref={ref_outer}"
        )
        live_holes = len(live.interiors)
        ref_holes = len(ref_p["holes"])
        assert live_holes == ref_holes, "hole count drift"
