"""FP-042/P5: canonical ownership of documentation and test-suite paths.

This is a *path and role* proof, NOT a semantic review of document contents,
Git bytes or a test of SketchUp behavior. Rejects unknown paths fail-closed.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs/specs/fp042_inventory.v1.json"
EXPLICIT = {
    ".impeccable/config.json": "agent_configuration",
    "CLAUDE.md": "agent_project_instructions",
    "README.md": "project_readme",
    "docker-compose.rag.yml": "infrastructure_compose",
    "docker-compose.yml": "infrastructure_compose",
}


def owner_for(path: str) -> str | None:
    if path in EXPLICIT:
        return EXPLICIT[path]
    if path.startswith(".ai_bridge/"):
        return "agent_handoff"
    if path.startswith(".claude/"):
        return "agent_skills_memory"
    if path.startswith("docs/") or (path.startswith("projects/") and path.endswith(".md")):
        return "project_documentation"
    if path.startswith("tests/"):
        return "regression_test_suite"
    if path.startswith("interior/") and path.endswith(".md"):
        return "interior_design_contracts"
    if path == "tools/rooms/knowledge_ownership.py":
        return "tooling_documentation"
    if path.startswith("tools/") and path.endswith(".md"):
        return "tooling_documentation"
    if path.startswith(("tools/prompts/", "tools/oracle/prompts/")):
        return "agent_prompts"
    return None


def audit_p5_roles(inventory: dict) -> dict:
    records = [entry for entry in inventory.get("entries", []) if entry.get("phase") == "P5"]
    bad = sorted(
        e["path"] for e in records
        if owner_for(e["path"]) is None
        or e.get("document_owner") != owner_for(e["path"])
        or e.get("disposition") != "retain_path_with_explicit_owner"
        or e.get("status") != "VERIFIED_PATH_BASED_OWNER_CLASSIFICATION"
        or e.get("ownership_evidence") != "FP042_P5_PATH_RULES_NOT_CONTENT_SEMANTICS"
    )
    return {"result": "PASS" if not bad else "FAIL",
            "reviewed_paths": len(records),
            "unresolved_paths": bad,
            "proof": "PATH_AND_ROLE_ONLY_NOT_DOCUMENT_SEMANTICS"}


def main() -> int:
    result = audit_p5_roles(json.loads(INVENTORY.read_text(encoding="utf-8")))
    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
