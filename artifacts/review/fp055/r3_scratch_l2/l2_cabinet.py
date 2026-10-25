"""Matriz L2 da P6b: materializa no SketchUp real, salva, REABRE em outro processo e compara com o plano.
Roda do repo (cwd = worktree). Saida: <out>/<caso>/{plan,build,inspect,verify}.json + summary.json. Fecha SO os PIDs que subiu."""
import copy
import pathlib
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from tools.rooms.shared.cabinet import plan_cabinet
from tools.rooms.shared.cabinet.assembly import definitions
from tools.rooms.shared.cabinet import sketchup as cs
from tools.sketchup import jobs

OUT = Path(sys.argv[1]).resolve()
BASE = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
FIX = Path("fixtures/synthetic_cabinets")
summary = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
           "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
           "base_skp": str(BASE), "base_sha256": hashlib.sha256(BASE.read_bytes()).hexdigest(), "cases": [], "pids": []}


def req(fx, rid, rot=None, pos=None):
    r = json.loads((FIX / f"{fx}.json").read_text("utf-8"))
    r["request_id"] = rid
    if rot is not None:
        r["pose"]["rotation_deg"]["value"] = rot
    if pos:
        r["pose"]["x"]["value"], r["pose"]["y"]["value"] = pos
    return r


def closeit(res):
    pid = res.get("pid")
    if pid:
        summary["pids"].append(int(pid))
        jobs.close(pid=int(pid), force=True, confirm=True)


def dump(case, name, obj):
    d = OUT / case
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def build(case, plan, out, base, edits=None):
    r = cs.materialize(plan, out, base_skp=base, edits=edits)
    closeit(r)
    dump(case, "build", {k: v for k, v in r.items()})
    assert r["status"] == "OK", (case, r.get("status"), r.get("reason"), (r.get("result") or {}).get("error"))
    return r


def reopen(case, out):
    r = cs.inspect(out)
    closeit(r)
    dump(case, "inspect", r)
    assert r["status"] == "OK", (case, r.get("status"), r.get("reason"), (r.get("result") or {}).get("error"))
    return r["result"]


def record(case, kind, plan, v, extra=None):
    row = {"case": case, "kind": kind, "request_id": plan["request_id"], "signature": plan["signature"],
           "ok": v["ok"], "max_corner_error_m": v.get("max_corner_error_m"), "checks": len(v["checks"]),
           "failed": [c for c in v["checks"] if not c["ok"]], **(extra or {})}
    summary["cases"].append(row)
    dump(case, "verify", v)
    print(("PASS " if v["ok"] else "FAIL ") + case, row.get("max_corner_error_m"), row["failed"][:3], flush=True)


b0 = cs.inspect(BASE)
closeit(b0)
assert b0["status"] == "OK"
baseline = b0["result"]
summary["sketchup_version"] = b0["result"] and (b0.get("result", {}).get("sketchup_version") or None)
dump("baseline", "inspect", b0)

# ---- M1: dimensoes x poses (0/90/30 graus), todas em arquivo novo, reaberto e verificado
M1 = [("valid_a_base_600", 0), ("valid_a_base_600", 90), ("valid_a_base_600", 30), ("valid_b_tall_900", 90),
      ("valid_b_tall_900", 30), ("holdout_c", 30), ("holdout_c", 0)]
first_out = None
for fx, rot in M1:
    case = f"m1_{fx}_r{rot}"
    plan = plan_cabinet(req(fx, f"{fx.split('_')[0]}{fx.split('_')[1][:1]}-r{rot}", rot))
    assert plan["status"] == "OK", plan["findings"]
    out = OUT / case / "cab.skp"
    b = build(case, plan, out, BASE)
    summary["sketchup_version"] = b["result"].get("sketchup_version")
    insp = reopen(case, out)
    v = cs.verify(plan, insp, baseline=baseline)
    record(case, "materialize+reopen", plan, v, {"fixture": fx, "rotation_deg": rot, "pid_build": b.get("pid")})
    if first_out is None:
        first_out, first_plan = out, plan

