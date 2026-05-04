"""Tests for the v2 delta-tracking layer in agents.auditor.run_audit.

Covers `derive_findings`, `diff_findings`, `latest_prior_snapshot`,
`load_findings_from_snapshot`, and the round-trip of writing and
reading back a snapshot. The full `main()` and the per-section
`check_*` functions are not tested here — those touch git, ruff,
and pytest collection in ways that depend on the live repo state.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "agents" / "auditor" / "run_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_audit_v2", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_audit_v2"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit():
    return _load_module()


@pytest.fixture()
def synthetic_report():
    """Minimal but realistic report shape that exercises every
    branch of derive_findings."""
    return {
        "schema_version": "2.0.0",
        "timestamp": "2026-05-04T01:00:00Z",
        "repo_root": "/x",
        "git": {
            "branch": "feature/x",
            "head_commit": "abc123" + "0" * 34,
            "working_tree_clean": False,
            "uncommitted_files_count": 3,
        },
        "runs": {"exists": True, "subdir_count": 12, "tracked_files": 4},
        "ruff": {
            "installed": True,
            "total_violations": 5,
            "by_code": {"F401": 3, "E741": 2},
            "exit_code": 1,
        },
        "pytest": {"collected": 218, "collection_errors": 1, "exit_code": 1},
        "root_python_files": {
            "total": 2, "files": ["main.py", "stale.py"],
            "expected": ["main.py"], "suspicious": ["stale.py"],
        },
        "render_scripts": {
            "root": ["render_a.py"],
            "tools": ["render_b.py"],
            "scripts": [],
            "scripts_preview": [],
        },
        "sys_path_shims": {"count": 0, "sample": []},
        "subprocess_use": {"count": 0, "sample": []},
        "hardcoded_paths": {
            "count": 1,
            "findings": [
                {"pattern": "C:/Users/", "desc": "Windows user home",
                 "match": "tools/foo.py:42:    p = 'C:/Users/me/x'"}
            ],
        },
        "patches": {
            "exists": True,
            "active": ["02-density-trigger.py"],
            "archived": ["07-reconnect.py"],
        },
        "large_files": {
            "count": 1,
            "top10": [{"path": "vendor/bigthing.bin", "size_bytes": 2_500_000}],
        },
        "todo_fixme": {
            "total_lines_with_marker": 0,
            "files_with_markers": 0,
            "top20": {},
        },
        "entrypoints": {
            "main.py": {"exit_code": 0, "ok": True, "first_line": "ok"},
            "validator/run.py": {"exit_code": 1, "ok": False,
                                 "first_line": "boom"},
        },
    }


# ---------------------------------------------------------------------------
# Finding helpers
# ---------------------------------------------------------------------------


def test_finding_to_from_dict_roundtrip(audit):
    f = audit.Finding(kind="x", key="k", severity="ok", message="m")
    assert audit.Finding.from_dict(f.to_dict()) == f


def test_finding_is_frozen(audit):
    f = audit.Finding(kind="x", key="k", severity="ok", message="m")
    with pytest.raises(Exception):
        f.kind = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# derive_findings
# ---------------------------------------------------------------------------


def test_derive_findings_covers_all_branches(audit, synthetic_report):
    findings = audit.derive_findings(synthetic_report)
    kinds = {f.kind for f in findings}
    expected_kinds = {
        "ruff_code", "suspicious_root_py", "hardcoded_path",
        "active_patch", "archived_patch", "large_file",
        "broken_entrypoint", "pytest_collection_errors",
        "render_scripts_duplicated", "working_tree_dirty",
    }
    assert expected_kinds.issubset(kinds), f"missing: {expected_kinds - kinds}"


def test_derive_findings_ruff_keys_match_codes(audit, synthetic_report):
    findings = audit.derive_findings(synthetic_report)
    ruff_keys = sorted(f.key for f in findings if f.kind == "ruff_code")
    assert ruff_keys == ["E741", "F401"]


def test_derive_findings_critical_severity_for_broken_entrypoint(audit, synthetic_report):
    findings = audit.derive_findings(synthetic_report)
    broken = [f for f in findings if f.kind == "broken_entrypoint"]
    assert len(broken) == 1
    assert broken[0].key == "validator/run.py"
    assert broken[0].severity == "critical"


def test_derive_findings_clean_report_yields_empty(audit):
    """A pristine report should produce zero findings."""
    clean = {
        "git": {"working_tree_clean": True, "uncommitted_files_count": 0},
        "runs": {"exists": True, "subdir_count": 0, "tracked_files": 0},
        "ruff": {"installed": True, "total_violations": 0, "by_code": {}},
        "pytest": {"collected": 100, "collection_errors": 0, "exit_code": 0},
        "root_python_files": {
            "total": 1, "files": ["main.py"],
            "expected": ["main.py"], "suspicious": [],
        },
        "render_scripts": {"tools": []},
        "hardcoded_paths": {"count": 0, "findings": []},
        "patches": {"exists": False},
        "large_files": {"count": 0, "top10": []},
        "todo_fixme": {"total_lines_with_marker": 0, "top20": {}},
        "entrypoints": {"main.py": {"ok": True, "exit_code": 0}},
    }
    assert audit.derive_findings(clean) == []


def test_derive_findings_is_deterministic_order(audit, synthetic_report):
    a = audit.derive_findings(synthetic_report)
    b = audit.derive_findings(synthetic_report)
    assert [f.to_dict() for f in a] == [f.to_dict() for f in b]


# ---------------------------------------------------------------------------
# diff_findings
# ---------------------------------------------------------------------------


def _F(audit, kind, key, sev="attention", msg="m"):
    return audit.Finding(kind=kind, key=key, severity=sev, message=msg)


def test_diff_findings_classifies_correctly(audit):
    prev = [_F(audit, "ruff_code", "F401"),
            _F(audit, "ruff_code", "E741"),
            _F(audit, "suspicious_root_py", "old.py")]
    curr = [_F(audit, "ruff_code", "F401"),
            _F(audit, "ruff_code", "E702"),  # NEW
            _F(audit, "suspicious_root_py", "new.py")]  # NEW
    # E741 and old.py disappeared -> RESOLVED
    diff = audit.diff_findings(curr, prev)
    new_keys = sorted((f["kind"], f["key"]) for f in diff["new"])
    resolved_keys = sorted((f["kind"], f["key"]) for f in diff["resolved"])
    persisting_keys = sorted((f["kind"], f["key"]) for f in diff["persisting"])
    assert new_keys == [("ruff_code", "E702"), ("suspicious_root_py", "new.py")]
    assert resolved_keys == [("ruff_code", "E741"),
                             ("suspicious_root_py", "old.py")]
    assert persisting_keys == [("ruff_code", "F401")]


def test_diff_findings_first_run_all_new(audit):
    curr = [_F(audit, "x", "1"), _F(audit, "x", "2")]
    diff = audit.diff_findings(curr, [])
    assert len(diff["new"]) == 2
    assert diff["resolved"] == []
    assert diff["persisting"] == []


def test_diff_findings_no_changes(audit):
    items = [_F(audit, "x", "1")]
    diff = audit.diff_findings(items, items)
    assert diff["new"] == []
    assert diff["resolved"] == []
    assert len(diff["persisting"]) == 1


def test_diff_findings_message_taken_from_curr_for_persisting(audit):
    """When a finding persists but its message changed (e.g. ruff
    count went 3 -> 5), the diff should reflect the latest text."""
    prev = [audit.Finding("ruff_code", "F401", "attention", "3 F401 violations")]
    curr = [audit.Finding("ruff_code", "F401", "attention", "5 F401 violations")]
    diff = audit.diff_findings(curr, prev)
    assert diff["persisting"][0]["message"] == "5 F401 violations"


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


def test_latest_prior_snapshot_picks_lexicographic_max(audit, tmp_path):
    (tmp_path / "repo_audit_20260501T000000Z.json").write_text("{}")
    (tmp_path / "repo_audit_20260503T120000Z.json").write_text("{}")
    (tmp_path / "repo_audit_20260502T080000Z.json").write_text("{}")
    latest = audit.latest_prior_snapshot(tmp_path)
    assert latest is not None
    assert latest.name == "repo_audit_20260503T120000Z.json"


def test_latest_prior_snapshot_skips_excluded(audit, tmp_path):
    a = tmp_path / "repo_audit_20260501T000000Z.json"
    b = tmp_path / "repo_audit_20260503T120000Z.json"
    a.write_text("{}")
    b.write_text("{}")
    latest = audit.latest_prior_snapshot(tmp_path, exclude=b)
    assert latest is not None
    assert latest.name == a.name


def test_latest_prior_snapshot_returns_none_when_empty(audit, tmp_path):
    assert audit.latest_prior_snapshot(tmp_path) is None


def test_latest_prior_snapshot_handles_missing_dir(audit, tmp_path):
    assert audit.latest_prior_snapshot(tmp_path / "does_not_exist") is None


def test_load_findings_from_v2_snapshot(audit, tmp_path):
    snap = tmp_path / "repo_audit_20260501T000000Z.json"
    findings_data = [
        {"kind": "ruff_code", "key": "F401", "severity": "attention",
         "message": "3 F401 violations"},
    ]
    snap.write_text(json.dumps({"findings": findings_data}))
    out = audit.load_findings_from_snapshot(snap)
    assert len(out) == 1
    assert out[0].kind == "ruff_code"
    assert out[0].key == "F401"


def test_load_findings_falls_back_to_v1_derive(audit, tmp_path, synthetic_report):
    """An old report without a `findings` array should be derivable
    in-place so v2 can diff against v1 history."""
    snap = tmp_path / "repo_audit_20260501T000000Z.json"
    # Remove the findings field — simulating a v1 snapshot.
    legacy = dict(synthetic_report)
    legacy.pop("findings", None)
    snap.write_text(json.dumps(legacy))
    out = audit.load_findings_from_snapshot(snap)
    # synthetic_report exercises every branch, so derive_findings
    # produces a non-empty list.
    assert out
    kinds = {f.kind for f in out}
    assert "ruff_code" in kinds


def test_load_findings_handles_corrupt_snapshot(audit, tmp_path):
    snap = tmp_path / "repo_audit_20260501T000000Z.json"
    snap.write_text("{not json")
    assert audit.load_findings_from_snapshot(snap) == []


# ---------------------------------------------------------------------------
# Round-trip: write → re-read → diff
# ---------------------------------------------------------------------------


def test_roundtrip_findings_via_snapshot(audit, tmp_path, synthetic_report):
    """Persisting findings to disk and re-reading them must
    preserve the (kind, key) identity that diff_findings relies on.
    """
    findings = audit.derive_findings(synthetic_report)
    snap = tmp_path / "repo_audit_20260501T000000Z.json"
    snap.write_text(json.dumps({
        "findings": [f.to_dict() for f in findings],
    }))
    reloaded = audit.load_findings_from_snapshot(snap)
    assert reloaded == findings

    # Now diff the reloaded set against itself: should be all
    # PERSISTING, zero NEW, zero RESOLVED.
    diff = audit.diff_findings(findings, reloaded)
    assert diff["new"] == []
    assert diff["resolved"] == []
    assert len(diff["persisting"]) == len(findings)
