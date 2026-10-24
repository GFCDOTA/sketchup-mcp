"""Proposta somente-leitura por comodo (FP-054 F2E): solve (F2C) + ordem (F2D) -> antes/depois, NUNCA aplicada a planta.

    PT_TO_M=0.0259 python -m tools.validation.f2e_proposal_board artifacts/review/fp054/f2e

Tipos de proposta:
  NO_CHANGE_NEEDED      o ORIGINAL ja e viavel e e o 1o da ordem;
  PROPOSAL_FEASIBLE     ha alternativa viavel no DOF declarado (precisa de aprovacao do Felipe e L2 antes de virar planta);
  CLOSEST_INFEASIBLE    nada viavel no DOF declarado: mostra o mais proximo e as decisoes que destravariam — NAO e solucao;
  NOT_SOLVED            entrada invalida ou orcamento esgotado (UNKNOWN).
Os overlays de antes/depois sao desenhados com as MESMAS linhas de avaliacao que decidiram o estado (sem recalculo no desenho).
"""
from __future__ import annotations

import json
from pathlib import Path

from tools.rooms.shared.spatial_solver.candidates import apply_candidate
from tools.rooms.shared.spatial_solver.problem import build_problem
from tools.rooms.shared.spatial_solver.ranking import rank
from tools.rooms.shared.spatial_solver.solver import DEFAULT_MAX_CANDIDATES, neighborhood, solve

ROOMS = (("r004", "KITCHEN"), ("r005", "BATHROOM"), ("r006", "BATHROOM"), ("r007", "BATHROOM"))

# o que destravaria cada violacao residual (codigo, culpado) — sempre decisao do Felipe, nunca aplicado aqui
_UNBLOCK = {
    ("FUNCTIONAL_SHOWER_ENTRY_WIDTH", "WALL"): "vao do box vem do modelo da porta no builder: parametro do vao (decisao)",
    ("FUNCTIONAL_SHOWER_ENTRY_WIDTH", "DECLARED_ENTRY"): "vao do box vem do modelo da porta no builder: parametro do vao (decisao)",
    ("FUNCTIONAL_TOILET_FRONT_CLEARANCE", "WALL"): "profundidade do comodo limita a frente do vaso: outra parede ou louca mais curta (decisao)",
    ("FUNCTIONAL_SHOWER_REACH_PATH", "BOTTLENECK"): "passagem ate o box estreita: depende do vao/posicao do box (decisao)",
}


def _rows_by_constraint(rows):
    return {(r["object_id"], r["constraint"]): r for r in rows}


def propose(con, boxes, ifaces, room_id, room_type, room_name, max_candidates=DEFAULT_MAX_CANDIDATES) -> dict:
    problem = build_problem(con, boxes, room_id, room_type, ifaces)
    res = solve(problem, con, boxes, ifaces, room_name, max_candidates)
    if res.status in ("INVALID_INPUT", "UNKNOWN"):
        return {"room_id": room_id, "kind": "NOT_SOLVED", "status": res.status, "issues": res.issues, "notes": res.notes,
                "applied": False}
    ranked = rank(res.results)
    best = ranked[0]
    orig = res.original
    kind = ("NO_CHANGE_NEEDED" if best.result.candidate.candidate_id == "ORIGINAL" and best.result.feasible
            else "PROPOSAL_FEASIBLE" if best.result.feasible else "CLOSEST_INFEASIBLE")
    before, after = _rows_by_constraint(orig.evaluation["rows"]), _rows_by_constraint(best.result.evaluation["rows"])
    delta = [{"object_id": k[0], "constraint": k[1], "before_m": before[k]["measured"], "after_m": after[k]["measured"],
              "before": before[k]["verdict"], "after": after[k]["verdict"]}
             for k in sorted(before) if k in after and (before[k]["measured"], before[k]["verdict"]) != (after[k]["measured"], after[k]["verdict"])]
    unblock = sorted({_UNBLOCK.get((v["code"], v.get("culprit")), f"{v['code']} ({v.get('culprit')}): fora do DOF declarado")
                      for v in best.result.hard_violations})
    return {"room_id": room_id, "kind": kind, "status": res.status, "applied": False,
            "candidates_total": res.total_candidates, "original_rank": next(x.rank for x in ranked if x.result is orig),
            "best": best.to_dict(), "original": {"hard_violations": orig.hard_violations, "metrics": orig.metrics},
            "delta": delta, "decisions_to_unblock": unblock, "notes": res.notes,
            "versions": {"algorithm": res.algorithm_version, "policy": res.policy_version},
            "_rows": {"before": orig.evaluation["rows"], "after": best.result.evaluation["rows"]},
            "_candidate": best.result.candidate}


def build(out_dir: Path, con, boxes, ifaces, max_candidates=DEFAULT_MAX_CANDIDATES) -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from tools.validation import functional_clearance_board as fb
    names = {r["id"]: r.get("name") for r in con.get("rooms", [])}
    out_dir.mkdir(parents=True, exist_ok=True)
    written, summary = [], []
    for rid, rtype in ROOMS:
        p = propose(con, boxes, ifaces, rid, rtype, names.get(rid) or rid, max_candidates)
        rows, cand = p.pop("_rows", None), p.pop("_candidate", None)
        summary.append(p)
        if rows is None:
            continue
        problem = build_problem(con, boxes, rid, rtype, ifaces)
        local = neighborhood(con, boxes, rid)
        after_boxes, _ = apply_candidate(problem, local, ifaces, cand, names.get(rid) or rid)
        fig = plt.figure(figsize=(22, 10))
        fig.suptitle(f"FP-054 F2E — {rid} {p['kind']} (proposta NAO aplicada) — {cand.candidate_id}", fontsize=14, weight="bold")
        for i, (label, bx, rr) in enumerate((("ANTES (ORIGINAL)", local, rows["before"]), ("DEPOIS (1o da ordem)", after_boxes, rows["after"]))):
            texts = fb._draw(fig.add_axes([0.01 + i * 0.5, 0.32, 0.48, 0.60]), rid, label, rr, fb._ctx(con, bx, rid))
            fb._legend_rows(fig.add_axes([0.02 + i * 0.5, 0.02, 0.47, 0.28]), texts)
        f = out_dir / f"{rid}_before_after.png"
        fig.savefig(f, dpi=90)
        plt.close(fig)
        written.append(f)
    j = out_dir / "proposals.json"
    j.write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str) + "\n", "utf-8", newline="\n")
    return [j, *written]

