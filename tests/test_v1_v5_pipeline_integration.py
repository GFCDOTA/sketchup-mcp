"""End-to-end integration test for V1 (canonicalize_rooms) +
V5 (classify_opening_kind) running together via the documented CLI
chain in ``OVERVIEW.md §4.4``.

Why a dedicated integration test?
---------------------------------
Each feature has its own unit + integration tests:

* V1 (``--canonicalize-rooms``):
  ``tests/test_living_terraco_shape_canonicity.py`` (16 tests).
* V5 (``--classify-kind``):
  ``tests/test_classify_opening_kind.py`` (11 tests).

Both pass independently. This test pins that **enabling both flags
together on a real planta** still produces a coherent consensus:

1. Global counts (``CLAUDE.md §10`` baseline) hold:
   ``walls=33, rooms=11, openings=12, soft_barriers=8``.
2. V1 invariant: SALA DE ESTAR diagonal segment count strictly
   decreases vs the no-flag run.
3. V4 invariant: A.S. stays narrow vertical strip
   (``width < 100 pt`` and ``height/width >= 2``).
4. V5 invariant: every opening receives a ``kind_v5`` + reason; the
   classifier metadata stamp is present; on planta_74 every kind_v5
   is ``door_arc`` (no false positives).
5. Both metadata stamps coexist:
   ``metadata.rooms_from_seeds.canonicalize_rooms`` and
   ``metadata.opening_kind_v5_classifier.{version, counts}``.

Skip behavior
-------------
The test SKIPs on a fresh checkout where ``planta_74.pdf`` is not on
disk (it is gitignored on CI). On a populated dev machine it runs the
full chain in a tmp_path and asserts everything above. No SketchUp
launch — vector pipeline + classifier only.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLANTA = REPO_ROOT / "planta_74.pdf"

# Anchored to CLAUDE.md §10 baseline for planta_74.
EXPECTED_WALLS = 33
EXPECTED_ROOMS = 11
EXPECTED_OPENINGS = 12
EXPECTED_SOFT_BARRIERS = 8

SNAP_TOL_PLANTA_74 = 8.0   # 1.5× wall_thickness; same as V1 fix


def _run(*args: str) -> None:
    """Invoke a Python module via subprocess from REPO_ROOT, raise on
    non-zero exit. Mirrors ``OVERVIEW.md §4.4`` invocation form.
    """
    cmd = [sys.executable, "-m", *args]
    proc = subprocess.run(cmd, cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, (
        f"command failed (rc={proc.returncode}): {' '.join(cmd)}\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def _diag_count(polygon_pts: list[list[float]], off_axis_min_deg: float = 5.0) -> int:
    """Count edges that are NOT axis-aligned.

    Inlined here so this test does not depend on ``tools.canonicalize_room_polygons``
    being importable. Same definition that ``diagonal_signature`` uses
    (off-axis angle >= 5° → diagonal).
    """
    n = len(polygon_pts)
    if n < 2:
        return 0
    count = 0
    for i in range(n):
        x0, y0 = polygon_pts[i]
        x1, y1 = polygon_pts[(i + 1) % n]
        dx = x1 - x0
        dy = y1 - y0
        L = math.hypot(dx, dy)
        if L < 1e-3:
            continue
        angle = math.degrees(math.atan2(dy, dx)) % 180
        d_axis = min(abs(angle - 0), abs(angle - 90), abs(angle - 180))
        if d_axis >= off_axis_min_deg:
            count += 1
    return count


def _bbox(poly: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


@pytest.fixture(scope="module")
def pipeline_with_flags(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Run the full vector chain WITH both --canonicalize-rooms and
    --classify-kind enabled. Returns the resulting consensus dict.

    Skipped if planta_74.pdf is not on disk (CI fresh checkout).
    """
    if not PLANTA.exists():
        pytest.skip("planta_74.pdf not in working tree")

    tmp = tmp_path_factory.mktemp("v1_v5_full")
    cons = tmp / "consensus.json"
    labels = tmp / "labels.json"
    final = tmp / "consensus_full.json"

    _run("tools.build_vector_consensus", str(PLANTA),
         "--out", str(cons), "--detect-openings")
    _run("tools.extract_room_labels", str(PLANTA), "--out", str(labels))
    _run("tools.rooms_from_seeds", str(cons), str(labels),
         "--out", str(final),
         "--canonicalize-rooms",
         "--room-canonicalization-tol", str(SNAP_TOL_PLANTA_74))
    _run("tools.extract_openings_vector", str(PLANTA),
         "--consensus", str(final), "--out", str(final),
         "--mode", "replace", "--classify-kind")

    return json.loads(final.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pipeline_baseline(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Run the full vector chain WITHOUT V1/V5 flags. Returns the
    baseline consensus for delta comparison.

    Skipped if planta_74.pdf is not on disk.
    """
    if not PLANTA.exists():
        pytest.skip("planta_74.pdf not in working tree")

    tmp = tmp_path_factory.mktemp("v1_v5_baseline")
    cons = tmp / "consensus.json"
    labels = tmp / "labels.json"
    final = tmp / "consensus_baseline.json"

    _run("tools.build_vector_consensus", str(PLANTA),
         "--out", str(cons), "--detect-openings")
    _run("tools.extract_room_labels", str(PLANTA), "--out", str(labels))
    _run("tools.rooms_from_seeds", str(cons), str(labels), "--out", str(final))
    _run("tools.extract_openings_vector", str(PLANTA),
         "--consensus", str(final), "--out", str(final),
         "--mode", "replace")

    return json.loads(final.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Global invariants — both runs must hold the CLAUDE.md §10 baseline
# ---------------------------------------------------------------------------


def test_global_counts_baseline(pipeline_baseline: dict) -> None:
    assert len(pipeline_baseline["walls"]) == EXPECTED_WALLS
    assert len(pipeline_baseline["rooms"]) == EXPECTED_ROOMS
    assert len(pipeline_baseline["openings"]) == EXPECTED_OPENINGS
    assert len(pipeline_baseline["soft_barriers"]) == EXPECTED_SOFT_BARRIERS


def test_global_counts_with_flags(pipeline_with_flags: dict) -> None:
    """V1+V5 must NOT change wall/room/opening/soft_barrier counts."""
    assert len(pipeline_with_flags["walls"]) == EXPECTED_WALLS
    assert len(pipeline_with_flags["rooms"]) == EXPECTED_ROOMS
    assert len(pipeline_with_flags["openings"]) == EXPECTED_OPENINGS
    assert len(pipeline_with_flags["soft_barriers"]) == EXPECTED_SOFT_BARRIERS


# ---------------------------------------------------------------------------
# V1 invariant — SALA DE ESTAR diagonals strictly decrease
# ---------------------------------------------------------------------------


def test_v1_sala_de_estar_diagonals_drop(
    pipeline_baseline: dict, pipeline_with_flags: dict
) -> None:
    sala_b = next(
        r for r in pipeline_baseline["rooms"] if r["name"] == "SALA DE ESTAR"
    )
    sala_a = next(
        r for r in pipeline_with_flags["rooms"] if r["name"] == "SALA DE ESTAR"
    )
    n_diag_b = _diag_count(sala_b["polygon_pts"])
    n_diag_a = _diag_count(sala_a["polygon_pts"])
    assert n_diag_a < n_diag_b, (
        f"V1 regression with V5 also enabled: "
        f"SALA DE ESTAR diagonal count {n_diag_b} -> {n_diag_a}"
    )


# ---------------------------------------------------------------------------
# V4 invariant — A.S. remains a narrow vertical strip
# ---------------------------------------------------------------------------


def test_v4_as_stays_narrow(pipeline_with_flags: dict) -> None:
    asv = next(r for r in pipeline_with_flags["rooms"] if r["name"] == "A.S.")
    x0, y0, x1, y1 = _bbox(asv["polygon_pts"])
    width = x1 - x0
    height = y1 - y0
    assert width < 100.0, (
        f"V4 regression: A.S. width {width:.1f}pt expected < 100pt"
    )
    assert height / width >= 2.0, (
        f"V4 regression: A.S. ratio {height / width:.2f} expected >= 2.0"
    )


# ---------------------------------------------------------------------------
# V5 invariants — every opening classified, no false positives on planta_74
# ---------------------------------------------------------------------------


def test_v5_every_opening_has_kind(pipeline_with_flags: dict) -> None:
    for o in pipeline_with_flags["openings"]:
        assert "kind_v5" in o, (
            f"opening {o.get('id')} missing kind_v5 — classifier didn't run"
        )
        assert "kind_v5_reason" in o
        assert o["kind_v5"] in (
            "door_arc", "open_passage", "glazed_balcony", "window"
        )


def test_v5_planta_74_all_door_arc(pipeline_with_flags: dict) -> None:
    """On planta_74 every opening is an arc-detected door (12/12).
    Anchored to docs/learning/v5_opening_kind_enrichment.md result.
    """
    kinds = [o["kind_v5"] for o in pipeline_with_flags["openings"]]
    assert all(k == "door_arc" for k in kinds), (
        f"unexpected kind_v5 distribution on planta_74: {set(kinds)}"
    )


# ---------------------------------------------------------------------------
# Metadata stamps — both V1 and V5 stamps must coexist
# ---------------------------------------------------------------------------


def test_v1_metadata_stamp_present(pipeline_with_flags: dict) -> None:
    rfs = pipeline_with_flags.get("metadata", {}).get("rooms_from_seeds", {})
    assert rfs.get("canonicalize_rooms") is True
    assert rfs.get("room_canonicalization_tol") == SNAP_TOL_PLANTA_74


def test_v5_metadata_stamp_present(pipeline_with_flags: dict) -> None:
    md = pipeline_with_flags.get("metadata", {}).get(
        "opening_kind_v5_classifier", {}
    )
    assert md.get("version") == "1.0.0"
    assert md.get("n_openings_input") == md.get("n_openings_output")
    assert md.get("n_openings_input") == EXPECTED_OPENINGS
    counts = md.get("counts", {})
    assert counts.get("door_arc") == EXPECTED_OPENINGS
    # Other classes should be zero on planta_74
    assert counts.get("open_passage", 0) == 0
    assert counts.get("glazed_balcony", 0) == 0
    assert counts.get("window", 0) == 0


def test_baseline_has_no_v1v5_stamps(pipeline_baseline: dict) -> None:
    """Baseline run (no flags) must NOT carry the V1/V5 metadata,
    or carry only the schema-additive `canonicalize_rooms: False`.
    """
    rfs = pipeline_baseline.get("metadata", {}).get("rooms_from_seeds", {})
    if rfs:
        # If stamped (default OFF case), it must say False/null
        assert rfs.get("canonicalize_rooms") is False
        assert rfs.get("room_canonicalization_tol") is None
    # V5 classifier must be absent in baseline
    assert "opening_kind_v5_classifier" not in (
        pipeline_baseline.get("metadata") or {}
    )
