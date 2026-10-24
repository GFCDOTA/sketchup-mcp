"""FP-055 P4 — fatia vertical no SketchUp real: fixture controlada (solucao viavel) + Banho 02 real (r006).

    PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp055/p4/run_p4.py runs/fp055/p4

Caso A (fixture): comodo sintetico 2,5 m com uma porta -> shell construido pelo builder real a partir do consensus sintetico ->
vaso na parede leste com armario na frente -> orquestrador (especialista do banheiro + solver) -> proposta FEASIBLE -> SketchUp
constroi -> modelo REABERTO noutro processo -> conferencia proposta x construido.
Caso B (real): Banho 02 pelo orquestrador; se nao for viavel, construcao DIAGNOSTICA do 1o da ordem (rotulada nao valida).
Grava commit/dirty, SHA-256 dos protegidos antes/depois e fecha so os PIDs abertos aqui. Sai != 0 se algo falhar.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
M = 39.3700787402
PROTECTED = ["fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json", "artifacts/planta_74/planta_74.skp",
             "artifacts/planta_74/furnished/planta_74_furnished.skp", "projects/planta_74/source/planta_74.pdf"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(*a: str) -> str:
    return subprocess.check_output(["git", *a], cwd=ROOT, text=True).strip()


def fixture_case(out: Path, ledger_cls) -> dict:
    from core.functional_constraints import FunctionalInterface
    from core.scale import PT_TO_IN
    from tools.navigation.baseline_probes import synthetic_room
    from tools.orchestration import intelligent_pipeline as ip
    from tools.sketchup import jobs
    con = synthetic_room(2.5, doors=("w_left",))
    cdir = out / "fixture"
    cdir.mkdir(parents=True, exist_ok=True)
    cpath = cdir / "consensus_synthetic.json"
    cpath.write_text(json.dumps(con, indent=1), "utf-8")
    shell = jobs.build_shell(str(cpath), out_path=str((cdir / "shell" / "model.skp").resolve()), force=True,
                             mode="interactive")
    pids = ip._pids(shell)
    for p in sorted(pids):
        jobs.close(pid=p, force=True, confirm=True)
    if shell.get("status") != "OK":
        return {"case": "fixture", "status": "SHELL_FAILED", "shell": shell}
    (ax, ay), (bx, by) = con["rooms"][0]["polygon_pts"][0], con["rooms"][0]["polygon_pts"][2]
    _x0, y0, x1, y1 = ax * PT_TO_IN, ay * PT_TO_IN, bx * PT_TO_IN, by * PT_TO_IN
    cy, fx = (y0 + y1) / 2, x1 - 0.65 * M

    def rect(module, kind, a, b, c, d, h):
        return {"module": module, "kind": kind, "room": "SINTETICO", "z0_in": 0.0, "h_in": h,
                "corners": [[a, b], [c, b], [c, d], [a, d]], "x0": a, "y0": b, "x1": c, "y1": d}
    vaso = rect("Vaso", "vaso", fx, cy - 0.18 * M, x1, cy + 0.18 * M, 16.0)
    ox = fx - 0.30 * M
    armario = rect("Armario", "body", ox - 0.40 * M, y0, ox, cy + 0.05 * M, 80.0)
    iface = FunctionalInterface("r_syn", "Vaso", "toilet", "use_face", ((fx, cy - 0.18 * M), (fx, cy + 0.18 * M)), (-1.0, 0.0),
                                "SEMANTIC_DECLARED", "fixture P4")
    boxes, ifaces = [vaso, armario], {("r_syn", "Vaso"): iface}
    ledger = ledger_cls()
    planned = ip.plan_room(con, boxes, ifaces, "r_syn", "BATHROOM", "SINTETICO", "tools.rooms.bathroom.layout.build_boxes",
                           ledger)
    prop = planned["proposal"]
    built = ip.build(boxes, {"r_syn": prop}, {"r_syn": "SINTETICO"}, (cdir / "shell" / "model.skp").resolve(), cdir, ledger)
    return {"case": "fixture", "status": built["status"], "proposal": prop.to_dict(), "build": built,
            "ledger": ledger.to_dict()}


def fixture_in_own_process(out: Path) -> dict:
    """A fixture roda noutro processo SEM `PT_TO_M`: o shell builder usa a escala padrao para consensus fora de
    fixtures/<planta>/, e as caixas da fixture precisam nascer na MESMA escala (core.scale congela no 1o import).
    Achado da 1a execucao: shell a 0,0352 e caixas a 0,0259 = mobilia fora do comodo com "conformidade" verde."""
    import os
    env = {k: v for k, v in os.environ.items() if k != "PT_TO_M"}
    res_path = out / "fixture_case.json"
    res_path.unlink(missing_ok=True)
    r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--fixture-case", str(out)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=1200)
    if not res_path.exists():
        return {"case": "fixture", "status": "FIXTURE_PROCESS_FAILED", "tail": (r.stdout + r.stderr)[-1500:]}
    return json.loads(res_path.read_text("utf-8"))


def real_case(out: Path) -> dict:
    from core.pipeline_contracts import GenerationRequest
    from tools.orchestration import intelligent_pipeline as ip
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    from tools.sketchup.runtime_identity import check
    src = PLANTA_74_CONSENSUS.relative_to(ROOT).as_posix()
    req = GenerationRequest("planta_74", src, sha(ROOT / src), git("rev-parse", "HEAD"), "INTELLIGENT_BUILD",
                            (out / "real").relative_to(ROOT).as_posix() if out.is_relative_to(ROOT) else str(out / "real"),
                            ("r006",))
    m = ip.run(req, runtime_check=lambda prof: check(prof, expected_commit=git("rev-parse", "HEAD")))
    if m["status"] == "BLOCKED_RUNTIME":
        return {"case": "real_r006", "status": "BLOCKED_RUNTIME", "runtime": m["runtime"]}
    prop = m["_proposals"]["r006"]
    from tools.furnish_apartment import CONSENSUS, collect_boxes
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _ = collect_boxes(json.loads(CONSENSUS.read_text("utf-8")))
    ledger = m["_ledger"]
    built = ip.build(boxes, {"r006": prop}, {"r006": "BANHO 02"}, ROOT / "artifacts/planta_74/planta_74.skp", out / "real",
                     ledger, diagnostic=not prop.buildable_as_valid)
    ip.write({**m, "build": built, "ledger": ledger.to_dict()}, out / "real")
    return {"case": "real_r006", "status": built["status"], "proposal": prop.to_dict(), "build": built,
            "runtime": m["runtime"]["status"], "runtime_reasons": m["runtime"]["reasons"]}


def main(out: Path) -> int:
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    before = {p: sha(ROOT / p) for p in PROTECTED}
    summary = {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")), "cases": []}
    summary["cases"].append(fixture_in_own_process(out))
    summary["cases"].append(real_case(out))
    summary["protected_unchanged"] = before == {p: sha(ROOT / p) for p in PROTECTED}
    ok_fixture = summary["cases"][0]["status"] == "BUILT"
    ok_real = summary["cases"][1]["status"] in ("BUILT", "DIAGNOSTIC_NOT_VALID")
    summary["result"] = "PASS" if ok_fixture and ok_real and summary["protected_unchanged"] else "FAIL"
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str) + "\n", "utf-8")
    print(summary["result"], [(c["case"], c["status"]) for c in summary["cases"]], "dirty", summary["dirty"])
    return 0 if summary["result"] == "PASS" else 1


if __name__ == "__main__":
    if sys.argv[1] == "--fixture-case":
        from core.pipeline_contracts import CapabilityLedger
        from core.scale import PT_TO_M
        o = Path(sys.argv[2]).resolve()
        res = {**fixture_case(o, CapabilityLedger), "pt_to_m": PT_TO_M}
        (o / "fixture_case.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), "utf-8")
        sys.exit(0)
    sys.exit(main(Path(sys.argv[1])))
