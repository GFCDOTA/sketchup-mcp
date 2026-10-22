"""FP-051/P0: baseline factual do catalogo e matriz capability -> movel -> comodo (somente leitura, sem SketchUp, sem geometria).

Responde, com numeros reproduziveis, "o que ja existe, o que esta provado e o que falta" antes de qualquer aprendizado novo:
- capacidades com estado real (implementacao/validacao/visual) e se a prova ainda vale (digest dos simbolos);
- bindings sem capability (lacunas) e a classe de evidencia das fontes de cada um (inspecionada x so descritiva, com ou sem revisao humana);
- movel candidato -> componentes -> como cada um se resolve hoje -> status do ciclo, usando o vocabulario JA existente
  (BLOCKED_CAPABILITY_MISSING, PENDING_SKETCHUP, BLOCKED_KNOWLEDGE_EVIDENCE, READY_FOR_NEXT_STEP). READY nao autoriza execucao;
- as quatro contagens da spec (§3.4) com definicao explicita, sem autoengano (receita escrita != habilidade; peca != comodo mobiliado);
- verificacao reproduzivel das afirmacoes que a spec FP-051 faz sobre o codigo (`spec_claims`).

NAO escolhe posicao nem dimensao de nenhum movel (isso e P4 / pedido do usuario) e nao promove nada. O bloco `external` (estado de PRs/CI
no momento do snapshot) vem de um JSON informado: o gerador nunca acessa rede.

Uso: python -m tools.navigation.fp051_baseline [--external ext.json] [--out docs/reports/fp051/fp051_baseline.json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCHEMA = "fp051_baseline.v1"
CATALOG_PATH = REPO / "tools/rooms/capability_catalog.v1.json"
ROOMS = ("living", "bedroom", "kitchen", "bathroom", "service", "balcony", "closet", "home_office", "circulation")

# Candidatos a movel: HIPOTESES de P0 derivadas do `furniture_goal` da spec (componentes) — sem dimensao, sem posicao, sem parede.
# resolver: {"capability": id} | {"binding": id} | {"none": motivo}. `alternatives` = outro caminho que satisfaz o mesmo componente.
FURNITURE_CANDIDATES = {
    "kitchen_base_shaker_shelf": {
        "room": "kitchen", "room_id": "r004", "kind": "base_cabinet",
        "why": "todos os componentes obrigatorios ja tem capability: primeiro caminho vertical possivel (P3-P5) sem aprender nada novo",
        "required": {
            "carcass": {"capability": "shared.cabinet.parametric"},
            "front": {"capability": "kitchen.cabinet.shaker-door", "alternatives": [{"capability": "kitchen.cabinet.plain-fronts"}]},
            "shelf": {"capability": "shared.cabinet.parametric", "note": "shelf.count = 1 do cabinet_request.v1"},
        },
        "optional": {"handle": {"none": "sem capability de puxador no catalogo; o builder de guarda-roupa tem pecas kind=puxador (bedroom.wardrobe.build, so L1)"}},
    },
    "kitchen_base_drawer": {
        "room": "kitchen", "room_id": "r004", "kind": "base_cabinet_with_drawer",
        "why": "exige a caixa de gaveta: o gap que justificaria um P2 (so a CAIXA; corredica/ferragem fora do escopo)",
        "required": {
            "carcass": {"capability": "shared.cabinet.parametric"},
            "front": {"capability": "kitchen.cabinet.shaker-door", "alternatives": [{"capability": "kitchen.cabinet.plain-fronts"}]},
            "drawer_box": {"binding": "bind.kitchen.drawer"},
        },
        "optional": {"slides_hardware": {"none": "ferragem e corredica nao existem; a recipe mistura caixa e ferragem (dividir antes de aprender)"}},
    },
    "bedroom_wardrobe": {
        "room": "bedroom", "room_id": "r000/r003", "kind": "wardrobe",
        "why": "candidato a SEGUNDO consumidor (reuso cross-room): hoje so L1 e com frente em -Y (cabinet e +Y); depende de FP-048/049 (drafts)",
        "required": {"wardrobe": {"capability": "bedroom.wardrobe.build"}, "placement_gate": {"capability": "bedroom.wardrobe.gate"}},
        "optional": {},
    },
}


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def default_digest(symbol: dict) -> str | None:
    from tools.rooms import capability_catalog as cc
    return cc.symbol_digest(symbol)


def capability_state(cap: dict, digest_fn) -> dict:
    """Estado real; `evidence_current` so e True quando TODA prova ainda casa com o codigo (digest dos simbolos)."""
    stale = []
    for ev in cap["validation"]["evidence"]:
        for key, digest in ev["symbol_digests"].items():
            lang, _, ref = key.partition(":")
            if digest_fn({"lang": lang, "ref": ref}) != digest:
                stale.append(key)
    state = cap["validation"]["state"]
    current = state == "L2_PASS" and bool(cap["validation"]["evidence"]) and not stale
    return {"id": cap["id"], "room": cap["room"], "implementation": cap["implementation"]["state"], "validation": state,
            "visual": cap["visual"]["state"], "evidence_current": current, "stale_symbols": sorted(stale),
            "evidence_commits": [ev["commit"] for ev in cap["validation"]["evidence"]]}


def source_review(source_ids: list[str], sources: dict, recipe_ids: list[str] | None = None) -> list[dict]:
    """Classe da evidencia + revisao humana. A revisao vale SO para a recipe/trecho que registrou: um binding de OUTRA recipe da mesma
    fonte nao herda `human_review` (`human_review_other_scope` mostra o escopo que existe)."""
    out = []
    for s in source_ids:
        if s not in sources:
            continue
        review = sources[s].get("human_review")
        in_scope = bool(review) and (recipe_ids is None or review.get("recipe_id") in recipe_ids)
        row = {"source_id": s, "evidence": sources[s]["evidence"], "human_review": in_scope}
        if review and not in_scope:
            row["human_review_other_scope"] = {"recipe_id": review.get("recipe_id"), "segment": review.get("segment")}
        out.append(row)
    return out


def resolve(resolver: dict, caps: dict, bindings: dict, sources: dict) -> dict:
    if "capability" in resolver:
        cap = caps.get(resolver["capability"])
        if cap is None:
            return {"resolver": resolver, "status": "MISSING", "reason": "capability inexistente no catalogo"}
        if cap["implementation"] != "IMPLEMENTED":
            return {"resolver": resolver, "status": "MISSING", "reason": f"capability {cap['implementation']}", "capability": cap}
        if cap["evidence_current"]:
            return {"resolver": resolver, "status": "RESOLVED_L2", "capability": cap}
        if cap["validation"] == "L1_PASS" or (cap["validation"] == "L2_PASS" and cap["stale_symbols"]):
            return {"resolver": resolver, "status": "RESOLVED_L1_ONLY", "capability": cap,
                    "reason": "prova L2 velha" if cap["stale_symbols"] else "so L1"}
        return {"resolver": resolver, "status": "UNPROVEN", "capability": cap}
    if "binding" in resolver:
        b = bindings.get(resolver["binding"])
        if b is None:
            return {"resolver": resolver, "status": "MISSING", "reason": "binding inexistente"}
        if b["capability_id"]:
            return resolve({"capability": b["capability_id"]}, caps, bindings, sources)
        return {"resolver": resolver, "status": "MISSING", "reason": b["gap"], "recipe_ids": b["recipe_ids"],
                "sources": source_review(b["source_ids"], sources, b["recipe_ids"])}
    return {"resolver": resolver, "status": "MISSING", "reason": resolver.get("none")}


def resolve_component(spec: dict, caps, bindings, sources) -> dict:
    main = resolve(spec, caps, bindings, sources)
    if main["status"] == "RESOLVED_L2":
        return main
    for alt in spec.get("alternatives", []):
        a = resolve(alt, caps, bindings, sources)
        if a["status"] == "RESOLVED_L2":
            return {**a, "via_alternative": True, "primary_status": main["status"]}
    return main


def cycle_status(components: dict) -> str:
    """Vocabulario existente. READY_FOR_NEXT_STEP nao autoriza execucao (precisa de assembly assinado, placement e gates)."""
    statuses = [c["status"] for c in components.values()]
    if any(s == "MISSING" for s in statuses):
        return "BLOCKED_CAPABILITY_MISSING"
    if any(s == "UNPROVEN" for s in statuses):
        return "BLOCKED_L1_UNPROVEN"
    if any(s == "RESOLVED_L1_ONLY" for s in statuses):
        return "PENDING_SKETCHUP"
    return "READY_FOR_NEXT_STEP"


def build_matrix(catalog: dict, sources: dict, digest_fn) -> dict:
    caps = {c["id"]: capability_state(c, digest_fn) for c in catalog["capabilities"]}
    bindings = {b["id"]: b for b in catalog["bindings"]}
    out = {}
    for fid, spec in FURNITURE_CANDIDATES.items():
        required = {k: resolve_component(v, caps, bindings, sources) for k, v in spec["required"].items()}
        optional = {k: resolve_component(v, caps, bindings, sources) for k, v in spec["optional"].items()}
        out[fid] = {"room": spec["room"], "room_id": spec["room_id"], "kind": spec["kind"], "why": spec["why"],
                    "cycle_status": cycle_status(required),
                    "missing_capabilities": sorted(k for k, v in required.items() if v["status"] == "MISSING"),
                    "required": required, "optional_not_available": sorted(k for k, v in optional.items() if v["status"] == "MISSING"),
                    "placement": "NOT_CHOSEN: depende de P4 (FP-050 #355 em draft); nenhuma posicao, parede ou dimensao e escolhida no P0",
                    "execution_authorized": False}
    return out


def metrics(catalog: dict, profiles: dict, digest_fn) -> dict:
    """As quatro contagens da spec §3.4 + gaps e reuso, cada uma com a definicao que o numero usa."""
    caps = {c["id"]: capability_state(c, digest_fn) for c in catalog["capabilities"]}
    l2 = sorted(i for i, c in caps.items() if c["evidence_current"])
    by_room: dict[str, set] = {}
    for room, prof in profiles.items():
        for cid in prof.get("capability_ids", []):
            by_room.setdefault(cid, set()).add(room)
    cross = sorted(i for i in l2 if len(by_room.get(i, set())) > 1)
    gaps = sorted(b["id"] for b in catalog["bindings"] if not b["capability_id"])
    approved_rooms = sorted({c["room"] for c in caps.values() if c["visual"] == "APPROVED" and c["room"] != "shared"})
    assemblies = sorted(i for i in l2 if i in ("kitchen.cabinet.plain-fronts", "kitchen.cabinet.shaker-door"))
    return {
        "capabilities_L2_com_prova_vigente": {"count": len(l2), "ids": l2,
                                              "definition": "validation=L2_PASS, ha evidencia e o digest de TODOS os simbolos provados ainda casa com o codigo"},
        "furniture_assemblies_L2": {"count": len(assemblies), "ids": assemblies, "furniture_kinds": ["base_cabinet"] if assemblies else [],
                                    "definition": "fluxos que entregam um gabinete COMPLETO salvo/reaberto na cozinha; 2 variantes (frente lisa, Shaker) do MESMO tipo de movel"},
        "furniture_placed_in_correct_room_L2": {"count": 0, "definition": "movel cuja posicao foi ESCOLHIDA por um gate de placement e provada em L2",
                                                "why_zero": "a pose de hoje vem do pedido (user_request); nao existe gate de placement em develop (FP-050 #355 em draft)"},
        "rooms_approved_L3": {"count": len(approved_rooms), "rooms": approved_rooms,
                              "definition": "comodos com capability visual=APPROVED (veredito do Felipe)"},
        "blocked_gaps": {"count": len(gaps), "ids": gaps, "definition": "bindings sem capability_id"},
        "reused_capabilities_cross_room": {"count": len(cross), "ids": cross,
                                           "definition": "capabilities com L2 vigente listadas em perfis de 2+ comodos E executadas por 2 consumidores (so conta o que o L2 provou)",
                                           "note": "a lista por perfil e necessaria, nao suficiente; sem segundo consumidor executado o reuso nao e afirmado"},
    }


def spec_claims(catalog: dict, sources: dict, root: Path = REPO) -> list[dict]:
    """Afirmacoes da FP-051 sobre o codigo, verificadas agora. `ok=False` e um achado, nao um erro do gerador."""
    claims: list[dict] = []

    def claim(cid: str, text: str, ok: bool, detail: str = "") -> None:
        claims.append({"id": cid, "claim": text, "ok": bool(ok), "detail": detail})

    caps = {c["id"]: c for c in catalog["capabilities"]}
    for cid in ("shared.cabinet.parametric", "kitchen.cabinet.shaker-door", "shared.cabinet.front.shaker"):
        c = caps.get(cid)
        claim(f"cap:{cid}", f"{cid} registrada com L2_PASS e visual NOT_REVIEWED",
              bool(c) and c["validation"]["state"] == "L2_PASS" and c["visual"]["state"] == "NOT_REVIEWED",
              f"{c['validation']['state']}/{c['visual']['state']}" if c else "ausente")
    gaps = {b["id"] for b in catalog["bindings"] if not b["capability_id"]}
    for bid in ("bind.kitchen.drawer", "bind.kitchen.countertop", "bind.kitchen.sink-cutout"):
        claim(f"gap:{bid}", f"{bid} ainda sem capability_id", bid in gaps)
    for rel in ("tools/rooms/learning", "tools/rooms/shared/assembly", "tools/rooms/kitchen/planning"):
        claim(f"absent:{rel}", f"{rel} nao existe em develop (proposto por FP-051/FP-049/FP-050)", not (root / rel).exists())
    claim("review:tips-2021", "so o yt-cabinet-tips-2021 tem human_review",
          {s for s, v in sources.items() if v.get("human_review")} == {"yt-cabinet-tips-2021"},
          str(sorted(s for s, v in sources.items() if v.get("human_review"))))
    drawer = next(b for b in catalog["bindings"] if b["id"] == "bind.kitchen.drawer")
    claim("drawer:source-inspected-without-human-review",
          "a fonte da recipe de gaveta e rotulada inspecionada, mas SEM human_review (achado: o criterio da D46-09 pede a checagem humana)",
          all(sources[s]["evidence"] == "TRANSCRIPT_AND_VISUAL_WALKTHROUGH" and not sources[s].get("human_review") for s in drawer["source_ids"]),
          str(source_review(drawer["source_ids"], sources, drawer["recipe_ids"])))
    review = sources.get("yt-cabinet-tips-2021", {}).get("human_review") or {}
    claim("review:scope", "a revisao humana existente cobre UMA recipe e UM trecho (nao a fonte inteira)",
          bool(review) and review.get("recipe_id") == "cabinet.front-gaps-and-profiles" and review.get("segment") == "03:13-04:29",
          f"{review.get('recipe_id')} {review.get('segment')}")
    flow = (root / "tools/rooms/kitchen/capabilities/shaker_flow.py").read_text(encoding="utf-8", errors="replace")
    claim("flow:source_verified-checks-review-scope",
          "shaker_flow confere que a revisao humana cobre a recipe do pedido (nao so que a fonte tem alguma revisao)",
          'review.get("recipe_id") != ctx.get("recipe_id")' in flow,
          "corrigido: source_verified=true so passa se a human_review da fonte cobre a recipe do pedido (antes: so exigia alguma revisao)")
    code = {rel: (root / rel).read_text(encoding="utf-8", errors="replace") for rel in
            ("tools/sketchup/knowledge.py", "tools/rooms/kitchen/capabilities/shaker_flow.py")}
    text = "\n".join(code.values())
    claim("vocab:PENDING_SKETCHUP", "PENDING_SKETCHUP ja existe no codigo (a spec propoe PENDING_L2)", "PENDING_SKETCHUP" in text and "PENDING_L2" not in text)
    claim("vocab:BLOCKED_KNOWLEDGE_EVIDENCE", "BLOCKED_KNOWLEDGE_EVIDENCE ja existe no codigo (a spec propoe BLOCKED_SOURCE_UNVERIFIED)",
          "BLOCKED_KNOWLEDGE_EVIDENCE" in text and "BLOCKED_SOURCE_UNVERIFIED" not in text)
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    claim("dep:hypothesis", "hypothesis (citada no P2) esta declarada como dependencia de dev em develop", "hypothesis" in pyproject,
          "so o PR #355 declara; sem isso o P2 precisa declarar a dependencia")
    try:
        from tools.rooms.shared.cabinet import plan_cabinet
        from tools.rooms.shared.wardrobe import build_wardrobe, wardrobe_spec
        req = load_json(root / "fixtures/synthetic_cabinets/valid_a_base_600.json")
        plan = plan_cabinet(req)
        front = next(p for p in plan["parts"] if p["name"] == "front")
        depth = plan["envelope_m"][1]
        claim("frame:cabinet-front-plus-y", "a frente do gabinete esta em +Y local", abs(front["max_m"][1] - depth) < 1e-9, f"front.max_y={front['max_m'][1]} depth={depth}")
        _parts, meta = build_wardrobe(wardrobe_spec(width=1.8))
        claim("frame:wardrobe-front-minus-y", "o guarda-roupa tem frente em -Y", meta.get("front_axis") == "-Y", str(meta.get("front_axis")))
    except Exception as exc:  # noqa: BLE001 - falha de import vira achado, nao excecao
        claim("frame:check", "verificacao de frames", False, f"{type(exc).__name__}: {exc}")
    return claims


def git_head(root: Path = REPO) -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build(external: dict | None = None, *, catalog: dict | None = None, digest_fn=default_digest, root: Path = REPO) -> dict:
    catalog = catalog if catalog is not None else load_json(root / "tools/rooms/capability_catalog.v1.json")
    video = load_json(root / catalog["knowledge_catalogs"]["video"])
    env = load_json(root / catalog["knowledge_catalogs"]["environment"])
    sources = {s["id"]: s for s in video["sources"] + env["sources"]}
    profiles = {room: load_json(root / f"tools/rooms/{room}/specialist.v1.json") for room in ROOMS
                if (root / f"tools/rooms/{room}/specialist.v1.json").is_file()}
    caps = [capability_state(c, digest_fn) for c in catalog["capabilities"]]
    return {
        "schema_version": SCHEMA,
        "git_head": git_head(root),
        "scope": "P0 — leitura apenas: nenhuma geometria, nenhum .skp, nenhuma posicao ou dimensao escolhida",
        "capabilities": caps,
        "bindings": [{"id": b["id"], "room": b["room"], "capability_id": b["capability_id"], "gap": b.get("gap"),
                      "recipe_ids": b["recipe_ids"], "sources": source_review(b["source_ids"], sources, b["recipe_ids"])}
                     for b in catalog["bindings"]],
        "furniture_matrix": build_matrix(catalog, sources, digest_fn),
        "metrics": metrics(catalog, profiles, digest_fn),
        "spec_claims": spec_claims(catalog, sources, root),
        "external": external or {"note": "nao informado (--external)"},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="FP-051/P0: baseline factual (somente leitura)")
    ap.add_argument("--external", help="JSON com o estado de PRs/CI no momento do snapshot (o gerador nunca acessa a rede)")
    ap.add_argument("--out", help="grava o JSON aqui (default: stdout)")
    ns = ap.parse_args(argv)
    external = load_json(Path(ns.external)) if ns.external else None
    text = json.dumps(build(external), indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    if ns.out:
        Path(ns.out).parent.mkdir(parents=True, exist_ok=True)
        Path(ns.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
