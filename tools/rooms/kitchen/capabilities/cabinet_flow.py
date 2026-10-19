"""Fluxo vertical do especialista de cozinha (FP-043/P7): pedido -> gabinete salvo, reaberto e inspecionado, com trace.

Encadeia, em um unico trace auditavel e SEM autorizacao implicita:
`request -> projeto/comodo -> consensus+requisitos -> source/recipe IDs -> capacidade+versao -> parametros+proveniencia ->
validacao do plano (ancora, arquitetura, mobilia, circulacao) -> allowlist -> job SketchUp (PID) -> .skp salvo ->
reabertura+inspecao -> verificacao plano x modelo -> evidencia (hashes, commit, versoes)`.

Garantias: roda numa COPIA da base (nunca o original, nunca fixtures/artifacts); qualquer bloqueio devolve um estado
`BLOCKED_*` ANTES de subir o SketchUp e deixa a entrada intacta; so ferramentas da allowlist do perfil sao usadas
(`_use` falha fechado); cada PID que subimos e fechado pelo PID; reexecucao com a mesma chave de idempotencia nao refaz.
Nao emite veredito visual.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from tools.rooms import capability_catalog as cc
from tools.rooms import specialists as sp

ROOT = Path(__file__).resolve().parents[4]
TRACE_SCHEMA = "kitchen_cabinet_trace.v1"
CONSENSUS_DEFAULT = ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"
USED_TOOLS = (
    "python:tools.rooms.kitchen.capabilities.cabinet.plan_kitchen_cabinet",
    "python:tools.rooms.shared.cabinet.plan.plan_cabinet",
    "python:tools.rooms.shared.cabinet.plan.require_valid",
    "python:tools.rooms.shared.cabinet.sketchup.materialize",
    "python:tools.rooms.shared.cabinet.sketchup.inspect",
    "ruby:tools/rooms/shared/cabinet/ruby/cabinet_build.rb",
    "ruby:tools/rooms/shared/cabinet/ruby/cabinet_inspect.rb",
)


class ToolNotAllowed(RuntimeError):
    """Tentativa de usar ferramenta fora da allowlist do perfil: falha fechada."""


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _sha_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs_to_cabinet_request(request_id: str, inputs: dict, materials: dict, grain: dict | None = None) -> dict:
    """Insumos achatados (`dimensions.width` ...) -> `cabinet_request.v1`. Nao inventa campo: o que falta fica ausente e
    o plano recusa com codigo proprio."""
    out: dict = {"schema_version": "cabinet_request.v1", "request_id": request_id}
    for name, node in inputs.items():
        if name.startswith("materials."):
            continue
        group, _, field = name.partition(".")
        if group == "fronts" or group == "shelf":
            out.setdefault(group, {})[field] = node["value"] if field == "count" else node
        else:
            out.setdefault(group, {})[field] = node
    out["materials"] = materials
    out["grain"] = grain or {k: ("none" if k == "back" else "along_height") for k in materials}
    return out


def run_request(request: dict, *, out_dir: str | Path, base_skp: str | Path, consensus_path: str | Path | None = None,
                project: str = "planta_74", su=None, mode: str | None = None, close_pids: bool = True) -> dict:
    """request: {request_id, text, room?, tool?, touches?, inputs{...}, materials{...}, grain?}. Devolve o trace."""
    from core.domain.room_registry import room_info
    from tools.rooms.kitchen.capabilities.cabinet import plan_kitchen_cabinet
    from tools.rooms.shared.cabinet import PlanRefused, require_valid
    from tools.rooms.shared.cabinet import sketchup as cs
    from tools.sketchup import jobs

    request_in = copy.deepcopy(request)                       # a entrada original nunca e mutada (prova abaixo)
    out_dir, base = Path(out_dir).resolve(), Path(base_skp).resolve()
    con_path = Path(consensus_path or CONSENSUS_DEFAULT).resolve()
    trace: dict = {"schema_version": TRACE_SCHEMA, "request_id": request["request_id"], "steps": [], "state": None,
                   "execution_authorized": False, "pids": []}
    profile = sp.load_profile("kitchen")
    launched: list[int] = []

    def step(name: str, status: str, **data) -> None:
        trace["steps"].append({"step": name, "status": status, **data})

    def finish(state: str, **extra) -> dict:
        trace["state"] = state
        trace.update(extra)
        trace["input_unchanged"] = request_in == request and (not base.exists() or trace.get("base_sha256") in (None, _sha_file(base)))
        if close_pids:
            for pid in launched:
                jobs.close(pid=int(pid), force=True, confirm=True)
        trace["pids"] = launched
        return trace

    def use(tool: str) -> None:
        if tool not in profile["tool_allowlist"]:
            raise ToolNotAllowed(f"{tool} fora da allowlist do perfil kitchen")
        trace.setdefault("tools_used", [])
        if tool not in trace["tools_used"]:
            trace["tools_used"].append(tool)

    step("request", "OK", request_sha256=hashlib.sha256(_canon(request).encode()).hexdigest(), text=request.get("text"))
    # 1. projeto/comodo
    info = room_info("kitchen", project_id=project)
    step("project_room", "OK", project=project, room_id=info.room_id, display_name=info.display_name, room_type=info.room_type)
    # 2. consensus + requisitos
    if not con_path.is_file() or not base.is_file():
        step("consensus_requirements", "BLOCKED", reason=f"consensus/base ausente: {con_path if not con_path.is_file() else base}")
        return finish("BLOCKED_INPUT_MISSING")
    consensus = json.loads(con_path.read_text("utf-8"))
    trace["base_sha256"] = _sha_file(base)
    catalog = cc.load_catalog()
    step("consensus_requirements", "OK", consensus=str(con_path.relative_to(ROOT)) if ROOT in con_path.parents else str(con_path),
         consensus_sha256=_sha_file(con_path), base_skp=str(base), base_sha256=trace["base_sha256"],
         required_inputs=[p["name"] for p in next(c for c in catalog["capabilities"] if c["id"] == "kitchen.cabinet.plain-fronts")["parameters"]])
    # 3. especialista: roteamento, tecnica, capacidade, allowlist, insumos
    sp_req = {k: request[k] for k in ("text", "room", "tool", "touches", "inputs") if k in request}
    sp_req.setdefault("room", "kitchen")
    splan = sp.plan(sp_req)
    binding = next((b for b in catalog["bindings"] if b["id"] == splan.get("binding")), None)
    env = json.loads((ROOT / catalog["knowledge_catalogs"]["environment"]).read_text("utf-8"))
    video = json.loads((ROOT / catalog["knowledge_catalogs"]["video"]).read_text("utf-8"))
    recipe_state = {r["id"]: r.get("proof_state") or r.get("knowledge_state") for r in env["recipes"] + video["recipes"]}
    step("knowledge", "OK" if binding else "NONE", binding=splan.get("binding"),
         source_ids=binding["source_ids"] if binding else [], recipe_ids=binding["recipe_ids"] if binding else [],
         recipe_states={r: recipe_state.get(r) for r in (binding["recipe_ids"] if binding else [])})
    if splan["state"] != sp.PLAN_READY:
        step("specialist_plan", "BLOCKED", state=splan["state"], reason=splan.get("reason"), next_step=splan.get("next_step"),
             gap=splan.get("gap"), missing=splan.get("missing"))
        return finish(splan["state"], reason=splan.get("reason"), next_step=splan.get("next_step"))
    step("specialist_plan", "OK", state=splan["state"], capability=splan["capability"], steps=[s["tool"] for s in splan["steps"]])
    step("capability", "OK", **splan["capability"])
    step("parameters", "OK", parameters={k: request["inputs"][k] for k in sorted(request["inputs"])})
    # 4. plano da cozinha (4 gates) -> require_valid
    cab_req = inputs_to_cabinet_request(request["request_id"], request["inputs"], request.get("materials") or {}, request.get("grain"))
    use("python:tools.rooms.kitchen.capabilities.cabinet.plan_kitchen_cabinet")
    use("python:tools.rooms.shared.cabinet.plan.plan_cabinet")
    plan = plan_kitchen_cabinet(consensus, info.room_id, cab_req)
    step("plan_validation", "OK" if plan["status"] == "OK" else "BLOCKED", result_status=plan["status"], stage=plan.get("stage"),
         gates=plan.get("gates"), findings=plan.get("findings"), signature=plan.get("signature"))
    use("python:tools.rooms.shared.cabinet.plan.require_valid")
    try:
        require_valid(plan)
    except PlanRefused as exc:
        return finish("BLOCKED_PLAN_REFUSED", reason=str(exc), findings=exc.findings)
    # 5. allowlist: tudo que o fluxo vai tocar esta no perfil
    try:
        for tool in USED_TOOLS:
            use(tool)
    except ToolNotAllowed as exc:
        step("allowlist", "BLOCKED", reason=str(exc))
        return finish("BLOCKED_TOOL_NOT_ALLOWED", reason=str(exc))
    step("allowlist", "OK", tools=list(USED_TOOLS))
    # 6. idempotencia + job
    key = hashlib.sha256(_canon({"request": hashlib.sha256(_canon(request).encode()).hexdigest(), "capability": plan["capability"],
                                  "consensus": _sha_file(con_path), "base": trace["base_sha256"], "signature": plan["signature"]}).encode()).hexdigest()
    job_dir = out_dir / key[:12]
    manifest_p, out_skp = job_dir / "manifest.json", job_dir / "cabinet.skp"
    trace["idempotency_key"] = key
    if manifest_p.is_file() and out_skp.is_file():
        prior = json.loads(manifest_p.read_text("utf-8"))
        if prior.get("idempotency_key") == key and prior.get("state") == "DONE_L2_VERIFIED" and _sha_file(out_skp) == prior.get("skp_sha256"):
            step("job", "SKIPPED", reason="mesma chave de idempotencia ja concluida e integra")
            return finish("ALREADY_DONE", prior_manifest=str(manifest_p), skp=str(out_skp), skp_sha256=prior["skp_sha256"])
    job_dir.mkdir(parents=True, exist_ok=True)
    use("python:tools.rooms.shared.cabinet.sketchup.inspect")
    baseline = cs.inspect(base, mode=mode, su=su)
    if baseline.get("pid"):
        launched.append(int(baseline["pid"]))
    if baseline["status"] != "OK":
        step("baseline_inspect", "FAILED", result_status=baseline["status"], reason=baseline.get("reason"))
        return finish("JOB_FAILED", reason="baseline da base nao inspecionado")
    step("baseline_inspect", "OK", pid=baseline.get("pid"), non_cabinet=baseline["result"]["non_cabinet"])
    use("python:tools.rooms.shared.cabinet.sketchup.materialize")
    built = cs.materialize(plan, out_skp, base_skp=base, mode=mode, su=su)
    if built.get("pid"):
        launched.append(int(built["pid"]))
    if built["status"] != "OK":
        step("job", "FAILED", result_status=built["status"], reason=built.get("reason"), pid=built.get("pid"),
             unedited_copy_removed=built.get("unedited_copy_removed"))
        return finish("JOB_FAILED", reason=built.get("reason") or built["status"])
    step("job", "OK", pid=built.get("pid"), sketchup_version=built["result"].get("sketchup_version"),
         elapsed_s=built.get("elapsed_s"), out_skp=str(out_skp), grain_support=built["result"].get("grain_support"),
         replaced_previous=built["result"].get("replaced_previous"))
    # 7. reabrir o salvo em outro processo + verificar
    reopened = cs.inspect(out_skp, mode=mode, su=su)
    if reopened.get("pid"):
        launched.append(int(reopened["pid"]))
    if reopened["status"] != "OK":
        step("reopen_inspection", "FAILED", result_status=reopened["status"], reason=reopened.get("reason"))
        return finish("JOB_FAILED", reason="reabertura nao inspecionada")
    report = cs.verify(plan, reopened["result"], baseline=baseline["result"])
    step("reopen_inspection", "OK" if report["ok"] else "FAILED", pid=reopened.get("pid"), checks=len(report["checks"]),
         failed=[c for c in report["checks"] if not c["ok"]], max_corner_error_m=report.get("max_corner_error_m"))
    # 8. ancora da cozinha continua integra apos o job (o consensus nao muda; o gate roda de novo)
    from tools.rooms.kitchen import anchor_rules
    anchor = anchor_rules.validate(consensus, info.room_id)
    step("kitchen_anchor_after", "OK" if anchor["result"] == "PASS" else "FAILED", result=anchor["result"])
    ok = report["ok"] and anchor["result"] == "PASS"
    evidence = {
        "commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or None,
        "capability": plan["capability"], "signature": plan["signature"], "idempotency_key": key,
        "skp": str(out_skp), "skp_sha256": _sha_file(out_skp), "skp_bytes": out_skp.stat().st_size,
        "consensus_sha256": _sha_file(con_path), "base_sha256": trace["base_sha256"],
        "sketchup_version": built["result"].get("sketchup_version"),
        "non_cabinet_fingerprint_before": baseline["result"]["non_cabinet"]["fingerprint"],
        "non_cabinet_fingerprint_after": reopened["result"]["non_cabinet"]["fingerprint"],
        "gates": [{"gate": g["gate"], "result": g["result"]} for g in plan["gates"]],
        "visual_review": "NOT_REVIEWED (nenhum veredito visual automatico)",
    }
    step("evidence", "OK" if ok else "FAILED", **evidence)
    trace["evidence"] = evidence
    finish("DONE_L2_VERIFIED" if ok else "VERIFY_FAILED")
    if ok:
        manifest_p.write_text(json.dumps({**trace, "skp_sha256": evidence["skp_sha256"]}, indent=1, ensure_ascii=False, default=str), "utf-8")
    return trace
