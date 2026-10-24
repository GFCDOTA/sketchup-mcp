"""FP-056 P6 (#439): geracao COMPLETA da planta_74 no SketchUp real, reaberta em outro processo e validada contra o ambiente construido.

Reproducao (cwd = raiz do repo, commit limpo; saida SEMPRE em runs/):
    PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp056/p6/run_p6.py runs/fp056/p6

O que faz: pre-voo obrigatorio -> `jobs.place_boxes` no shell canonico (copia; o canonico nunca e aberto) -> `inspect_model` e
`inspect_geometry` em processos novos -> conformidade proposta x construido (5 mm) -> `built_geometry.validate_room` nos 8
comodos (piso, parede, porta, objetos) -> nao regressao contra o baseline de defeitos da FP-055 P4 e a completude do programa
da FP-056 P2. Fecha SO os PIDs que subiu. Confere o SHA-256 dos canonicos antes/depois. Aparencia: PENDING_HUMAN (nunca auto).
"""
from __future__ import annotations

import contextlib
import glob
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(sys.argv[1]).resolve()
CANONICAL = ("artifacts/planta_74/planta_74.skp", "artifacts/planta_74/furnished/planta_74_furnished.skp",
             "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")


def sha(path) -> str:
    data = Path(path).read_bytes()
    return hashlib.sha256(data.replace(b"\r\n", b"\n") if str(path).endswith(".json") else data).hexdigest()


def git(*a: str) -> str:
    return subprocess.check_output(["git", *a], cwd=ROOT, text=True).strip()


def main() -> int:
    from core.plan_frame import check_chain, frame_for_consensus, verify_against_built
    from tools.furnish_apartment import CONSENSUS, collect_boxes
    from tools.orchestration import intelligent_pipeline as ip
    from tools.sketchup import jobs
    from tools.validation import built_geometry as bg
    from tools.validation import defect_baseline as db
    from tools.validation.layout_preflight import preflight

    OUT.mkdir(parents=True, exist_ok=True)
    summary = {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")),
               "canonical_before": {p: sha(ROOT / p) for p in CANONICAL}, "pids": [], "cases": []}

    def case(name, ok, **data):
        summary["cases"].append({"case": name, "ok": bool(ok), **data})
        print(("PASS " if ok else "FAIL ") + name, flush=True)

    con = json.loads(CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, rooms_summary = collect_boxes(con)
    room_names = {str(r[0]): str(r[1]) for r in rooms_summary if r[4]}
    pre = preflight(con, boxes, rooms_summary)
    case("preflight_allows_materialization", pre["status"] in ("PASS", "NOT_APPLICABLE"), status=pre["status"],
         blocking=pre["blocking"])
    case("clean_commit", not summary["dirty"], commit=summary["commit"])
    chain = check_chain(CONSENSUS)
    case("scale_contract_ok", chain["status"] == "OK", chain=chain)

    opened: set[int] = set()
    try:
        placed = jobs.place_boxes(boxes, base=ROOT / "artifacts/planta_74/planta_74.skp", d=OUT / "build", mode="interactive")
        opened |= ip._pids(placed)
        case("furnish_ok_and_skp_saved", placed.get("status") == "OK", status=placed.get("status"))
        if placed.get("status") != "OK":
            raise RuntimeError(f"place_boxes: {placed.get('status')}")
        skp = Path(placed["files"]["skp"])
        insp = jobs.inspect_model(str(skp), max_depth=1, out_dir=str(OUT / "inspect"), mode="interactive")
        opened |= ip._pids(insp)
        geo = jobs.inspect_geometry(str(skp), out_dir=str(OUT / "geometry"), mode="interactive")
        opened |= ip._pids(geo)
    finally:
        closed = [jobs.close(pid=p, force=True, confirm=True) for p in sorted(opened)]
        summary["pids"] = sorted(opened)
    res, gres = insp.get("result") or {}, geo.get("result") or {}
    case("reopened_and_geometry_extracted", bool(res.get("ok")) and bool(gres.get("ok")),
         inspect=insp.get("status"), geometry=geo.get("status"), sketchup_version=res.get("sketchup_version"))
    if not (res.get("ok") and gres.get("ok")):
        return finish(summary, 1)

    names = list(room_names.values())
    req, built, omitted, div = ip.conformance(res["nodes"], boxes, names)
    case("every_planned_module_is_a_group_within_5mm", not omitted and not div, planned=len(req), built=len(built),
         omitted=list(omitted)[:20] if omitted else [], diverging=div[:20])

    idx = bg.group_index(gres)
    frame = frame_for_consensus(CONSENSUS)
    contract = verify_against_built(bg.expected_walls_pt(con), frame, bg.built_walls(idx), con.get("walls"))
    case("built_walls_match_consensus", contract["status"] == "OK", frame=contract.get("status"))
    doors = bg.door_kinematics_m(con, frame) if contract["status"] == "OK" else None
    reports = {rid: bg.validate_room(idx, rid, name, doors=doors) for rid, name in room_names.items()}
    status = {rid: bg.status(r) for rid, r in reports.items()}
    raw = Path(glob.glob(str(OUT / "geometry" / "*result*.json"))[0])
    base = json.loads((ROOT / "artifacts/review/fp055/p4/defect_baseline.json").read_text("utf-8"))["defects"]
    program = json.loads((ROOT / "artifacts/review/fp056/p2/program_baseline.json").read_text("utf-8"))["program"]
    reg = db.regression(reports, base, program)
    (OUT / "regression.json").write_text(json.dumps(reg, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    (OUT / "env_reports.json").write_text(json.dumps({"status": status, "reports": reports}, indent=1, ensure_ascii=False,
                                                     default=str), encoding="utf-8")
    case("no_new_or_worse_defect_vs_fp055_p4_baseline", not reg["new"] and not reg["worse"], new=reg["new"], worse=reg["worse"])
    case("no_program_loss_without_a_recorded_decision", not reg["missing_program"], missing_program=reg["missing_program"])
    summary.update({"environment_status": status, "regression_status": reg["status"], "resolved": reg["resolved"],
                    "vanished_with_piece": reg.get("vanished_with_piece"), "raw_geometry_sha256": sha(raw),
                    "skp": str(skp), "skp_sha256": sha(skp), "renders": placed.get("files"),
                    "sketchup_version": res.get("sketchup_version"), "visual": "PENDING_HUMAN"})
    summary["canonical_after"] = {p: sha(ROOT / p) for p in CANONICAL}
    case("canonicals_byte_identical", summary["canonical_before"] == summary["canonical_after"])
    running = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SketchUp.exe", "/FO", "CSV", "/NH"],
                             capture_output=True).stdout.decode("latin-1")
    case("all_my_pids_closed", not [p for p in summary["pids"] if f'"{p}"' in running] and bool(closed), pids=summary["pids"])
    return finish(summary, 0)


def finish(summary: dict, code: int) -> int:
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    ok = all(c["ok"] for c in summary["cases"])
    print("TOTAL", len(summary["cases"]), "ok=", sum(c["ok"] for c in summary["cases"]), "pids", summary["pids"])
    return code or (0 if ok else 1)


if __name__ == "__main__":
    sys.exit(main())
