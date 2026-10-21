"""FP-045 / F4 (R-03, R-04): guarda de proveniencia dos catalogos de conhecimento.

Nao altera dado nem permite execucao: so impede que o vocabulario de evidencia mude em silencio,
que um locator de video passe da duracao da fonte e que uma capability implementada fique
justificada apenas por fonte "so descricao".
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOW = ROOT / "references/sketchup/knowledge"
CATALOG = ROOT / "tools/rooms/capability_catalog.v1.json"

# Vocabulario existente em develop@2af60b0. Valor novo exige decisao consciente (editar aqui + spec FP-045 2.6.1).
EVIDENCE_INSPECTED = {"OFFICIAL_DOCUMENTATION_READ", "TRANSCRIPT_AND_VISUAL_WALKTHROUGH"}
EVIDENCE_DESCRIPTION_ONLY = {"PUBLIC_DESCRIPTION_ONLY", "TRANSCRIPT_AND_DESCRIPTION_ONLY"}
TIMESTAMP = re.compile(r"\d+:\d{2}(?::\d{2})?")


def _load(name: str) -> dict:
    return json.loads((KNOW / name).read_text(encoding="utf-8"))


def _sources() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name in ("video_recipes.v1.json", "environment_recipes.v1.json"):
        for s in _load(name)["sources"]:
            assert s["id"] not in out, f"id de fonte duplicado entre catalogos: {s['id']}"
            out[s["id"]] = s
    return out


def _seconds(stamp: str) -> int:
    parts = [int(x) for x in stamp.split(":")]
    return parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1]


def test_evidence_vocabulary_is_closed():
    seen = {s["evidence"] for s in _sources().values()}
    assert seen <= EVIDENCE_INSPECTED | EVIDENCE_DESCRIPTION_ONLY, seen - (EVIDENCE_INSPECTED | EVIDENCE_DESCRIPTION_ONLY)


def test_video_locators_never_exceed_source_duration():
    data = _load("video_recipes.v1.json")
    duration = {s["id"]: _seconds(s["duration"]) for s in data["sources"]}
    for recipe in data["recipes"]:
        for ref in recipe["sources"]:
            for stamp in TIMESTAMP.findall(ref["locator"]):
                assert _seconds(stamp) <= duration[ref["id"]], (recipe["id"], ref["id"], stamp)


def test_every_recipe_source_ref_resolves():
    sources = _sources()
    video, env = _load("video_recipes.v1.json"), _load("environment_recipes.v1.json")
    refs = [(r["id"], ref["id"]) for r in video["recipes"] for ref in r["sources"]]
    refs += [(r["id"], ref["id"]) for r in env["recipes"] for ref in r["source_refs"]]
    assert refs
    assert [x for x in refs if x[1] not in sources] == []


def test_implemented_binding_is_not_backed_only_by_description_only_sources():
    sources = _sources()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    implemented = [b for b in catalog["bindings"] if b["capability_id"]]
    assert implemented
    for binding in implemented:
        evidence = {sources[sid]["evidence"] for sid in binding["source_ids"]}
        assert evidence & EVIDENCE_INSPECTED, f"{binding['id']}: so fontes descritivas ({sorted(evidence)})"


def test_shaker_binding_is_backed_by_an_inspected_source_with_a_recorded_human_review():
    """FP-046/D46-09 (opcao C): a fonte inspecionada que sustenta o binding tem revisao humana registrada (quem, quando, trecho)."""
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    binding = next(b for b in catalog["bindings"] if b["id"] == "bind.kitchen.shaker")
    assert binding["capability_id"] == "kitchen.cabinet.shaker-door" and not binding.get("gap")
    sources = _sources()
    reviewed = [sid for sid in binding["source_ids"] if sources[sid].get("human_review")]
    assert reviewed == ["yt-cabinet-tips-2021"]
    review = sources["yt-cabinet-tips-2021"]["human_review"]
    assert review["reviewer"] == "Felipe" and review["date"] == "2026-10-21" and review["segment"] == "03:13-04:29"
    assert review["recipe_id"] in binding["recipe_ids"] and len(review["confirmed"]) == 4
    assert sources["yt-cabinet-tips-2021"]["evidence"] in EVIDENCE_INSPECTED
    assert sources["yt-cabinet-styles-2024"]["evidence"] in EVIDENCE_DESCRIPTION_ONLY       # a fonte descritiva continua descritiva


def test_human_review_exists_only_where_a_person_recorded_it():
    reviewed = {sid for sid, s in _sources().items() if s.get("human_review")}
    assert reviewed == {"yt-cabinet-tips-2021"}


def test_unimplemented_binding_declares_its_gap():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    missing = [b for b in catalog["bindings"] if not b["capability_id"]]
    assert missing
    assert [b["id"] for b in missing if not (b.get("gap") or "").strip()] == []


def _recipe_sources() -> dict[str, set[str]]:
    video, env = _load("video_recipes.v1.json"), _load("environment_recipes.v1.json")
    out = {r["id"]: {x["id"] for x in r["sources"]} for r in video["recipes"]}
    out.update({r["id"]: {x["id"] for x in r["source_refs"]} for r in env["recipes"]})
    return out


def test_binding_sources_are_exactly_the_sources_of_its_recipes():
    """FP-046/P0: o binding nao cita fonte que a recipe nao referencia, nem omite uma que ela referencia."""
    recipes = _recipe_sources()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    bad = {}
    for b in catalog["bindings"]:
        expected = set().union(*(recipes[rid] for rid in b["recipe_ids"]))
        if set(b["source_ids"]) != expected:
            bad[b["id"]] = {"declared": sorted(b["source_ids"]), "from_recipes": sorted(expected)}
    assert bad == {}


def test_catalog_verify_rejects_binding_source_that_recipe_does_not_cite():
    import copy

    from tools.rooms import capability_catalog as cc

    catalog = cc.load_catalog(CATALOG)
    assert cc.verify(catalog=catalog)["result"] == "PASS"
    forged = copy.deepcopy(catalog)
    shaker = next(b for b in forged["bindings"] if b["id"] == "bind.kitchen.shaker")
    shaker["source_ids"] = ["yt-cabinet-tips-2021"]   # fonte que a recipe Shaker NAO cita
    report = cc.verify(catalog=forged)
    assert report["result"] == "FAIL"
    assert "BINDING_SOURCE_MISMATCH" in report["errors"]
