"""L2 da FP-046/P4: fluxo opt-in da porta Shaker na COZINHA REAL da planta_74, no SketchUp real, numa COPIA do .skp mobiliado.

Roda do repo (cwd = raiz do worktree), com `PYTHONPATH=.` e `PT_TO_M=0.0259`:
    python artifacts/review/fp046/p4_kitchen_shaker_l2/l2_p4.py <saida> <base_mobiliado.skp> <request.json>
`<saida>` fora de fixtures/ e artifacts/ (use runs/...). A base e o .skp mobiliado canonico: aqui ela e COPIADA pelo driver, nunca aberta,
e o SHA-256 de canonicos/consensus e conferido antes e depois. Fecha SO os PIDs que subiu. Nada e promovido: o fluxo roda com
`prepromotion_ack=True` (argumento de codigo), estado final esperado `PREPROMOTION_L2_VERIFIED`, aparencia `PENDING_HUMAN`.
"""
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from tools.rooms.kitchen.capabilities import shaker_flow
from tools.validation import room_regression_diff as rd
from tools.validation import room_regression_gates as gates

OUT = Path(sys.argv[1]).resolve()
BASE = Path(sys.argv[2]).resolve()
REQUEST = json.loads(Path(sys.argv[3]).read_text("utf-8"))
OUT.mkdir(parents=True, exist_ok=True)
CANONICAL = ("artifacts/planta_74/planta_74.skp", "artifacts/planta_74/furnished/planta_74_furnished.skp",
             "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")


def sha(path):
    data = Path(path).read_bytes()
    return hashlib.sha256(data.replace(b"\r\n", b"\n") if str(path).endswith(".json") else data).hexdigest()


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def states(trace):
    return [(s["step"], s["status"]) for s in trace["steps"]]


summary = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
           "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
           "base_copy_source_sha256": sha(BASE), "canonical_before": {p: sha(p) for p in CANONICAL}, "cases": []}


def case(name, ok, **data):
    summary["cases"].append({"case": name, "ok": bool(ok), **data})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


# --- FP-047 antes: snapshot + gates das caixas planejadas (a Shaker nao entra no planner; mobilia nao pode mudar)
before = rd.capture()
con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json").read_text("utf-8"))
gates_before = gates.run(con, [p["box"] for p in before["parts"]])

# --- 1. positivo: com ack, cozinha real
t = shaker_flow.run_prepromotion_request(copy.deepcopy(REQUEST), out_dir=OUT / "flow", base_skp=BASE, prepromotion_ack=True, mode="interactive")
dump("trace.json", t)
summary["pids"] = list(t.get("pids", []))
ev = t.get("evidence", {})
case("positive_kitchen_shaker", t["state"] == "PREPROMOTION_L2_VERIFIED" and t["promotion"] == "NOT_PROMOTED"
     and ev.get("non_cabinet_fingerprint_before") == ev.get("non_cabinet_fingerprint_after") and t["input_unchanged"] is True,
     state=t["state"], steps=states(t), checks=next((s.get("checks") for s in t["steps"] if s["step"] == "reopen_inspection"), None),
     max_corner_error_m=next((s.get("max_corner_error_m") for s in t["steps"] if s["step"] == "reopen_inspection"), None),
     gates=ev.get("gates"), skp_sha256=ev.get("skp_sha256"), sketchup_version=ev.get("sketchup_version"))

# --- 2. idempotencia: mesma chave nao refaz (nenhum SketchUp)
again = shaker_flow.run_prepromotion_request(copy.deepcopy(REQUEST), out_dir=OUT / "flow", base_skp=BASE, prepromotion_ack=True, mode="interactive")
case("same_key_already_done", again["state"] == "ALREADY_DONE" and not again["pids"], state=again["state"])

