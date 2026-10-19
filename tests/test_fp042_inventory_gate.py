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


def test_strict_mode_fails_on_pending_and_manual_owner():
    data = _index()
    pending = check_inventory(data, {"tools/a.py"}, require_complete=True)
    assert pending["result"] == "FAIL"
    assert "UNRESOLVED_OWNERSHIP_OR_MIGRATION" in pending["errors"]
    assert pending["unresolved"] == ["tools/a.py"]
    data["entries"][0].update({"status": "VERIFIED_CODE_OWNERSHIP",
                               "disposition": "tools.rooms.kitchen"})
    assert check_inventory(data, {"tools/a.py"}, require_complete=True)["result"] == "PASS"
    data["entries"][0]["disposition"] = "manual_owner_review"
    assert check_inventory(data, {"tools/a.py"}, require_complete=True)["result"] == "FAIL"


def test_strict_mode_rejects_unclassified_and_pending_ci():
    data = _index()
    data["entries"][0].update({"status": "VERIFIED_CODE_OWNERSHIP_PENDING_CI",
                               "domain": "unclassified_special_case"})
    result = check_inventory(data, {"tools/a.py"}, require_complete=True)
    assert result["result"] == "FAIL"
    data["entries"][0].update({"status": "VERIFIED_CODE_OWNERSHIP", "domain": "room_kitchen",
                               "disposition": "tools.rooms.kitchen"})
    assert check_inventory(data, {"tools/a.py"}, require_complete=True)["result"] == "PASS"


def test_coverage_mode_keeps_historical_contract_without_masking_unresolved():
    result = check_inventory(_index(), {"tools/a.py"})
    assert result["result"] == "PASS"
    assert result["pending_count"] == result["unresolved_count"] == 1
    assert result["strict"] is False
