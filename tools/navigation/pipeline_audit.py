"""pipeline_audit.py — FP-055 P0: o que EXISTE × o que a geracao do apartamento EXECUTA (rastreio dinamico, nao leitura).

    PT_TO_M=0.0259 python -m tools.navigation.pipeline_audit docs/reports/fp055/p0

Roda o caminho de geracao compartilhado pelos dois entrypoints do apartamento inteiro (`furnish_apartment.main` e
`su_furnish` -> `tools.sketchup.jobs.furnish`): `collect_boxes(consensus)`, com `sys.setprofile` registrando cada funcao do repo
chamada. Cruza com o catalogo de capacidades, os especialistas, as receitas de conhecimento e os modulos do solver/validacao.

Estados por capacidade (FP-055 §6.7), nesta ordem, cada um exige o anterior:
  AVAILABLE           os simbolos declarados existem no codigo;
  INVOKED             pelo menos um simbolo foi CHAMADO durante a geracao;
  CONSUMED            a saida chamada alimenta o que vai para o SketchUp (caixas entregues ao placer). Decidido por regra
                      explicita (`_CONSUMED_RULES`), nunca por "foi importado";
  REFLECTED_IN_MODEL  so com inspecao do .skp construido — este audit NAO afirma (fica `NOT_EVALUATED`);
  VALIDATED           idem (gates sobre o modelo construido) — `NOT_EVALUATED`.
Deterministico: sem data/relogio na saida; listas ordenadas. Rodar em processo NOVO: num processo que ja importou/cacheou o
caminho, imports (`<module>`) e funcoes memoizadas nao aparecem de novo.
"""
from __future__ import annotations

import contextlib
import importlib
import io
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Saidas que o orquestrador ENTREGA ao placer Ruby: as caixas devolvidas pelos brains de comodo. Simbolo chamado cuja saida
# so e lida para log/descartada nao entra aqui (ex.: bathroom._functional_interfaces vai em `out` e collect_boxes ignora).
_CONSUMED_RULES = {
    "tools.rooms.kitchen.layout.build_boxes": "caixas -> LAYOUT_BOXES -> place_layout_skp.rb",
    "tools.rooms.bathroom.layout.build_boxes": "caixas -> LAYOUT_BOXES -> place_layout_skp.rb",
    "tools.rooms.living.furnishing.living_room_boxes": "caixas -> LAYOUT_BOXES -> place_layout_skp.rb",
    "tools.rooms.bedroom.furnishing.bedroom_designer_boxes": "caixas -> LAYOUT_BOXES -> place_layout_skp.rb",
    "tools.rooms.service.layout.build_boxes": "caixas -> LAYOUT_BOXES -> place_layout_skp.rb",
    "tools.rooms.kitchen.validation.require_kitchen_anchor": "aborta o build se a pia migrar (gate bloqueante)",
    "tools.rooms.bathroom.validation.unexpected_wet_room_kinds": "so LOGA (nao bloqueia)",
    "tools.rooms.kitchen.anchor_rules.validate": "via require_kitchen_anchor: aborta o build se a pia migrar",
    # chamados DENTRO de um brain consumido; as pecas que devolvem sao parte das caixas do brain (consumo transitivo)
    "tools.rooms.shared.bed.build_bed": "transitivo: pecas da cama dentro das caixas do brain do quarto",
    "tools.rooms.shared.wardrobe.build_wardrobe": "transitivo: pecas do guarda-roupa dentro das caixas do brain do quarto",
    "tools.rooms.living.sofa_class.derive_living_sofa": "transitivo: dimensoes do sofa usadas pelo brain da sala",
}
# Modulos que a FP-054/F1 entregou e que a FP-055 quer no fluxo — rastreados por arquivo
_WATCHED_MODULES = {
    "specialists.plan (perfil+allowlist+binding)": "tools/rooms/specialists.py",
    "specialist fragments": "tools/rooms/specialist_fragments.py",
    "capability catalog": "tools/rooms/capability_catalog.py",
    "knowledge loader (tools/sketchup/knowledge.py)": "tools/sketchup/knowledge.py",
    "F1C kitchen functional_interfaces": "tools/rooms/kitchen/functional_interfaces.py",
    "F1B/F1C functional_clearance": "tools/validation/functional_clearance.py",
    "core.functional_constraints (provenance A-E)": "core/functional_constraints.py",
    "F2 solver: problem": "tools/rooms/shared/spatial_solver/problem.py",
    "F2 solver: engine": "tools/rooms/shared/spatial_solver/engine.py",
    "F2 solver: candidates": "tools/rooms/shared/spatial_solver/candidates.py",
    "F2 solver: solver": "tools/rooms/shared/spatial_solver/solver.py",
    "F2 solver: ranking": "tools/rooms/shared/spatial_solver/ranking.py",
    "F2 solver: proposal": "tools/rooms/shared/spatial_solver/proposal.py",
    "furniture_overlap_gate": "tools/validation/furniture_overlap_gate.py",
    "room_collisions (parede/giro de porta)": "tools/validation/room_collisions.py",
    "circulation_gate": "tools/validation/circulation_gate.py",
    "shared cabinet (parametrico/Shaker)": "tools/rooms/shared/cabinet/",
    "core.spatial_semantics": "core/spatial_semantics.py",
    "layout_decisions (decisoes aprovadas)": "tools/rooms/bedroom/layout_decisions.py",
}


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:  # noqa: BLE001 — checkout sem git: registrar, nao inventar
        return "UNKNOWN"


