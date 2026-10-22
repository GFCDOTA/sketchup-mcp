"""L2 do ESCOPO DA REVISAO HUMANA (follow-up do #357): igual ao `promotion_l2/l2_promoted.py` + o negativo real novo
(`source_verified=true` para OUTRA recipe do mesmo video -> `BLOCKED_KNOWLEDGE_EVIDENCE`, 0 PIDs). Fluxo `shaker_flow.run_request` na COZINHA REAL da planta_74, SketchUp real, numa COPIA do .skp mobiliado.

Roda do repo (cwd = raiz do worktree), com `PYTHONPATH=.` e `PT_TO_M=0.0259`:
    python artifacts/review/fp046/review_scope_l2/l2_review_scope.py <saida> <base_mobiliado.skp> artifacts/review/fp046/promotion_l2/request.json
`<saida>` fora de fixtures/ e artifacts/ (use runs/...). Nao ha contorno: o fluxo roda porque o catalogo/perfil liberam a Shaker
(binding -> kitchen.cabinet.shaker-door, fonte inspecionada com revisao humana). Fecha SO os PIDs que subiu; SHA-256 dos canonicos
conferido antes e depois.
"""
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from tools.rooms.kitchen.capabilities import shaker_flow
from tools.rooms.kitchen.capabilities.cabinet_flow import run_request as plain_run
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


def steps(trace):
    return [(s["step"], s["status"]) for s in trace["steps"]]


summary = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
           "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
           "canonical_before": {p: sha(p) for p in CANONICAL}, "cases": []}


def case(name, ok, **data):
    summary["cases"].append({"case": name, "ok": bool(ok), **data})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def run(req, sub, **kw):
    return shaker_flow.run_request(req, out_dir=OUT / sub, base_skp=BASE, mode="interactive", **kw)


before = rd.capture()
con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json").read_text("utf-8"))
gates_before = gates.run(con, [p["box"] for p in before["parts"]])

# --- 1. positivo: cozinha real, sem nenhum argumento de contorno
t = run(copy.deepcopy(REQUEST), "flow")
dump("trace.json", t)
summary["pids"] = list(t.get("pids", []))
ev = t.get("evidence", {})
know = next((s for s in t["steps"] if s["step"] == "knowledge"), {})
reopen = next((s for s in t["steps"] if s["step"] == "reopen_inspection"), {})
case("positive_kitchen_shaker_promoted", t["state"] == "DONE_L2_VERIFIED"
     and ev.get("non_cabinet_fingerprint_before") == ev.get("non_cabinet_fingerprint_after") and t["input_unchanged"] is True
     and know.get("capability_id") == "kitchen.cabinet.shaker-door" and "yt-cabinet-tips-2021" in know.get("human_review", {}),
     state=t["state"], steps=steps(t), checks=reopen.get("checks"), max_corner_error_m=reopen.get("max_corner_error_m"),
     gates=ev.get("gates"), skp_sha256=ev.get("skp_sha256"), sketchup_version=ev.get("sketchup_version"),
     source_evidence=know.get("source_evidence"), human_review=know.get("human_review"))

# --- 2. idempotencia
again = run(copy.deepcopy(REQUEST), "flow")
case("same_key_already_done", again["state"] == "ALREADY_DONE" and not again["pids"], state=again["state"])

# --- 3. negativos reais (nenhum sobe o SketchUp)
neg = {}


def negative(name, req, expected):
    r = run(req, "neg_" + name)
    neg[name] = {"state": r["state"], "pids": r["pids"], "reason": r.get("reason"), "next_step": r.get("next_step")}
    case("negative_" + name, r["state"] == expected and not r["pids"] and "evidence" not in r and not (OUT / ("neg_" + name)).exists(),
         state=r["state"], expected=expected)


no_block = copy.deepcopy(REQUEST)
del no_block["shaker"]
negative("without_shaker_block", no_block, "BLOCKED_INPUT_INCOMPLETE")
outside = copy.deepcopy(REQUEST)
outside["inputs"]["pose.x"] = {"value": 0.5, "unit": "m", "origin": "user_request"}
negative("pose_outside_kitchen", outside, "BLOCKED_PLAN_REFUSED")
arch = copy.deepcopy(REQUEST)
arch["text"] += " e remover a parede oeste"
negative("architecture_change", arch, "BLOCKED_ARCHITECTURE_CHANGE")
thick = copy.deepcopy(REQUEST)
thick["shaker"]["frame"]["frame_thickness"] = {"value": 20, "unit": "mm", "origin": "user_request"}
negative("frame_thickness_mismatch", thick, "BLOCKED_PLAN_REFUSED")
liso = copy.deepcopy(REQUEST)
liso["text"] = "Quero um gabinete baixo de frentes lisas na cozinha"
negative("text_does_not_ask_shaker", liso, "BLOCKED_TECHNIQUE_UNRESOLVED")
fake = copy.deepcopy(REQUEST)
fake["shaker"]["origin_context"] = {"recipe_id": "cabinet.recessed-shaker-and-louvers", "source_id": "yt-cabinet-styles-2024", "source_verified": True}
negative("source_verified_without_human_review", fake, "BLOCKED_KNOWLEDGE_EVIDENCE")
other_recipe = copy.deepcopy(REQUEST)        # mesma fonte COM revisao humana, mas a revisao cobre outra recipe (tampo, 07:09-08:53)
other_recipe["shaker"]["origin_context"] = {"recipe_id": "cabinet.countertop-separate-and-bevel", "source_id": "yt-cabinet-tips-2021",
                                            "source_verified": True}
negative("source_verified_for_another_recipe_of_the_same_video", other_recipe, "BLOCKED_KNOWLEDGE_EVIDENCE")

plain = copy.deepcopy(REQUEST)
plain["inputs"].update(shaker_flow.shaker_inputs(plain["shaker"]))
plain.pop("shaker")
p = plain_run(plain, out_dir=OUT / "neg_plain_flow", base_skp=BASE, mode="interactive")
neg["plain_front_flow_refuses_shaker"] = {"state": p["state"], "pids": p["pids"]}
case("negative_plain_front_flow_refuses_shaker", p["state"] == "BLOCKED_CAPABILITY_MISMATCH" and not p["pids"] and not (OUT / "neg_plain_flow").exists(),
     state=p["state"])
dump("negatives.json", neg)

# --- 4. depois: canonicos, snapshot e gates (FP-047 strict_identity)
after = rd.capture()
gates_after = gates.run(con, [p["box"] for p in after["parts"]])
contract = {"schema_version": "room_regression_request.v1", "change_id": "fp046-review-scope-kitchen-shaker-l2", "fixture": "planta_74",
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

summary["note"] = ("Promocao do binding bind.kitchen.shaker (opcao C da D46-09): fonte yt-cabinet-tips-2021 03:13-04:29 revisada pelo Felipe; "
                   "aparencia PENDING_HUMAN; veio NOT_SUPPORTED; valores da porta sao do pedido de teste")
dump("summary.json", summary)
print("TOTAL", len(summary["cases"]), "ok=", sum(c["ok"] for c in summary["cases"]), "pids", len(summary["pids"]))
sys.exit(0 if all(c["ok"] for c in summary["cases"]) else 1)
