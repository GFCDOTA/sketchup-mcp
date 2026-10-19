"""L2 da P7: pedido inedito -> gabinete na cozinha da planta_74 (copia do .skp mobiliado canonico), salvo, reaberto e inspecionado.
Tambem os negativos reais (sem SketchUp) e o job interrompido de verdade (processo do SketchUp encerrado no meio).
Uso (cwd = repo, PT_TO_M=0.0259): l2_p7.py <saida> <request.json> <base_furnished.skp>"""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from tools.rooms.kitchen.capabilities.cabinet_flow import run_request
from tools.rooms.shared.cabinet import plan_cabinet, sketchup as cs
from tools.sketchup import jobs
from tools.sketchup.process import SketchUp

OUT = Path(sys.argv[1]).resolve()
REQ = json.loads(Path(sys.argv[2]).read_text("utf-8"))
BASE_SRC = Path(sys.argv[3]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
BASE = OUT / "base_copy" / "planta_74_furnished.skp"        # copia de trabalho: o canonico nunca e aberto
BASE.parent.mkdir(exist_ok=True)
shutil.copy2(BASE_SRC, BASE)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731
canon_sha = sha(BASE_SRC)
print("canonico sha", canon_sha[:12], "copia sha", sha(BASE)[:12], flush=True)

# ---------------- positivo (SketchUp real)
trace = run_request(REQ, out_dir=OUT / "jobs", base_skp=BASE, mode="interactive", close_pids=True)
(OUT / "trace.json").write_text(json.dumps(trace, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
print("POSITIVO", trace["state"], [(s["step"], s["status"]) for s in trace["steps"]], flush=True)
assert trace["state"] == "DONE_L2_VERIFIED", trace["steps"][-3:]
skp = Path(trace["evidence"]["skp"])

# ---------------- renders (so ilustracao; nenhum veredito)
r = jobs.render_views(str(skp), views=[{"preset": "top"}, {"preset": "iso"}], width=1600, height=1200, focus_contains="Cabinet_",
                      out_dir=str(OUT / "renders"), mode="interactive")
if r.get("pid"):
    jobs.close(pid=int(r["pid"]), force=True, confirm=True)
print("render", r["status"], flush=True)

# ---------------- negativos reais (nenhum sobe o SketchUp)
def q(v, u, o="user_request"):
    return {"value": v, "unit": u, "origin": o}


negs = {}


def neg(name, req):
    before = (json.dumps(req, sort_keys=True), sha(BASE))
    t = run_request(req, out_dir=OUT / "jobs_neg", base_skp=BASE, mode="interactive", close_pids=True)
    ok = (json.dumps(req, sort_keys=True), sha(BASE)) == before
    negs[name] = {"state": t["state"], "reason": t.get("reason"), "next_step": t.get("next_step"), "no_positive_evidence": "evidence" not in t,
                  "input_and_base_unchanged": ok, "sketchup_launched": bool(t["pids"]), "execution_authorized": t["execution_authorized"]}
    print("NEG", name, negs[name]["state"], flush=True)


neg("shaker_sem_builder", {**copy.deepcopy(REQ), "request_id": "neg-shaker", "text": "armario de cozinha com porta Shaker"})
neg("ferramenta_fora_da_allowlist", {**copy.deepcopy(REQ), "request_id": "neg-tool", "tool": "mcp:su_apply_edits"})
bad = copy.deepcopy(REQ)
bad["request_id"] = "neg-geom"
bad["inputs"]["dimensions.width"] = q(30, "mm")
neg("geometria_impossivel", bad)
bad = copy.deepcopy(REQ)
bad["request_id"] = "neg-unit"
del bad["inputs"]["dimensions.depth"]["unit"]
del bad["inputs"]["dimensions.height"]["origin"]
neg("entrada_sem_unidade_ou_origem", bad)
neg("alterar_arquitetura", {**copy.deepcopy(REQ), "request_id": "neg-arch", "text": "gabinete de cozinha e remover a parede oeste"})
bad = copy.deepcopy(REQ)
bad["request_id"] = "neg-pose"
bad["inputs"]["pose.x"] = q(0.5, "m")
bad["inputs"]["pose.y"] = q(0.5, "m")
neg("pose_fora_da_cozinha_gate_de_arquitetura", bad)
(OUT / "negatives.json").write_text(json.dumps(negs, indent=1, ensure_ascii=False), encoding="utf-8")

# ---------------- job interrompido DE VERDADE: o SketchUp (processo filho) e encerrado no meio do build
from tools.rooms.kitchen.capabilities.cabinet import plan_kitchen_cabinet  # noqa: E402
from tools.rooms.kitchen.capabilities.cabinet_flow import inputs_to_cabinet_request  # noqa: E402

con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json").read_text("utf-8"))
plan = plan_kitchen_cabinet(con, "r004", inputs_to_cabinet_request("interrupted-job", REQ["inputs"], REQ["materials"], REQ.get("grain")))
assert plan["status"] == "OK"
su = SketchUp()
orig_popen = su.system.popen
killed = {}


def popen(cmd, env=None):
    h = orig_popen(cmd, env)
    if str(cmd[-1]).endswith("cabinet_build.rb"):
        killed["pid"] = h.pid
        threading.Timer(6.0, h.terminate).start()      # encerra SO o processo filho que nos subimos (handle), nunca por nome
    return h


su.system.popen = popen
out_int = OUT / "interrupted" / "cabinet.skp"
before_base = sha(BASE)
res = cs.materialize(plan, out_int, base_skp=BASE, mode="interactive", su=su, timeout_s=60)
intr = {"status": res["status"], "reason": res.get("reason"), "killed_pid": killed.get("pid"), "out_skp_exists": out_int.exists(),
        "unedited_copy_removed": res.get("unedited_copy_removed"), "base_unchanged": sha(BASE) == before_base,
        "result_file_exists": (OUT / "interrupted" / "_cabinet_build" / "cabinet_build_result.json").exists(),
        "no_positive_proof": res["status"] != "OK"}
(OUT / "interrupted_job.json").write_text(json.dumps(intr, indent=1), encoding="utf-8")
print("INTERROMPIDO", intr, flush=True)

summary = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "canonical_furnished_sha256": canon_sha,
           "base_copy_sha256": sha(BASE), "canonical_unchanged": sha(BASE_SRC) == canon_sha, "state": trace["state"],
           "negatives": {k: v["state"] for k, v in negs.items()}, "interrupted": intr["status"]}
(OUT / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
print("SUMMARY", summary)
