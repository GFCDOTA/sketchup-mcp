"""Unit tests for the Validation Cockpit's History view (Cycle 12f).

Covers:
- run discovery (`discover_runs`)
- fidelity report parsing (`summarise_run`)
- history-model assembly (RunSummary fields + as_dict)
- before/after comparison (`compare_runs`)
- pre-SKP review status logic (`pre_skp_review`)

All tests build their own ``runs/`` tree under ``tmp_path`` so they
do NOT depend on the gitignored ``runs/`` directory existing in the
checkout.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cockpit.history_view import (
    PRE_SKP_PASS_FIDELITY,
    PRE_SKP_WARN_FIDELITY,
    RunSummary,
    compare_runs,
    discover_runs,
    history_summary,
    order_runs_for_history,
    pre_skp_review,
    summarise_run,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _consensus_payload(rooms: int = 11, walls: int = 33,
                       openings: int = 11, soft: int = 8,
                       branch: str = "feature/foo",
                       commit: str = "abcdef1234",
                       stage: str = "5_classify",
                       generated_at: str = "2026-05-08T10:00:00Z",
                       plan_id: str | None = "planta_74") -> dict:
    """A consensus dict shaped like the post-classifier `c3` output.
    Sized to match the planta_74 baseline by default (33/11/11/8 per
    CLAUDE.md §10) so the test reads as a realistic snapshot."""
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "plan_id": plan_id,
        "metadata": {
            "git": {"branch": branch, "commit": commit},
            "stage": stage,
            "generated_at": generated_at,
            "plan_id": plan_id,
        },
        "walls": [
            {"id": f"w{i}", "start": [0, i * 10], "end": [100, i * 10],
             "thickness": 5.4, "orientation": "h"}
            for i in range(walls)
        ],
        "rooms": [
            {"id": f"r{i}", "name": f"ROOM_{i}",
             "polygon_pts": [[0, 0], [50, 0], [50, 50], [0, 50]],
             "area_pts2": 2500}
            for i in range(rooms)
        ],
        "openings": [
            {"id": f"o{i}", "wall_id": f"w{i}",
             "kind_v5": "interior_door", "decision": "clean",
             "center": [50.0, 50.0],
             "evidence": {"room_left": "ROOM_0", "room_right": "ROOM_1"}}
            for i in range(openings)
        ],
        "soft_barriers": [{"id": f"sb{i}"} for i in range(soft)],
    }


def _fidelity_report_payload(score: float = 0.917,
                              hard_fails: list[str] | None = None,
                              warnings: list[str] | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "global_fidelity": score,
        "sub_scores": {"room_score": 0.95, "count_score": 1.0,
                        "adjacency_score": 0.78, "bbox_score": 1.0},
        "hard_fails": hard_fails or [],
        "warnings": warnings or [],
        "would_block_strict": hard_fails or [],
    }


def _materialise_run(repo: Path,
                     run_id: str,
                     consensus_payload: dict | None,
                     fidelity_payload: dict | None = None,
                     consensus_filename: str = (
                         "consensus_with_room_context.json"),
                     extra_files: dict[str, bytes | str] | None = None
                     ) -> Path:
    """Create a synthetic ``runs/<run_id>/`` directory under
    ``repo`` and write the given payloads to disk."""
    run_dir = repo / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if consensus_payload is not None:
        (run_dir / consensus_filename).write_text(
            json.dumps(consensus_payload), encoding="utf-8",
        )
    if fidelity_payload is not None:
        (run_dir / "fidelity_report.json").write_text(
            json.dumps(fidelity_payload), encoding="utf-8",
        )
    for name, contents in (extra_files or {}).items():
        target = run_dir / name
        if isinstance(contents, str):
            target.write_text(contents, encoding="utf-8")
        else:
            target.write_bytes(contents)
    return run_dir


# ---------------------------------------------------------------------------
# Test 1 — Run discovery
# ---------------------------------------------------------------------------

def test_discover_runs_finds_only_consensus_bearing_dirs(tmp_path: Path):
    """``discover_runs`` walks `runs/` and ignores dirs that don't
    contain at least one consensus-shaped JSON. Empty subdirs and
    pure-PNG-only dirs must be excluded so the cockpit doesn't list
    rows it cannot summarise."""
    # Two valid runs
    _materialise_run(tmp_path, "run_a", _consensus_payload())
    _materialise_run(tmp_path, "run_b", _consensus_payload(rooms=10))
    # Empty noise dir — must be skipped
    (tmp_path / "runs" / "noise_empty").mkdir(parents=True, exist_ok=True)
    # PNG-only dir — must be skipped (no consensus JSON)
    png_only = tmp_path / "runs" / "preview_only"
    png_only.mkdir(parents=True, exist_ok=True)
    (png_only / "preview.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    # JSON that's not consensus-shaped — must be skipped
    other = tmp_path / "runs" / "other_json_only"
    other.mkdir(parents=True, exist_ok=True)
    (other / "metrics.json").write_text(
        json.dumps({"some_field": 1}), encoding="utf-8",
    )

    found = discover_runs(tmp_path)
    names = {p.name for p in found}
    assert names == {"run_a", "run_b"}, names


def test_discover_runs_returns_empty_list_when_runs_dir_absent(tmp_path: Path):
    """Stripped checkout with no `runs/` directory must NOT crash."""
    assert discover_runs(tmp_path) == []


# ---------------------------------------------------------------------------
# Test 2 — Fidelity report parsing + summary assembly
# ---------------------------------------------------------------------------

def test_summarise_run_parses_consensus_and_fidelity(tmp_path: Path):
    """``summarise_run`` populates counts, fidelity, metadata, and
    image_paths from the artifacts present on disk."""
    payload = _consensus_payload(rooms=11, walls=33, openings=11)
    fidelity = _fidelity_report_payload(score=0.917, warnings=["w1", "w2"])
    run_dir = _materialise_run(
        tmp_path, "feature_room_context_2026_05_06",
        payload, fidelity, extra_files={
            "preview_overlay.png": b"\x89PNG\r\n\x1a\n",
            "axon_top.png": b"\x89PNG\r\n\x1a\n",
            "fidelity_scorecard.md": "# Score\n",
        },
    )
    rs = summarise_run(run_dir, repo=tmp_path)
    assert rs.run_id == "feature_room_context_2026_05_06"
    assert rs.consensus_path is not None
    assert rs.fidelity_report_path is not None
    assert rs.scorecard_path is not None
    assert rs.rooms_count == 11
    assert rs.walls_count == 33
    assert rs.openings_count == 11
    assert rs.soft_barriers_count == 8
    assert rs.fidelity_score == 0.917
    assert rs.warnings == ["w1", "w2"]
    assert rs.hard_fails == []
    assert rs.branch == "feature/foo"
    assert rs.commit and rs.commit.startswith("abcdef")
    assert rs.stage == "5_classify"
    # Image collection picks up both PNGs and ranks overlay-hinted first.
    img_names = [p.name for p in rs.image_paths]
    assert "preview_overlay.png" in img_names
    assert "axon_top.png" in img_names
    # `as_dict()` truncates commit to 8 chars for the dataframe view
    snap = rs.as_dict()
    assert snap["commit"] == "abcdef12"
    assert snap["fidelity_score"] == 0.917
    assert snap["hard_fails"] == 0
    assert snap["warnings"] == 2


def test_summarise_run_handles_missing_fidelity_gracefully(tmp_path: Path):
    """A run without `fidelity_report.json` must still produce a valid
    ``RunSummary`` — fidelity_score=None, hard_fails=[], warnings=[]."""
    payload = _consensus_payload(rooms=5, walls=10, openings=4)
    run_dir = _materialise_run(tmp_path, "partial_run", payload, None)
    rs = summarise_run(run_dir, repo=tmp_path)
    assert rs.run_id == "partial_run"
    assert rs.fidelity_score is None
    assert rs.fidelity_report_path is None
    assert rs.hard_fails == []
    assert rs.warnings == []
    assert rs.rooms_count == 5
    assert rs.walls_count == 10
    assert rs.openings_count == 4


def test_summarise_run_handles_completely_missing_consensus(tmp_path: Path):
    """If the consensus JSON cannot be parsed (corrupt / absent), the
    summary returns 0 counts + None metadata instead of raising."""
    # Materialise a directory with NO consensus + NO fidelity. We have
    # to skip discovery (it would not list this dir) — `summarise_run`
    # should still tolerate the input.
    run_dir = tmp_path / "runs" / "ghost_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    rs = summarise_run(run_dir, repo=tmp_path)
    assert rs.run_id == "ghost_run"
    assert rs.consensus_path is None
    assert rs.rooms_count == 0
    assert rs.walls_count == 0
    assert rs.openings_count == 0
    assert rs.fidelity_score is None
    assert rs.branch is None


# ---------------------------------------------------------------------------
# Test 3 — History-model assembly + ordering
# ---------------------------------------------------------------------------

def test_history_summary_orders_runs_newest_first(tmp_path: Path):
    """`history_summary` walks every consensus-bearing dir AND orders
    them newest-first using consensus.metadata.generated_at as the
    primary key. Falls back to the YYYY-MM-DD substring in the run id
    when generated_at is absent."""
    _materialise_run(
        tmp_path, "old_run_2026_04_01",
        _consensus_payload(generated_at="2026-04-01T00:00:00Z"),
    )
    _materialise_run(
        tmp_path, "new_run_2026_05_08",
        _consensus_payload(generated_at="2026-05-08T19:00:00Z"),
    )
    _materialise_run(
        tmp_path, "mid_run_2026_04_15",
        _consensus_payload(generated_at="2026-04-15T12:00:00Z"),
    )
    history = history_summary(tmp_path)
    assert [r.run_id for r in history] == [
        "new_run_2026_05_08", "mid_run_2026_04_15", "old_run_2026_04_01",
    ]


def test_order_runs_for_history_falls_back_to_run_id_date(tmp_path: Path):
    """When generated_at is unset, the fallback parses YYYY-MM-DD or
    YYYY_MM_DD substrings from the run_id."""
    rs1 = RunSummary(run_id="run_2026_04_01", run_dir=tmp_path / "a")
    rs2 = RunSummary(run_id="run_2026_05_08", run_dir=tmp_path / "b")
    rs3 = RunSummary(run_id="run_2026_04_15", run_dir=tmp_path / "c")
    ordered = order_runs_for_history([rs1, rs2, rs3])
    assert [r.run_id for r in ordered] == [
        "run_2026_05_08", "run_2026_04_15", "run_2026_04_01",
    ]


# ---------------------------------------------------------------------------
# Test 4 — Before/after comparison
# ---------------------------------------------------------------------------

def test_compare_runs_emits_fidelity_delta_and_warning_diff(tmp_path: Path):
    """`compare_runs` returns the right deltas + warning sets."""
    a_dir = _materialise_run(
        tmp_path, "run_a",
        _consensus_payload(rooms=10, walls=30, openings=8),
        _fidelity_report_payload(
            score=0.69, hard_fails=["hf:area_in_range:SUITE 01 actual=69.91"],
            warnings=["w1", "w2"]),
    )
    b_dir = _materialise_run(
        tmp_path, "run_b",
        _consensus_payload(rooms=11, walls=33, openings=11),
        _fidelity_report_payload(score=0.917,
                                  hard_fails=[], warnings=["w2", "w3"]),
    )
    a = summarise_run(a_dir, repo=tmp_path)
    b = summarise_run(b_dir, repo=tmp_path)
    diff = compare_runs(a, b)
    assert diff.run_a_id == "run_a"
    assert diff.run_b_id == "run_b"
    assert diff.fidelity_delta is not None
    assert round(diff.fidelity_delta, 3) == round(0.917 - 0.69, 3)
    assert diff.rooms_delta == 1
    assert diff.walls_delta == 3
    assert diff.openings_delta == 3
    # New warning in B that wasn't in A
    assert diff.warnings_new == ["w3"]
    # Warning resolved (in A but no longer in B)
    assert diff.warnings_resolved == ["w1"]
    # The hard_fail from A is gone in B
    assert diff.hard_fails_new == []
    assert diff.hard_fails_resolved == [
        "hf:area_in_range:SUITE 01 actual=69.91",
    ]
    # Per-room table must be populated (delegates to render_overlay)
    assert isinstance(diff.rooms, list)
    assert len(diff.rooms) > 0


def test_compare_runs_handles_missing_fidelity_on_one_side(tmp_path: Path):
    """When one side lacks `fidelity_report.json`, fidelity_delta=None
    but the comparison still produces count + room deltas."""
    a_dir = _materialise_run(
        tmp_path, "run_a", _consensus_payload(rooms=10),
        _fidelity_report_payload(score=0.85),
    )
    b_dir = _materialise_run(
        tmp_path, "run_b", _consensus_payload(rooms=12), None,
    )
    a = summarise_run(a_dir, repo=tmp_path)
    b = summarise_run(b_dir, repo=tmp_path)
    diff = compare_runs(a, b)
    assert diff.fidelity_delta is None
    assert diff.rooms_delta == 2
    assert diff.warnings_new == []
    assert diff.warnings_resolved == []


# ---------------------------------------------------------------------------
# Test 5 — Pre-SKP Review status logic
# ---------------------------------------------------------------------------

def test_pre_skp_review_passes_on_clean_run(tmp_path: Path):
    """High fidelity + zero hard_fails + few warnings → PASS / safe."""
    run_dir = _materialise_run(
        tmp_path, "clean_run", _consensus_payload(),
        _fidelity_report_payload(score=0.92, hard_fails=[], warnings=["w1"]),
    )
    rs = summarise_run(run_dir, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["status"] == "PASS"
    assert review["recommendation"] == "safe"
    assert review["fidelity_score"] == 0.92
    assert review["hard_fails_count"] == 0
    assert review["warnings_count"] == 1
    assert review["thresholds"]["pass_fidelity"] == PRE_SKP_PASS_FIDELITY


def test_pre_skp_review_warns_on_marginal_fidelity(tmp_path: Path):
    """Fidelity between warn and pass thresholds, no hard_fails →
    WARN / review."""
    run_dir = _materialise_run(
        tmp_path, "marginal_run", _consensus_payload(),
        _fidelity_report_payload(score=0.78, hard_fails=[], warnings=[]),
    )
    rs = summarise_run(run_dir, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["status"] == "WARN"
    assert review["recommendation"] == "review"
    assert any("pass_threshold" in r for r in review["reasons"])


def test_pre_skp_review_fails_on_hard_fail(tmp_path: Path):
    """Even with high fidelity, ANY hard_fail caps to FAIL."""
    run_dir = _materialise_run(
        tmp_path, "hard_fail_run", _consensus_payload(),
        _fidelity_report_payload(
            score=0.92,
            hard_fails=["hf:area_in_range:SUITE 01 actual=69.91"],
            warnings=[]),
    )
    rs = summarise_run(run_dir, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["status"] == "FAIL"
    assert review["recommendation"] == "review"
    assert review["hard_fails_count"] == 1


def test_pre_skp_review_fails_when_no_fidelity_report(tmp_path: Path):
    """Cockpit must not greenlight a run it cannot grade. No
    fidelity_report.json → FAIL with explanatory reason."""
    run_dir = _materialise_run(
        tmp_path, "ungraded_run", _consensus_payload(), None,
    )
    rs = summarise_run(run_dir, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["status"] == "FAIL"
    assert review["recommendation"] == "review"
    assert any("no fidelity_report" in r for r in review["reasons"])


def test_pre_skp_review_warns_on_too_many_warnings(tmp_path: Path):
    """Even with passing fidelity + zero hard_fails, exceeding the
    warning budget bumps the run to WARN."""
    many_warns = [f"warning:check_{i}" for i in range(10)]
    run_dir = _materialise_run(
        tmp_path, "noisy_run", _consensus_payload(),
        _fidelity_report_payload(score=0.95, hard_fails=[],
                                 warnings=many_warns),
    )
    rs = summarise_run(run_dir, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["status"] == "WARN"
    assert review["recommendation"] == "review"


def test_pre_skp_review_fails_below_warn_threshold(tmp_path: Path):
    """Fidelity below the warn threshold → FAIL even when hard_fails
    is empty (mirrors the engine's strict cap)."""
    run_dir = _materialise_run(
        tmp_path, "low_fidelity_run", _consensus_payload(),
        _fidelity_report_payload(
            score=PRE_SKP_WARN_FIDELITY - 0.05, hard_fails=[], warnings=[]),
    )
    rs = summarise_run(run_dir, repo=tmp_path)
    review = pre_skp_review(rs)
    assert review["status"] == "FAIL"


# ---------------------------------------------------------------------------
# Test 6 — Custom thresholds (bonus coverage)
# ---------------------------------------------------------------------------

def test_pre_skp_review_threshold_kwargs_override_defaults(tmp_path: Path):
    """Callers can tighten or loosen the cockpit thresholds without
    touching the module constants."""
    run_dir = _materialise_run(
        tmp_path, "threshold_run", _consensus_payload(),
        _fidelity_report_payload(score=0.80, hard_fails=[], warnings=[]),
    )
    rs = summarise_run(run_dir, repo=tmp_path)
    # Tight pass threshold (0.95) — this run drops to WARN
    review = pre_skp_review(rs, pass_fidelity=0.95)
    assert review["status"] == "WARN"
    # Loose pass threshold (0.75) — same run promotes to PASS
    review = pre_skp_review(rs, pass_fidelity=0.75)
    assert review["status"] == "PASS"


# ---------------------------------------------------------------------------
# Smoke: real planta_74 expected_model resolution path
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_summarise_run_resolves_expected_model_from_plan_id(tmp_path: Path):
    """When the consensus carries a `plan_id`, `summarise_run` should
    resolve `<repo>/ground_truth/<plan_id>/expected_model.json` —
    BUT only when that file actually exists in the repo."""
    payload = _consensus_payload(plan_id="planta_74")
    run_dir = _materialise_run(tmp_path, "plan74_run", payload, None)
    # tmp_path has no ground_truth dir — should resolve to None
    rs = summarise_run(run_dir, repo=tmp_path)
    assert rs.expected_model_path is None
    # Now create ground_truth/planta_74/expected_model.json — it
    # should resolve.
    gt = tmp_path / "ground_truth" / "planta_74"
    gt.mkdir(parents=True, exist_ok=True)
    (gt / "expected_model.json").write_text("{}", encoding="utf-8")
    rs2 = summarise_run(run_dir, repo=tmp_path)
    assert rs2.expected_model_path is not None
    assert rs2.expected_model_path.parent.name == "planta_74"


# ---------------------------------------------------------------------------
# Real-data smoke: against the on-disk repo (skip on stripped checkout)
# ---------------------------------------------------------------------------

def test_history_summary_on_real_repo_does_not_raise():
    """Smoke: running `history_summary(REPO_ROOT)` against the live
    checkout must not raise. The exact list depends on what's in
    `runs/` so we only assert it returns a list."""
    out = history_summary(REPO_ROOT)
    assert isinstance(out, list)
    # Each entry must be a RunSummary
    for rs in out:
        assert isinstance(rs, RunSummary)
        assert rs.run_id
        assert rs.run_dir.exists()


def test_pre_skp_review_real_planta_74_baseline_smoke():
    """If the canonical planta_74 run dir exists locally, validate
    the verdict against documented expectation (CLAUDE.md §10:
    fidelity ~0.917 + 0 hard_fails + 2 warnings = WARN because
    warnings > 3? No — exactly 2 warnings, so should be PASS)."""
    canonical = (REPO_ROOT / "runs"
                 / "feature_room_context_2026_05_06")
    if not canonical.exists():
        pytest.skip("canonical planta_74 c3 missing")
    rs = summarise_run(canonical, repo=REPO_ROOT)
    review = pre_skp_review(rs)
    assert review["status"] in {"PASS", "WARN", "FAIL"}
    assert review["recommendation"] in {"safe", "review"}
