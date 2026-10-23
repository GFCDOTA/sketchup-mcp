"""L2 da FP-054 F1-01 (#380): os fluxos de gabinete da cozinha depois do contrato novo do `circulation_gate`.

A cozinha da planta_74 tem 1 portal: o gate de circulacao agora devolve NOT_APPLICABLE (antes, PASS sem medir nada). Os planos
de frentes lisas e Shaker passam a REGISTRAR o N/A com o motivo e seguem; FAIL e BLOCKED_MISSING_INPUT continuam recusando.
Base: `promotion_l2/l2_promoted.py` (Shaker) + `p7_kitchen_cabinet/l2_p7.py` (frentes lisas), mais os negativos novos.

Roda do repo (cwd = raiz do worktree), com `PYTHONPATH=.` e `PT_TO_M=0.0259`:
    python artifacts/review/fp054/f1_circulation_l2/l2_f1_circulation.py <saida em runs/> <copia do .skp mobiliado>
Pedidos: os mesmos das provas anteriores (`fp043/p7_kitchen_cabinet/request.json`, `fp046/promotion_l2/request.json`).
Fecha SO os PIDs que subiu; SHA-256 dos canonicos conferido antes e depois; sai != 0 se algum caso falhar.
"""
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from tools.rooms.kitchen.capabilities import shaker_flow
from tools.rooms.kitchen.capabilities.cabinet_flow import run_request as plain_run
from tools.validation import circulation_gate as cg
from tools.validation import room_regression_diff as rd
from tools.validation import room_regression_gates as gates

OUT = Path(sys.argv[1]).resolve()
BASE = Path(sys.argv[2]).resolve()
PLAIN_REQ = json.loads(Path("artifacts/review/fp043/p7_kitchen_cabinet/request.json").read_text("utf-8"))
SHAKER_REQ = json.loads(Path("artifacts/review/fp046/promotion_l2/request.json").read_text("utf-8"))
OUT.mkdir(parents=True, exist_ok=True)
CANONICAL = ("artifacts/planta_74/planta_74.skp", "artifacts/planta_74/furnished/planta_74_furnished.skp",
             "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")


def sha(path):
    data = Path(path).read_bytes()
    return hashlib.sha256(data.replace(b"\r\n", b"\n") if str(path).endswith(".json") else data).hexdigest()


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def steps(trace):
    return [(s["step"], s["status"]) for s in trace["steps"]]


def circulation_gates(trace):
    """Registros do gate de circulacao nos planos (passo `plan_validation` do trace: frentes lisas = `gates`; Shaker = pai +
    composicao)."""
    st = next((x for x in trace["steps"] if x["step"] == "plan_validation"), {})
    rows = (st.get("gates") or []) + (st.get("parent_gates") or []) + (st.get("shaker_gates") or [])
    return [g for g in rows if g.get("gate") == "circulation"]


summary = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
           "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
           "canonical_before": {p: sha(p) for p in CANONICAL}, "cases": [], "pids": []}


def case(name, ok, **data):
    summary["cases"].append({"case": name, "ok": bool(ok), **data})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


before = rd.capture()
con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json").read_text("utf-8"))
gates_before = gates.run(con, [p["box"] for p in before["parts"]])
kitchen = cg.gate(con, [p["box"] for p in before["parts"]], "r004")
case("kitchen_gate_is_not_applicable_not_pass", kitchen["result"] == "NOT_APPLICABLE"
     and kitchen["checks"]["corredor_principal"]["reason_code"] == "SINGLE_PORTAL",
     result=kitchen["result"], reasons={k: v.get("reason_code") for k, v in kitchen["checks"].items()})

# --- 1. frentes lisas (P7), SketchUp real
t = plain_run(copy.deepcopy(PLAIN_REQ), out_dir=OUT / "plain", base_skp=BASE, mode="interactive", close_pids=True)
dump("plain_trace.json", t)
summary["pids"] += list(t.get("pids", []))
reopen = next((s for s in t["steps"] if s["step"] == "reopen_inspection"), {})
circ = circulation_gates(t)
case("positive_plain_fronts", t["state"] == "DONE_L2_VERIFIED" and t["input_unchanged"] is True,
     state=t["state"], steps=steps(t), checks=reopen.get("checks"), max_corner_error_m=reopen.get("max_corner_error_m"),
     skp_sha256=t.get("evidence", {}).get("skp_sha256"), sketchup_version=t.get("evidence", {}).get("sketchup_version"))
case("plain_plan_records_circulation_not_applicable", len(circ) == 1 and "NOT_APPLICABLE" in circ[0]["detail"]
     and "circulation_gate PASS" not in circ[0]["detail"], circulation=circ)
again = plain_run(copy.deepcopy(PLAIN_REQ), out_dir=OUT / "plain", base_skp=BASE, mode="interactive", close_pids=True)
case("plain_same_key_already_done", again["state"] == "ALREADY_DONE" and not again["pids"], state=again["state"])

# --- 2. Shaker (promocao FP-046), SketchUp real
s = shaker_flow.run_request(copy.deepcopy(SHAKER_REQ), out_dir=OUT / "shaker", base_skp=BASE, mode="interactive")
dump("shaker_trace.json", s)
summary["pids"] += list(s.get("pids", []))
ev = s.get("evidence", {})
reopen = next((x for x in s["steps"] if x["step"] == "reopen_inspection"), {})
know = next((x for x in s["steps"] if x["step"] == "knowledge"), {})
case("positive_kitchen_shaker", s["state"] == "DONE_L2_VERIFIED" and s["input_unchanged"] is True
     and ev.get("non_cabinet_fingerprint_before") == ev.get("non_cabinet_fingerprint_after")
     and know.get("capability_id") == "kitchen.cabinet.shaker-door",
     state=s["state"], steps=steps(s), checks=reopen.get("checks"), max_corner_error_m=reopen.get("max_corner_error_m"),
     skp_sha256=ev.get("skp_sha256"), sketchup_version=ev.get("sketchup_version"))
