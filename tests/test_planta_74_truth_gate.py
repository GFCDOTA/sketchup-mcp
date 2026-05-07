"""Plan Truth Gate — versioned baseline for the planta_74 pipeline.

Stage 1.5 (PR feature/plan-truth-gate-planta-74). Locks the
deterministic output of the V7 vector + room-context pipeline against
the JSON baseline at ``tests/baselines/planta_74.json``.

Why this gate exists:

The pipeline has 4+ tunable detectors (walls, rooms, openings, wall
gaps) plus a downstream classifier. Each step has thresholds. Without
a baseline, a tweak to ANY threshold could silently shift counts and
no test would catch it. The previous CI gate (`smoke_skp_export.py`)
checked SHAPE but not COUNTS — so a regression where 11 -> 9
openings would have passed silently.

This file:

1. Runs the canonical 5-step vector pipeline against ``planta_74.pdf``
   exactly as encoded in the baseline JSON's ``pipeline.stages``.
2. Asserts each top-level entity count matches the baseline within
   the specified delta tolerance (default 0 — exact match).
3. Asserts kind/decision distributions match exactly.
4. Asserts every documented invariant holds (no invalid rooms, no
   floating openings, no duplicate walls, every opening has kind_v5
   + wall_id, every room has seed_pt).

The full run takes ~5-10 s (CPU-only, no SU). Marked
``@pytest.mark.skipif`` when the PDF is missing so CI on the
classifier-removed branch can still pass.

Update procedure (when baseline NEEDS to change):

* Bump ``schema_version`` only on breaking changes to the JSON shape.
* Update ``expected_counts`` + ``expected_by_kind`` /
  ``expected_by_decision`` + ``notes`` together in a SINGLE PR that
  explains why the count moved and which detector / threshold change
  caused it.
* Never edit this file to make a failing test pass without an
  accompanying explanation in the PR body.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PDF = REPO_ROOT / "planta_74.pdf"
BASELINE = REPO_ROOT / "tests" / "baselines" / "planta_74.json"
PYTHON = sys.executable


pytestmark = pytest.mark.skipif(
    not PDF.exists() or not BASELINE.exists(),
    reason="planta_74.pdf or baseline JSON missing",
)


def _run_pipeline(tmp_path: Path) -> dict:
    """Run the canonical 5-step vector pipeline and return the final
    classified consensus dict. tmp_path holds intermediate JSONs."""
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    stages = baseline["pipeline"]["stages"]

    # Stage 1: build_vector_consensus PDF -> consensus.json
    c0 = tmp_path / "c0_consensus.json"
    s0 = stages[0]
    cmd = [PYTHON, "-m", s0["module"], str(PDF), "--out", str(c0),
           *s0["flags"]]
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True,
                    capture_output=True, text=True)

    # Stage 2: extract_room_labels PDF -> labels.json
    labels = tmp_path / "labels.json"
    s1 = stages[1]
    cmd = [PYTHON, "-m", s1["module"], str(PDF), "--out", str(labels),
           *s1["flags"]]
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True,
                    capture_output=True, text=True)

    # Stage 3: rooms_from_seeds c0 + labels -> c1
    c1 = tmp_path / "c1_with_rooms.json"
    s2 = stages[2]
    cmd = [PYTHON, "-m", s2["module"], str(c0), str(labels),
           "--out", str(c1), *s2["flags"]]
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True,
                    capture_output=True, text=True)

    # Stage 4: extract_openings_vector c1 -> c2
    c2 = tmp_path / "c2_with_openings.json"
    s3 = stages[3]
    cmd = [PYTHON, "-m", s3["module"], str(PDF),
           "--consensus", str(c1), "--out", str(c2), *s3["flags"]]
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True,
                    capture_output=True, text=True)

    # Stage 5: classify_openings_by_room_context c2 -> c3
    c3 = tmp_path / "c3_classified.json"
    s4 = stages[4]
    cmd = [PYTHON, "-m", s4["module"], str(c2), "--out", str(c3),
           *s4["flags"]]
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True,
                    capture_output=True, text=True)

    return json.loads(c3.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def consensus(tmp_path_factory) -> dict:
    """Run the pipeline once per test module."""
    tmp = tmp_path_factory.mktemp("plan_truth_gate")
    return _run_pipeline(tmp)


# ---- Top-level counts ----

def test_walls_count_matches_baseline(consensus, baseline):
    expected = baseline["expected_counts"]["walls"]
    actual = len(consensus.get("walls", []))
    delta = abs(actual - expected)
    tol = baseline["tolerances"]["wall_count_delta"]
    assert delta <= tol, (
        f"walls={actual} expected={expected} (tol={tol}). If this is "
        f"intentional, update tests/baselines/planta_74.json + "
        f"document the change in the PR body."
    )


def test_rooms_count_matches_baseline(consensus, baseline):
    expected = baseline["expected_counts"]["rooms"]
    actual = len(consensus.get("rooms", []))
    delta = abs(actual - expected)
    tol = baseline["tolerances"]["room_count_delta"]
    assert delta <= tol, f"rooms={actual} expected={expected}"


def test_openings_count_matches_baseline(consensus, baseline):
    expected = baseline["expected_counts"]["openings"]
    actual = len(consensus.get("openings", []))
    delta = abs(actual - expected)
    tol = baseline["tolerances"]["opening_count_delta"]
    assert delta <= tol, (
        f"openings={actual} expected={expected} (tol={tol}). "
        f"Trajectory note: 12 was the May-5 pre-wall-gap baseline; "
        f"15 is post-detector pre-classifier; 11 is post-classifier. "
        f"Update tests/baselines/planta_74.json with rationale."
    )


def test_soft_barriers_count_matches_baseline(consensus, baseline):
    expected = baseline["expected_counts"]["soft_barriers"]
    actual = len(consensus.get("soft_barriers", []))
    delta = abs(actual - expected)
    tol = baseline["tolerances"]["soft_barrier_count_delta"]
    assert delta <= tol, f"soft_barriers={actual} expected={expected}"


# ---- Distribution counts ----

def test_openings_by_kind_matches_baseline(consensus, baseline):
    expected = baseline["expected_by_kind"]
    actual = Counter(o.get("kind_v5") for o in consensus.get("openings", []))
    tol = baseline["tolerances"]["by_kind_count_delta"]
    for kind, count in expected.items():
        delta = abs(actual.get(kind, 0) - count)
        assert delta <= tol, (
            f"by_kind[{kind}]={actual.get(kind, 0)} expected={count}"
        )
    # Reject unexpected new kinds (would change the model semantics)
    for kind in actual:
        if kind not in expected:
            assert actual[kind] == 0, (
                f"unexpected kind '{kind}' appeared in output; not "
                f"in baseline. If new kind is intentional, add it "
                f"to expected_by_kind."
            )


def test_openings_by_decision_matches_baseline(consensus, baseline):
    expected = baseline["expected_by_decision"]
    actual = Counter(o.get("decision") for o in consensus.get("openings", []))
    tol = baseline["tolerances"]["by_decision_count_delta"]
    for dec, count in expected.items():
        delta = abs(actual.get(dec, 0) - count)
        assert delta <= tol, (
            f"by_decision[{dec}]={actual.get(dec, 0)} expected={count}"
        )


def test_room_names_present(consensus, baseline):
    expected = set(baseline["expected_room_names"])
    actual = {r.get("name") for r in consensus.get("rooms", [])}
    missing = expected - actual
    assert not missing, (
        f"missing rooms: {missing}. Either the OCR/seed step changed "
        f"or the PDF was replaced. Investigate before updating "
        f"tests/baselines/planta_74.json."
    )


# ---- Invariants ----

def test_no_invalid_room_polygons(consensus, baseline):
    invalid = [
        r["id"] for r in consensus.get("rooms", [])
        if len(r.get("polygon_pts") or []) < 3
    ]
    expected_max = baseline["invariants"]["invalid_rooms"]
    assert len(invalid) <= expected_max, (
        f"{len(invalid)} invalid room polygon(s): {invalid}; "
        f"baseline allows {expected_max}"
    )


def test_no_floating_openings(consensus, baseline):
    walls_by_id = {w["id"] for w in consensus.get("walls", [])
                    if w.get("id")}
    floating = [
        o["id"] for o in consensus.get("openings", [])
        if not o.get("wall_id") or o["wall_id"] not in walls_by_id
    ]
    expected_max = baseline["invariants"]["floating_openings"]
    assert len(floating) <= expected_max, (
        f"{len(floating)} floating opening(s): {floating}; "
        f"baseline allows {expected_max}"
    )


def test_no_duplicate_walls(consensus, baseline):
    walls = consensus.get("walls", [])
    dups = []
    for i, a in enumerate(walls):
        for b in walls[i + 1:]:
            if a.get("orientation") != b.get("orientation"):
                continue
            if a.get("orientation") == "h":
                if abs(a["start"][1] - b["start"][1]) > 1.0:
                    continue
                ax = sorted([a["start"][0], a["end"][0]])
                bx = sorted([b["start"][0], b["end"][0]])
                if ax[1] < bx[0] - 1.0 or bx[1] < ax[0] - 1.0:
                    continue
            else:
                if abs(a["start"][0] - b["start"][0]) > 1.0:
                    continue
                ay = sorted([a["start"][1], a["end"][1]])
                by = sorted([b["start"][1], b["end"][1]])
                if ay[1] < by[0] - 1.0 or by[1] < ay[0] - 1.0:
                    continue
            dups.append((a.get("id"), b.get("id")))
    expected_max = baseline["invariants"]["duplicate_walls"]
    assert len(dups) <= expected_max, (
        f"{len(dups)} duplicate wall pair(s): {dups}; "
        f"baseline allows {expected_max}"
    )


def test_every_opening_has_kind_v5(consensus, baseline):
    missing = [
        o.get("id") for o in consensus.get("openings", [])
        if not o.get("kind_v5")
    ]
    expected_max = baseline["invariants"]["openings_without_kind_v5"]
    assert len(missing) <= expected_max, (
        f"{len(missing)} opening(s) without kind_v5: {missing}"
    )


def test_every_opening_has_wall_id(consensus, baseline):
    missing = [
        o.get("id") for o in consensus.get("openings", [])
        if not o.get("wall_id")
    ]
    expected_max = baseline["invariants"]["openings_without_wall_id"]
    assert len(missing) <= expected_max, (
        f"{len(missing)} opening(s) without wall_id: {missing}"
    )


def test_every_room_has_seed_pt(consensus, baseline):
    missing = [
        r.get("id") for r in consensus.get("rooms", [])
        if not r.get("seed_pt")
    ]
    expected_max = baseline["invariants"]["rooms_without_seed_pt"]
    assert len(missing) <= expected_max, (
        f"{len(missing)} room(s) without seed_pt: {missing}"
    )


# ---- Schema sanity ----

def test_baseline_schema_version_is_one_zero(baseline):
    assert baseline["schema_version"] == "1.0"


def test_baseline_pipeline_has_five_stages(baseline):
    assert len(baseline["pipeline"]["stages"]) == 5
