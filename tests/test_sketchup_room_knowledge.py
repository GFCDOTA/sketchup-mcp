"""Validação consultiva do catálogo de ambientes SketchUp; não altera modelos."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "references/sketchup/knowledge/environment_recipes.v1.json"
SKILL = ROOT / ".claude/skills/sketchup-room-knowledge/SKILL.md"
EXPECTED = {"living", "bedroom", "kitchen", "bathroom", "laundry", "balcony",
            "home_office", "closet", "circulation"}


def test_catalog_is_read_only_and_covers_nine_categories():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert data["schema_version"] == "sketchup_room_knowledge.v1"
    assert data["mode"] == "ADVISORY_ONLY"
    assert data["execution_policy"] == "NEVER_AUTHORIZE_MODEL_MUTATIONS_FROM_THIS_CATALOG"
    assert {room["id"] for room in data["rooms"]} == EXPECTED
    assert len(data["recipes"]) >= 9
    assert {x for r in data["recipes"] for x in r["rooms"]} == EXPECTED
    assert all(r["knowledge_state"] == "KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP"
               and r["execution_authorized"] is False
               for r in data["recipes"])


def test_provenance_and_every_room_links_are_valid():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    sources = {s["id"]: s for s in data["sources"]}
    assert len(sources) == len(data["sources"])
    assert len({r["id"] for r in data["recipes"]}) == len(data["recipes"])
    assert {s["evidence"] for s in sources.values()} <= {
        "OFFICIAL_DOCUMENTATION_READ", "PUBLIC_DESCRIPTION_ONLY"
    }
    for r in data["recipes"]:
        assert r["source_refs"] and r["gui_workflow"]
        assert r["parameters_required"] and r["validation_criteria"]
        assert r["pitfalls"] and r["candidate_implementation"]
        assert set(r["rooms"]) <= EXPECTED
        for ref in r["source_refs"]:
            assert ref["id"] in sources
            assert ref["relationship"] in {
                "TRANSFER_APPLIED", "DIRECT_GENERAL_TECHNIQUE",
                "DIRECT_TOPIC_DESCRIPTION_ONLY", "CANDIDATE_API",
            }
            assert ref["locator"]


def test_skill_links_catalog_without_mutation_permission():
    skill = SKILL.read_text(encoding="utf-8")
    assert "environment_recipes.v1.json" in skill
    assert "video_recipes.v1.json" in skill
    assert "BLOCKED_NEEDS_FELIPE_GEO" in skill
    assert "KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP" in skill
