"""FP-042/P5: cross-catalog referential integrity and advisory-only policy."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = ROOT / "references/sketchup/knowledge"


def _load(name):
    return json.loads((CATALOG_ROOT / name).read_text(encoding="utf-8"))


def test_environment_refs_exist_in_video_catalog():
    env = _load("environment_recipes.v1.json")
    videos = _load("video_recipes.v1.json")
    source_ids = {s["id"] for s in env["sources"]}
    video_recipe_ids = {r["id"] for r in videos["recipes"]}
    assert len(video_recipe_ids) == len(videos["recipes"])
    assert len({r["id"] for r in env["recipes"]}) == len(env["recipes"])
    for recipe in env["recipes"]:
        assert set(recipe.get("prior_catalog_recipe_ids", [])) <= video_recipe_ids
        assert {ref["id"] for ref in recipe["source_refs"]} <= source_ids


def test_catalogs_are_consultative_not_sketchup_execution_authority():
    env = _load("environment_recipes.v1.json")
    videos = _load("video_recipes.v1.json")
    assert env["execution_policy"] == videos["execution_policy"] == (
        "NEVER_AUTHORIZE_MODEL_MUTATIONS_FROM_THIS_CATALOG")
    assert all(r.get("execution_authorized") is False for r in env["recipes"])
    assert all(r["knowledge_state"] == "KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP"
               for r in env["recipes"])