def trace_generation() -> dict:
    """Executa collect_boxes sob profiler. Devolve arquivos e (arquivo, funcao) chamados, mais o resumo por comodo."""
    calls: Counter = Counter()
    root = str(ROOT)

    def prof(frame, event, _arg):
        if event == "call":
            f = frame.f_code.co_filename
            if f.startswith(root) and "site-packages" not in f:
                rel = Path(f).resolve().relative_to(ROOT).as_posix()
                calls[(rel, getattr(frame.f_code, "co_qualname", frame.f_code.co_name))] += 1

    from tools.furnish_apartment import CONSENSUS, collect_boxes
    con = json.loads(CONSENSUS.read_text("utf-8"))
    log = io.StringIO()
    sys.setprofile(prof)
    try:
        with contextlib.redirect_stdout(log):
            boxes, summary = collect_boxes(con)
    finally:
        sys.setprofile(None)
    return {"files": sorted({f for f, _ in calls}), "calls": sorted(f"{f}::{q}" for f, q in calls),
            "rooms": [{"id": s[0], "name": s[1], "type": s[2], "result": s[3], "n_boxes": s[4]} for s in summary],
            "n_boxes": len(boxes), "log": [ln for ln in log.getvalue().splitlines() if ln.startswith("[furnish-apt]")]}


def _symbol_called(ref: str, calls: set[str]) -> bool:
    mod, _, name = ref.rpartition(".")
    path = mod.replace(".", "/") + ".py"
    return any(c == f"{path}::{name}" or c.startswith(f"{path}::{name}.") for c in calls)


def _symbol_exists(ref: str) -> bool:
    mod, _, name = ref.rpartition(".")
    try:
        return hasattr(importlib.import_module(mod), name)
    except Exception:  # noqa: BLE001
        return False


def capability_inventory(trace: dict) -> list[dict]:
    cat = json.loads((ROOT / "tools/rooms/capability_catalog.v1.json").read_text("utf-8"))
    calls = set(trace["calls"])
    ruby_used = {"tools/sketchup/furnish/place_layout_skp.rb", "tools/sketchup/furnish/place_layout_geom.rb"}
    out = []
    for c in cat["capabilities"]:
        syms = c["implementation"].get("symbols", [])
        py = [s["ref"] for s in syms if s["lang"] == "python"]
        rb = [s["ref"] for s in syms if s["lang"] == "ruby"]
        available = all(_symbol_exists(r) for r in py) and all((ROOT / r).exists() for r in rb)
        invoked_py = [r for r in py if _symbol_called(r, calls)]
        invoked = bool(invoked_py) or any(r in ruby_used for r in rb)
        consumed = [r for r in invoked_py if r in _CONSUMED_RULES and "LOGA" not in _CONSUMED_RULES[r]]
        mods = {r.rpartition(".")[0].replace(".", "/") + ".py" for r in py}
        module_executed = sorted(m for m in mods if m in set(trace["files"]))
        out.append({"id": c["id"], "room": c["room"], "catalog_validation": c["validation"]["state"],
                    "module_executed_other_entry": [m for m in module_executed if not invoked_py],
                    "AVAILABLE": available, "INVOKED": invoked, "CONSUMED": bool(consumed),
                    "consumed_basis": [_CONSUMED_RULES[r] for r in consumed],
                    "REFLECTED_IN_MODEL": "NOT_EVALUATED", "VALIDATED": "NOT_EVALUATED",
                    "symbols_python": py, "symbols_ruby": rb, "invoked_python": invoked_py})
    return out


def specialist_inventory(trace: dict) -> list[dict]:
    files = set(trace["files"])
    plan_called = "tools/rooms/specialists.py" in files
    out = []
    for p in sorted((ROOT / "tools/rooms").glob("*/specialist.v1.json")):
        s = json.loads(p.read_text("utf-8"))
        out.append({"room": s["room"], "state": s.get("state"), "execution_authorized": s.get("execution_authorized"),
                    "capability_ids": s.get("capability_ids", []), "recipe_ids": s.get("recipe_ids", []),
                    "AVAILABLE": True, "INVOKED": plan_called, "CONSUMED": False,
                    "note": "o furnish do apartamento despacha por room_type (tools.rooms.dispatch), sem specialists.plan()"})
    return out


