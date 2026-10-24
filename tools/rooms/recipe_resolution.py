"""recipe_resolution.py — receita -> operacao -> implementacao -> prova, por comodo (FP-055 P5, #416). Somente leitura.

O especialista ja sabe dizer, por comodo, quais receitas usa (`recipe_ids`); a geracao inteligente so as marcava SELECTED. Este
modulo resolve cada receita ate o fim da cadeia, SEM executar nada e SEM tocar simbolo provado (R-18):

    receita --(binding do catalogo)--> capacidade --(tools/symbols)--> operacao e implementacao --(estados)--> prova

e mantem TRES conceitos separados, cada um lido de um lugar diferente (nunca misturados):
  functional_rules       regras funcionais: `constraints` do perfil do especialista (e a politica do solver, fora daqui);
  constructive_recipes   receitas construtivas: `recipe_ids` -> bindings -> capacidades (conhecimento, `video_recipes`/`environment_recipes`);
  aesthetic_references   referencias esteticas: `reference_target.v1` aprovados em `artifacts/reference_lab/targets/` (FP-052).
Estado de cada receita (nunca promove):
  RESOLVED_PROVEN       capacidade IMPLEMENTED com validacao L1_PASS/L2_PASS;
  RESOLVED_UNPROVEN     capacidade existe mas validacao UNTESTED/PLANNED;
  BLOCKED_CAPABILITY_MISSING  binding sem capacidade (lacuna declarada no catalogo): recusa com o motivo, nao inventa;
  UNBOUND               receita do especialista que nenhum binding do comodo cita.
`shared_techniques` mostra quais capacidades `shared.*` tem consumidores em >= 2 componentes (criterio da P5): hoje o
numero e honesto, pode ser 0.

Uso:  python -m tools.rooms.recipe_resolution [comodo ...]
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from tools.rooms import capability_catalog as cc

ROOT = Path(__file__).resolve().parents[2]
PROVEN = ("L1_PASS", "L2_PASS")


def _targets(room_ids: tuple[str, ...], root: Path) -> list[dict]:
    """Referencias esteticas (`reference_target.v1`) dos ids de comodo do consensus; o estado e o do alvo (DRAFT_BLOCKED nao autoriza nada)."""
    base = root / "artifacts/reference_lab/targets"
    out = []
    for p in sorted(base.glob("*/*/*.target.v1.json")) if base.exists() else []:
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("room_id") in room_ids:
            out.append({"path": str(p.relative_to(root)).replace("\\", "/"), "target_id": d.get("target_id"), "state": d.get("state"),
                        "approval": (d.get("approval") or {}).get("state")})
    return out


def resolve_room(room: str, root: Path = ROOT, room_ids: tuple[str, ...] = ()) -> dict:
    """`room_ids`: ids do consensus que sao deste tipo de comodo (para ligar os alvos esteticos); vazio = sem referencias."""
    catalog = cc.load_catalog(root / "tools/rooms/capability_catalog.v1.json")
    profile = json.loads((root / f"tools/rooms/{room}/specialist.v1.json").read_text(encoding="utf-8"))
    caps = {c["id"]: c for c in catalog["capabilities"]}
    bindings = [b for b in catalog["bindings"] if b["room"] == room]
    by_recipe: dict[str, list[dict]] = defaultdict(list)
    for b in bindings:
        for r in b["recipe_ids"]:
            by_recipe[r].append(b)
    recipes = []
    for rid in profile["recipe_ids"]:
        bs = by_recipe.get(rid, [])
        if not bs:
            recipes.append({"recipe_id": rid, "state": "UNBOUND", "bindings": [], "capability": None,
                            "reason": "nenhum binding do comodo cita a receita"})
            continue
        for b in bs:
            cap = caps.get(b["capability_id"]) if b["capability_id"] else None
            if cap is None:
                recipes.append({"recipe_id": rid, "state": "BLOCKED_CAPABILITY_MISSING", "bindings": [b["id"]], "capability": None,
                                "reason": b.get("gap") or "capacidade ausente"})
                continue
            proven = cap["implementation"]["state"] == "IMPLEMENTED" and cap["validation"]["state"] in PROVEN
            recipes.append({"recipe_id": rid, "state": "RESOLVED_PROVEN" if proven else "RESOLVED_UNPROVEN", "bindings": [b["id"]],
                            "capability": {"id": cap["id"], "version": cap["version"], "implementation": cap["implementation"]["state"],
                                           "validation": cap["validation"]["state"], "visual": cap["visual"]["state"]},
                            "operation": list(cap["tools"]),
                            "implementation_symbols": [f"{s['lang']}:{s['ref']}" for s in cap["implementation"]["symbols"]]})
    return {"room": room, "functional_rules": list(profile["constraints"]), "constructive_recipes": recipes,
            "aesthetic_references": _targets(room_ids, root), "execution_authorized": False}


def shared_techniques(root: Path = ROOT) -> dict[str, list[str]]:
    """{capacidade `shared.*`: comodos cujos bindings a usam}; so entra quem tem >= 2 componentes consumidores."""
    catalog = cc.load_catalog(root / "tools/rooms/capability_catalog.v1.json")
    caps = {c["id"]: c for c in catalog["capabilities"]}
    users: dict[str, set[str]] = defaultdict(set)
    for b in catalog["bindings"]:
        cap = caps.get(b["capability_id"]) if b["capability_id"] else None
        if cap is None:
            continue
        users[cap["id"]].add(b["room"])
        for s in cap["implementation"]["symbols"]:
            if s["lang"] == "python" and s["ref"].startswith("tools.rooms.shared."):
                users[s["ref"].rsplit(".", 1)[0]].add(b["room"])
    return {k: sorted(v) for k, v in sorted(users.items()) if k.startswith(("shared.", "tools.rooms.shared.")) and len(v) >= 2}


def main(argv: list[str]) -> int:
    rooms = argv or list(cc.ROOMS)
    for room in rooms:
        res = resolve_room(room)
        print(f"== {room}: {len(res['constructive_recipes'])} receita(s)")
        for r in res["constructive_recipes"]:
            cap = r["capability"]["id"] if r["capability"] else "-"
            print(f"   {r['state']:28} {r['recipe_id']}  -> {cap}")
    print("tecnicas compartilhadas com >= 2 componentes:", shared_techniques() or "NENHUMA")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
