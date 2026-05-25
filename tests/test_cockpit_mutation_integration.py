"""Cross-PR integration tests — Slice 2 (writer) -> Slice 3 (reader).

PR #83 (Slice 2) shipped ``cockpit/overrides.py`` (the writer side
that the Streamlit cockpit calls when a human mutates an opening
kind, label, etc.) PR #84 (Slice 3) shipped ``tools/apply_overrides``
+ ``gate_f0`` + the fidelity-engine apply-overrides mode (the reader
side the smoke harness + CI consume). Each ships with its own unit
tests against schema fixtures.

This module exercises the actual round-trip: a real Slice 2
``save_override()`` writes a ``review_overrides.json`` to disk, then
Slice 3's ``apply_overrides()`` + ``compare(..., apply_overrides=True)``
+ ``_compute_pre_skp_review`` consume it. Asserts the verdict and
amended observation reflect the override end-to-end.

Boundary (per the task brief):
- This PR is a strict CONSUMER: it ONLY uses public APIs of
  ``cockpit.overrides`` and ``tools.apply_overrides``. Any API gap
  found here is documented in the PR body, not patched here.
- Tests are filesystem-isolated under ``tmp_path`` (no real
  ``runs/`` writes, no SketchUp).
- The canonical planta_74 baseline is gitignored, so the smoke
  test against ``runs/.../consensus_with_room_context.json`` skips
  cleanly when missing (CI-stripped checkouts).

ADR-001 references in assertions:
  §2.5  precedence + signature + validation
  §2.7  audit_trail append-only
  §2.8  pre_skp_review verdict matrix
  §2.10 immutable consensus + sha binding + amended schema
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from cockpit.overrides import (
    OVERRIDES_FILENAME,
    compute_consensus_sha256,
    load_overrides,
    overrides_path,
    save_override,
    set_block_skp_export,
)
from tools.apply_overrides import (
    AMENDED_SCHEMA_VERSION,
    OVERRIDES_SCHEMA_VERSION,
    _consensus_sha256,
    apply_overrides,
)
from tools.fidelity.compare_generated_to_expected import (
    EXPECTED_SCHEMA_VERSION,
    compare,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = (
    REPO_ROOT / "tests" / "fixtures" / "cockpit_mutation_integration"
)
CONSENSUS_FIXTURE = FIXTURE_DIR / "consensus_minimal.json"
EXPECTED_FIXTURE = FIXTURE_DIR / "expected_minimal.json"

# Canonical planta_74 baseline — present only on dev checkouts. CI
# strips ``runs/``; the matching test pytest.skip()s when absent.
CANONICAL_CONSENSUS = (
    REPO_ROOT
    / "runs"
    / "feature_room_context_2026_05_06"
    / "consensus_with_room_context.json"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_consensus() -> dict:
    """Hand-crafted 2-room/1-opening/5-wall consensus (see fixture
    JSON for the full coordinates). Returned as a fresh dict so each
    test gets an independent copy."""
    return json.loads(
        CONSENSUS_FIXTURE.read_text(encoding="utf-8"),
    )


@pytest.fixture
def minimal_expected() -> dict:
    return json.loads(
        EXPECTED_FIXTURE.read_text(encoding="utf-8"),
    )


@pytest.fixture
def run_with_consensus(tmp_path: Path, minimal_consensus: dict):
    """Materialises ``tmp_path/<run_id>/consensus.json`` and returns
    (run_dir, consensus_path, consensus_dict). Each test gets a clean
    run dir under pytest's tmp_path."""
    run_dir = tmp_path / "test_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    cons_path = run_dir / "consensus.json"
    cons_path.write_text(
        json.dumps(minimal_consensus), encoding="utf-8",
    )
    return run_dir, cons_path, minimal_consensus