def recipe_inventory(trace: dict) -> list[dict]:
    files = set(trace["files"])
    loader = "tools/sketchup/knowledge.py" in files or "tools/rooms/specialists.py" in files
    out = []
    for name in ("environment_recipes", "video_recipes"):
        doc = json.loads((ROOT / f"references/sketchup/knowledge/{name}.v1.json").read_text("utf-8"))
        for r in doc.get("recipes", []):
            out.append({"catalog": name, "id": r.get("id"), "proof_state": r.get("proof_state"),
                        "AVAILABLE": True, "INVOKED": loader, "CONSUMED": False})
    return out


def runtime_inventory() -> dict:
    mcp_cfg_path = ROOT.parents[1] / ".mcp.json"
    mcp = json.loads(mcp_cfg_path.read_text("utf-8")) if mcp_cfg_path.exists() else {}
    srv = (mcp.get("mcpServers") or {}).get("sketchup", {})
    mcp_cwd = Path(srv["cwd"]) if srv.get("cwd") else None
    rt = {"audit_checkout": {"path": ROOT.as_posix(), "head": _git("rev-parse", "HEAD"),
                             "origin_develop": _git("rev-parse", "origin/develop"),
                             "dirty": bool(_git("status", "--porcelain").strip())},
          "mcp_server": {"config": mcp_cfg_path.as_posix() if mcp_cfg_path.exists() else None, "command": srv.get("command"),
                         "cwd": srv.get("cwd"), "pythonpath": (srv.get("env") or {}).get("PYTHONPATH")}}
    if mcp_cwd and mcp_cwd.exists():
        g = ["git", "-C", str(mcp_cwd)]
        def run(*a):
            try:
                return subprocess.check_output([*g, *a], text=True, stderr=subprocess.DEVNULL).strip()
            except Exception:  # noqa: BLE001
                return "UNKNOWN"
        lr = run("rev-list", "--left-right", "--count", "HEAD...origin/develop").split()
        rt["mcp_server"].update({"checkout_head": run("rev-parse", "HEAD"), "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
                                 "ahead_of_origin_develop": int(lr[0]) if len(lr) == 2 else None,
                                 "behind_origin_develop": int(lr[1]) if len(lr) == 2 else None,
                                 "dirty_entries": [ln for ln in run("status", "--porcelain").splitlines() if ln]})
        rt["worktrees"] = [ln for ln in run("worktree", "list").splitlines() if ln]
    return rt


def watched_modules(trace: dict) -> list[dict]:
    files = trace["files"]
    return [{"component": k, "path": v, "exists": (ROOT / v).exists(),
             "EXECUTED_IN_GENERATION": any(f == v or f.startswith(v) for f in files)} for k, v in _WATCHED_MODULES.items()]


def run(out_dir: Path) -> dict:
    trace = trace_generation()
    result = {"generation_trace": trace, "capabilities": capability_inventory(trace),
              "specialists": specialist_inventory(trace), "recipes": recipe_inventory(trace),
              "watched_modules": watched_modules(trace), "runtime": runtime_inventory()}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "capability_inventory.json").write_text(json.dumps(
        {k: result[k] for k in ("capabilities", "specialists", "recipes", "watched_modules")}, indent=1, ensure_ascii=False)
        + "\n", "utf-8", newline="\n")
    (out_dir / "runtime_inventory.json").write_text(json.dumps(result["runtime"], indent=1, ensure_ascii=False) + "\n",
                                                    "utf-8", newline="\n")
    (out_dir / "generation_trace.json").write_text(json.dumps(trace, indent=1, ensure_ascii=False) + "\n", "utf-8",
                                                   newline="\n")
    return result


if __name__ == "__main__":
    r = run(Path(sys.argv[1]))
    caps = r["capabilities"]
    print(f"capacidades {len(caps)}: invoked {sum(c['INVOKED'] for c in caps)}, consumed {sum(c['CONSUMED'] for c in caps)}")
    print(f"especialistas invocados: {sum(s['INVOKED'] for s in r['specialists'])}/{len(r['specialists'])}; "
          f"receitas consumidas: {sum(x['CONSUMED'] for x in r['recipes'])}/{len(r['recipes'])}")
    for m in r["watched_modules"]:
        print(f"  {m['component']:46} {'EXECUTED' if m['EXECUTED_IN_GENERATION'] else 'not executed'}")
    print(json.dumps(r["runtime"]["mcp_server"], ensure_ascii=False))
