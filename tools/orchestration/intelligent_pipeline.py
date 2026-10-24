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
    after, ifaces_after = apply_candidate(problem, local, ifaces, best.result.candidate, room_name)
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
            "interfaces": ifaces_after,                  # interfaces MOVIDAS com o candidato (avaliacao funcional do construido)
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
        manifest.setdefault("_interfaces", {})[rid] = out.get("interfaces")
    manifest["ledger"] = ledger.to_dict()
    manifest["_ledger"] = ledger                         # objeto vivo para o estagio de construcao (nao serializado)
    # valido so se TODO comodo pedido foi planejado e e viavel: NOT_INTEGRATED/BLOCKED/INFEASIBLE derrubam (fail closed)
    manifest["valid"] = bool(manifest["rooms"]) and all(x["status"] == "FEASIBLE" for x in manifest["rooms"])
    manifest["status"] = ("DRY_RUN_COMPLETE" if request.generation_profile == "INTELLIGENT_DRY_RUN" else "PLANNED")
    manifest["not_integrated"] = sorted(x["room_id"] for x in manifest["rooms"] if x["status"] == "NOT_INTEGRATED")
    return manifest


# ----------------------------------------------------------------------------------------- P4: construcao + conferencia
CONFORMANCE_TOL_M = 0.005          # 5 mm: a materializacao das caixas foi medida em 0,0 mm (auditoria 2026-10-23)
IN2M = 0.0254


def compose_boxes(all_boxes: list[dict], proposals: dict[str, LayoutProposal], room_names: dict[str, str]) -> list[dict]:
    """Planta = caixas de base com as de cada comodo planejado TROCADAS pelas da proposta (o builder constroi a proposta)."""
    replaced = {room_names[rid] for rid, p in proposals.items() if p.boxes}
    out = [b for b in all_boxes if b.get("room") not in replaced]
    for rid, p in proposals.items():
        out += [dict(b) for b in p.boxes]
    return out


def module_bbox_m(parts: list[dict]) -> tuple[list[float], list[float]]:
    xs = [c[0] for b in parts for c in b["corners"]]
    ys = [c[1] for b in parts for c in b["corners"]]
    z0 = [float(b.get("z0_in") or 0) for b in parts]
    z1 = [float(b.get("z0_in") or 0) + float(b.get("h_in") or 0) for b in parts]
    return [min(xs) * IN2M, min(ys) * IN2M, min(z0) * IN2M], [max(xs) * IN2M, max(ys) * IN2M, max(z1) * IN2M]


def conformance(nodes: list[dict], boxes: list[dict], rooms: list[str], tol_m: float = CONFORMANCE_TOL_M):
    """Proposta x MODELO REABERTO, por grupo "<comodo> · <modulo>": bbox do mundo dentro da tolerancia."""
    by_name = {n["name"]: n for n in nodes if n.get("bbox_world_m")}
    requested, built, omitted, div = [], [], {}, []
    for room in rooms:
        for mod in sorted({b.get("module") for b in boxes if b.get("room") == room and b.get("corners")}):
            key = f"{room} · {mod}"
            requested.append(key)
            node = by_name.get(key)
            if node is None:
                omitted[key] = "grupo ausente no modelo reaberto"
                continue
            built.append(key)
            pmin, pmax = module_bbox_m([b for b in boxes if b.get("room") == room and b.get("module") == mod
                                        and b.get("corners")])
            bmin, bmax = node["bbox_world_m"]["min"], node["bbox_world_m"]["max"]
            d = max(abs(a - c) for a, c in zip(pmin + pmax, bmin + bmax))
            if d > tol_m:
                div.append({"group": key, "max_delta_m": round(d, 4), "proposal": [pmin, pmax], "built": [bmin, bmax]})
    return requested, built, omitted, div


SHELL_TOL_M = 0.02                 # folga da pegada contra o piso construido (encosto na parede, arredondamento)


