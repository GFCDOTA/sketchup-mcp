"""Teste do gate de inventário: adições, exclusões e classificações."""
import json
from pathlib import Path

from tools.rooms.inventory_gate import check_inventory, CONTROL_PATHS

ROOT = Path(__file__).resolve().parents[1]


def _index():
    return {"schema_version": "fp042_exhaustive_inventory.v1",
            "entries": [{"path": "tools/a.py", "domain": "runtime", "disposition": "review",
                         "phase": "P4", "status": "PENDING_REVIEW_OR_MIGRATION"}]}


def test_inventory_baseline_matches_git_tree():
    import subprocess
    tracked = {p.decode("utf-8") for p in subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT).split(b"\0") if p}
    index = json.loads((ROOT / "docs/specs/fp042_inventory.v1.json").read_text("utf-8"))
    result = check_inventory(index, tracked)
    assert result["result"] == "PASS", result


def test_new_file_must_be_registered():
    assert check_inventory(_index(), {"tools/a.py", "tools/b.py"})["errors"] == [
        "UNREGISTERED_FILES"]


def test_stale_file_must_be_removed():
    assert "STALE_FILES" in check_inventory(_index(), set())["errors"]


def test_missing_classification_fails_closed():
    index = _index()
    index["entries"][0]["domain"] = ""
    assert "UNCLASSIFIED_FILES" in check_inventory(index, {"tools/a.py"})["errors"]


def test_duplicate_path_is_detected():
    index = _index()
    index["entries"].append(index["entries"][0].copy())
    assert "DUPLICATE_PATHS" in check_inventory(index, {"tools/a.py"})["errors"]


def test_gate_controls_are_not_counted_as_business_files():
    assert check_inventory(_index(), {"tools/a.py", *CONTROL_PATHS})["result"] == "PASS"