shaker_circ = circulation_gates(s)
case("shaker_gates_record_circulation_not_applicable", len(shaker_circ) == 2
     and all("NOT_APPLICABLE" in g["detail"] and "circulation_gate PASS" not in g["detail"] for g in shaker_circ),
     circulation=shaker_circ)
again = shaker_flow.run_request(copy.deepcopy(SHAKER_REQ), out_dir=OUT / "shaker", base_skp=BASE, mode="interactive")
case("shaker_same_key_already_done", again["state"] == "ALREADY_DONE" and not again["pids"], state=again["state"])

# --- 3. negativos (nenhum sobe o SketchUp)
neg = {}


def negative(name, runner, req, expected, sub):
    r = runner(req, sub)
    neg[name] = {"state": r["state"], "pids": r["pids"], "reason": r.get("reason")}
    case("negative_" + name, r["state"] == expected and not r["pids"] and "evidence" not in r and not (OUT / sub).exists(),
         state=r["state"], expected=expected)


def plain_runner(req, sub):
    return plain_run(req, out_dir=OUT / sub, base_skp=BASE, mode="interactive", close_pids=True)


def shaker_runner(req, sub):
    return shaker_flow.run_request(req, out_dir=OUT / sub, base_skp=BASE, mode="interactive")


# o novo: circulacao BLOCKED_MISSING_INPUT (portal descartado) recusa antes do SketchUp, nos dois fluxos
real_points = cg._portal_points
cg._portal_points = lambda sm, cell: (real_points(sm, cell)[0], [{"zone": 0, "why": "portal forcado ausente (negativo L2)"}])
try:
    negative("plain_circulation_blocked_missing_input", plain_runner,
             {**copy.deepcopy(PLAIN_REQ), "request_id": "neg-circ-blocked"}, "BLOCKED_PLAN_REFUSED", "neg_plain_circ")
    negative("shaker_circulation_blocked_missing_input", shaker_runner,
             {**copy.deepcopy(SHAKER_REQ), "request_id": "neg-shaker-circ-blocked"}, "BLOCKED_PLAN_REFUSED", "neg_shaker_circ")
finally:
    cg._portal_points = real_points
outside = copy.deepcopy(PLAIN_REQ)
outside["request_id"] = "neg-pose"
outside["inputs"]["pose.x"] = {"value": 0.5, "unit": "m", "origin": "user_request"}
outside["inputs"]["pose.y"] = {"value": 0.5, "unit": "m", "origin": "user_request"}
negative("plain_pose_outside_kitchen", plain_runner, outside, "BLOCKED_PLAN_REFUSED", "neg_plain_pose")
arch = copy.deepcopy(SHAKER_REQ)
arch["text"] += " e remover a parede oeste"
negative("shaker_architecture_change", shaker_runner, arch, "BLOCKED_ARCHITECTURE_CHANGE", "neg_shaker_arch")
other_recipe = copy.deepcopy(SHAKER_REQ)
other_recipe["shaker"]["origin_context"] = {"recipe_id": "cabinet.countertop-separate-and-bevel",
                                            "source_id": "yt-cabinet-tips-2021", "source_verified": True}
negative("shaker_source_verified_for_another_recipe", shaker_runner, other_recipe, "BLOCKED_KNOWLEDGE_EVIDENCE", "neg_shaker_recipe")
dump("negatives.json", neg)

# --- 4. depois: canonicos, snapshot e gates (FP-047 strict_identity)
after = rd.capture()
gates_after = gates.run(con, [p["box"] for p in after["parts"]])
contract = {"schema_version": "room_regression_request.v1", "change_id": "fp054-f1-01-circulation-contract-l2", "fixture": "planta_74",
            "change_mode": "strict_identity", "control_rooms": ["r000", "r001", "r002", "r003", "r005", "r006", "r007"],
            "protect_canonicals": True, "require_l2": False, "require_l3_if_visual_changed": True, "pt_to_m": 0.0259}
report = rd.compare(before, after, contract, canonical_before=before["source_digests"], canonical_after=after["source_digests"],
                    gates_before=gates_before, gates_after=gates_after)
dump("fp047_report.json", {k: v for k, v in report.items() if k != "room_results"})
case("fp047_strict_identity_planned_boxes_and_canonicals", report["state"] == "PASS" and report["canonical_hashes_unchanged"] is True,
     state=report["state"], preexisting=report["evidence"].get("preexisting_gate_findings"), delta_count=report["evidence"]["delta_count"])
summary["canonical_after"] = {p: sha(p) for p in CANONICAL}
case("canonicals_byte_identical", summary["canonical_before"] == summary["canonical_after"])
leftovers = [str(p) for p in Path("artifacts/planta_74").rglob("*") if p.is_file() and p.parent.name.startswith("_")]
case("no_scratch_left_inside_artifacts", not leftovers, leftovers=leftovers)

summary["note"] = ("FP-054 F1-01: contrato do circulation_gate (BLOCKED_MISSING_INPUT/NOT_APPLICABLE). Cozinha = 1 portal -> N/A registrado; "
                   "aparencia PENDING_HUMAN; valores dos pedidos sao os das provas P7 e FP-046")
dump("summary.json", summary)
print("TOTAL", len(summary["cases"]), "ok=", sum(c["ok"] for c in summary["cases"]), "pids", len(summary["pids"]))
sys.exit(0 if all(c["ok"] for c in summary["cases"]) else 1)