def inside_built_shell(nodes: list[dict], boxes: list[dict], room_ids: dict[str, str], tol_m: float = SHELL_TOL_M):
    """Cada modulo construido, no plano, dentro do PISO CONSTRUIDO do comodo (`Floor_Group_<rid>` no modelo reaberto).
    Pega o que proposta x construido nao pega: shell noutro referencial/escala (achado da P4: shell sintetico a 0,0352 com
    caixas a 0,0259 — tudo "conforme" e a mobilia fora do comodo)."""
    by_name = {n["name"]: n for n in nodes if n.get("bbox_world_m")}
    problems = []
    for rid, room in room_ids.items():
        floor = by_name.get(f"Floor_Group_{rid}")
        if floor is None:
            problems.append({"room": rid, "problem": "piso construido ausente: nao da para verificar (BLOCKED)"})
            continue
        fmin, fmax = floor["bbox_world_m"]["min"], floor["bbox_world_m"]["max"]
        for mod in sorted({b.get("module") for b in boxes if b.get("room") == room and b.get("corners")}):
            low = [b for b in boxes if b.get("room") == room and b.get("module") == mod and b.get("corners")
                   and float(b.get("z0_in") or 0) < 1.2 / IN2M]
            if not low:                                  # so pecas altas (espelho, prateleira): nao ocupam o piso
                continue
            pmin, pmax = module_bbox_m(low)
            out = max(fmin[0] - pmin[0], fmin[1] - pmin[1], pmax[0] - fmax[0], pmax[1] - fmax[1])
            if out > tol_m:
                problems.append({"room": rid, "group": f"{room} · {mod}", "outside_floor_m": round(out, 4)})
    return problems


def _pids(job_result: dict) -> set[int]:
    """PID do SketchUp que o JOB subiu: so a chave de topo `pid` (e `build.pid` do shell). Nunca varrer o resultado
    recursivamente — os nos da inspecao tem `pid` = persistent_id do SketchUp, que pode coincidir com um PID real."""
    out = set()
    for v in (job_result.get("pid"), (job_result.get("build") or {}).get("pid")):
        if isinstance(v, int) and not isinstance(v, bool):
            out.add(v)
    return out


