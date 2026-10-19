"""Regression: every P4 public entrypoint/tooling path has a declared owner."""
import json

from tools.rooms.tooling_ownership import INDEX, check_tool_owners, owner_for


def test_all_p4_paths_have_a_deterministic_owner():
    index = json.loads(INDEX.read_text("utf-8"))
    audit = check_tool_owners(index)
    assert audit["result"] == "PASS", audit
    assert audit["checked"] >= 137


def test_unclassified_tooling_does_not_fall_through():
    assert owner_for("unknown/tool.py") is None
    bad = {"entries": [{"path": "unknown/tool.py", "phase": "P4",
                        "tool_owner": "whatever",
                        "disposition": "retain_legacy_public_or_tooling_path",
                        "status": "VERIFIED_PATH_BASED_OWNER_CLASSIFICATION",
                        "ownership_evidence": "FP042_P4_TOOL_ROLE_RULES_NOT_RUNTIME_FUNCTIONAL_PROOF"}]}
    assert check_tool_owners(bad)["result"] == "FAIL"


def test_shared_implementation_stays_out_of_public_adapter():
    assert owner_for("tools/furnish_apartment.py") == "cross_room_furnishing_orchestrator"
    assert owner_for("tools/mcp_server/server.py") == "mcp_server_api"
    assert owner_for("tools/sofa_builder.py") == "legacy_public_compatibility_api"
    assert owner_for("tools/rooms/shared/sofa.py") is None
