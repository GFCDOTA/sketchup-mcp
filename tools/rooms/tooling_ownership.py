"""FP-042 P4: classification of public entrypoints and cross-room tooling paths.

Path/role ownership only. A passing result is not functional proof and does
not authorize SketchUp launches. Existing CLI, MCP and deterministic gates do.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "docs/specs/fp042_inventory.v1.json"
LEGACY_FACADES = frozenset(["sofa_builder.py","bed_builder.py","wardrobe_builder.py","nightstand_builder.py","furniture_anatomy_spec.py","style_spec.py","service_layout.py"])
OWNER_DIRS = (
    ("tools/interior_studio/", "interior_studio_runtime"),
    ("tools/mcp_server/", "mcp_server_api"),
    ("tools/claude_bridge/", "agent_bridge"),
    ("tools/pdf_knowledge/", "pdf_knowledge_runtime"),
    ("tools/quadrado/", "synthetic_fixture_tooling"),
    ("tools/prompts/", "agent_prompt_assets"),
    ("tools/oracle/prompts/", "agent_prompt_assets"),
    ("tools/knowledge/pdf/", "pdf_knowledge_runtime"),
    ("tools/rendering/quadrado/", "synthetic_fixture_tooling"),
)


def owner_for(path: str) -> str | None:
    if path.startswith("scripts/"):
        return "repository_automation_scripts"
    if path == "tools/furnish_apartment.py":
        return "cross_room_furnishing_orchestrator"
    for prefix, role in OWNER_DIRS:
        if path.startswith(prefix):
            return role
    if path == "tools/Dockerfile.dashboard":
        return "dashboard_container_runtime"
    if path.startswith("tools/") and path.removeprefix("tools/") in LEGACY_FACADES:
        return "legacy_public_compatibility_api"
    if path == "tests/test_fp042_tooling_ownership.py":
        return "regression_test_suite"
    if path == "tools/rooms/tooling_ownership.py":
        return "cross_room_pipeline_tooling"
    if path.startswith("tools/rooms/"):
        return None
    if path.startswith("tools/") and Path(path).suffix.lower() in {
        ".py", ".rb", ".ps1", ".json", ".yml", ".yaml", ".sh", ".md"
    }:
        return "cross_room_pipeline_tooling"
    return None


def check_tool_owners(index: dict) -> dict:
    candidates = [rec for rec in index.get("entries", []) if rec.get("phase") == "P4"]
    unresolved = sorted(rec["path"] for rec in candidates if
                        owner_for(rec["path"]) is None
                        or rec.get("tool_owner") != owner_for(rec["path"])
                        or rec.get("disposition") != "retain_legacy_public_or_tooling_path"
                        or rec.get("status") != "VERIFIED_PATH_BASED_OWNER_CLASSIFICATION"
                        or rec.get("ownership_evidence") !=
                        "FP042_P4_TOOL_ROLE_RULES_NOT_RUNTIME_FUNCTIONAL_PROOF")
    return {"result": "FAIL" if unresolved else "PASS",
            "checked": len(candidates), "unresolved": unresolved,
            "proof": "TOOLING_PATH_OWNER_NOT_FUNCTIONAL_PROOF"}


def main() -> int:
    result = check_tool_owners(json.loads(INDEX.read_text(encoding="utf-8")))
    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