# --- 3. negativos reais (nenhum sobe o SketchUp)
neg = {}
default = shaker_flow.run_prepromotion_request(copy.deepcopy(REQUEST), out_dir=OUT / "neg_default", base_skp=BASE, mode="interactive")
neg["default_no_ack"] = {"state": default["state"], "pids": default["pids"]}
case("default_blocked_capability_missing", default["state"] == "BLOCKED_CAPABILITY_MISSING" and not default["pids"] and not (OUT / "neg_default").exists())

outside = copy.deepcopy(REQUEST)
outside["inputs"]["pose.x"] = {"value": 0.5, "unit": "m", "origin": "user_request"}
r = shaker_flow.run_prepromotion_request(outside, out_dir=OUT / "neg_outside", base_skp=BASE, prepromotion_ack=True, mode="interactive")
neg["pose_outside_kitchen"] = {"state": r["state"], "pids": r["pids"]}
case("pose_outside_kitchen_refused_before_job", r["state"] == "BLOCKED_PLAN_REFUSED" and not r["pids"] and not (OUT / "neg_outside").exists())

arch = copy.deepcopy(REQUEST)
arch["text"] += " e remover a parede oeste"
r = shaker_flow.run_prepromotion_request(arch, out_dir=OUT / "neg_arch", base_skp=BASE, prepromotion_ack=True, mode="interactive")
neg["architecture_change"] = {"state": r["state"], "pids": r["pids"]}
case("architecture_change_blocked_even_with_ack", r["state"] == "BLOCKED_ARCHITECTURE_CHANGE" and not r["pids"])

thick = copy.deepcopy(REQUEST)
thick["shaker"]["frame"]["frame_thickness"] = {"value": 20, "unit": "mm", "origin": "user_request"}
r = shaker_flow.run_prepromotion_request(thick, out_dir=OUT / "neg_thick", base_skp=BASE, prepromotion_ack=True, mode="interactive")
neg["frame_thickness_mismatch"] = {"state": r["state"], "pids": r["pids"]}
case("shaker_geometry_refused_before_job", r["state"] == "BLOCKED_PLAN_REFUSED" and not r["pids"])
dump("negatives.json", neg)

# --- 4. depois: canonicos, snapshot e gates (FP-047, strict_identity: a Shaker nao pode mexer no planejado do apartamento)
after = rd.capture()
gates_after = gates.run(con, [p["box"] for p in after["parts"]])
contract = {"schema_version": "room_regression_request.v1", "change_id": "fp046-p4-kitchen-shaker-l2", "fixture": "planta_74",
            "change_mode": "strict_identity", "control_rooms": ["r000", "r001", "r002", "r003", "r005", "r006", "r007"],
            "protect_canonicals": True, "require_l2": False, "require_l3_if_visual_changed": True, "pt_to_m": 0.0259}
report = rd.compare(before, after, contract, canonical_before=before["source_digests"], canonical_after=after["source_digests"],
                    gates_before=gates_before, gates_after=gates_after)
dump("fp047_report.json", {k: v for k, v in report.items() if k != "room_results"})
case("fp047_strict_identity_planned_boxes_and_canonicals", report["state"] == "PASS" and report["canonical_hashes_unchanged"] is True,
     state=report["state"], preexisting=report["evidence"].get("preexisting_gate_findings"), delta_count=report["evidence"]["delta_count"])
summary["canonical_after"] = {p: sha(p) for p in CANONICAL}
case("canonicals_byte_identical", summary["canonical_before"] == summary["canonical_after"])

summary["note"] = ("PRE-PROMOCAO: binding bind.kitchen.shaker segue sem capability (D46-09); nada entrou no catalogo/perfil; "
                   "veio NOT_SUPPORTED; aparencia PENDING_HUMAN; valores da porta sao do pedido de teste, nao decisao de design")
dump("summary.json", summary)
print("TOTAL", len(summary["cases"]), "ok=", sum(c["ok"] for c in summary["cases"]), "pids", len(summary["pids"]))
sys.exit(0 if all(c["ok"] for c in summary["cases"]) else 1)
