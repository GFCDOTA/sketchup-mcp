"""Fluxo vertical da porta Shaker na cozinha (FP-046): pedido -> gabinete + Shaker salvos, reabertos e inspecionados, com trace.

Encadeia, em um unico trace auditavel e SEM autorizacao implicita:
`request -> projeto/comodo -> consensus+base -> especialista (binding, capacidade, insumos, allowlist) -> planos do pai (4 gates) e da
Shaker (composicao final, 4 gates) -> require_valid de ambos -> job SketchUp (PID) -> .skp salvo -> reabertura+inspecao ->
verificacao plano x modelo -> evidencia (hashes, commit, versoes)`.

Garantias: roda numa COPIA da base (nunca o original, nunca fixtures/artifacts); qualquer bloqueio devolve um estado `BLOCKED_*`
ANTES de subir o SketchUp; so ferramentas da allowlist do perfil; cada PID que subimos e fechado pelo PID; mesma chave de
idempotencia nao refaz. Nao emite veredito visual (`PENDING_HUMAN`).

Este fluxo NAO tem contorno: se o catalogo/perfil deixarem de liberar a Shaker (capacidade ausente, evidencia velha, ferramenta fora
da allowlist), o especialista bloqueia e o fluxo para. O pedido tambem precisa PEDIR Shaker (o binding tem de ser selecionado pelo
texto): um bloco `shaker` num pedido que fala so de "gabinete liso" e recusado, e um pedido de Shaker no fluxo de frentes lisas
(`cabinet_flow.run_request`) tambem — nenhum dos dois constroi a peca errada em silencio.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

from tools.rooms import capability_catalog as cc
from tools.rooms import specialists as sp

from .cabinet_flow import CONSENSUS_DEFAULT, ROOT, _canon, _sha_file, inputs_to_cabinet_request

TRACE_SCHEMA = "kitchen_shaker_trace.v2"
SHAKER_BINDING = "bind.kitchen.shaker"
FLOW_TOOLS = (
    "python:tools.rooms.kitchen.capabilities.cabinet.plan_kitchen_cabinet",
    "python:tools.rooms.kitchen.capabilities.shaker.plan_kitchen_shaker",
    "python:tools.rooms.shared.cabinet.plan.plan_cabinet",
    "python:tools.rooms.shared.cabinet.plan.require_valid",
    "python:tools.rooms.shared.cabinet.shaker.plan.plan_shaker_door",
    "python:tools.rooms.shared.cabinet.shaker.plan.require_valid_shaker",
    "python:tools.rooms.shared.cabinet.shaker.sketchup.materialize_shaker",
    "python:tools.rooms.shared.cabinet.shaker.sketchup.inspect_shaker",
    "python:tools.rooms.shared.cabinet.sketchup.materialize",
    "ruby:tools/rooms/shared/cabinet/ruby/cabinet_build.rb",
    "ruby:tools/rooms/shared/cabinet/ruby/shaker_build.rb",
    "ruby:tools/rooms/shared/cabinet/ruby/shaker_inspect.rb",
)
SHAKER_QUANTITIES = ("frame.stile_width", "frame.rail_height", "frame.frame_thickness", "panel.thickness", "panel.recess_from_frame_front")
SHAKER_MATERIALS = ("frame", "panel")


def shaker_inputs(block: dict) -> dict:
    """Bloco `shaker_door_request.v1` -> insumos achatados `shaker.*` que o catalogo de capacidades exige (valor, unidade, origem).
    Nao inventa nada: o que falta no bloco continua faltando e o especialista devolve `BLOCKED_INPUT_INCOMPLETE`."""
    out: dict = {}
    for name in SHAKER_QUANTITIES:
        group, _, field = name.partition(".")
        node = (block.get(group) or {}).get(field) if isinstance(block, dict) else None
        if isinstance(node, dict):
            out[f"shaker.{name}"] = node
    for role in SHAKER_MATERIALS:
        value = ((block.get("materials") or {}).get(role)) if isinstance(block, dict) else None
        if isinstance(value, str) and value.strip():
            out[f"shaker.materials.{role}"] = {"value": value, "unit": "text", "origin": "user_request"}
    return out


def run_request(request: dict, *, out_dir: str | Path, base_skp: str | Path, consensus_path: str | Path | None = None,
                project: str = "planta_74", su=None, mode: str | None = None, close_pids: bool = True) -> dict:
    """request: {request_id, text, room?, touches?, inputs{...}, materials{...}, grain?, shaker{shaker_door_request.v1}}."""
    from core.domain.room_registry import room_info
    from tools.rooms.kitchen import anchor_rules
    from tools.rooms.kitchen.capabilities.shaker import plan_kitchen_shaker
    from tools.rooms.shared.cabinet import PlanRefused, require_valid
    from tools.rooms.shared.cabinet import sketchup as cs
    from tools.rooms.shared.cabinet.shaker import ShakerPlanRefused, require_valid_shaker
    from tools.rooms.shared.cabinet.shaker import sketchup as ss
    from tools.sketchup import jobs

    request_in = copy.deepcopy(request)
    out_dir, base = Path(out_dir).resolve(), Path(base_skp).resolve()
    con_path = Path(consensus_path or CONSENSUS_DEFAULT).resolve()
    trace: dict = {"schema_version": TRACE_SCHEMA, "request_id": request["request_id"], "steps": [], "state": None,
                   "execution_authorized": False, "pids": [], "visual_review": "PENDING_HUMAN"}
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

    def track(res: dict) -> None:
        if res.get("pid"):
            launched.append(int(res["pid"]))

    step("request", "OK", request_sha256=hashlib.sha256(_canon(request).encode()).hexdigest(), text=request.get("text"))
    info = room_info("kitchen", project_id=project)
    step("project_room", "OK", project=project, room_id=info.room_id, display_name=info.display_name, room_type=info.room_type)
    if not con_path.is_file() or not base.is_file():
        step("consensus_requirements", "BLOCKED", reason=f"consensus/base ausente: {con_path if not con_path.is_file() else base}")
        return finish("BLOCKED_INPUT_MISSING")
    consensus = json.loads(con_path.read_text("utf-8"))
    trace["base_sha256"] = _sha_file(base)
    step("consensus_requirements", "OK", consensus_sha256=_sha_file(con_path), base_skp=str(base), base_sha256=trace["base_sha256"])

    # especialista: o veredito REAL (binding, capacidade, insumos achatados, allowlist, evidencia nao velha)
    catalog = cc.load_catalog()
    shaker_req = request.get("shaker")
    sp_req = {k: request[k] for k in ("text", "room", "tool", "touches") if k in request}
    sp_req.setdefault("room", "kitchen")
    sp_req["inputs"] = {**(request.get("inputs") or {}), **shaker_inputs(shaker_req or {})}
    splan = sp.plan(sp_req)
    selected = [b for b in catalog["bindings"] if b["id"] in [splan.get("binding"), *splan.get("also_matched", [])]]
    video = json.loads((ROOT / catalog["knowledge_catalogs"]["video"]).read_text("utf-8"))
    env = json.loads((ROOT / catalog["knowledge_catalogs"]["environment"]).read_text("utf-8"))
    sources = {s["id"]: s for s in video["sources"] + env["sources"]}
    shaker_binding = next((b for b in catalog["bindings"] if b["id"] == SHAKER_BINDING), None)
    step("knowledge", "OK" if shaker_binding else "NONE", binding=SHAKER_BINDING, capability_id=(shaker_binding or {}).get("capability_id"),
         source_ids=(shaker_binding or {}).get("source_ids", []),
         source_evidence={s: sources[s]["evidence"] for s in (shaker_binding or {}).get("source_ids", []) if s in sources},
         human_review={s: sources[s]["human_review"] for s in (shaker_binding or {}).get("source_ids", [])
                       if s in sources and sources[s].get("human_review")},
         recipe_ids=(shaker_binding or {}).get("recipe_ids", []))
    if splan["state"] != sp.PLAN_READY:
        step("specialist_plan", "BLOCKED", state=splan["state"], reason=splan.get("reason"), next_step=splan.get("next_step"),
             gap=splan.get("gap"), missing=splan.get("missing"))
        return finish(splan["state"], reason=splan.get("reason"), next_step=splan.get("next_step"))
    if SHAKER_BINDING not in [b["id"] for b in selected]:
        step("specialist_plan", "BLOCKED", state="BLOCKED_TECHNIQUE_UNRESOLVED", selected=[b["id"] for b in selected])
        return finish("BLOCKED_TECHNIQUE_UNRESOLVED", reason="o texto do pedido nao pede porta Shaker; um bloco 'shaker' nao basta",
                      next_step="descrever a porta Shaker no pedido ou usar o fluxo de frentes lisas")
    step("specialist_plan", "OK", state=splan["state"], capability=splan["capability"], steps=[s["tool"] for s in splan["steps"]],
         selected=[b["id"] for b in selected])
    step("capability", "OK", **splan["capability"])
    if not isinstance(shaker_req, dict):                      # inalcancavel com insumos completos; defesa em profundidade
        return finish("BLOCKED_INPUT_INCOMPLETE", reason="faltou o bloco 'shaker'")
    ctx = shaker_req.get("origin_context") if isinstance(shaker_req.get("origin_context"), dict) else {}
    if ctx.get("source_verified") is True and not (sources.get(ctx.get("source_id")) or {}).get("human_review"):
        step("source_review", "BLOCKED", source_id=ctx.get("source_id"))
        return finish("BLOCKED_KNOWLEDGE_EVIDENCE", reason=f"o pedido declara source_verified=true para {ctx.get('source_id')!r}, "
                      "mas o catalogo nao tem revisao humana registrada para essa fonte (a fonte nunca e presumida)")

    # planos: pai (4 gates) -> Shaker -> composicao final (gates); so entao require_valid
    cab_req = inputs_to_cabinet_request(request["request_id"], request["inputs"], request.get("materials") or {}, request.get("grain"))
    planned = plan_kitchen_shaker(consensus, info.room_id, cab_req, shaker_req)
    parent, shaker = planned["parent_plan"], planned["shaker_plan"]
    step("plan_validation", "OK" if planned["status"] == "OK" else "BLOCKED", result_status=planned["status"], stage=planned["stage"],
         parent_gates=parent.get("gates"), shaker_gates=planned["gates"], parent_signature=parent.get("signature"),
         shaker_signature=(shaker or {}).get("signature"), findings=(shaker or parent).get("findings"))
    try:
        require_valid(parent)
        if shaker is None:
            raise ShakerPlanRefused(parent.get("findings") or [{"code": "NO_SHAKER_PLAN", "detail": planned["stage"]}])
        require_valid_shaker(shaker, parent)
    except (PlanRefused, ShakerPlanRefused) as exc:
        return finish("BLOCKED_PLAN_REFUSED", reason=str(exc), findings=exc.findings)
    outside = [t for t in FLOW_TOOLS if t not in profile["tool_allowlist"]]
    if outside:
        step("allowlist", "BLOCKED", reason=f"ferramentas fora da allowlist do perfil kitchen: {outside}")
        return finish("BLOCKED_TOOL_NOT_ALLOWED", reason=f"fora da allowlist: {outside}")
    step("allowlist", "OK", tools=list(FLOW_TOOLS))

    # idempotencia + job: base -> (pai) -> (pai + Shaker), sempre em copias
    key = hashlib.sha256(_canon({"request": hashlib.sha256(_canon(request).encode()).hexdigest(), "consensus": _sha_file(con_path),
                                  "base": trace["base_sha256"], "parent": parent["signature"],
                                  "shaker": shaker["signature"]}).encode()).hexdigest()
    job_dir = out_dir / key[:12]
    manifest_p, out_skp, parent_skp = job_dir / "manifest.json", job_dir / "kitchen_shaker.skp", job_dir / "kitchen_parent.skp"
    trace["idempotency_key"] = key
    if manifest_p.is_file() and out_skp.is_file():
        prior = json.loads(manifest_p.read_text("utf-8"))
        if prior.get("idempotency_key") == key and prior.get("skp_sha256") == _sha_file(out_skp) and prior.get("state") == "DONE_L2_VERIFIED":
            step("job", "SKIPPED", reason="mesma chave de idempotencia ja concluida e integra")
            return finish("ALREADY_DONE", prior_manifest=str(manifest_p), skp=str(out_skp), skp_sha256=prior["skp_sha256"])
    job_dir.mkdir(parents=True, exist_ok=True)
    baseline = ss.inspect_shaker(base, mode=mode, su=su)
    track(baseline)
    if baseline["status"] != "OK":
        step("baseline_inspect", "FAILED", result_status=baseline["status"], reason=baseline.get("reason"))
        return finish("JOB_FAILED", reason="baseline da base nao inspecionado")
    step("baseline_inspect", "OK", pid=baseline.get("pid"), non_cabinet=baseline["result"]["non_cabinet"])
    built_parent = cs.materialize(parent, parent_skp, base_skp=base, mode=mode, su=su)
    track(built_parent)
    if built_parent["status"] != "OK":
        step("job_parent", "FAILED", result_status=built_parent["status"], reason=built_parent.get("reason"))
        return finish("JOB_FAILED", reason=built_parent.get("reason") or built_parent["status"])
    step("job_parent", "OK", pid=built_parent.get("pid"), sketchup_version=built_parent["result"].get("sketchup_version"))
    built = ss.materialize_shaker(shaker, parent, out_skp, base_skp=parent_skp, mode=mode, su=su)
    track(built)
    if built["status"] != "OK":
        step("job_shaker", "FAILED", result_status=built["status"], reason=built.get("reason"),
             unedited_copy_removed=built.get("unedited_copy_removed"))
        return finish("JOB_FAILED", reason=built.get("reason") or built["status"])
    step("job_shaker", "OK", pid=built.get("pid"), sketchup_version=built["result"].get("sketchup_version"), out_skp=str(out_skp),
         removed_front=built["result"].get("removed_front"), grain_support=built["result"].get("grain_support"))
    reopened = ss.inspect_shaker(out_skp, mode=mode, su=su)
    track(reopened)
    if reopened["status"] != "OK":
        step("reopen_inspection", "FAILED", result_status=reopened["status"], reason=reopened.get("reason"))
        return finish("JOB_FAILED", reason="reabertura nao inspecionada")
    report = ss.verify_shaker(shaker, parent, reopened["result"], baseline=baseline["result"])
    step("reopen_inspection", "OK" if report["ok"] else "FAILED", pid=reopened.get("pid"), checks=len(report["checks"]),
         failed=[c for c in report["checks"] if not c["ok"]], max_corner_error_m=report.get("max_corner_error_m"))
    anchor = anchor_rules.validate(consensus, info.room_id)
    step("kitchen_anchor_after", "OK" if anchor["result"] == "PASS" else "FAILED", result=anchor["result"])
    ok = report["ok"] and anchor["result"] == "PASS"
    evidence = {
        "commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or None,
        "capability": shaker["capability"], "parent_capability": parent["capability"],
        "specialist_capability": splan["capability"],
        "parent_signature": parent["signature"], "shaker_signature": shaker["signature"], "idempotency_key": key,
        "skp": str(out_skp), "skp_sha256": _sha_file(out_skp), "skp_bytes": out_skp.stat().st_size,
        "consensus_sha256": _sha_file(con_path), "base_sha256": trace["base_sha256"],
        "sketchup_version": built["result"].get("sketchup_version"),
        "non_cabinet_fingerprint_before": baseline["result"]["non_cabinet"]["fingerprint"],
        "non_cabinet_fingerprint_after": reopened["result"]["non_cabinet"]["fingerprint"],
        "gates": {"parent": [{"gate": g["gate"], "result": g["result"]} for g in parent["gates"]],
                  "composition": [{"gate": g["gate"], "result": g["result"]} for g in planned["gates"]]},
        "source_verified": shaker["origin_context"]["source_verified"],
        "visual_review": "PENDING_HUMAN (nenhum veredito visual automatico)",
    }
    step("evidence", "OK" if ok else "FAILED", **evidence)
    trace["evidence"] = evidence
    finish("DONE_L2_VERIFIED" if ok else "VERIFY_FAILED")
    if ok:
        manifest_p.write_text(json.dumps({**trace, "skp_sha256": evidence["skp_sha256"]}, indent=1, ensure_ascii=False, default=str), "utf-8")
    return trace
