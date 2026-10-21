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


def test_unimplemented_binding_declares_its_gap():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    missing = [b for b in catalog["bindings"] if not b["capability_id"]]
    assert missing
    assert [b["id"] for b in missing if not (b.get("gap") or "").strip()] == []
