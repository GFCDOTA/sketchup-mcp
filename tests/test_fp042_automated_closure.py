"""P0-P6 automated completion means strict tracked inventory, never SketchUp L2."""
import json
import subprocess
from tools.rooms.inventory_gate import ROOT, INVENTORY, CONTROL_PATHS, check_inventory
from tools.rooms.p3_ownership import audit_p3


def test_strict_inventory_has_no_missing_or_pending_files():
    index = json.loads(INVENTORY.read_text("utf-8"))
    paths = {v.decode("utf-8") for v in subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT).split(b"\0") if v}
    report = check_inventory(index, paths, require_complete=True)
    assert report["result"] == "PASS", report
    assert report["registered_count"] == len(paths - CONTROL_PATHS)
    assert report["unresolved_count"] == report["pending_count"] == 0
    assert audit_p3(index)["result"] == "PASS"


def test_provenance_support_has_previous_green_ci_without_l2_claim():
    index = json.loads(INVENTORY.read_text("utf-8"))
    support = [e for e in index["entries"] if e["phase"] == "P6"
               and e["status"] == "VERIFIED_PROVENANCE_SUPPORT_IN_CI"]
    assert len(support) == 8
    assert all(e["ownership_evidence"].startswith("GITHUB_ACTIONS_SUCCESS_") for e in support)
    assert all(e["proof_scope"] == "GIT_BYTES_AND_PATH_ONLY_NOT_SKETCHUP_L2" for e in support)