# ---- M2: reexecucao controlada (mesmo request_id sobre o arquivo anterior): substitui, nao duplica
case = "m2_idempotent_rebuild"
out2 = OUT / case / "cab.skp"
b = build(case, first_plan, out2, first_out)
insp = reopen(case, out2)
v = cs.verify(first_plan, insp, baseline=baseline)
roots = [c for c in insp["cabinets"] if c["request_id"] == first_plan["request_id"]]
v["checks"].append({"check": "replaced_not_duplicated", "ok": b["result"]["replaced_previous"] == 1 and len(roots) == 1
                    and insp["counts"]["cabinet_definitions"] == len(first_plan["definitions"]),
                    "detail": f"replaced={b['result']['replaced_previous']} roots={len(roots)} defs={insp['counts']['cabinet_definitions']}"})
v["ok"] = all(c["ok"] for c in v["checks"])
record(case, "rebuild", first_plan, v)

# ---- M3: repeticao + make_unique + atualizacao local (dois gabinetes no MESMO modelo)
pa = plan_cabinet(req("valid_b_tall_900", "rep-x", 0, (0.5, 0.5)))
pb = plan_cabinet(req("valid_b_tall_900", "rep-y", 0, (3.0, 0.5)))
o1 = OUT / "m3_repeat_x" / "cab.skp"
build("m3_repeat_x", pa, o1, BASE)
o2 = OUT / "m3_repeat_y" / "cab.skp"
build("m3_repeat_y", pb, o2, o1)
insp = reopen("m3_repeat_y", o2)
va, vb = cs.verify(pa, insp, baseline=None), cs.verify(pb, insp, baseline=None)
record("m3_repeat_x", "repetition", pa, va)
record("m3_repeat_y", "repetition", pb, vb)
side_l = next(p for p in pa["parts"] if p["name"] == "side_left")
new_size = [side_l["size_m"][0], side_l["size_m"][1], side_l["size_m"][2] - 0.100]       # encurta 100 mm so a lateral esquerda


def expect_after(plan, part_id, size):
    p = copy.deepcopy(plan)
    for x in p["parts"]:
        if x["id"] == part_id:
            x["max_m"] = [x["min_m"][k] + size[k] for k in range(3)]
            x["size_m"] = list(size)
    p["definitions"] = definitions(p["parts"])
    return p


# (a) edicao LOCAL: propagate=false faz make_unique -> so a lateral esquerda de X muda; direita de X e as de Y ficam
o3 = OUT / "m3_edit_local" / "cab.skp"
e = build("m3_edit_local", pa, o3, o2, edits=[{"op": "edit_definition", "part": side_l["id"], "size_m": new_size, "propagate": False}])
insp3 = reopen("m3_edit_local", o3)
pa_after = expect_after(pa, side_l["id"], new_size)
v = cs.verify(pa_after, insp3)
v2 = cs.verify(pb, insp3)
xr = next(c for c in insp3["cabinets"] if c["request_id"] == "rep-x")
right = next(p for p in xr["parts"] if p["part_id"].endswith("/side_right"))
left = next(p for p in xr["parts"] if p["part_id"].endswith("/side_left"))
v["checks"].append({"check": "other_instances_unchanged", "ok": v2["ok"], "detail": "gabinete Y inteiro igual ao plano"})
v["checks"].append({"check": "make_unique_split_definition", "ok": left["definition"] != right["definition"] and right["definition_instances"] == 1,
                    "detail": f"{left['definition']} != {right['definition']}"})
v["ok"] = all(c["ok"] for c in v["checks"])
record("m3_edit_local", "make_unique+local_update", pa_after, v, {"edit_report": e["result"]["edits"]})

