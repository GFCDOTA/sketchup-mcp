"""FP-055 P4 — prova no SketchUp real: construido x AMBIENTE REAL, nao so construido x pedido.

    PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp055/p4/run_p4.py runs/fp055/p4

Casos (cada um reabre o .skp salvo noutro processo e le a geometria construida: faces de piso, paredes, moveis):
  A fixture_valid    comodo quadrado 2,5 m; especialista do banheiro + solver desloca o vaso; tudo na escala do shell.
                     Esperado: contrato OK, IoU das paredes >= 0,95, CONTAINMENT/WALL/DOOR_SWING/OBJECTS PASS -> BUILT.
  B fixture_notch    comodo em L; um armario INJETADO no quadrante que nao e comodo (dentro do bbox do piso, fora do
                     poligono). Esperado: cheque antigo por bbox "passaria"; CONTAINMENT FAIL -> nao valido.
  C scale_mismatch   o erro da 1a execucao: caixas a 0,0259 num shell a 0,0352. Esperado: BLOCKED_SCALE_MISMATCH antes de
                     construir; forcando (so prova), proposta x construido "bate" e mesmo assim a verificacao contra as
                     paredes construidas recusa (BLOCKED_FRAME_MISMATCH) -> nunca valido.
  D real_r006        Banho 02 real pelo orquestrador; proposta INFEASIBLE construida so como diagnostico.
A e B rodam noutro processo SEM `PT_TO_M` (o shell builder usa a escala padrao para consensus fora de fixtures/<planta>/).
Grava commit/dirty, SHA-256 dos protegidos antes/depois; fecha so os PIDs abertos aqui; sai != 0 se o esperado falhar.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
M = 39.3700787402
BATH = "tools.rooms.bathroom.layout.build_boxes"
PROTECTED = ["fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json", "artifacts/planta_74/planta_74.skp",
             "artifacts/planta_74/furnished/planta_74_furnished.skp", "projects/planta_74/source/planta_74.pdf"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(*a: str) -> str:
    return subprocess.check_output(["git", *a], cwd=ROOT, text=True).strip()


def rect(module, kind, room, a, b, c, d, h):
    return {"module": module, "kind": kind, "room": room, "z0_in": 0.0, "h_in": h,
            "corners": [[a, b], [c, b], [c, d], [a, d]], "x0": a, "y0": b, "x1": c, "y1": d}


def l_room() -> dict:
    """Consensus de um comodo em L (pt), porta na parede de baixo. Mesmo formato do synthetic_room."""
    from core.scale import PT_TO_M
    wt, s = 5.4, 3.0 / PT_TO_M
    x0, y0, xm, ym, x1, y1 = 100.0, 100.0, 100.0 + s / 2, 100.0 + s / 2, 100.0 + s, 100.0 + s
    ring = [(x0, y0), (x1, y0), (x1, ym), (xm, ym), (xm, y1), (x0, y1)]
    walls = [{"id": f"w{i}", "start": list(ring[i]), "end": list(ring[(i + 1) % 6]), "thickness": wt,
              "orientation": "h" if ring[i][1] == ring[(i + 1) % 6][1] else "v"} for i in range(6)]
    h = wt / 2
    inner = [(x0 + h, y0 + h), (x1 - h, y0 + h), (x1 - h, ym - h), (xm - h, ym - h), (xm - h, y1 - h), (x0 + h, y1 - h)]
    return {"schema_version": "1.0.0", "wall_thickness_pts": wt, "plan_id": "synthetic_L", "walls": walls,
            "soft_barriers": [],
            "rooms": [{"id": "r_syn", "name": "SINTETICO", "polygon_pts": [list(p) for p in inner],
                       "seed_pt": [x0 + s / 4, y0 + s / 4]}],
            "openings": [{"id": "d_w0", "wall_id": "w0", "kind_v5": "interior_door", "kind": "door",
                          "center": [x0 + s / 4, y0], "opening_width_pts": 0.8 / PT_TO_M}]}


def shell_for(con: dict, cdir: Path) -> tuple[dict, Path]:
    from tools.orchestration import intelligent_pipeline as ip
    from tools.sketchup import jobs
    cdir.mkdir(parents=True, exist_ok=True)
    cpath = cdir / "consensus_synthetic.json"
    cpath.write_text(json.dumps(con, indent=1), "utf-8")
    shell = jobs.build_shell(str(cpath), out_path=str((cdir / "shell" / "model.skp").resolve()), force=True,
                             mode="interactive")
    for p in sorted(ip._pids(shell)):
        jobs.close(pid=p, force=True, confirm=True)
    return shell, cpath


def _toilet_scene(con):
    from core.functional_constraints import FunctionalInterface
    from core.scale import PT_TO_IN
    (_ax, ay), (bx, by) = con["rooms"][0]["polygon_pts"][0], con["rooms"][0]["polygon_pts"][2]
    y0, x1, y1 = ay * PT_TO_IN, bx * PT_TO_IN, by * PT_TO_IN
    cy, fx = (y0 + y1) / 2, x1 - 0.65 * M
    vaso = rect("Vaso", "vaso", "SINTETICO", fx, cy - 0.18 * M, x1, cy + 0.18 * M, 16.0)
    ox = fx - 0.30 * M
    armario = rect("Armario", "body", "SINTETICO", ox - 0.40 * M, y0, ox, cy + 0.05 * M, 80.0)
    iface = FunctionalInterface("r_syn", "Vaso", "toilet", "use_face", ((fx, cy - 0.18 * M), (fx, cy + 0.18 * M)), (-1.0, 0.0),
                                "SEMANTIC_DECLARED", "fixture P4")
    return [vaso, armario], {("r_syn", "Vaso"): iface}


def case_fixture_valid(out: Path) -> dict:
    from core.pipeline_contracts import CapabilityLedger
    from tools.navigation.baseline_probes import synthetic_room
    from tools.orchestration import intelligent_pipeline as ip
    con = synthetic_room(2.5, doors=("w_left",))
    cdir = out / "A_fixture_valid"
    shell, cpath = shell_for(con, cdir)
    if shell.get("status") != "OK":
        return {"case": "A_fixture_valid", "status": "SHELL_FAILED", "shell": shell}
    boxes, ifaces = _toilet_scene(con)
    led = CapabilityLedger()
    plan = ip.plan_room(con, boxes, ifaces, "r_syn", "BATHROOM", "SINTETICO", BATH, led)
    from tools.rooms.shared.spatial_solver.engine import evaluate_layout
    func = {"r_syn": lambda bx: evaluate_layout(con, bx, "r_syn", "BATHROOM", plan["interfaces"], "SINTETICO")}
    built = ip.build(boxes, {"r_syn": plan["proposal"]}, {"r_syn": "SINTETICO"}, (cdir / "shell" / "model.skp").resolve(),
                     cdir, led, consensus=con, consensus_path=cpath, functional=func)
    return {"case": "A_fixture_valid", "status": built["status"], "proposal": plan["proposal"].to_dict(), "build": built,
            "ledger": led.to_dict()}


def case_fixture_notch(out: Path) -> dict:
    from core.pipeline_contracts import CapabilityLedger, LayoutProposal
    from core.scale import PT_TO_IN
    from tools.orchestration import intelligent_pipeline as ip
    con = l_room()
    cdir = out / "B_fixture_notch"
    shell, cpath = shell_for(con, cdir)
    if shell.get("status") != "OK":
        return {"case": "B_fixture_notch", "status": "SHELL_FAILED", "shell": shell}
    xs = [p[0] for w in con["walls"] for p in (w["start"], w["end"])]
    x0, x1 = min(xs) * PT_TO_IN, max(xs) * PT_TO_IN
    q = (x1 - x0) / 4                                          # centro do quadrante que NAO e comodo: (3/4, 3/4)
    cx = cy = x0 + 3 * q
    armario = rect("Armario", "body", "SINTETICO", cx - 0.25 * M, cy - 0.25 * M, cx + 0.25 * M, cy + 0.25 * M, 60.0)
    # defeito INJETADO de proposito (nao veio do solver): o que se prova e que a validacao do construido o pega
    prop = LayoutProposal("r_syn:INJECTED_NOTCH", "r_syn", "FEASIBLE", "INJECTED_NOTCH", (), (), {}, 1, 1,
                          "defeito injetado para a prova P4", "injected", "injected", boxes=(armario,))
    built = ip.build([armario], {"r_syn": prop}, {"r_syn": "SINTETICO"}, (cdir / "shell" / "model.skp").resolve(), cdir,
                     CapabilityLedger(), consensus=con, consensus_path=cpath)
    return {"case": "B_fixture_notch", "status": built["status"], "build": built}


def case_scale_mismatch(out: Path) -> dict:
    """Processo a 0,0259 construindo no shell do caso A (0,0352) — o erro da 1a execucao."""
    from core.pipeline_contracts import CapabilityLedger
    from tools.navigation.baseline_probes import synthetic_room
    from tools.orchestration import intelligent_pipeline as ip
    adir = out / "A_fixture_valid"
    cpath = adir / "consensus_synthetic.json"
    if not cpath.exists():
        return {"case": "C_scale_mismatch", "status": "BLOCKED_NO_SHELL_FROM_A"}
    boxes, ifaces = _toilet_scene(synthetic_room(2.5, doors=("w_left",)))      # pt -> in a 0,0259 (este processo)
    led = CapabilityLedger()
    plan = ip.plan_room(synthetic_room(2.5, doors=("w_left",)), boxes, ifaces, "r_syn", "BATHROOM", "SINTETICO", BATH, led)
    shell = (adir / "shell" / "model.skp").resolve()
    con_shell = json.loads(cpath.read_text("utf-8"))
    guarded = ip.build(boxes, {"r_syn": plan["proposal"]}, {"r_syn": "SINTETICO"}, shell, out / "C_guarded", led,
                       consensus=con_shell, consensus_path=cpath)
    forced = ip.build(boxes, {"r_syn": plan["proposal"]}, {"r_syn": "SINTETICO"}, shell, out / "C_forced",
                      CapabilityLedger(), consensus=con_shell, consensus_path=cpath, unsafe_skip_scale_check=True)
    return {"case": "C_scale_mismatch", "status": f"{guarded['status']} / forced:{forced['status']}",
            "guarded": guarded, "forced": forced}


def case_real_r006(out: Path) -> dict:
    from core.pipeline_contracts import GenerationRequest
    from tools.orchestration import intelligent_pipeline as ip
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    from tools.sketchup.runtime_identity import check
    src = PLANTA_74_CONSENSUS.relative_to(ROOT).as_posix()
    req = GenerationRequest("planta_74", src, sha(ROOT / src), git("rev-parse", "HEAD"), "INTELLIGENT_BUILD",
                            "runs/fp055/p4_real", ("r006",))
    m = ip.run(req, runtime_check=lambda prof: check(prof, expected_commit=git("rev-parse", "HEAD")))
    if m["status"] == "BLOCKED_RUNTIME":
        return {"case": "D_real_r006", "status": "BLOCKED_RUNTIME", "runtime": m["runtime"]}
    prop = m["_proposals"]["r006"]
    from tools.furnish_apartment import CONSENSUS, collect_boxes
    con = json.loads(CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _ = collect_boxes(con)
    from tools.rooms.shared.spatial_solver.engine import evaluate_layout
    ifs = m["_interfaces"]["r006"]
    func = {"r006": lambda bx: evaluate_layout(con, bx, "r006", "BATHROOM", ifs, "BANHO 02")}
    built = ip.build(boxes, {"r006": prop}, {"r006": "BANHO 02"}, ROOT / "artifacts/planta_74/planta_74.skp",
                     out / "D_real_r006", m["_ledger"], consensus=con, consensus_path=PLANTA_74_CONSENSUS,
                     diagnostic=not prop.buildable_as_valid, functional=func)
    ip.write({**m, "build": built, "ledger": m["_ledger"].to_dict()}, out / "D_real_r006")
    return {"case": "D_real_r006", "status": built["status"], "proposal": prop.to_dict(), "build": built,
            "runtime": m["runtime"]["status"]}


def in_default_scale_process(case: str, out: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "PT_TO_M"}
    res = out / f"{case}.json"
    res.unlink(missing_ok=True)
    r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--case", case, str(out)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=1500)
    if not res.exists():
        return {"case": case, "status": "CASE_PROCESS_FAILED", "tail": (r.stdout + r.stderr)[-2000:]}
    return json.loads(res.read_text("utf-8"))


EXPECT = {
    # valido: geometria PASS (contrato, paredes por parede, extracao, piso/parede/porta/objetos) E funcional PASS
    "A_fixture_valid": lambda c: (c["status"] == "BUILT" and c["build"]["valid"]
                                  and c["build"]["geometric_validity"] == "PASS"
                                  and c["build"]["functional_validity"] == "PASS"
                                  and not c["build"]["frame_verification"]["walls_failed"]),
    # negativo: dentro do bbox, fora do poligono — o cheque antigo passaria; o novo reprova
    "B_fixture_notch": lambda c: (not c["build"]["valid"] and c["build"]["geometric_validity"] == "FAIL"
                                  and c["build"]["environment"]["r_syn"]["checks"]["CONTAINMENT"] == "FAIL"
                                  and c["build"]["legacy_bbox_check_not_decisive"]["would_pass"]
                                  and c["build"]["functional_validity"] == "NOT_EXECUTED"),
    # negativo: escala divergente — bloqueia antes; forcado, proposta=construido e mesmo assim as paredes recusam
    "C_scale_mismatch": lambda c: (c["guarded"]["status"] == "BLOCKED_SCALE_MISMATCH" and not c["forced"]["valid"]
                                   and c["forced"]["proposal_conformance"]
                                   and c["forced"]["geometric_validity"] == "BLOCKED"
                                   and c["forced"]["frame_verification"]["status"] == "BLOCKED_FRAME_MISMATCH"),
    # real: referencial confere com as paredes construidas; funcional NAO aprovado (proposta INFEASIBLE)
    "D_real_r006": lambda c: (not c["build"]["valid"]
                              and c["build"]["frame_verification"]["status"] == "OK"
                              and c["build"]["functional_validity"] in ("FAIL", "NOT_EXECUTED")),
}


def main(out: Path) -> int:
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    before = {p: sha(ROOT / p) for p in PROTECTED}
    summary = {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")), "cases": []}
    summary["cases"].append(in_default_scale_process("A_fixture_valid", out))
    summary["cases"].append(in_default_scale_process("B_fixture_notch", out))
    summary["cases"].append(case_scale_mismatch(out))
    summary["cases"].append(case_real_r006(out))
    summary["protected_unchanged"] = before == {p: sha(ROOT / p) for p in PROTECTED}
    summary["expectations"] = {}
    for c in summary["cases"]:
        try:
            summary["expectations"][c["case"]] = bool(EXPECT[c["case"]](c))
        except Exception as exc:  # noqa: BLE001 — caso que nao chegou ao fim nao cumpre o esperado
            summary["expectations"][c["case"]] = f"ERRO: {exc!r}"
    ok = all(v is True for v in summary["expectations"].values()) and summary["protected_unchanged"]
    summary["result"] = "PASS" if ok else "FAIL"
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str) + "\n", "utf-8")
    print(summary["result"], summary["expectations"], [(c["case"], c["status"]) for c in summary["cases"]],
          "dirty", summary["dirty"])
    return 0 if ok else 1


if __name__ == "__main__":
    if sys.argv[1] == "--case":
        o = Path(sys.argv[3]).resolve()
        fn = {"A_fixture_valid": case_fixture_valid, "B_fixture_notch": case_fixture_notch}[sys.argv[2]]
        from core.scale import PT_TO_M
        res = {**fn(o), "pt_to_m": PT_TO_M}
        (o / f"{sys.argv[2]}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), "utf-8")
        sys.exit(0)
    sys.exit(main(Path(sys.argv[1])))
