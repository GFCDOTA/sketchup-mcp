"""Consulta local e estudo sintético L1. Não importa jobs nem executa Ruby/MCP.

O resultado é advisory_cabinet_plan.v1, NÃO operation_plan.v1 e nunca uma
capability executável. O FP-041 completo continua dependente de ledger/validador.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "references/sketchup/knowledge/video_recipes.v1.json"
PROOF_STATE = "KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP"
RECIPE_IDS = (
    "cabinet.reusable-components",
    "cabinet.front-gaps-and-profiles",
    "cabinet.drawer-box-and-hardware",
)


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def load_catalog(path: Path = CATALOG):
    data = json.loads(path.read_text(encoding="utf-8"))
    if (data.get("schema_version") != "video_sketchup_knowledge.v1"
            or data.get("intent") != "ADVISORY_ONLY"
            or data.get("execution_policy") != "NEVER_AUTHORIZE_MODEL_MUTATIONS_FROM_THIS_CATALOG"):
        raise ValueError("CATALOG_POLICY_INVALID")
    sources = data.get("sources", [])
    recipes = data.get("recipes", [])
    if not sources or not recipes:
        raise ValueError("CATALOG_EMPTY")
    source_ids = [s["id"] for s in sources]
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("SOURCE_ID_DUPLICATE")
    recipe_ids = [r["id"] for r in recipes]
    if len(set(recipe_ids)) != len(recipe_ids):
        raise ValueError("RECIPE_ID_DUPLICATE")
    for source in sources:
        if (not source.get("url", "").startswith("https://www.youtube.com/watch?v=")
                or not source.get("evidence") or not source.get("creator")):
            raise ValueError("SOURCE_PROVENANCE_MISSING")
    for item in recipes:
        if item.get("proof_state") != PROOF_STATE:
            raise ValueError("EVIDENCE_OVERCLAIM")
        allowed_api_states = {
            "DOCUMENTED_API", "DOCUMENTED_API_OPTIONAL_REQUIRES_PROBE",
            "DOCUMENTED_API_RECHECK_VERSION", "DOCUMENTED_API_REQUIRES_MICRO_FIXTURE",
            "DOCUMENTED_API_VALIDATE_RESULT", "ABSENT_METHOD_COMPUTE_PROFILE",
        }
        if not item.get("api_candidates") or any(
            api.get("status") not in allowed_api_states for api in item["api_candidates"]
        ):
            raise ValueError("API_EVIDENCE_OVERCLAIM_OR_UNKNOWN")
        if not item.get("sources") or any(
            s.get("id") not in source_ids or not s.get("locator", "").strip()
            for s in item["sources"]
        ):
            raise ValueError("RECIPE_PROVENANCE_MISSING")
    return data


def _recipe(data, recipe_id):
    item = next((r for r in data["recipes"] if r["id"] == recipe_id), None)
    if item is None:
        raise ValueError(f"RECIPE_UNKNOWN: {recipe_id}")
    sources = {s["id"]: s for s in data["sources"]}
    return {**item, "sources": [{**sources[s["id"]], "locator": s["locator"]}
                                for s in item["sources"]]}


def recipe(recipe_id):
    return _recipe(load_catalog(), recipe_id)


def _words(text):
    normalized = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", normalized) if len(w) > 2}


def search(query=""):
    """Recall lexical explícito; sem confiança/score ou inferência de capability."""
    terms = _words(query)
    matches = []
    for item in load_catalog()["recipes"]:
        words = _words(" ".join(str(item.get(k, "")) for k in (
            "id", "domain", "title", "goal", "when_use",
        )))
        if not terms or terms & words:
            priority = len(terms & _words(item["title"]))
            matches.append((priority, {k: item[k] for k in ("id", "domain", "title", "proof_state")}))
    return [item for _, item in sorted(matches, key=lambda pair: -pair[0])]


def _exact_keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f"INVALID_FIELDS: {label}")


def _validate_case(case):
    _exact_keys(case, (
        "schema_version", "case_id", "purpose", "dimension_grounding", "units",
        "dimensions", "drawer_count", "hardware",
    ), "case")
    if (case["schema_version"] != "advisory_cabinet_case.v1"
            or case["purpose"] != "EDITABLE_MODEL_STUDY"
            or case["dimension_grounding"] != "SYNTHETIC_TEST_ONLY_NOT_PLANTA_74"
            or case["units"] != "mm"
            or not isinstance(case["case_id"], str) or not case["case_id"].strip()):
        raise ValueError("SYNTHETIC_CASE_REQUIRED")
    dims = case["dimensions"]
    _exact_keys(dims, (
        "width", "height", "carcass_depth", "panel_thickness",
        "back_thickness", "front_thickness", "front_gap",
    ), "dimensions")
    for name, value in dims.items():
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"INVALID_DIMENSION: {name}")
    n = case["drawer_count"]
    if type(n) is not int or not 1 <= n <= 10:
        raise ValueError("INVALID_DRAWER_COUNT")
    if case["hardware"] is not None:
        raise ValueError("HARDWARE_NOT_SUPPORTED_IN_SYNTHETIC_STUDY")
    w, h, d = dims["width"], dims["height"], dims["carcass_depth"]
    t, b, g = dims["panel_thickness"], dims["back_thickness"], dims["front_gap"]
    if (w <= 3 * t or h <= 2 * t or d <= b or w <= 3 * g
            or h <= (n + 1) * g):
        raise ValueError("CONSTRAINT_INFEASIBLE")
    return dims


def _overlap(a, b):
    return all(min(a[i + 3], b[i + 3]) - max(a[i], b[i]) > 1e-7 for i in range(3))


def cabinet_plan(case):
    """BOM geométrica proposta; não dimensiona caixaria/ferragens de gaveta."""
    dims = _validate_case(case)
    data = load_catalog()
    w, h, d = dims["width"], dims["height"], dims["carcass_depth"]
    t, b = dims["panel_thickness"], dims["back_thickness"]
    f, g, n = dims["front_thickness"], dims["front_gap"], case["drawer_count"]
    parts = []

    def panel(name, parent, bounds):
        parts.append({"id": name, "parent": parent, "bbox_mm": bounds,
                      "intended_entity": "INDEPENDENT_COMPONENT_INSTANCE",
                      "definition_policy": "UNIQUE_UNTIL_REPETITION_IS_VERIFIED"})

    panel("side_left", "carcass", [0, 0, 0, t, d - b, h])
    panel("side_right", "carcass", [w - t, 0, 0, w, d - b, h])
    panel("bottom", "carcass", [t, 0, 0, w - t, d - b, t])
    panel("top", "carcass", [t, 0, h - t, w - t, d - b, h])
    panel("divider", "carcass", [w / 2 - t / 2, 0, t, w / 2 + t / 2, d - b, h - t])
    panel("back", "carcass", [0, d - b, 0, w, d, h])
    panel("door_left", "fronts", [g, -f, g, w / 2 - g / 2, 0, h - g])
    dh = (h - (n + 1) * g) / n
    for i in range(n):
        z = g + i * (dh + g)
        panel(f"drawer_front_{i + 1}", "fronts", [w / 2 + g / 2, -f, z, w - g, 0, z + dh])
    if any(any(p["bbox_mm"][i + 3] <= p["bbox_mm"][i] for i in range(3)) for p in parts):
        raise ValueError("NON_POSITIVE_PANEL")
    if any(_overlap(a["bbox_mm"], b_["bbox_mm"])
           for i, a in enumerate(parts) for b_ in parts[i + 1:]):
        raise ValueError("PANEL_COLLISION")
    return {
        "schema_version": "advisory_cabinet_plan.v1",
        "case_id": case["case_id"], "case_sha256": _digest(case),
        "catalog_sha256": _digest(data),
        "dimension_grounding": case["dimension_grounding"],
        "edit_model": "READ_ONLY", "execution_authorized": False,
        "plan_state": "BLOCKED_CAPABILITY_MISSING",
        "validation": {"L1": "PASS_SYNTHETIC_CALCULATIONS_ONLY",
                       "L2": "PENDING_SKETCHUP", "L3": "PENDING_HUMAN"},
        "recipes": [_recipe(data, rid) for rid in RECIPE_IDS],
        "strategies": [
            {"id": "M0", "choice": "VISUAL_FALLBACK_ONLY",
             "reason": "Caixas separadas não comprovam componentes editáveis nem ferragens."},
            {"id": "M1", "choice": "PROPOSED_NOT_IMPLEMENTED",
             "reason": "Spec + componentes independentes preservam intenção após regeneração."},
            {"id": "M2", "choice": "REJECTED_FOR_REGENERABLE_BASE",
             "reason": "Edição avulsa no SKP pode ser descartada pelo rebuild."},
        ],
        "repo_evidence": [
            {"path": "tools/wardrobe_builder.py", "symbol": "build_wardrobe",
             "claim": "Emite corpo, portas e puxadores como peças _p; não articula portas."},
            {"path": "tools/kitchen_layout.py", "symbol": "_kmod",
             "claim": "Usa volumes e painéis para representar módulos e frentes."},
        ],
        "reference_frame": "LOCAL_MM_X_WIDTH_Y_DEPTH_Z_HEIGHT_FRONT_NEGATIVE_Y",
        "calculations_mm": {"bay_clear_width": (w - 3 * t) / 2,
                            "bay_clear_height": h - 2 * t,
                            "carcass_internal_depth": d - b,
                            "drawer_front_height": dh,
                            "front_gap": g},
        "proposed_parts": parts,
        "proposed_hierarchy": {"cabinet": {"carcass": [p["id"] for p in parts if p["parent"] == "carcass"],
                                            "fronts": [p["id"] for p in parts if p["parent"] == "fronts"]}},
        "drawer_boxes": "NOT_DIMENSIONED_HARDWARE_REQUIRED",
        "L1_checks": {"positive_dimensions": True, "unique_semantic_ids": True,
                      "no_positive_volume_overlaps": True},
        "capability_gaps": ["PARAMETRIC_COMPONENT_MATERIALIZER_NOT_PROVEN",
                            "PARAMETRIC_DRAWER_ASSEMBLY_MISSING",
                            "DOOR_AND_DRAWER_MOTION_ENVELOPES_NOT_PROVEN"],
        "missing_info": ["Modelo e ficha técnica de dobradiças e corrediças",
                         "Folgas de instalação e curso; validar interferências e cargas"],
        "required_L2_evidence": [
            "Instâncias/definições e árvore medidas no Outliner; IDs persistentes",
            "Bboxes e transformações em mundo; nenhuma geometria solta na raiz",
            "Teste de definição compartilhada/make_unique e envelopes de abertura",
            "Snapshot pré/pós comprova que módulos externos e arquitetura não mudaram",
        ],
        "protected_elements": ["PDF/consensus", "fixtures/planta_74", "fixtures/quadrado",
                               "artifacts", "architecture", "rest_of_scene"],
        "rollback": "Nenhum modelo foi alterado. Futuro executor usa cópia descartável e transação.",
        "limitations": [
            "BOM de estudo; não é plano de corte nem modelo pronto para fabricação",
            "L1 calcula só painéis e frentes; não prova componentes, ferragens ou estética",
            "Não é operation_plan.v1; ledger, validador geral e avaliação de competência pendentes",
            "Não gera Ruby, _p, comandos MCP ou arquivos SKP",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--q", default="")
    detail = commands.add_parser("recipe")
    detail.add_argument("--id", required=True)
    study = commands.add_parser("cabinet-plan")
    study.add_argument("--case", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            result = search(args.q)
        elif args.command == "recipe":
            result = recipe(args.id)
        else:
            result = cabinet_plan(json.loads(args.case.read_text(encoding="utf-8")))
    except (ValueError, KeyError, TypeError, AttributeError, OSError, OverflowError) as exc:
        print(json.dumps({"status": "INVALID_INPUT", "execution_authorized": False,
                          "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
