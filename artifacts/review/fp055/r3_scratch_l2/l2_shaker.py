"""Matriz L2 da FP-046/P3: materializa a porta Shaker no SketchUp real, salva, REABRE em outro processo e compara com o plano.

Roda do repo (cwd = raiz do worktree), com `PYTHONPATH=.`:   python artifacts/review/fp046/p3_shaker_l2/l2_matrix.py <saida> <template.skp>
`<template.skp>`: um .skp de template do SketchUp (o SketchUp precisa abrir COM um arquivo; sem ele o -RubyStartup fica parado na
tela inicial). A base e copiada, nunca aberta. `<saida>` deve ficar FORA de fixtures/ e artifacts/ (use runs/...). Saida: <saida>/<caso>/{plan,build,inspect,verify}.json + summary.json.
Fecha SO os PIDs que subiu (jobs.close por PID, nunca por nome). Gabinetes-pai e portas sao SINTETICOS (fixtures/synthetic_cabinets).
"""
import copy
import pathlib
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from tools.rooms.shared.cabinet import plan_cabinet
from tools.rooms.shared.cabinet import sketchup as cabinet_su
from tools.rooms.shared.cabinet.assembly import definitions
from tools.rooms.shared.cabinet.shaker import plan_shaker_door
from tools.rooms.shared.cabinet.shaker import sketchup as ss
from tools.sketchup import jobs

OUT = Path(sys.argv[1]).resolve()
BASE = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
FIX = Path("fixtures/synthetic_cabinets")
summary = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
           "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
           "base_template": str(BASE), "base_template_sha256": hashlib.sha256(BASE.read_bytes()).hexdigest(),
           "cases": [], "pids": [], "outputs_sha256": {}}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(case, name, obj):
    d = OUT / case
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def closeit(res):
    pid = res.get("pid")
    if pid:
        summary["pids"].append(int(pid))
        jobs.close(pid=int(pid), force=True, confirm=True)


def parent(rid, rot, fronts=1):
    r = json.loads((FIX / "valid_a_base_600.json").read_text("utf-8"))
    r["request_id"], r["fronts"] = rid, {"count": fronts}
    r["pose"]["rotation_deg"]["value"] = rot
    plan = plan_cabinet(r)
    assert plan["status"] == "OK", plan["findings"]
    return plan


def shaker(par, rid, front="front"):
    r = json.loads((FIX / "fp046_shaker_valid_a.json").read_text("utf-8"))
    r.update(request_id=rid, parent_cabinet_request_id=par["request_id"], target_front=front)
    plan = plan_shaker_door(r, par)
    assert plan["status"] == "OK", plan["findings"]
    return plan


def build_parent(case, par):
    out = OUT / case / "parent.skp"
    res = cabinet_su.materialize(par, out, base_skp=BASE)
    closeit(res)
    dump(case, "build_parent", res)
    assert res["status"] == "OK", (case, res.get("status"), res.get("reason"), (res.get("result") or {}).get("error"))
    summary["sketchup_version"] = res["result"].get("sketchup_version")
    summary["outputs_sha256"][f"{case}/parent.skp"] = sha(out)
    return out


def apply(case, label, plan, par, base, edits=None):
    out = OUT / case / f"{label}.skp"
    res = ss.materialize_shaker(plan, par, out, base_skp=base, edits=edits)
    closeit(res)
    dump(case, f"build_{label}", res)
    assert res["status"] == "OK", (case, res.get("status"), res.get("reason"), (res.get("result") or {}).get("error"))
    summary["outputs_sha256"][f"{case}/{label}.skp"] = sha(out)
    return out, res


def reopen(case, label, skp):
    res = ss.inspect_shaker(skp)
    closeit(res)
    dump(case, f"inspect_{label}", res)
    assert res["status"] == "OK", (case, res.get("status"), res.get("reason"), (res.get("result") or {}).get("error"))
    return res["result"]


def record(case, kind, plan, v, extra=None):
    row = {"case": case, "kind": kind, "request_id": plan["request_id"], "signature": plan["signature"], "ok": v["ok"],
           "max_corner_error_m": v.get("max_corner_error_m"), "checks": len(v["checks"]),
           "failed": [c for c in v["checks"] if not c["ok"]], **(extra or {})}
    summary["cases"].append(row)
    dump(case, "verify", v)
    print(("PASS " if v["ok"] else "FAIL ") + case, row.get("max_corner_error_m"), row["failed"][:3], flush=True)


