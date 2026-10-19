"""FP-042 P1/P2: path roles plus existing AST cross-room dependency gate."""
import json

from tools.rooms.architecture_ownership import INVENTORY, audit, owner_for
from tools.rooms.ownership_audit import scan


def test_every_p1_and_p2_record_is_owned():
    result = audit(json.loads(INVENTORY.read_text("utf-8")))
    assert result["result"] == "PASS", result
    assert result["checked"] >= 100


def test_unknown_path_fails_closed():
    assert owner_for("elsewhere/unknown.py", "P2") is None
    index = {"entries": [{
        "path": "elsewhere/unknown.py", "phase": "P2",
        "architecture_owner": "invented",
        "disposition": "retain_architecture_boundary_with_explicit_owner",
        "status": "VERIFIED_PATH_BASED_OWNER_CLASSIFICATION",
        "ownership_evidence": "FP042_P1_P2_PATH_ROLES_AND_AST_GATES_NO_SEMANTIC_REWRITE",
    }]}
    assert audit(index)["result"] == "FAIL"


def test_existing_cross_room_ast_gate_remains_green():
    assert scan()["result"] == "PASS"
