"""Tests for scripts/dashboard/generate_architecture_radar.py.

Each test stages a tiny synthetic repo under ``tmp_path`` and asserts that
the radar generator finds (or doesn't find) the expected signals — without
ever touching the real repo. Stdlib + pytest only; no network, no deps.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add scripts/dashboard/ to import path so the generator module is importable
# directly. Tests prefer importing over subprocess so coverage and traceback
# data flow naturally.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "dashboard"))

import generate_architecture_radar as gar  # noqa: E402,I001


# ---------------------------------------------------------------------------
# Fixtures (helper, not pytest fixture — just a builder).
# ---------------------------------------------------------------------------

def _stage_minimal_repo(root: Path) -> None:
    """Create a tiny but realistic repo under ``root``."""
    (root / "CLAUDE.md").write_text(
        "see tools/build_vector_consensus.py and scripts/missing.py\n",
        encoding="utf-8",
    )
    (root / "OVERVIEW.md").write_text("# Overview\nshort doc\n", encoding="utf-8")
    # A real-looking script the doc references.
    (root / "tools").mkdir()
    (root / "tools" / "build_vector_consensus.py").write_text(
        "# real script\n", encoding="utf-8"
    )
    # No scripts/missing.py — that's the drift we expect to surface.
    (root / "tools" / "dashboard").mkdir()
    (root / "tools" / "dashboard" / "index.html").write_text("<!doctype html>\n")


# ---------------------------------------------------------------------------
# 1. Generator produces valid, schema-tagged JSON.
# ---------------------------------------------------------------------------

def test_generates_valid_json(tmp_path: Path) -> None:
    _stage_minimal_repo(tmp_path)
    out = tmp_path / "radar.json"
    rc = gar.main(["--repo-root", str(tmp_path), "--out", str(out),
                   "--no-command-checks"])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == gar.SCHEMA_VERSION
    assert "generated_at" in data
    assert "overall" in data and "scores" in data
    assert "markdown" in data and "services" in data


# ---------------------------------------------------------------------------
# 2. A 1500-line markdown file lands in the saturated bucket.
# ---------------------------------------------------------------------------

def test_saturated_doc_detected(tmp_path: Path) -> None:
    _stage_minimal_repo(tmp_path)
    big = tmp_path / "BIG.md"
    # 1500 lines (>1000 → +35) of long content (≈100KB → +10), seven
    # TODO/FIXME/OUTDATED markers (>5 → +10), and the planned-vs-done mix
    # (+10). Expected score = 65, well into saturated.
    long_line = "filler line " * 6  # ≈70 chars per line
    body = "# Big doc\n" + (long_line + "\n") * 1500
    body += "\n## planned\nstill on the list\n## done\nshipped already\n"
    body += "TODO 1\nTODO 2\nFIXME 3\nFIXME 4\nOUTDATED 5\nOUTDATED 6\nTODO 7\n"
    big.write_text(body, encoding="utf-8")
    radar = gar.build_radar(tmp_path, run_commands=False)
    big_entry = next((d for d in radar["markdown"]["top_saturated"]
                      if d["path"] == "BIG.md"), None)
    assert big_entry is not None, "saturated BIG.md should appear in top_saturated"
    assert big_entry["score"] >= gar.MD_SCORE_SATURATED_AT, (
        f"score={big_entry['score']}, reasons={big_entry['reasons']}"
    )
    assert ">1000 lines" in big_entry["reasons"]
    assert radar["markdown"]["saturated_count"] >= 1


# ---------------------------------------------------------------------------
# 3. Drift: a doc referencing a missing path produces a finding.
# ---------------------------------------------------------------------------

def test_broken_ref_detected(tmp_path: Path) -> None:
    _stage_minimal_repo(tmp_path)
    radar = gar.build_radar(tmp_path, run_commands=False)
    refs = [f["ref"] for f in radar["drift_findings"]]
    assert "scripts/missing.py" in refs
    # The existing path must NOT be flagged.
    assert "tools/build_vector_consensus.py" not in refs


# ---------------------------------------------------------------------------
# 4. A service whose path is missing reports exists=false.
# ---------------------------------------------------------------------------

def test_missing_service_marked_exists_false(tmp_path: Path) -> None:
    _stage_minimal_repo(tmp_path)
    radar = gar.build_radar(tmp_path, run_commands=False)
    by_name = {s["name"]: s for s in radar["services"]}
    # `main.py` does not exist in this fixture.
    assert by_name["main"]["exists"] is False
    # `dashboard_index` does (we created tools/dashboard/index.html).
    assert by_name["dashboard_index"]["exists"] is True


# ---------------------------------------------------------------------------
# 5. --no-command-checks does not invoke subprocess for service probes.
# ---------------------------------------------------------------------------

def test_no_command_checks_flag(tmp_path: Path, monkeypatch: object) -> None:
    _stage_minimal_repo(tmp_path)
    calls: list[list[str]] = []

    def _fake_run(*args, **kwargs):
        calls.append(list(args[0]) if args else [])
        raise AssertionError("subprocess.run should not be invoked")

    # Patch subprocess.run inside the generator module so service probes
    # would be observable. Note: the generator also calls _git() which uses
    # subprocess; but _git only runs once per build_radar (for git metadata)
    # — those calls are allowed because they're not service probes. We
    # whitelist them by argv[0] == "git".
    real_run = gar.subprocess.run

    def _selective_run(cmd, *a, **kw):
        if cmd and cmd[0] == "git":
            return real_run(cmd, *a, **kw)
        return _fake_run(cmd, *a, **kw)

    monkeypatch.setattr(gar.subprocess, "run", _selective_run)
    radar = gar.build_radar(tmp_path, run_commands=False)
    assert radar["command_checks"] is False
    # All services should report help_passed=None when commands are skipped.
    for svc in radar["services"]:
        if svc["exists"]:
            assert svc["help_passed"] is None, f"{svc['name']} ran a probe"


# ---------------------------------------------------------------------------
# 6. When saturation is high, recommendations include a split/archive item.
# ---------------------------------------------------------------------------

def test_recommendations_present_when_score_high(tmp_path: Path) -> None:
    _stage_minimal_repo(tmp_path)
    long_line = "filler line " * 6
    body = "# Big\n" + (long_line + "\n") * 1200
    body += "\n## planned\nstill open\n## done\nshipped\n"
    body += "TODO 1\nTODO 2\nFIXME 3\nFIXME 4\nOUTDATED 5\nOUTDATED 6\n"
    (tmp_path / "BIG.md").write_text(body, encoding="utf-8")
    radar = gar.build_radar(tmp_path, run_commands=False)
    titles = [r["title"] for r in radar["recommendations"]]
    assert any("BIG.md" in t for t in titles), titles


# ---------------------------------------------------------------------------
# 7. A failing service probe (subprocess raises) does not crash the run.
# ---------------------------------------------------------------------------

def test_does_not_crash_on_missing_command(tmp_path: Path,
                                           monkeypatch: object) -> None:
    _stage_minimal_repo(tmp_path)
    real_run = gar.subprocess.run

    def _fail_for_services(cmd, *a, **kw):
        if cmd and cmd[0] == "git":
            return real_run(cmd, *a, **kw)
        raise FileNotFoundError("simulated missing python")

    monkeypatch.setattr(gar.subprocess, "run", _fail_for_services)
    radar = gar.build_radar(tmp_path, run_commands=True)
    # Generator must still complete and produce all sections.
    assert "scores" in radar
    assert isinstance(radar["services"], list)
    # At least one existing service should report help_passed=False with no
    # exception bubbling up.
    failed = [s for s in radar["services"]
              if s["exists"] and s.get("help_passed") is False]
    assert failed, "expected at least one service to record a probe failure"