def _load_smoke_module():
    """Load the smoke harness via importlib (same trick as
    tests/test_smoke_gate_f0.py — script lives in scripts/smoke/ and
    is not on sys.path)."""
    script_path = REPO_ROOT / "scripts" / "smoke" / "smoke_skp_export.py"
    spec = importlib.util.spec_from_file_location(
        "smoke_skp_export_for_integration", script_path,
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["smoke_skp_export_for_integration"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def smoke():
    return _load_smoke_module()


def _make_smoke_args(smoke, **overrides):
    parser = smoke._build_parser()
    args = parser.parse_args([])
    # Mutation-integration tests use minimal synthetic fixtures whose
    # wall topology trips the FP-014 gamma gate's C7/C9 cosmetic
    # warnings. Default the flag ON here so existing scenario tests
    # keep their original verdict expectations. Tests that want to
    # exercise the gamma gate can override.
    if "no_structural_checks" not in overrides:
        overrides["no_structural_checks"] = True
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


def _make_smoke_report(smoke, **overrides):
    defaults = {
        "consensus_path": "/x/consensus.json",
        "out_dir": "/x/out",
        "started_at": "2026-05-08T00:00:00Z",
    }
    defaults.update(overrides)
    return smoke.SmokeReport(**defaults)


# ---------------------------------------------------------------------------
# Scenario 1 — opening_kind_override round-trip through apply_overrides
# ---------------------------------------------------------------------------


def test_opening_kind_override_round_trip_through_apply(
    run_with_consensus, minimal_consensus,
):
    """Slice 2 writes opening_kind_override -> Slice 3 applies ->
    amended observation has new kind, original preserved, source=manual."""
    run_dir, cons_path, cons = run_with_consensus

    # --- WRITE (Slice 2) -------------------------------------------------
    payload = {
        "type": "opening_kind_override",
        "target": {"kind": "opening", "id": "o0"},
        "payload": {"new_kind_v5": "interior_passage"},
        "reason": "round-trip integration: door is actually a passage",
    }
    saved = save_override(
        run_dir, payload,
        audit_actor="human:integration_test",
        consensus_path=cons_path, consensus=cons,
    )
    assert len(saved["overrides"]) == 1
    assert overrides_path(run_dir).exists()

    # --- READ (Slice 3) --------------------------------------------------
    overrides_doc = json.loads(
        overrides_path(run_dir).read_text(encoding="utf-8"),
    )
    assert overrides_doc["schema_version"] == OVERRIDES_SCHEMA_VERSION

    amended = apply_overrides(cons, overrides_doc)

    # --- ASSERTS ---------------------------------------------------------
    assert amended["_overrides_metadata"]["schema_version"] == (
        AMENDED_SCHEMA_VERSION
    )
    assert amended["_overrides_applied"] == 1

    o0 = next(o for o in amended["openings"] if o["id"] == "o0")
    assert o0["kind_v5"] == "interior_passage"
    assert o0["_kind_v5_original"] == "interior_door"
    assert o0["source"] == "manual"

    # Source consensus on disk was NOT mutated (ADR §2.10.1).
    cons_redux = json.loads(cons_path.read_text(encoding="utf-8"))
    o0_orig = next(o for o in cons_redux["openings"] if o["id"] == "o0")
    assert o0_orig["kind_v5"] == "interior_door"
    assert "_kind_v5_original" not in o0_orig
    assert "source" not in o0_orig


# ---------------------------------------------------------------------------
# Scenario 2 — room_label_override round-trip
# ---------------------------------------------------------------------------


def test_room_label_override_round_trip(
    run_with_consensus, minimal_consensus,
):
    run_dir, cons_path, cons = run_with_consensus
    payload = {
        "type": "room_label_override",
        "target": {"kind": "room", "id": "r1"},
        "payload": {"new_name": "KITCHEN"},
        "reason": "anglicise label",
    }
    save_override(
        run_dir, payload,
        audit_actor="human:integration_test",
        consensus_path=cons_path, consensus=cons,
    )

    overrides_doc = json.loads(
        overrides_path(run_dir).read_text(encoding="utf-8"),
    )
    amended = apply_overrides(cons, overrides_doc)

    r1 = next(r for r in amended["rooms"] if r["id"] == "r1")
    assert r1["name"] == "KITCHEN"
    assert r1["_name_original"] == "COZINHA"
    assert r1["source"] == "manual"


# ---------------------------------------------------------------------------
# Scenario 3 — reject_element drops opening + fidelity reflects it
# ---------------------------------------------------------------------------


def test_reject_element_round_trip(
    run_with_consensus, minimal_expected,
):
    """Reject opening o0 via Slice 2; Slice 3 drops it from amended;
    fidelity engine sees opening_count_delta of -1."""
    run_dir, cons_path, cons = run_with_consensus
    save_override(
        run_dir,
        {
            "type": "reject_element",
            "target": {"kind": "opening", "id": "o0"},
            "payload": {},
            "reason": "phantom door",
        },
        audit_actor="human:integration_test",
        consensus_path=cons_path, consensus=cons,
    )

    overrides_doc = json.loads(
        overrides_path(run_dir).read_text(encoding="utf-8"),
    )
    amended = apply_overrides(cons, overrides_doc)

    # Opening dropped from amended observation
    assert all(o["id"] != "o0" for o in amended["openings"])
    md = amended["_overrides_metadata"]
    assert md["rejected_opening_ids"] == ["o0"]

    # Fidelity in apply mode shows the count change in post.
    report = compare(
        cons, minimal_expected,
        apply_overrides=True, overrides_doc=overrides_doc,
    )
    counts = report["metrics"]["counts"]["checks"]
    # expected: 1 opening, actual after reject: 0, delta=-1, tol=1 -> still pass
    assert counts["openings_count_delta"]["actual"] == 0
    assert report["overrides_applied_count"] == 1


# ---------------------------------------------------------------------------
# Scenario 4 — approve_element round-trip
# ---------------------------------------------------------------------------


def test_approve_element_round_trip(
    run_with_consensus, minimal_consensus,
):
    run_dir, cons_path, cons = run_with_consensus
    save_override(
        run_dir,
        {
            "type": "approve_element",
            "target": {"kind": "opening", "id": "o0"},
            "payload": {},
            "reason": "reviewer confirms door",
        },
        audit_actor="human:integration_test",
        consensus_path=cons_path, consensus=cons,
    )
    overrides_doc = json.loads(
        overrides_path(run_dir).read_text(encoding="utf-8"),
    )
    amended = apply_overrides(cons, overrides_doc)
    o0 = next(o for o in amended["openings"] if o["id"] == "o0")
    assert o0["_approved"] is True
    assert o0["source"] == "manual"


# ---------------------------------------------------------------------------
# Scenario 5 — block_skp_export propagates Slice 2 -> gate_f0 verdict FAIL
# ---------------------------------------------------------------------------


def test_block_skp_export_propagates_to_pre_skp_review(
    smoke, run_with_consensus, tmp_path: Path,
):
    """set_block_skp_export() via Slice 2 -> gate_f0 reads the file ->
    pre_skp_review_report.json verdict = FAIL even when fidelity is high."""
    run_dir, cons_path, cons = run_with_consensus
    set_block_skp_export(
        run_dir, blocked=True,
        reason="reviewer demands manual SKP review",
        audit_actor="human:integration_test",
        consensus_path=cons_path,
    )

    # gate_f0 reads review_overrides.json from out_dir; we point
    # out_dir at the run_dir directly so the override file is found.
    out_dir = run_dir
    # gate_f0 also wants a fidelity_report next to it. Write a
    # high-fidelity report so block_skp_export is the SOLE reason
    # for FAIL.
    (out_dir / "fidelity_report.json").write_text(
        json.dumps({
            "schema_version": "1.0",
            "global_fidelity": 0.95,
            "sub_scores": {"room_score": 1.0, "count_score": 1.0},
            "hard_fails": [],
            "warnings": [],
            "would_block_strict": [],
        }),
        encoding="utf-8",
    )
    args = _make_smoke_args(smoke, out_dir=out_dir, review_mode="block")
    report = _make_smoke_report(
        smoke,
        out_dir=str(out_dir),
        consensus_path=str(cons_path),
        consensus_sha256=compute_consensus_sha256(cons_path),
    )
    g = smoke.gate_f0(args, report)

    # Verdict file present
    review_path = out_dir / "pre_skp_review_report.json"
    assert review_path.exists()
    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["verdict"] == "FAIL"
    assert review["block_skp_export"] is True
    # In block-mode + FAIL -> gate aborts (per ADR §2.8 matrix)
    assert g.status == "fail"


# ---------------------------------------------------------------------------
# Scenario 6 — consensus_sha256 mismatch invalidates overrides at apply time
# ---------------------------------------------------------------------------


def test_consensus_sha256_mismatch_invalidates_overrides_at_apply(
    run_with_consensus, minimal_consensus,
):
    """Slice 2 writes against sha A; consensus changes; Slice 3 sees
    sha B. apply_overrides() rejects ALL overrides + records warning."""
    run_dir, cons_path, cons = run_with_consensus
    save_override(
        run_dir,
        {
            "type": "opening_kind_override",
            "target": {"kind": "opening", "id": "o0"},
            "payload": {"new_kind_v5": "window"},
            "reason": "round-trip",
        },
        audit_actor="human:integration_test",
        consensus_path=cons_path, consensus=cons,
    )

    # Mutate consensus on disk so the live sha differs from bound sha
    mutated = dict(cons)
    mutated["_mutated_for_test"] = True
    cons_path.write_text(json.dumps(mutated), encoding="utf-8")

    # Slice 2's load_overrides reports the mismatch
    re_loaded = load_overrides(run_dir, consensus_path=cons_path)
    assert re_loaded["_consensus_sha256_match"] is False
    assert overrides_path(run_dir).exists(), (
        "override file must persist on sha mismatch — only flagged stale"
    )

    overrides_doc = json.loads(
        overrides_path(run_dir).read_text(encoding="utf-8"),
    )
    # Slice 3 receives the LIVE consensus + computes its own sha for
    # the apply check — overrides bound to A while live is B -> reject.
    live_sha = _consensus_sha256(mutated)
    amended = apply_overrides(
        mutated, overrides_doc, expected_sha=live_sha,
    )
    md = amended["_overrides_metadata"]
    assert amended["_overrides_applied"] == 0
    assert md.get("sha_mismatch") is True
    assert any("consensus_sha256 mismatch" in w for w in md["warnings"])
    # Original kind preserved
    o0 = next(o for o in amended["openings"] if o["id"] == "o0")
    assert o0["kind_v5"] == "interior_door"
    assert o0["source"] == "detected"


# ---------------------------------------------------------------------------
# Scenario 7 — fidelity emits both pre and post override scores
# ---------------------------------------------------------------------------


def test_apply_overrides_preserves_pre_override_fidelity(
    run_with_consensus, minimal_expected,
):
    """ADR §2.10.5: a review can never make the score look better
    without leaving evidence — both global_fidelity (post) and
    global_fidelity_pre_override (pre) must appear in the report."""
    run_dir, cons_path, cons = run_with_consensus
    save_override(
        run_dir,
        {
            "type": "opening_kind_override",
            "target": {"kind": "opening", "id": "o0"},
            "payload": {"new_kind_v5": "window"},
            "reason": "demonstrate dual-score emission",
        },
        audit_actor="human:integration_test",
        consensus_path=cons_path, consensus=cons,
    )
    overrides_doc = json.loads(
        overrides_path(run_dir).read_text(encoding="utf-8"),
    )
    report = compare(
        cons, minimal_expected,
        apply_overrides=True, overrides_doc=overrides_doc,
    )
    # Required dual-score keys
    assert "global_fidelity" in report
    assert "global_fidelity_pre_override" in report
    assert "sub_scores_pre_override" in report
    assert "warnings_pre_override" in report
    assert "hard_fails_pre_override" in report
    assert report["overrides_applied_count"] == 1


# ---------------------------------------------------------------------------
# Scenario 8 — audit_trail entries survive Slice 3 apply (read-only)
# ---------------------------------------------------------------------------


def test_audit_trail_survives_through_apply(
    run_with_consensus, minimal_consensus,
):
    """Slice 3 reads the override file but never writes back to it.
    audit_trail entries appended by Slice 2 must remain on disk
    untouched after apply_overrides + compare run."""
    run_dir, cons_path, cons = run_with_consensus
    # Build up several audit events
    save_override(
        run_dir,
        {
            "type": "opening_kind_override",
            "target": {"kind": "opening", "id": "o0"},
            "payload": {"new_kind_v5": "window"},
            "reason": "first",
        },
        audit_actor="human:a",
        consensus_path=cons_path, consensus=cons,
    )
    save_override(
        run_dir,
        {
            "type": "approve_element",
            "target": {"kind": "room", "id": "r0"},
            "payload": {},
            "reason": "second",
        },
        audit_actor="human:b",
        consensus_path=cons_path, consensus=cons,
    )
    set_block_skp_export(
        run_dir, blocked=True, reason="third",
        audit_actor="human:c", consensus_path=cons_path,
    )

    on_disk_before = json.loads(
        overrides_path(run_dir).read_text(encoding="utf-8"),
    )
    audit_before = list(on_disk_before["audit_trail"])
    assert len(audit_before) == 3

    # Apply through Slice 3 — must NOT touch the file
    overrides_doc = on_disk_before
    apply_overrides(cons, overrides_doc)

    on_disk_after = json.loads(
        overrides_path(run_dir).read_text(encoding="utf-8"),
    )
    assert on_disk_after["audit_trail"] == audit_before
    # All entries still have unique uuids + diff_signatures
    ids = [a["id"] for a in on_disk_after["audit_trail"]]
    assert len(set(ids)) == len(ids)
    for a in on_disk_after["audit_trail"]:
        assert "diff_signature" in a
        assert len(a["diff_signature"]) == 64


# ---------------------------------------------------------------------------
# Scenario 9 — no overrides: full pipeline byte-equivalent to no-overrides
# ---------------------------------------------------------------------------


def test_full_pipeline_no_overrides_byte_equivalent(
    run_with_consensus, minimal_expected,
):
    """When ``review_overrides.json`` is missing on disk:
       - Slice 3 apply_overrides(cons, None) yields identity (with
         source=detected tags + zero applied count).
       - Slice 3 compare(... default mode) emits a v1 report (no
         override-aware keys), byte-equivalent to the legacy invocation.
    """
    run_dir, cons_path, cons = run_with_consensus
    # No save_override calls — verify no file was ever created.
    assert not overrides_path(run_dir).exists()

    amended = apply_overrides(cons, None)
    assert amended["_overrides_applied"] == 0
    for op in amended["openings"]:
        assert op["source"] == "detected"
    for r in amended["rooms"]:
        assert r["source"] == "detected"

    # Compare in default mode: no override-aware keys present.
    legacy_report = compare(cons, minimal_expected)
    explicit_off = compare(
        cons, minimal_expected, apply_overrides=False,
    )
    assert "global_fidelity_pre_override" not in legacy_report
    assert "overrides_applied_count" not in legacy_report
    assert "block_skp_export" not in legacy_report
    # Byte-equivalent (ignoring generated_at timestamp)
    legacy_report.pop("generated_at", None)
    explicit_off.pop("generated_at", None)
    assert legacy_report == explicit_off


# ---------------------------------------------------------------------------
# Scenario 10 — precedence: reject beats kind_override at apply
# ---------------------------------------------------------------------------


def test_precedence_reject_beats_kind_override_at_apply(
    run_with_consensus, minimal_consensus,
):
    """Slice 2 saves both a kind_override AND a reject_element on the
    same opening (write order: kind, then reject). Slice 3 must apply
    the reject (per ADR §2.5 precedence) — the opening drops, kind
    change does not surface."""
    run_dir, cons_path, cons = run_with_consensus

    # First override: change kind to window
    save_override(
        run_dir,
        {
            "type": "opening_kind_override",
            "target": {"kind": "opening", "id": "o0"},
            "payload": {"new_kind_v5": "window"},
            "reason": "intermediate review",
        },
        audit_actor="human:integration_test",
        consensus_path=cons_path, consensus=cons,
    )
    # Second override: reject same opening (newer created_at -> wins)
    save_override(
        run_dir,
        {
            "type": "reject_element",
            "target": {"kind": "opening", "id": "o0"},
            "payload": {},
            "reason": "actually phantom",
        },
        audit_actor="human:integration_test",
        consensus_path=cons_path, consensus=cons,
    )

    overrides_doc = json.loads(
        overrides_path(run_dir).read_text(encoding="utf-8"),
    )
    assert len(overrides_doc["overrides"]) == 2

    amended = apply_overrides(cons, overrides_doc)
    assert all(o["id"] != "o0" for o in amended["openings"])
    md = amended["_overrides_metadata"]
    assert "o0" in md["rejected_opening_ids"]
    # Both audit entries still present in source file (audit is
    # append-only; precedence is an apply-time concept).
    assert len(overrides_doc["audit_trail"]) == 2


# ---------------------------------------------------------------------------
# Scenario 11 — gate_f0 verdict matrix on the real fixture pair
# ---------------------------------------------------------------------------


def test_gate_f0_verdict_pass_on_minimal_baseline(
    smoke, run_with_consensus, minimal_expected,
):
    """End-to-end: write fidelity report from minimal fixture pair,
    no overrides, gate_f0 in default off mode -> verdict PASS,
    gate passes."""
    run_dir, cons_path, cons = run_with_consensus
    report_data = compare(
        cons, minimal_expected,
        observed_path=cons_path, expected_path=EXPECTED_FIXTURE,
    )
    out_dir = run_dir
    (out_dir / "fidelity_report.json").write_text(
        json.dumps(report_data), encoding="utf-8",
    )
    args = _make_smoke_args(smoke, out_dir=out_dir, review_mode="off")
    report = _make_smoke_report(
        smoke,
        out_dir=str(out_dir),
        consensus_path=str(cons_path),
        consensus_sha256=compute_consensus_sha256(cons_path),
    )
    g = smoke.gate_f0(args, report)
    assert g.status == "pass"
    review = json.loads(
        (out_dir / "pre_skp_review_report.json").read_text(encoding="utf-8"),
    )
    # global_fidelity from the fixture pair is 1.0 -> PASS
    assert review["verdict"] == "PASS"
    assert review["block_skp_export"] is False


# ---------------------------------------------------------------------------
# Scenario 12 — opening_connects_override round-trip
# ---------------------------------------------------------------------------


def test_opening_connects_override_round_trip(
    run_with_consensus, minimal_consensus,
):
    """Slice 2 -> Slice 3: re-link an opening to a different room pair.
    Amended opening carries the new room ids + ``_room_*_id_original``
    preservation per ADR §2.10.4."""
    run_dir, cons_path, cons = run_with_consensus
    # Swap the room link (silly for this 2-room fixture but exercises
    # the field-preservation contract end-to-end).
    save_override(
        run_dir,
        {
            "type": "opening_connects_override",
            "target": {"kind": "opening", "id": "o0"},
            "payload": {"room_left_id": "r1", "room_right_id": "r0"},
            "reason": "swap orientation",
        },
        audit_actor="human:integration_test",
        consensus_path=cons_path, consensus=cons,
    )
    overrides_doc = json.loads(
        overrides_path(run_dir).read_text(encoding="utf-8"),
    )
    amended = apply_overrides(cons, overrides_doc)
    o0 = next(o for o in amended["openings"] if o["id"] == "o0")
    assert o0["room_left_id"] == "r1"
    assert o0["room_right_id"] == "r0"
    assert o0["_room_left_id_original"] == "r0"
    assert o0["_room_right_id_original"] == "r1"
    assert o0["source"] == "manual"


# ---------------------------------------------------------------------------
# Scenario 13 — mark_suspect high severity surfaces in pre_skp_review
# ---------------------------------------------------------------------------


def test_mark_suspect_high_severity_surfaces_in_review(
    smoke, run_with_consensus,
):
    """Slice 2 marks an opening as suspect (severity=high). Slice 3
    gate_f0 in off mode reads it, verdict bumps to WARN per ADR §2.8."""
    run_dir, cons_path, cons = run_with_consensus
    save_override(
        run_dir,
        {
            "type": "mark_suspect",
            "target": {"kind": "opening", "id": "o0"},
            "payload": {"severity": "high", "tag": "needs_review"},
            "reason": "shape unclear in PDF",
        },
        audit_actor="human:integration_test",
        consensus_path=cons_path, consensus=cons,
    )
    out_dir = run_dir
    # High-fidelity baseline so suspect is the SOLE reason for WARN
    (out_dir / "fidelity_report.json").write_text(
        json.dumps({
            "schema_version": "1.0",
            "global_fidelity": 0.95,
            "sub_scores": {},
            "hard_fails": [],
            "warnings": [],
            "would_block_strict": [],
        }),
        encoding="utf-8",
    )
    args = _make_smoke_args(smoke, out_dir=out_dir, review_mode="off")
    smoke_report = _make_smoke_report(
        smoke,
        out_dir=str(out_dir),
        consensus_path=str(cons_path),
        consensus_sha256=compute_consensus_sha256(cons_path),
    )
    smoke.gate_f0(args, smoke_report)
    review = json.loads(
        (out_dir / "pre_skp_review_report.json").read_text(encoding="utf-8"),
    )
    assert review["verdict"] == "WARN"
    assert any("mark_suspect" in r for r in review["reasons"])


# ---------------------------------------------------------------------------
# Scenario 14 — sha mismatch surfaces FAIL in gate_f0 (Slice 2 + 3 wired)
# ---------------------------------------------------------------------------


def test_sha_mismatch_surfaces_fail_in_gate_f0(
    smoke, run_with_consensus,
):
    """Slice 2 writes override bound to consensus sha A. Consensus on
    disk mutates to sha B. gate_f0's _compute_pre_skp_review compares
    bound sha vs the live consensus_sha256 it received and emits
    verdict FAIL (per ADR §2.8 verdict matrix)."""
    run_dir, cons_path, cons = run_with_consensus
    save_override(
        run_dir,
        {
            "type": "opening_kind_override",
            "target": {"kind": "opening", "id": "o0"},
            "payload": {"new_kind_v5": "window"},
            "reason": "round-trip",
        },
        audit_actor="human:integration_test",
        consensus_path=cons_path, consensus=cons,
    )
    # Mutate consensus -> live sha changes
    mutated = dict(cons)
    mutated["_mutated_for_test"] = True
    cons_path.write_text(json.dumps(mutated), encoding="utf-8")
    live_sha = compute_consensus_sha256(cons_path)

    out_dir = run_dir
    (out_dir / "fidelity_report.json").write_text(
        json.dumps({
            "schema_version": "1.0",
            "global_fidelity": 0.95,
            "sub_scores": {},
            "hard_fails": [],
            "warnings": [],
            "would_block_strict": [],
        }),
        encoding="utf-8",
    )
    args = _make_smoke_args(smoke, out_dir=out_dir, review_mode="block")
    smoke_report = _make_smoke_report(
        smoke,
        out_dir=str(out_dir),
        consensus_path=str(cons_path),
        consensus_sha256=live_sha,
    )
    g = smoke.gate_f0(args, smoke_report)
    review = json.loads(
        (out_dir / "pre_skp_review_report.json").read_text(encoding="utf-8"),
    )
    assert review["verdict"] == "FAIL"
    assert any("consensus_sha256_mismatch" in r for r in review["reasons"])
    # block-mode + FAIL aborts the gate
    assert g.status == "fail"


# ---------------------------------------------------------------------------
# Scenario 15 — overrides file is the canonical filename Slice 3 looks for
# ---------------------------------------------------------------------------


def test_overrides_filename_matches_slice3_lookup(
    run_with_consensus,
):
    """Defensive: Slice 2 names the file ``review_overrides.json``;
    Slice 3 (gate_f0 + apply_overrides CLI) looks for that exact
    filename. A rename in either layer breaks the integration silently
    until this test fails."""
    run_dir, cons_path, cons = run_with_consensus
    save_override(
        run_dir,
        {
            "type": "approve_element",
            "target": {"kind": "opening", "id": "o0"},
            "payload": {},
        },
        audit_actor="human:integration_test",
        consensus_path=cons_path, consensus=cons,
    )
    assert OVERRIDES_FILENAME == "review_overrides.json"
    assert overrides_path(run_dir).name == OVERRIDES_FILENAME
    assert (run_dir / OVERRIDES_FILENAME).exists()


# ---------------------------------------------------------------------------
# Scenario 16 — canonical planta_74 baseline smoke (skipped on stripped CI)
# ---------------------------------------------------------------------------


def test_canonical_planta_74_baseline_smoke():
    """End-to-end smoke against the canonical planta_74 baseline.

    Skipped cleanly when ``runs/feature_room_context_2026_05_06/
    consensus_with_room_context.json`` isn't on disk (CI checkouts
    strip ``runs/``). Just verifies apply_overrides() ingests the
    real consensus + identity-copy yields source=detected.
    """
    if not CANONICAL_CONSENSUS.exists():
        pytest.skip(
            f"canonical baseline absent at {CANONICAL_CONSENSUS} "
            "(expected in dev checkouts; CI strips runs/)",
        )
    cons = json.loads(CANONICAL_CONSENSUS.read_text(encoding="utf-8"))
    amended = apply_overrides(cons, None)
    assert amended["_overrides_applied"] == 0
    # Every opening + room tagged source=detected after identity copy
    for op in amended.get("openings") or []:
        assert op["source"] == "detected"
    for r in amended.get("rooms") or []:
        assert r["source"] == "detected"