def leftover_is_not_a_result(res, out):
    """Job recusado: a copia nao editada foi apagada OU (SketchUp ainda a segurava) ficou com marcador NOT_A_RESULT. Depois de
    fechar o PID proprio, limpa o resto (copia + marcador) — ela nunca pode ser lida como saida valida."""
    marker = res.get("unedited_copy_marker")
    ok = res.get("unedited_copy_removed") is True or bool(marker and Path(marker).exists())
    for leftover in (out, Path(marker) if marker else None):
        if leftover is not None and leftover.exists():
            leftover.unlink()
    return ok


def expect_after(plan, part_id, size):
    p = copy.deepcopy(plan)
    for x in p["parts"]:
        if x["id"] == part_id:
            x["max_m"] = [x["min_m"][k] + size[k] for k in range(3)]
            x["size_m"] = list(size)
    p["definitions"] = definitions(p["parts"])
    return p


def extra_check(v, name, ok, detail):
    v["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
    v["ok"] = all(c["ok"] for c in v["checks"])


# ---- S1: 1 porta x poses 0/90/30 -------------------------------------------------------------------------------------
keep = {}
for rot in (0, 90, 30):
    case = f"s1_one_door_r{rot}"
    par = parent(f"synthetic-a-r{rot}", rot)
    base = build_parent(case, par)
    b0 = reopen(case, "parent", base)
    plan = shaker(par, f"shaker-r{rot}")
    dump(case, "plan", plan)
    out, res = apply(case, "shaker", plan, par, base)
    insp = reopen(case, "shaker", out)
    v = ss.verify_shaker(plan, par, insp, baseline=b0)
    extra_check(v, "base_parent_skp_unchanged", sha(base) == summary["outputs_sha256"][f"{case}/parent.skp"], "o pai nao foi sobrescrito")
    extra_check(v, "removed_front_reported_by_job", res["result"]["removed_front"] == plan["replaces_part"], str(res["result"]["removed_front"]))
    extra_check(v, "orphan_front_definition_removed", insp["counts"]["cabinet_definitions"] == b0["counts"]["cabinet_definitions"] - 1,
                f"CabinetDef antes={b0['counts']['cabinet_definitions']} depois={insp['counts']['cabinet_definitions']}")
    record(case, "build_parent+shaker+reopen", plan, v, {"rotation_deg": rot, "pid_build": res.get("pid")})
    keep[rot] = (par, plan, base, out, b0)

# ---- S2: 2 portas no MESMO gabinete (rot 30), duas execucoes em sequencia -----------------------------------------------
case = "s2_two_doors_r30"
par2 = parent("synthetic-two", 30, fronts=2)
base2 = build_parent(case, par2)
b2 = reopen(case, "parent", base2)
pl, pr = shaker(par2, "shaker-left", "front_1"), shaker(par2, "shaker-right", "front_2")
o1, _ = apply(case, "left", pl, par2, base2)
o2, _ = apply(case, "right", pr, par2, o1)
insp2 = reopen(case, "right", o2)
vl = ss.verify_shaker(pl, par2, insp2, baseline=b2, sibling_replaced=(pr["replaces_part"],))
vr = ss.verify_shaker(pr, par2, insp2, baseline=b2, sibling_replaced=(pl["replaces_part"],))
cab = insp2["cabinets"][0]
ids = [p["part_id"] for s in cab["shakers"] for p in s["parts"]]
extra_check(vl, "two_groups_ten_parts_no_duplicate_ids", len(cab["shakers"]) == 2 and len(ids) == len(set(ids)) == 10, f"{len(cab['shakers'])} grupos, {len(ids)} pecas")
extra_check(vl, "orphan_front_definition_removed", insp2["counts"]["cabinet_definitions"] == b2["counts"]["cabinet_definitions"] - 1,
            f"CabinetDef antes={b2['counts']['cabinet_definitions']} depois={insp2['counts']['cabinet_definitions']}")
extra_check(vl, "no_plain_front_left", not [p for p in cab["parts"] if p["role"] == "front"], f"{[p['part_id'] for p in cab['parts']]}")
extra_check(vl, "second_door_verified_too", vr["ok"], f"{[c for c in vr['checks'] if not c['ok']][:2]}")
record(case, "two_doors_same_cabinet", pl, vl, {"right_ok": vr["ok"], "right_checks": len(vr["checks"])})

# ---- S3: reexecucao do MESMO request_id substitui, nao duplica ------------------------------------------------------------
case = "s3_idempotent_rebuild"
par, plan, base, out, b0 = keep[30]
o3, res = apply(case, "shaker_again", plan, par, out)
insp3 = reopen(case, "shaker_again", o3)
v = ss.verify_shaker(plan, par, insp3, baseline=b0)
groups = [s for c in insp3["cabinets"] for s in c["shakers"]]
extra_check(v, "replaced_not_duplicated", res["result"]["replaced_previous"] == 1 and len(groups) == 1 and res["result"]["removed_front"] is None
            and insp3["counts"]["shaker_definitions"] == len(plan["definitions"]),
            f"replaced={res['result']['replaced_previous']} groups={len(groups)} defs={insp3['counts']['shaker_definitions']}")
record(case, "rebuild", plan, v)

# ---- S4: make_unique (edicao local, propagate=false) ---------------------------------------------------------------------
case = "s4_make_unique_local"
stile = next(p for p in plan["parts"] if p["name"] == "stile_left")
new = [stile["size_m"][0], stile["size_m"][1], stile["size_m"][2] - 0.050]
o4, res = apply(case, "edit", plan, par, out, edits=[{"op": "edit_definition", "part": stile["id"], "size_m": new, "propagate": False}])
insp4 = reopen(case, "edit", o4)
after = expect_after(plan, stile["id"], new)
v = ss.verify_shaker(after, par, insp4)
parts4 = {p["part_id"]: p for s in insp4["cabinets"][0]["shakers"] for p in s["parts"]}
left, right = parts4[stile["id"]], parts4[stile["id"].replace("stile_left", "stile_right")]
extra_check(v, "make_unique_split_definition", left["definition"] != right["definition"] and right["definition_instances"] == 1 and left["definition_instances"] == 1,
            f"{left['definition']} != {right['definition']}")
extra_check(v, "right_stile_untouched", right["world_corners_m"] and ss._match(ss.expected_corners(plan, next(p for p in plan["parts"] if p["name"] == "stile_right")), right["world_corners_m"], 1e-5) is not None, "montante direito igual ao plano original")
record(case, "make_unique+local_update", after, v, {"edit_report": res["result"]["edits"]})

# ---- S5: edicao da definicao COM propagate (travessas equivalentes) -----------------------------------------------------------
case = "s5_edit_propagate"
rail = next(p for p in plan["parts"] if p["name"] == "rail_top")
rnew = [rail["size_m"][0] - 0.020, rail["size_m"][1], rail["size_m"][2]]
o5, res = apply(case, "edit", plan, par, out, edits=[{"op": "edit_definition", "part": rail["id"], "size_m": rnew, "propagate": True}])
insp5 = reopen(case, "edit", o5)
after5 = expect_after(expect_after(plan, rail["id"], rnew), rail["id"].replace("rail_top", "rail_bottom"), rnew)
v = ss.verify_shaker(after5, par, insp5)
extra_check(v, "propagated_only_because_requested", res["result"]["edits"][0]["definition_instances_before"] == 2 and res["result"]["edits"][0]["propagate"] is True, str(res["result"]["edits"][0]))
record(case, "definition_edit_propagates_when_explicit", after5, v, {"edit_report": res["result"]["edits"]})

# ---- S6: material local do painel ------------------------------------------------------------------------------------------------
case = "s6_set_material_panel"
panel = next(p for p in plan["parts"] if p["name"] == "recessed_panel")
o6, res = apply(case, "edit", plan, par, out, edits=[{"op": "set_material", "part": panel["id"], "material": "mdf_azul_teste"}])
insp6 = reopen(case, "edit", o6)
parts6 = {p["part_id"]: p for s in insp6["cabinets"][0]["shakers"] for p in s["parts"]}
orig = {p["id"]: p["material"] for p in plan["parts"]}
ok = parts6[panel["id"]]["material"] == "mdf_azul_teste" and all(p["material"] == orig[i] for i, p in parts6.items() if i != panel["id"])
row = {"ok": ok, "checks": [{"check": "only_panel_changed", "ok": ok, "detail": parts6[panel["id"]]["material"]}], "max_corner_error_m": 0.0}
record(case, "local_material_update", plan, row)

# ---- S7/S8: o PROPRIO Ruby recusa pai errado / ausente (negativos reais; driver passa porque o plano e valido) -----------------------
neg_cases = {}
par_a, par_b = parent("synthetic-neg-a", 0), parent("synthetic-neg-b", 30)
case = "s7_ruby_refuses_stale_parent"
base_b = build_parent(case, par_b)                                                       # modelo tem o pai B
plan_a = shaker(par_a, "shaker-neg")                                                     # plano feito para o pai A (outra pose)
plan_a_same_id = copy.deepcopy(plan_a)
out7 = OUT / case / "refused.skp"
res = ss.materialize_shaker(plan_a, par_a, out7, base_skp=base_b)
closeit(res)
dump(case, "build_refused", res)
msg = (res.get("result") or {}).get("error", "") or res.get("reason", "")
no_result = leftover_is_not_a_result(res, out7)
row = {"ok": res["status"] == "FAILED" and no_result and "não existe" in msg,
       "checks": [{"check": "ruby_refused_and_no_result_left", "ok": res["status"] == "FAILED" and no_result, "detail": msg[:160]}],
       "max_corner_error_m": None}
record(case, "negative_parent_missing_in_model", plan_a, row)

case = "s8_ruby_refuses_changed_parent_signature"
par_c = parent("synthetic-neg-c", 0)
base_c = build_parent(case, par_c)
par_c_alt = parent("synthetic-neg-c", 90)                                                 # mesmo request_id, outra pose => outra assinatura
plan_c_alt = shaker(par_c_alt, "shaker-neg-c")
out8 = OUT / case / "refused.skp"
res = ss.materialize_shaker(plan_c_alt, par_c_alt, out8, base_skp=base_c)
closeit(res)
dump(case, "build_refused", res)
msg = (res.get("result") or {}).get("error", "") or res.get("reason", "")
no_result = leftover_is_not_a_result(res, out8)
row = {"ok": res["status"] == "FAILED" and no_result and "outra assinatura" in msg,
       "checks": [{"check": "ruby_refused_wrong_signature_and_no_result_left", "ok": res["status"] == "FAILED" and no_result, "detail": msg[:160]}],
       "max_corner_error_m": None}
record(case, "negative_parent_signature_changed", plan_c_alt, row)


# ---- N1 (#460, R3/T0.2): inspecionar um .skp DENTRO de artifacts/ nao deixa lixo ao lado dele; o scratch vai para runs/ (SketchUp real,
# outro processo). O "repo" e um diretorio temporario (paths.REPO_ROOT trocado so aqui): o artifacts/ de verdade nunca e tocado.
import shutil
import tempfile

from tools.sketchup import paths as _paths

_fake = Path(tempfile.mkdtemp(prefix="skmcp_fake_repo_"))
(_fake / "artifacts" / "planta").mkdir(parents=True)
(_fake / "fixtures").mkdir()
_protected = _fake / "artifacts" / "planta" / "mobiliado.skp"
shutil.copy2(base_c, _protected)
_sha_before = sha(_protected) if "sha" in globals() else hashlib.sha256(_protected.read_bytes()).hexdigest()
_real_root = _paths.REPO_ROOT
_paths.REPO_ROOT = _fake
try:
    _r = ss.inspect_shaker(_protected)
finally:
    _paths.REPO_ROOT = _real_root
closeit(_r)
_beside = sorted(p.name for p in (_fake / "artifacts").rglob("*") if p.is_file())
_in_runs = pathlib.Path(_r.get("out_dir", "")).resolve().is_relative_to((_fake / "runs").resolve()) if _r.get("out_dir") else False
_row = {"ok": _r.get("status") == "OK" and _beside == ["mobiliado.skp"] and _in_runs
        and hashlib.sha256(_protected.read_bytes()).hexdigest() == _sha_before,
        "checks": [{"check": "no_trash_beside_protected_skp", "ok": _beside == ["mobiliado.skp"], "detail": str(_beside)},
                   {"check": "scratch_under_runs", "ok": _in_runs, "detail": str(_r.get("out_dir"))},
                   {"check": "inspect_status_ok", "ok": _r.get("status") == "OK", "detail": str(_r.get("status"))}],
        "max_corner_error_m": None}
shutil.rmtree(_fake, ignore_errors=True)
record("n1_inspect_protected_skp_leaves_no_trash", "negative_scratch_policy", plan_c_alt, _row)

summary["grain"] = {"state": "NOT_SUPPORTED", "note": "sem textura/UV: o veio fica como atributo, nao aplicado"}
summary["scope_note"] = "SINTETICO: pai valid_a_base_600; nenhuma cozinha real, ferragem, gaveta ou veredito visual (L3 PENDING_HUMAN)"
(OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
print("TOTAL", len(summary["cases"]), "ok=", sum(c["ok"] for c in summary["cases"]), "pids", len(summary["pids"]))
sys.exit(0 if all(c["ok"] for c in summary["cases"]) else 1)
