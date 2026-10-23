"""L2 da decisao da Suite 01 (#381): o apartamento mobiliado no SketchUp real, salvo, REABERTO em outro processo e inspecionado.

Roda do repo (cwd = raiz do worktree), com `PYTHONPATH=.` e `PT_TO_M=0.0259`:
    python artifacts/review/fp054/suite01_l2/l2_suite01.py <saida em runs/>
O shell base e o canonico `artifacts/planta_74/planta_74.skp`, mas o `jobs.furnish` abre uma COPIA dentro da saida. Fecha SO os
PIDs que subiu (por PID). Confere SHA-256 dos canonicos antes/depois. Sai != 0 se algum caso falhar.

Casos: pre-voo PASS; furnish OK com .skp salvo; reabertura+inspecao: a Suite 01 do modelo bate com o plano (sem cadeira da
escrivaninha; bbox XY de cada modulo da suite = plano, tolerancia 1 mm); demais comodos com os mesmos grupos do plano; negativo:
sem a decisao (layout original) o furnish recusa ANTES de subir o SketchUp; canonicos intactos.
"""
import contextlib
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

from tools.furnish_apartment import CONSENSUS, collect_boxes
from tools.rooms.bedroom import layout_decisions
from tools.sketchup import jobs
from tools.validation.layout_preflight import preflight

OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
CANONICAL = ("artifacts/planta_74/planta_74.skp", "artifacts/planta_74/furnished/planta_74_furnished.skp",
             "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
IN_M = 0.0254
TOL_M = 0.001


def sha(path):
    data = Path(path).read_bytes()
    return hashlib.sha256(data.replace(b"\r\n", b"\n") if str(path).endswith(".json") else data).hexdigest()


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


summary = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
           "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
           "canonical_before": {p: sha(p) for p in CANONICAL}, "cases": [], "pids": []}


def case(name, ok, **data):
    summary["cases"].append({"case": name, "ok": bool(ok), **data})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def close(res):
    pid = res.get("pid")
    if pid:
        summary["pids"].append(pid)
        if res.get("su_left_running") or res.get("status") in ("OK", "DONE"):
            jobs.close(pid=int(pid), force=True, confirm=True)


con = json.loads(CONSENSUS.read_text("utf-8"))
with contextlib.redirect_stdout(io.StringIO()):
    boxes, rooms = collect_boxes(con)
pre = preflight(con, boxes, rooms)
case("preflight_allows_materialization", pre["status"] in ("PASS", "NOT_APPLICABLE"), status=pre["status"], blocking=pre["blocking"])

# --- 1. negativo: layout ORIGINAL da Suite 01 (sem a decisao) nao sobe o SketchUp
saved, layout_decisions.DECISIONS = layout_decisions.DECISIONS, ()
try:
    neg = jobs.furnish(out_dir=str(OUT / "neg_original_layout"), mode="interactive")
finally:
    layout_decisions.DECISIONS = saved
case("negative_original_layout_refused_before_sketchup", neg["status"] == "BLOCKED_LAYOUT_GATE" and not neg.get("pid")
     and not (OUT / "neg_original_layout").exists(), status=neg["status"],
     blocking=[(b["room_id"], b["gate"]) for b in neg.get("preflight", {}).get("blocking", [])])

# --- 2. positivo: furnish no SketchUp real
res = jobs.furnish(out_dir=str(OUT / "furnish"), mode="interactive", timeout_s=600)
close(res)
dump("furnish_result.json", {k: v for k, v in res.items() if k != "log"})
skp = Path(res.get("files", {}).get("skp", OUT / "furnish" / "planta_74_furnished.skp"))
case("furnish_ok_and_skp_saved", res["status"] == "OK" and skp.exists() and skp.stat().st_size > 0,
     status=res["status"], skp_bytes=skp.stat().st_size if skp.exists() else 0, skp_sha256=sha(skp) if skp.exists() else None)

# --- 3. reabrir em OUTRO processo e inspecionar
ins = jobs.inspect_model(str(skp), max_depth=1, out_dir=str(OUT / "inspect"), mode="interactive")
close(ins)
result = ins.get("result") or {}
if not result and (OUT / "inspect").exists():
    for f in (OUT / "inspect").rglob("*.json"):
        data = json.loads(f.read_text("utf-8"))
        if isinstance(data, dict) and "nodes" in data:
            result = data
            break
dump("inspect_summary.json", {"status": ins.get("status"), "counts": result.get("counts"),
                              "nodes": [{k: n.get(k) for k in ("name", "tag", "bbox_world_m")} for n in result.get("nodes", [])]})
nodes = {n["name"]: n for n in result.get("nodes", []) if n.get("name")}
case("reopened_in_another_process", ins.get("status") == "OK" and bool(nodes), status=ins.get("status"), nodes=len(nodes))

planned: dict[str, list] = {}
for b in boxes:
    if b.get("corners"):
        planned.setdefault(f"{b.get('room')} · {b.get('module')}", []).append(Polygon(b["corners"]))
suite = {k: v for k, v in planned.items() if k.startswith("SUITE 01 · ")}
rows, worst = [], 0.0
for name, polys in sorted(suite.items()):
    x0, y0, x1, y1 = (v * IN_M for v in unary_union(polys).bounds)
    got = nodes.get(name, {}).get("bbox_world_m")
    if not got:
        rows.append({"module": name, "found": False})
        worst = float("inf")
        continue
    (gx0, gy0, _gz0), (gx1, gy1, _gz1) = got["min"], got["max"]
    err = max(abs(gx0 - x0), abs(gy0 - y0), abs(gx1 - x1), abs(gy1 - y1))
    worst = max(worst, err)
    rows.append({"module": name, "found": True, "max_xy_error_m": round(err, 6)})
dump("suite01_plan_vs_model.json", rows)
case("suite01_modules_match_plan_xy", worst <= TOL_M, max_xy_error_m=worst, modules=len(rows))
case("suite01_desk_chair_absent_in_model", "SUITE 01 · Cadeira escrivaninha" not in nodes
     and "SUITE 01 · Escrivaninha" in nodes and "SUITE 01 · Criado-mudo 1" in nodes)
furn_groups = {k for k in nodes if " · " in k}
missing = sorted(set(planned) - furn_groups)
case("every_planned_module_is_a_group_in_the_model", not missing, missing=missing[:20], planned=len(planned))

summary["canonical_after"] = {p: sha(p) for p in CANONICAL}
case("canonicals_byte_identical", summary["canonical_before"] == summary["canonical_after"])
leftovers = [str(p) for p in Path("artifacts/planta_74").rglob("*") if p.is_file() and p.parent.name.startswith("_")]
case("no_scratch_left_inside_artifacts", not leftovers, leftovers=leftovers)
running = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SketchUp.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
mine_alive = [p for p in summary["pids"] if f'"{p}"' in running]
case("all_my_pids_closed", not mine_alive, alive=mine_alive)

summary["note"] = ("Suite 01 #381: decisao do Felipe (sem cadeira da escrivaninha; criado-mudo 1 1 in -y). Aparencia PENDING_HUMAN.")
dump("summary.json", summary)
print("TOTAL", len(summary["cases"]), "ok=", sum(c["ok"] for c in summary["cases"]), "pids", summary["pids"])
sys.exit(0 if all(c["ok"] for c in summary["cases"]) else 1)
