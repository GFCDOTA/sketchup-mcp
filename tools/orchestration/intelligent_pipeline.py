"""Orquestrador inteligente (FP-055 P3): contexto -> especialista -> receitas -> solver -> proposta -> manifesto.

    PT_TO_M=0.0259 python -m tools.orchestration.intelligent_pipeline --profile INTELLIGENT_DRY_RUN --rooms r006 \
        --out runs/fp055/<run>

Perfis: `INTELLIGENT_DRY_RUN` (aqui: propostas + evidencia, nunca SketchUp) e `INTELLIGENT_BUILD` (P4: constroi a proposta em
`runs/`). Os dois passam primeiro pela identidade de runtime (P1) e pela revisao da fonte (sha256 do consensus).

O que cada estagio CONSOME (registrado no `CapabilityLedger`, nunca por import):
  - especialista: o perfil valida o builder (allowlist) e a `solver_policy` dele vira os objetos/graus de liberdade do problema;
  - interfaces F1C: viram a entrada semantica de cada objeto do problema (sem elas o solver acusa INPUT_SEMANTIC_INTERFACE_MISSING);
  - builder do comodo: as caixas viram o estado ORIGINAL do problema;
  - solver + ordem: a 1a alternativa vira a proposta (e as caixas que o builder deve construir).
Receitas de conhecimento: so SELECTED (P5 liga receita -> operacao). Comodo sem politica de solver: NOT_INTEGRATED, explicito.
Fail closed: proposta nao viavel nunca e rotulada valida; o manifesto diz `valid: false` com as violacoes.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any

from core.pipeline_contracts import (
    CapabilityLedger,
    ContractError,
    GenerationRequest,
    LayoutProposal,
    RoomContext,
    SpecialistPlan,
    ValidationReport,
)

ROOT = Path(__file__).resolve().parents[2]
PIPELINE_VERSION = "fp055-p3.v1"
INTEGRATED_TYPES = ("BATHROOM", "KITCHEN")          # tipos com solver_policy; os demais: NOT_INTEGRATED (P6)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _builder_symbol(fn) -> str:
    return f"{fn.__module__}.{fn.__name__}"


def specialist_plan(room_type: str, builder_symbol: str, policy=None) -> SpecialistPlan:
    """Perfil do especialista (validado por schema) + politica do solver. Recusa builder fora da allowlist do perfil."""
    from tools.rooms.shared.spatial_solver.problem import room_policy
    from tools.rooms.specialists import load_profile, room_key
    key = room_key(room_type.lower())
    prof = load_profile(key)
    if f"python:{builder_symbol}" not in prof["tool_allowlist"]:
        raise ContractError(f"builder {builder_symbol} fora da allowlist do especialista {key}")
    pol = policy if policy is not None else room_policy(room_type)
    if pol is None:
        raise ContractError(f"especialista {key} sem solver_policy")
    return SpecialistPlan(
        room=key, profile_version=prof["schema_version"], profile_state=prof["state"], builder_symbol=builder_symbol,
        policy_version=getattr(pol, "POLICY_VERSION", ""),
        object_policies={t: {"anchor": a, "dof": d.__dict__ if hasattr(d, "__dict__") else str(d)}
                         for t, (a, d) in sorted(pol.ANCHOR_AND_DOF.items())},
        constraints=tuple(prof["constraints"]), recipe_ids=tuple(prof["recipe_ids"]), source_ids=tuple(prof["source_ids"]),
        capability_ids=tuple(prof["capability_ids"]))


def plan_room(con, boxes, ifaces, room_id, room_type, room_name, builder_symbol, ledger: CapabilityLedger,
              policy=None, max_candidates=None) -> dict[str, Any]:
    """Um comodo: especialista -> problema -> solver -> ordem -> proposta. Puro (sem SketchUp)."""
    from tools.rooms.shared.spatial_solver import solver as sv
    from tools.rooms.shared.spatial_solver.candidates import apply_candidate
    from tools.rooms.shared.spatial_solver.problem import build_problem, room_policy
    from tools.rooms.shared.spatial_solver.ranking import rank
    from tools.validation.functional_clearance import _room_context
    spec_name = f"specialist.{room_type.lower()}"
    ledger.available(spec_name)
    try:
        sp = specialist_plan(room_type, builder_symbol, policy)
    except (ContractError, KeyError, ValueError) as exc:
        return {"room_id": room_id, "status": "BLOCKED", "reason": f"especialista: {exc}"}
    ledger.invoke(spec_name, f"perfil {sp.room} ({sp.profile_state}) + {sp.policy_version}")
    for rid in sp.recipe_ids:
        ledger.available(f"recipe.{rid}")
        ledger.select(f"recipe.{rid}", f"recipe_ids do especialista {sp.room}")
    cell, portals, _d, _rb = _room_context(con, boxes, room_id)
    ctx = RoomContext(room_id, room_name, room_type, tuple(tuple(map(lambda v: round(v, 4), c)) for c in cell.exterior.coords),
                      tuple((round(p.x, 4), round(p.y, 4)) for p in portals))
    pol = policy if policy is not None else room_policy(room_type)
    problem = build_problem(con, boxes, room_id, room_type, ifaces, policy=pol)
    ledger.consume(spec_name, f"solver_policy -> {len(problem.objects)} objeto(s) do problema com ancora/DOF do especialista")
    room_ifaces = [o for o in problem.objects if o.interfaces]
    ledger.available("f1c.functional_interfaces")
    ledger.invoke("f1c.functional_interfaces", "collect_interfaces(con, caixas)")
    if room_ifaces:
        ledger.consume("f1c.functional_interfaces", f"{room_id}: {len(room_ifaces)} interface(s) semantica(s) no problema")
    ledger.available(f"builder.{builder_symbol}")
    ledger.invoke(f"builder.{builder_symbol}", "caixas do comodo (estado ORIGINAL)")
    ledger.consume(f"builder.{builder_symbol}", f"{room_id}: caixas do builder = estado ORIGINAL do problema")
    kw = {} if max_candidates is None else {"max_candidates": max_candidates}
    res = sv.solve(problem, con, boxes, ifaces, room_name, **kw)
    ledger.available("f2.spatial_solver")
    ledger.invoke("f2.spatial_solver", f"{room_id}: {res.evaluated}/{res.total_candidates} candidatos")
    if res.status in ("INVALID_INPUT", "UNKNOWN") or not res.results:
        prop = LayoutProposal(f"{room_id}:{res.status}", room_id, res.status, "-", (), tuple(res.issues), {}, None,
                              res.total_candidates, "; ".join(res.notes) or res.status, res.algorithm_version,
                              res.policy_version or sp.policy_version)
        return {"room_id": room_id, "status": res.status, "context": ctx, "specialist": sp, "proposal": prop}
    ranked = rank(res.results)
    best = ranked[0]
    local = sv.neighborhood(con, boxes, room_id)
    after, _ = apply_candidate(problem, local, ifaces, best.result.candidate, room_name)
    room_boxes = tuple(b for b in after if b.get("room") == room_name)
    status = "FEASIBLE" if best.result.feasible else "INFEASIBLE"
    prop = LayoutProposal(
        proposal_id=f"{room_id}:{best.result.candidate.candidate_id}", room_id=room_id, status=status,
        candidate_id=best.result.candidate.candidate_id, moves=tuple(m.__dict__ for m in best.result.candidate.moved),
        hard_violations=tuple(best.result.hard_violations), metrics=best.result.metrics, rank=best.rank,
        candidates_total=res.total_candidates, explanation=best.explanation, algorithm_version=res.algorithm_version,
        policy_version=res.policy_version, boxes=room_boxes)
    ledger.consume("f2.spatial_solver", f"{room_id}: proposta {prop.proposal_id} ({status}) da ordem lexicografica")
    return {"room_id": room_id, "status": status, "context": ctx, "specialist": sp, "proposal": prop,
            "original_rank": next(x.rank for x in ranked if x.result.candidate.candidate_id == "ORIGINAL")}


def run(request: GenerationRequest, *, runtime_check=None, max_candidates=None) -> dict[str, Any]:
    from tools.sketchup.runtime_identity import check
    rt = (runtime_check or check)(request.generation_profile)
    manifest: dict[str, Any] = {"pipeline_version": PIPELINE_VERSION, "request": request.__dict__, "runtime": rt,
                                "valid": False, "rooms": [], "validations": []}
    if rt["status"] == "BLOCKED":
        manifest["status"] = "BLOCKED_RUNTIME"
        return manifest
    src = ROOT / request.source_document
    if not src.exists() or _sha(src) != request.source_revision:
        manifest["status"] = "BLOCKED_SOURCE_REVISION"
        return manifest
    con = json.loads(src.read_text("utf-8"))
    from tools.orchestration import furnish_apartment as fa
    from tools.room_type import classify_rooms
    from tools.validation.functional_clearance import collect_interfaces
    ledger = CapabilityLedger()
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        boxes, summary = fa.collect_boxes(con)
        ifaces = collect_interfaces(con, boxes)
    manifest["legacy_log"] = [ln for ln in log.getvalue().splitlines() if ln.startswith("[furnish-apt]")]
    rooms = {r["id"]: r for r in classify_rooms(con)}
    targets = request.target_rooms or tuple(sorted(rooms))
    for rid in targets:
        r = rooms.get(rid)
        if r is None:
            manifest["rooms"].append({"room_id": rid, "status": "BLOCKED", "reason": "comodo inexistente no consensus"})
            continue
        name, rtype = str(r.get("name") or rid), r["room_type"]
        if rtype not in INTEGRATED_TYPES:
            manifest["rooms"].append({"room_id": rid, "name": name, "type": rtype, "status": "NOT_INTEGRATED",
                                      "reason": "sem solver_policy do especialista (FP-055 P6)"})
            continue
        brain = fa.BRAINS.get(rtype)
        out = plan_room(con, boxes, ifaces, rid, rtype, name, _builder_symbol(brain), ledger, max_candidates=max_candidates)
        prop = out.get("proposal")
        rec = {"room_id": rid, "name": name, "type": rtype, "status": out["status"], "reason": out.get("reason"),
               "original_rank": out.get("original_rank"),
               "specialist": out["specialist"].__dict__ if out.get("specialist") else None,
               "proposal": prop.to_dict() if prop else None}
        if prop:
            manifest["validations"].append(ValidationReport(
                "solver_validation", "PASS" if prop.buildable_as_valid else "FAIL", prop.algorithm_version,
                f"{rid} proposta {prop.proposal_id}", {"hard_violations": list(prop.hard_violations)}).__dict__)
        manifest["rooms"].append(rec)
        manifest.setdefault("_proposals", {})[rid] = prop
    manifest["ledger"] = ledger.to_dict()
    # valido so se TODO comodo pedido foi planejado e e viavel: NOT_INTEGRATED/BLOCKED/INFEASIBLE derrubam (fail closed)
    manifest["valid"] = bool(manifest["rooms"]) and all(x["status"] == "FEASIBLE" for x in manifest["rooms"])
    manifest["status"] = ("DRY_RUN_COMPLETE" if request.generation_profile == "INTELLIGENT_DRY_RUN" else "PLANNED")
    manifest["not_integrated"] = sorted(x["room_id"] for x in manifest["rooms"] if x["status"] == "NOT_INTEGRATED")
    return manifest


def write(manifest: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in manifest.items() if not k.startswith("_")}
    p = out_dir / "run_manifest.json"
    p.write_text(json.dumps(clean, indent=1, ensure_ascii=False, default=str) + "\n", "utf-8", newline="\n")
    return p


def main(argv=None) -> int:
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    from tools.sketchup.runtime_identity import code_identity
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="INTELLIGENT_DRY_RUN", choices=("INTELLIGENT_DRY_RUN",))
    ap.add_argument("--rooms", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--allow-dev", action="store_true", help="aceita checkout divergente (marcado DEV_OVERRIDE)")
    a = ap.parse_args(argv)
    src = PLANTA_74_CONSENSUS.relative_to(ROOT).as_posix()
    req = GenerationRequest("planta_74", src, _sha(ROOT / src), code_identity()["head"], a.profile, a.out,
                            tuple(x for x in a.rooms.split(",") if x))
    from tools.sketchup.runtime_identity import check
    m = run(req, runtime_check=lambda prof: check(prof, allow_dev=a.allow_dev))
    p = write(m, ROOT / a.out)
    print(p, m["status"], "valid" if m["valid"] else "NOT VALID", [(x["room_id"], x["status"]) for x in m["rooms"]])
    return 0 if m["status"] != "BLOCKED_RUNTIME" else 2


if __name__ == "__main__":
    sys.exit(main())
