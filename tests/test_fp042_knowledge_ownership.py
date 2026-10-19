"""P5: deterministic role classification of every tracked knowledge/test document."""
import json
from pathlib import Path

from tools.rooms.knowledge_ownership import ROOT, INVENTORY, audit_p5_roles, owner_for


def test_p5_inventory_has_zero_unowned_paths():
    index = json.loads(INVENTORY.read_text(encoding="utf-8"))
    result = audit_p5_roles(index)
    assert result["result"] == "PASS", result
    assert result["reviewed_paths"] >= 390


def test_unknown_knowledge_path_is_not_silently_accepted():
    assert owner_for("random/path/new_knowledge.bin") is None
    index = {"entries": [{"path": "random/path/new_knowledge.bin",
                          "phase": "P5", "document_owner": "fake",
                          "status": "VERIFIED_PATH_BASED_OWNER_CLASSIFICATION",
                          "disposition": "retain_path_with_explicit_owner",
                          "ownership_evidence": "FP042_P5_PATH_RULES_NOT_CONTENT_SEMANTICS"}]}
    report = audit_p5_roles(index)
    assert report["result"] == "FAIL"
    assert report["unresolved_paths"] == ["random/path/new_knowledge.bin"]


def test_path_owner_does_not_imply_semantic_or_sketchup_proof():
    assert owner_for("docs/handoffs/2026-08-27_ai_pipeline_inspector_handoff.md") == "project_documentation"
    assert owner_for("HANDOFF.md") is None        # saiu da raiz em FP-043/P2: a raiz não aceita mais documento solto
    assert owner_for("docker-compose.yml") == "infrastructure_compose"
    assert owner_for(".claude/skills/example/SKILL.md") == "agent_skills_memory"
    assert audit_p5_roles({"entries": []})["proof"] == "PATH_AND_ROLE_ONLY_NOT_DOCUMENT_SEMANTICS"
