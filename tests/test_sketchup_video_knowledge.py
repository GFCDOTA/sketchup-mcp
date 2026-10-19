"""Valida o catálogo consultivo de vídeos SketchUp sem carregar Ruby ou alterar SKP."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "references/sketchup/knowledge/video_recipes.v1.json"
SKILL = ROOT / ".claude/skills/sketchup-video-knowledge/SKILL.md"


def test_catalog_source_and_recipe_integrity():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert data["schema_version"] == "video_sketchup_knowledge.v1"
    assert data["intent"] == "ADVISORY_ONLY"
    assert data["execution_policy"] == "NEVER_AUTHORIZE_MODEL_MUTATIONS_FROM_THIS_CATALOG"
    sources = {s["id"]: s for s in data["sources"]}
    recipes = data["recipes"]
    assert len(sources) >= 3 and len(recipes) >= 8
    assert len({r["id"] for r in recipes}) == len(recipes)
    for s in sources.values():
        assert s["url"].startswith("https://www.youtube.com/watch?v=")
        assert s["license"] == "VIDEO_REFERENCE_ONLY_NO_REPUBLICATION"
    for r in recipes:
        assert r["proof_state"] == "KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP"
        assert r["sources"] and all(p["id"] in sources and p["locator"] for p in r["sources"])
        assert r["gui_steps"] and r["preconditions"] and r["invariants"] and r["pitfalls"]
        assert r["api_candidates"] and r["implementation_route"]
        for api in r["api_candidates"]:
            assert api["status"] not in ("PROVEN_REAL_SU", "PROVEN")


def test_skill_is_consultative():
    skill = SKILL.read_text(encoding="utf-8")
    assert "references/sketchup/knowledge/video_recipes.v1.json" in skill
    assert "BLOCKED_CAPABILITY_MISSING" in skill
    assert "sem tentar executar Ruby" in skill