def build(all_boxes, proposals: dict[str, LayoutProposal], room_names: dict[str, str], base_skp: Path, out_dir: Path,
          ledger: CapabilityLedger, *, consensus: dict, consensus_path, diagnostic: bool = False,
          unsafe_skip_scale_check: bool = False, functional=None, su=None) -> dict[str, Any]:
    """Constroi a proposta no SketchUp real (copia em `out_dir`), reabre em outro processo e valida DUAS coisas:
      1. proposta x construido (grupos "<comodo> · <modulo>" no bbox de mundo, 5 mm) — prova que o builder obedeceu;
      2. construido x ambiente real (`tools.validation.built_geometry` sobre as faces do modelo reaberto: poligono do piso,
         massa de parede, varredura de porta, outros objetos) — prova que o resultado esta certo no apartamento.
    So (1) nunca vale PASS (falso PASS da P4). Antes de construir, o contrato de escala (`core.plan_frame.check_chain`) precisa
    estar OK; depois, o referencial e conferido contra as paredes construidas (IoU). Qualquer verificacao que nao rode = BLOCKED.
    `unsafe_skip_scale_check` existe SO para a prova reproduzir o erro antigo; o resultado sai marcado e nunca valido.
    Proposta nao viavel so e construida com `diagnostic=True` e sai DIAGNOSTIC_NOT_VALID. Fecha so os PIDs que abriu.

    Tres veredictos INDEPENDENTES (nenhum implica o outro):
      geometric_validity  contrato de referencial + paredes por parede + extracao + piso/parede/porta/objetos + proposta=construido;
      functional_validity regras funcionais (folga, vao, alcance) reavaliadas por `functional[rid](caixas)` sobre as caixas
                          provadas iguais ao construido; sem avaliador = NOT_EXECUTED (nunca PASS);
      visual              sempre PENDING_HUMAN.
    `valid` = geometrico PASS e funcional PASS."""
    from core.plan_frame import check_chain, frame_for_consensus, verify_against_built
    from tools.sketchup import jobs
    from tools.validation import built_geometry as bg
    bad = sorted(rid for rid, p in proposals.items() if not p.buildable_as_valid)
    if bad and not diagnostic:
        return {"status": "BLOCKED_NOT_FEASIBLE", "rooms": bad, "valid": False}
    chain = check_chain(consensus_path)
    if chain["status"] != "OK" and not unsafe_skip_scale_check:
        return {"status": chain["status"], "coordinate_contract": chain, "valid": False}
    boxes = compose_boxes(all_boxes, proposals, room_names)
    opened: set[int] = set()
    try:
        placed = jobs.place_boxes(boxes, base=base_skp, d=out_dir / "build", mode="interactive", su=su)
        opened |= _pids(placed)
        if placed.get("status") != "OK":
            return {"status": "BUILD_FAILED", "placed": placed, "valid": False, "coordinate_contract": chain}
        skp = Path(placed["files"]["skp"])
        insp = jobs.inspect_model(str(skp), max_depth=1, out_dir=str(out_dir / "inspect"), mode="interactive", su=su)
        opened |= _pids(insp)
        geo = jobs.inspect_geometry(str(skp), out_dir=str(out_dir / "geometry"), mode="interactive", su=su)
        opened |= _pids(geo)
        res, gres = insp.get("result") or {}, geo.get("result") or {}
        if not res.get("ok") or not gres.get("ok"):
            return {"status": "BLOCKED_INSPECTION_FAILED", "inspect": insp, "geometry": geo, "valid": False,
                    "coordinate_contract": chain}
    finally:
        closed = [jobs.close(pid=p, force=True, confirm=True, su=su) for p in sorted(opened)]
    rooms = {r: room_names[r] for r in proposals}
    # (1) proposta x construido
    req, built, omitted, div = conformance(res["nodes"], boxes, list(rooms.values()))
    from core.pipeline_contracts import BuildResult
    br = BuildResult(tuple(req), tuple(built), omitted, tuple(div), str(res.get("sketchup_version") or "UNKNOWN"))
    conform = not omitted and not div
    # (2) construido x ambiente real
    idx = bg.group_index(gres)
    frame = frame_for_consensus(consensus_path)
    contract = verify_against_built(bg.expected_walls_pt(consensus), frame, bg.built_walls(idx), consensus.get("walls"))
    swings = bg.door_swings_m(consensus, frame) if contract["status"] == "OK" else None
    env_reports = {rid: bg.validate_room(idx, rid, name, door_swings=swings) for rid, name in rooms.items()}
    env_status = {rid: bg.status(r) for rid, r in env_reports.items()}
    env_ok = contract["status"] == "OK" and all(s == "PASS" for s in env_status.values())
    if unsafe_skip_scale_check or contract["status"] != "OK" or "BLOCKED" in env_status.values():
        geometric = "BLOCKED"
    else:
        geometric = "PASS" if conform and env_ok else "FAIL"
    func_reports = {}
    for rid in rooms:
        fn = (functional or {}).get(rid)
        if fn is None or geometric != "PASS":
            func_reports[rid] = {"status": "NOT_EXECUTED",
                                 "reason": "sem avaliador funcional" if fn is None else "geometria nao aprovada"}
            continue
        ev = fn(boxes)
        func_reports[rid] = {"status": "PASS" if ev.feasible else "FAIL",
                             "hard_violations": [v.to_dict() for v in ev.hard_violations],
                             "basis": "motor F2 sobre as caixas provadas iguais ao construido (<= 5 mm)"}
    fstat = [r["status"] for r in func_reports.values()]
    functional_validity = ("NOT_EXECUTED" if "NOT_EXECUTED" in fstat else "FAIL" if "FAIL" in fstat else "PASS")
    valid = geometric == "PASS" and functional_validity == "PASS" and not bad
    if conform and ledger.state("f2.spatial_solver") == "CONSUMED":
        ledger.reflect("f2.spatial_solver", f"{sorted(rooms)}: reaberto no SketchUp, {len(built)} grupos <= "
                                            f"{CONFORMANCE_TOL_M * 1000:.0f} mm da proposta")
        if env_ok and not bad and functional_validity == "PASS":
            ledger.validate("f2.spatial_solver", f"{sorted(rooms)}: construido x ambiente real PASS (piso, parede, porta, "
                                                 "objetos) e contrato de referencial OK")
    if valid:
        status = "BUILT"
    elif contract["status"] != "OK" or "BLOCKED" in env_status.values():
        status = "BLOCKED_ENVIRONMENT_UNVERIFIED"
    elif not conform:
        status = "BUILT_NONCONFORMING"
    elif not env_ok:
        status = "BUILT_FAILS_ENVIRONMENT"
    elif functional_validity == "FAIL":
        status = "DIAGNOSTIC_NOT_VALID" if bad else "BUILT_FUNCTIONAL_FAIL"
    elif functional_validity == "NOT_EXECUTED":
        status = "BUILT_FUNCTIONAL_NOT_EXECUTED"
    else:
        status = "DIAGNOSTIC_NOT_VALID"
    legacy = inside_built_shell(res["nodes"], boxes, rooms)          # so comparacao: o cheque antigo NAO decide nada
    return {"status": status, "valid": valid, "geometric_validity": geometric, "functional_validity": functional_validity,
            "functional": func_reports, "visual": "PENDING_HUMAN",
            "coordinate_contract": chain, "frame_verification": contract,
            "environment": env_reports, "environment_status": env_status, "proposal_conformance": conform,
            "legacy_bbox_check_not_decisive": {"problems": legacy, "would_pass": not legacy},
            "unsafe_skip_scale_check": unsafe_skip_scale_check, "skp": str(skp), "skp_sha256": _sha(skp),
            "renders": placed.get("files"), "build_result": br.__dict__, "sketchup_version": br.sketchup_version,
            "pids_opened": sorted(opened), "pids_closed": closed}


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
