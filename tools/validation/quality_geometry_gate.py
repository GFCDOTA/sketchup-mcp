"""quality_geometry_gate.py — regressao geometrica e completude do programa da planta_74 (Quality Guardian, P1).

Gera o apartamento (`collect_boxes`), roda o pre-voo obrigatorio e valida as CAIXAS PROPOSTAS com o mesmo validador do construido
(`box_geometry`, o gemeo) contra o baseline de defeitos da FP-055 P4 e o programa de mobiliario da FP-056 P2.

Veredito (nunca confunde teste verde com aprovacao geometrica ou funcional):
- FAIL     defeito NOVO ou PIOR, pre-voo reprovado, ou perda de programa SEM registro em `docs/governance/known_gaps.json`;
- KNOWN    so ha o que ja esta registrado (defeitos do baseline; perda de programa ligada a uma Issue de decisao). Nao e aprovacao:
           `geometric_approved` e `functional_approved` saem sempre `false` enquanto houver defeito conhecido ou perda de programa;
- PASS     sem defeito conhecido nem perda (ainda nao ocorre na planta_74).
Gemeo em caixas NAO substitui o SketchUp real (L2): a prova real e `artifacts/review/fp056/p6/`.

Uso (escala da planta, processo novo):  PT_TO_M=0.0259 python -m tools.validation.quality_geometry_gate
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def evaluate() -> dict:
    from tools.furnish_apartment import collect_boxes
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    from tools.validation import box_geometry as bx
    from tools.validation import defect_baseline as db
    from tools.validation import layout_preflight
    from tools.validation.layout_preflight import allows_materialization, preflight
    con = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, summary = collect_boxes(con)
    pre = preflight(con, boxes, summary, layout_preflight.planta74_twin(PLANTA_74_CONSENSUS))
    rooms = {r["id"]: str(r.get("name") or r["id"]) for r in con["rooms"]}
    reports = bx.validate_boxes(con, boxes, PLANTA_74_CONSENSUS, rooms)
    base = json.loads((ROOT / "artifacts/review/fp055/p4/defect_baseline.json").read_text("utf-8"))["defects"]
    program = json.loads((ROOT / "artifacts/review/fp056/p2/program_baseline.json").read_text("utf-8"))["program"]
    reg = db.regression(reports, base, program)
    from tools.validation import known_gaps
    known = {"program": {}, **known_gaps.load()}
    registered = set(known.get("program", {}))
    unregistered = sorted(set(reg["missing_program"]) - registered)
    stale = sorted(registered - set(reg["missing_program"]))             # registro de lacuna que ja nao existe: limpar
    reasons = []
    borderline = set(known.get("twin_borderline", {}))          # medida a ~0,1 mm do limiar so no gemeo (o construido mede dentro do ruido)
    new = [d for d in reg["new"] if d["key"] not in borderline]
    if new or reg["worse"]:
        reasons.append(f"defeito novo={new} pior={reg['worse']}")
    if not allows_materialization(pre):
        reasons.append(f"pre-voo {pre['status']}: {[(b['room_id'], b['gate']) for b in pre['blocking']]}")
    if unregistered:
        reasons.append(f"perda de programa sem registro: {unregistered}")
    if stale:
        reasons.append(f"lacuna registrada que nao existe mais (remover de known_gaps.json): {stale}")
    from tools.validation import room_collisions
    sweep_now = {f"{d['door']}|{d['module']}" for r in room_collisions.audit(con, boxes).values() for d in r["door_sweep_hits"]}
    sweep_registered = set(known.get("door_sweep", {}))
    if sweep_now - sweep_registered:
        reasons.append(f"peca na varredura real da folha sem registro: {sorted(sweep_now - sweep_registered)}")
    if sweep_registered - sweep_now:
        reasons.append(f"door_sweep registrado que nao existe mais (remover de known_gaps.json): {sorted(sweep_registered - sweep_now)}")
    persisting = len(reg.get("compared_rooms", [])) and sum(1 for b in base) - len(reg["resolved"]) - len(reg.get("vanished_with_piece", []))
    known_pending = bool(reg["missing_program"]) or persisting > 0 or bool(sweep_now)
    verdict = "FAIL" if reasons else ("KNOWN" if known_pending else "PASS")
    return {"verdict": verdict, "reasons": reasons, "new": new, "twin_borderline_ignored": [d["key"] for d in reg["new"] if d["key"] in borderline], "worse": reg["worse"], "resolved": reg["resolved"],
            "vanished_with_piece": reg.get("vanished_with_piece", []), "missing_program": reg["missing_program"],
            "known_program_gaps": {k: known["program"][k] for k in sorted(registered & set(reg["missing_program"]))},
            "persisting_baseline_defects": persisting, "known_door_sweep": sorted(sweep_now), "preflight": pre["status"], "boxes": len(boxes),
            "geometric_approved": verdict == "PASS", "functional_approved": verdict == "PASS",
            "basis": "gemeo em caixas (L1); a prova no SketchUp real fica em artifacts/review/fp056/p6/"}


def main() -> int:
    res = evaluate()
    print(json.dumps(res, indent=1, ensure_ascii=False))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"### Quality Guardian — geometria e programa: **{res['verdict']}**\n\n"
                     f"- novos: {len(res['new'])}, piores: {len(res['worse'])}, resolvidos: {len(res['resolved'])}, "
                     f"persistentes do baseline: {res['persisting_baseline_defects']}\n"
                     f"- perda de programa registrada: {list(res['known_program_gaps'])}\n"
                     f"- aprovado geometrico/funcional: {res['geometric_approved']}/{res['functional_approved']} (gemeo L1)\n")
    return 1 if res["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
