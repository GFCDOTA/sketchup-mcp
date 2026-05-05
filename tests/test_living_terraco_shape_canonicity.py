"""Tests for V1 (SALA DE ESTAR diagonal notch) canonicalization.

Validates `tools.canonicalize_room_polygons` behavior:
- preserves room counts (rooms / openings / soft_barriers stay invariant)
- reduces diagonal segment count + total length on SALA DE ESTAR
- preserves A.S. as a narrow vertical strip (V4 invariant)
- does NOT regress TERRACO SOCIAL / TERRACO TECNICO (V2 still pending
  evidence; canonicalization is allowed to touch them but not make them
  worse)

Two flavors:
1. **Unit:** synthetic walls + polygons; tests the snap mechanic and
   helpers in isolation. Always runs.
2. **Integration:** if a live planta_74 consensus exists under
   ``runs/skp_p74_*/consensus_with_rooms.json``, runs the canonicalizer
   end-to-end and asserts V1 improvement + V4 preservation. Skipped on a
   fresh CI checkout (no ``runs/`` content).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.canonicalize_room_polygons import (
    DEFAULT_SNAP_TOL_PTS,
    axis_grids_from_walls,
    canonicalize_rooms,
    diagonal_signature,
    snap_polygon,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAP_TOL_PLANTA_74 = 8.0  # empirically validated for planta_74 (1.5× wall_thickness)


def _bbox(poly: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_axis_grids_extract_both_edges_per_wall() -> None:
    walls = [
        {"start": [10, 20], "end": [10, 50], "orientation": "v"},
        {"start": [30, 50], "end": [60, 50], "orientation": "h"},
    ]
    xs, ys = axis_grids_from_walls(walls, thickness_pts=4.0)
    # vertical wall at x=10, thickness=4 -> edges at 8 and 12
    assert 8.0 in xs and 12.0 in xs
    # horizontal wall at y=50, thickness=4 -> edges at 48 and 52
    assert 48.0 in ys and 52.0 in ys


def test_snap_polygon_collapses_off_grid_vertex_within_tolerance() -> None:
    # Square room with one off-grid vertex 4pt away from the corner.
    poly = [[10, 10], [50, 10], [50, 50], [13, 47]]
    xs = [10.0, 50.0]
    ys = [10.0, 50.0]
    snapped = snap_polygon(poly, xs, ys, tol_pts=8.0)
    # All resulting coordinates should lie on one of the wall edges.
    for x, y in snapped:
        assert x in (10.0, 50.0), f"x={x} not on grid"
        assert y in (10.0, 50.0), f"y={y} not on grid"
    # Consecutive duplicates removed; result still has >= 4 distinct verts.
    assert len(snapped) >= 4


def test_snap_polygon_preserves_off_grid_vertex_outside_tolerance() -> None:
    # Vertex 20pt off the nearest axis must stay put with tol=8.
    poly = [[10, 10], [50, 10], [50, 50], [30, 30], [10, 50]]
    xs = [10.0, 50.0]
    ys = [10.0, 50.0]
    snapped = snap_polygon(poly, xs, ys, tol_pts=8.0)
    assert [30.0, 30.0] in snapped


def test_snap_polygon_returns_original_when_degenerate() -> None:
    # Snap that would collapse to <4 distinct vertices returns input unchanged.
    poly = [[10, 10], [11, 11], [12, 12], [13, 13]]  # all snap to same point
    snapped = snap_polygon(poly, [10.0], [10.0], tol_pts=5.0)
    # function returns original to avoid corrupting schema
    assert snapped == poly


def test_canonicalize_rooms_preserves_metadata() -> None:
    walls = [
        {"start": [0, 0], "end": [0, 100], "orientation": "v"},
        {"start": [0, 100], "end": [100, 100], "orientation": "h"},
        {"start": [100, 100], "end": [100, 0], "orientation": "v"},
        {"start": [0, 0], "end": [100, 0], "orientation": "h"},
    ]
    rooms = [{
        "id": "r000",
        "name": "ROOM_A",
        "polygon_pts": [[0, 0], [50, 0], [50, 50], [0, 50]],
        "area_pts2": 2500.0,
        "label_id": "l017",
        "centroid": [25.0, 25.0],
    }]
    out = canonicalize_rooms(rooms, walls, thickness_pts=2.0, tol_pts=4.0)
    assert len(out) == 1
    # All non-polygon_pts fields survive verbatim.
    for k in ("id", "name", "area_pts2", "label_id", "centroid"):
        assert out[0][k] == rooms[0][k]


def test_canonicalize_rooms_with_empty_input_returns_empty() -> None:
    assert canonicalize_rooms([], [], 5.0) == []


def test_diagonal_signature_pure_axis() -> None:
    poly = [[0, 0], [10, 0], [10, 10], [0, 10]]
    sig = diagonal_signature(poly)
    assert sig["axis"] == 4
    assert sig["diag"] == 0
    assert sig["diag_total_len"] == 0.0


def test_diagonal_signature_counts_45deg_segment() -> None:
    # One 45° segment from (0,0) to (5,5) -> length sqrt(50) ≈ 7.07.
    poly = [[0, 0], [5, 5], [10, 5], [10, 0]]
    sig = diagonal_signature(poly)
    assert sig["diag"] == 1
    assert 7.0 < sig["diag_total_len"] < 7.2


def test_default_snap_tol_pts_is_conservative() -> None:
    # The module's default stays small; the V1 fix uses 8pt explicitly,
    # documented in tests as SNAP_TOL_PLANTA_74. This test pins the default
    # so a future PR can't silently widen it.
    assert DEFAULT_SNAP_TOL_PTS == 5.0


# ---------------------------------------------------------------------------
# Integration tests — live planta_74 consensus
# ---------------------------------------------------------------------------


def _find_live_consensus() -> Path | None:
    """Return the most recent consensus_with_rooms.json under runs/skp_p74_*."""
    candidates = sorted(REPO_ROOT.glob("runs/skp_p74_*/consensus_with_rooms.json"))
    return candidates[-1] if candidates else None


@pytest.fixture(scope="module")
def live_consensus() -> dict:
    p = _find_live_consensus()
    if p is None:
        pytest.skip("no live planta_74 consensus under runs/skp_p74_*")
    return json.loads(p.read_text(encoding="utf-8"))


def test_v1_canonicalize_preserves_room_count(live_consensus: dict) -> None:
    """Room count must not change after canonicalization."""
    walls = live_consensus["walls"]
    t = live_consensus["wall_thickness_pts"]
    n_before = len(live_consensus["rooms"])
    after = canonicalize_rooms(
        live_consensus["rooms"], walls, t, tol_pts=SNAP_TOL_PLANTA_74
    )
    assert len(after) == n_before


def test_v1_canonicalize_preserves_global_invariants(live_consensus: dict) -> None:
    """Walls / openings / soft_barriers are not touched by canonicalize_rooms.

    Pin the planta_74 vector baseline numbers from CLAUDE.md §10.
    """
    assert len(live_consensus["walls"]) == 33, "wall count regression on planta_74"
    assert len(live_consensus["openings"]) == 12, "opening count regression on planta_74"
    assert len(live_consensus["soft_barriers"]) == 8, "soft_barrier count regression on planta_74"
    assert len(live_consensus["rooms"]) == 11, "room count regression on planta_74"


def test_v1_sala_de_estar_diag_decreases(live_consensus: dict) -> None:
    """V1 fix: SALA DE ESTAR diagonal count and total length must drop."""
    walls = live_consensus["walls"]
    t = live_consensus["wall_thickness_pts"]
    sala_before = next(r for r in live_consensus["rooms"] if r["name"] == "SALA DE ESTAR")
    after = canonicalize_rooms(live_consensus["rooms"], walls, t, tol_pts=SNAP_TOL_PLANTA_74)
    sala_after = next(r for r in after if r["name"] == "SALA DE ESTAR")
    sig_b = diagonal_signature(sala_before["polygon_pts"])
    sig_a = diagonal_signature(sala_after["polygon_pts"])
    assert sig_a["diag"] < sig_b["diag"], (
        f"V1 regression: SALA DE ESTAR diagonal count "
        f"{sig_b['diag']} -> {sig_a['diag']} (expected decrease)"
    )
    # baseline: 78.94pt diagonal -> after (tol=8): 59.4pt. Require >= 10pt drop
    # so the test catches regression but tolerates minor render variance.
    assert sig_a["diag_total_len"] <= sig_b["diag_total_len"] - 10.0, (
        f"V1 regression: SALA DE ESTAR diagonal total length "
        f"{sig_b['diag_total_len']:.1f}pt -> {sig_a['diag_total_len']:.1f}pt "
        f"(expected reduction >= 10pt)"
    )


def test_v4_as_stays_narrow_vertical_strip(live_consensus: dict) -> None:
    """V4 invariant: A.S. must remain a narrow vertical strip after V1 fix.

    Concrete bound: width < 100pt, height/width >= 2 (elongated vertical).
    Anchored to docs/tour/matterport_visual_findings_74m2.md V4 verdict.
    """
    walls = live_consensus["walls"]
    t = live_consensus["wall_thickness_pts"]
    after = canonicalize_rooms(live_consensus["rooms"], walls, t, tol_pts=SNAP_TOL_PLANTA_74)
    asv = next(r for r in after if r["name"] == "A.S.")
    x0, y0, x1, y1 = _bbox(asv["polygon_pts"])
    width = x1 - x0
    height = y1 - y0
    assert width < 100.0, f"V4 regression: A.S. width={width:.1f}pt expected < 100pt"
    assert height / width >= 2.0, (
        f"V4 regression: A.S. height/width ratio {height/width:.2f} expected >= 2.0"
    )


def test_v2_terracos_dont_regress(live_consensus: dict) -> None:
    """V2 still pending evidence: canonicalize is allowed to touch
    TERRACO SOCIAL / TERRACO TECNICO but must NOT increase their
    diagonal segment count.
    """
    walls = live_consensus["walls"]
    t = live_consensus["wall_thickness_pts"]
    after = canonicalize_rooms(live_consensus["rooms"], walls, t, tol_pts=SNAP_TOL_PLANTA_74)
    for name in ("TERRACO SOCIAL", "TERRACO TECNICO"):
        b = next(r for r in live_consensus["rooms"] if r["name"] == name)
        a = next(r for r in after if r["name"] == name)
        sig_b = diagonal_signature(b["polygon_pts"])
        sig_a = diagonal_signature(a["polygon_pts"])
        assert sig_a["diag"] <= sig_b["diag"], (
            f"{name} diagonal count regressed: {sig_b['diag']} -> {sig_a['diag']}"
        )


# ---------------------------------------------------------------------------
# Pipeline CLI integration tests — exercise tools.rooms_from_seeds CLI
# ---------------------------------------------------------------------------


def _run_rooms_from_seeds_cli(
    consensus_in: Path, labels_in: Path, out: Path,
    canonicalize: bool = False, tol: float = 8.0,
) -> None:
    """Invoke `python -m tools.rooms_from_seeds` as a subprocess. Mirrors
    OVERVIEW.md §4.4 step 3 invocation."""
    import subprocess
    import sys

    cmd = [
        sys.executable, "-m", "tools.rooms_from_seeds",
        str(consensus_in), str(labels_in),
        "--out", str(out),
    ]
    if canonicalize:
        cmd += ["--canonicalize-rooms", "--room-canonicalization-tol", str(tol)]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, (
        f"rooms_from_seeds CLI failed (rc={proc.returncode}):\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def _live_pipeline_inputs() -> tuple[Path, Path] | None:
    """Locate the most recent pre-rooms consensus.json + labels.json pair
    under runs/v1_pipeline_*/ or runs/skp_p74_*/.

    Returns (consensus_path, labels_path) or None if neither exists.
    """
    for pattern in ("runs/v1_pipeline_*", "runs/skp_p74_*"):
        candidates = sorted(REPO_ROOT.glob(pattern))
        for c in reversed(candidates):
            cons = c / "consensus.json"
            lbl = c / "labels.json"
            if cons.exists() and lbl.exists():
                return cons, lbl
    return None


@pytest.fixture(scope="module")
def live_inputs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, Path]:
    """Copy pipeline inputs to a tmp dir and return (consensus, labels, tmp).

    Skipped on a fresh checkout where no pipeline has run yet.
    """
    inputs = _live_pipeline_inputs()
    if inputs is None:
        pytest.skip("no pre-rooms consensus.json + labels.json under runs/v1_pipeline_*")
    cons_src, lbl_src = inputs
    tmp = tmp_path_factory.mktemp("v1_cli")
    cons = tmp / "consensus.json"
    lbl = tmp / "labels.json"
    cons.write_bytes(cons_src.read_bytes())
    lbl.write_bytes(lbl_src.read_bytes())
    return cons, lbl, tmp


def test_pipeline_cli_default_off_preserves_baseline(
    live_inputs: tuple[Path, Path, Path],
) -> None:
    """Pipeline without --canonicalize-rooms must produce baseline rooms
    AND must stamp metadata.rooms_from_seeds.canonicalize_rooms = False.
    """
    cons, lbl, tmp = live_inputs
    out = tmp / "default_off.json"
    _run_rooms_from_seeds_cli(cons, lbl, out, canonicalize=False)
    d = json.loads(out.read_text(encoding="utf-8"))
    assert len(d["rooms"]) == 11
    assert len(d["walls"]) == 33
    assert len(d["openings"]) == 12
    assert len(d["soft_barriers"]) == 8
    md = d.get("metadata", {}).get("rooms_from_seeds", {})
    assert md.get("canonicalize_rooms") is False
    assert md.get("room_canonicalization_tol") is None


def test_pipeline_cli_with_flag_reduces_v1(
    live_inputs: tuple[Path, Path, Path],
) -> None:
    """Pipeline with --canonicalize-rooms must (a) reduce SALA DE ESTAR
    diagonals, (b) preserve global counts, (c) keep A.S. narrow.
    Stamps metadata.rooms_from_seeds.canonicalize_rooms = True.
    """
    cons, lbl, tmp = live_inputs

    out_off = tmp / "v1_cli_off.json"
    _run_rooms_from_seeds_cli(cons, lbl, out_off, canonicalize=False)
    d_off = json.loads(out_off.read_text(encoding="utf-8"))

    out_on = tmp / "v1_cli_on.json"
    _run_rooms_from_seeds_cli(cons, lbl, out_on, canonicalize=True, tol=8.0)
    d_on = json.loads(out_on.read_text(encoding="utf-8"))

    # Global counts identical (33/11/12/8)
    for k in ("walls", "rooms", "openings", "soft_barriers"):
        assert len(d_off[k]) == len(d_on[k]), f"{k} count diverged off vs on"
    assert len(d_on["rooms"]) == 11
    assert len(d_on["openings"]) == 12

    # Metadata stamp
    md = d_on.get("metadata", {}).get("rooms_from_seeds", {})
    assert md.get("canonicalize_rooms") is True
    assert md.get("room_canonicalization_tol") == 8.0

    # V1 invariant: SALA DE ESTAR diagonals strictly reduced
    sala_off = next(r for r in d_off["rooms"] if r["name"] == "SALA DE ESTAR")
    sala_on = next(r for r in d_on["rooms"] if r["name"] == "SALA DE ESTAR")
    sig_off = diagonal_signature(sala_off["polygon_pts"])
    sig_on = diagonal_signature(sala_on["polygon_pts"])
    assert sig_on["diag"] < sig_off["diag"], (
        f"V1 CLI regression: SALA DE ESTAR diag {sig_off['diag']} -> {sig_on['diag']}"
    )
    assert sig_on["diag_total_len"] <= sig_off["diag_total_len"] - 10.0, (
        f"V1 CLI regression: diag total len {sig_off['diag_total_len']:.1f} -> "
        f"{sig_on['diag_total_len']:.1f}, expected drop >= 10pt"
    )

    # V4 invariant: A.S. stays narrow vertical strip
    asv_on = next(r for r in d_on["rooms"] if r["name"] == "A.S.")
    x0, y0, x1, y1 = _bbox(asv_on["polygon_pts"])
    width = x1 - x0
    height = y1 - y0
    assert width < 100.0, f"V4 CLI regression: A.S. width {width:.1f}pt"
    assert height / width >= 2.0, f"V4 CLI regression: A.S. ratio {height/width:.2f}"