# (b) edicao da DEFINICAO com propagate=true: a equivalente (lateral direita de Y? nao: definicao e por gabinete) -> frentes de X
front1 = next(p for p in pa["parts"] if p["name"] == "front_1")
fsize = [front1["size_m"][0], front1["size_m"][1], front1["size_m"][2] - 0.050]
o4 = OUT / "m3_edit_propagate" / "cab.skp"
e = build("m3_edit_propagate", pa, o4, o3, edits=[{"op": "edit_definition", "part": front1["id"], "size_m": fsize, "propagate": True}])
insp4 = reopen("m3_edit_propagate", o4)
pa2 = expect_after(expect_after(pa_after, front1["id"], fsize), next(p for p in pa["parts"] if p["name"] == "front_2")["id"], fsize)
v = cs.verify(pa2, insp4)
v["checks"].append({"check": "propagated_only_because_requested", "ok": e["result"]["edits"][0]["definition_instances_before"] == 2
                    and e["result"]["edits"][0]["propagate"] is True, "detail": str(e["result"]["edits"][0])})
v["checks"].append({"check": "gabinete_Y_intacto", "ok": cs.verify(pb, insp4)["ok"], "detail": "Y igual ao plano"})
v["ok"] = all(c["ok"] for c in v["checks"])
record("m3_edit_propagate", "definition_edit_propagates_when_explicit", pa2, v, {"edit_report": e["result"]["edits"]})

# (c) atualizacao local de material em uma peca
o5 = OUT / "m3_set_material" / "cab.skp"
back = next(p for p in pa["parts"] if p["name"] == "back")
e = build("m3_set_material", pa, o5, o4, edits=[{"op": "set_material", "part": back["id"], "material": "mdf_vermelho_teste"}])
insp5 = reopen("m3_set_material", o5)
cab = next(c for c in insp5["cabinets"] if c["request_id"] == "rep-x")
bk = next(p for p in cab["parts"] if p["part_id"].endswith("/back"))
others = [p for p in cab["parts"] if not p["part_id"].endswith("/back")]
orig = {p["id"]: p["material"] for p in pa["parts"]}
ok = bk["material"] == "mdf_vermelho_teste" and all(p["material"] == orig[p["part_id"]] for p in others)
rec = {"ok": ok, "checks": [{"check": "only_back_changed", "ok": ok, "detail": bk["material"]}], "max_corner_error_m": 0.0}
record("m3_set_material", "local_material_update", pa, rec)


# ---- N1 (#460, R3/T0.2): inspecionar um .skp DENTRO de artifacts/ nao deixa lixo ao lado dele; o scratch vai para runs/ (SketchUp real,
# outro processo). O "repo" e um diretorio temporario (paths.REPO_ROOT trocado so aqui): o artifacts/ de verdade nunca e tocado.
import shutil
import tempfile

from tools.sketchup import paths as _paths

_fake = Path(tempfile.mkdtemp(prefix="skmcp_fake_repo_"))
(_fake / "artifacts" / "planta").mkdir(parents=True)
(_fake / "fixtures").mkdir()
_protected = _fake / "artifacts" / "planta" / "mobiliado.skp"
shutil.copy2(first_out, _protected)
_sha_before = sha(_protected) if "sha" in globals() else hashlib.sha256(_protected.read_bytes()).hexdigest()
_real_root = _paths.REPO_ROOT
_paths.REPO_ROOT = _fake
try:
    _r = cs.inspect(_protected)
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
summary["cases"].append({"case": "n1_inspect_protected_skp_leaves_no_trash", "kind": "negative_scratch_policy", "ok": _row["ok"], "checks": len(_row["checks"]), "failed": [c for c in _row["checks"] if not c["ok"]]})
print(("PASS " if _row["ok"] else "FAIL ") + "n1_inspect_protected_skp_leaves_no_trash", flush=True)

# ---- M4: veio: nao suportado (registrado, nao verificado)
summary["grain"] = {"state": "NOT_SUPPORTED", "note": "sem textura/UV no SketchUp scratch: o veio fica como atributo, nao aplicado"}
(OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
print("TOTAL", len(summary["cases"]), "ok=", sum(c["ok"] for c in summary["cases"]), "pids", len(summary["pids"]))
