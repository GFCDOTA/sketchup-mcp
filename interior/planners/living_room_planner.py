"""living_room_planner.py — Interior Common Sense Engine (slice 1c): PLACEMENT SOLVER
da sala. NAO "coloca movel": RESOLVE RESTRICAO. Usa o WallAffordanceMap (TV em parede
LIMPA) + escolhe a parede do SOFA de FRENTE pra TV (normal oposta) fora das zonas de
circulacao, gera CANDIDATOS, pontua (hard reject + soft) e emite um ValidationReport
(porque ganhou / porque rejeitou). Saida = PlacementPlan (parede/centro/facing/justif).
Deterministico, sem SU. Reusa as zonas de circulacao/giro de porta dos brains.

Uso: python interior/planners/living_room_planner.py [r002]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shapely.ops import unary_union                              # noqa: E402
from interior.semantics.wall_affordance import wall_affordance   # noqa: E402
from tools.bedroom_layout import _door_zones, _fbox, _wall_setup, M  # noqa: E402
from tools.spatial_model import PT_TO_M, build_spatial_model     # noqa: E402

PT_TO_IN = (0.19 / 5.4) * 39.3700787402
SOFA_W, SOFA_D = 2.20, 0.95          # default; pode vir do catalogo
TV_MIN_VIEW, TV_MAX_VIEW = 1.8, 5.0  # distancia sofa-TV plausivel (m)


def _inward_normal(ws):
    return (0.0, float(ws["sgn"])) if ws["orient"] == "h" else (float(ws["sgn"]), 0.0)


def _wall_center_point(ws, inward_offset_m):
    """Ponto (pdf pts) no meio da parede, deslocado p/ dentro do comodo."""
    amid = (ws["along_lo"] + ws["along_hi"]) / 2.0
    perp = ws["face"] + ws["sgn"] * M(inward_offset_m)
    return (amid, perp) if ws["orient"] == "h" else (perp, amid)


def _slide_clear(ws, cell, keepout, w_m, d_m):
    """Desliza o movel pela parede (range no comodo) e devolve o along do 1o spot
    dentro do comodo + LIVRE de circulacao (preferindo o centro). None se nao acha."""
    lo = ws["along_lo"] + M(w_m / 2 + 0.1)
    hi = ws["along_hi"] - M(w_m / 2 + 0.1)
    if hi <= lo:
        return None
    mid = (lo + hi) / 2
    comodo = cell.buffer(M(0.06))
    nstep = max(1, int((hi - lo) / M(0.15)))
    for i in sorted(range(nstep + 1), key=lambda j: abs((lo + (hi - lo) * j / nstep) - mid)):
        ac = lo + (hi - lo) * i / nstep
        b = _fbox(ws["orient"], ws["face"], ws["sgn"], ac, M(0.03), M(w_m), M(d_m))
        if not comodo.contains(b):
            continue
        if keepout is not None and b.intersection(keepout).area > (0.05 / PT_TO_M ** 2):
            continue
        return ac
    return None


def plan_living(con, room_id, sofa_w=SOFA_W, sofa_d=SOFA_D):
    sm = build_spatial_model(con, room_id)
    aff = wall_affordance(con, room_id)
    tv_id = aff["best_tv_wall"]
    report = {"room_id": room_id, "room_name": sm.get("room_name"),
              "tv_wall": tv_id, "candidates_sofa": [], "rejected_sofa": []}
    if tv_id is None:
        report["result"] = "NO_TV_WALL"
        report["reason"] = "nenhuma parede limpa serve de parede-TV"
        return report
    tv_ws = _wall_setup(sm, tv_id)
    tv_n = _inward_normal(tv_ws)
    tv_pt = _wall_center_point(tv_ws, 0.25)            # rack ~0.25m da parede

    circ = list(sm["_geom"]["circ"] or [])
    dz = _door_zones(sm)
    if dz is not None:
        circ.append(dz)
    keepout = unary_union(circ) if circ else None

    cell = sm["_geom"]["cell"]
    for w in aff["walls"]:
        if w["wall_id"] == tv_id:
            continue
        ws = _wall_setup(sm, w["wall_id"])
        if ws is None:
            continue
        n = _inward_normal(ws)
        oppose = -(n[0] * tv_n[0] + n[1] * tv_n[1])   # 1 = parede oposta (sofa de frente p/ TV)
        rej = []
        if not w["clean"]:
            rej.append("parede nao-limpa (porta/janela)")
        if oppose < 0.5:
            rej.append(f"nao fica de frente pra TV (oppose {oppose:.2f})")
        if w["length_m"] < 1.6:
            rej.append("parede curta p/ sofa")
        # desliza o sofa pra achar um spot LIVRE de circulacao (ponta-cega -> centro)
        along = _slide_clear(ws, cell, keepout, sofa_w, sofa_d)
        if along is None:
            rej.append("sofa nao acha spot livre de circulacao na parede")
            along = (ws["along_lo"] + ws["along_hi"]) / 2
        perp = ws["face"] + ws["sgn"] * M(sofa_d / 2 + 0.03)
        sofa_pt = (along, perp) if ws["orient"] == "h" else (perp, along)
        dist_m = math.hypot(sofa_pt[0] - tv_pt[0], sofa_pt[1] - tv_pt[1]) * PT_TO_M
        ang = _angle(n, (tv_pt[0] - sofa_pt[0], tv_pt[1] - sofa_pt[1]))
        if ang > 30:
            rej.append(f"sofa nao olha pra TV (angulo {ang:.0f}>30)")
        if not (TV_MIN_VIEW <= dist_m <= TV_MAX_VIEW):
            rej.append(f"distancia sofa-TV {dist_m:.1f}m fora de [{TV_MIN_VIEW},{TV_MAX_VIEW}]")
        score = round(w["sofa_score"] + oppose * 40 - ang, 1)
        entry = {"wall_id": w["wall_id"], "length_m": w["length_m"], "clean": w["clean"],
                 "oppose": round(oppose, 2), "view_dist_m": round(dist_m, 2),
                 "face_angle_deg": round(ang, 1), "score": score, "rejects": rej,
                 "_pt": sofa_pt, "_n": n}
        (report["rejected_sofa"] if rej else report["candidates_sofa"]).append(entry)

    report["candidates_sofa"].sort(key=lambda c: -c["score"])
    if report["candidates_sofa"]:
        best = report["candidates_sofa"][0]
        sp, sn = best["_pt"], best["_n"]
        report["result"] = "OK"
        report["plan"] = {
            "tv_rack": {"wall_id": tv_id,
                        "center_in": [round(tv_pt[0] * PT_TO_IN, 1), round(tv_pt[1] * PT_TO_IN, 1)],
                        "facing": list(tv_n), "rule": "parede limpa (WallAffordanceMap)"},
            "sofa": {"wall_id": best["wall_id"],
                     "center_in": [round(sp[0] * PT_TO_IN, 1), round(sp[1] * PT_TO_IN, 1)],
                     "facing": list(sn), "width_m": sofa_w,
                     "rule": f"parede de frente p/ TV (oppose {best['oppose']}, ang {best['face_angle_deg']}, dist {best['view_dist_m']}m)"},
        }
    else:
        report["result"] = "NO_VALID_SOFA_WALL"
    for c in report["candidates_sofa"] + report["rejected_sofa"]:
        c.pop("_pt", None)
        c.pop("_n", None)
    return report


def _angle(a, b):
    na, nb = math.hypot(*a), math.hypot(*b)
    if na == 0 or nb == 0:
        return 180.0
    cos = max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / (na * nb)))
    return math.degrees(math.acos(cos))


if __name__ == "__main__":
    rid = sys.argv[1] if len(sys.argv) > 1 else "r002"
    con = json.loads((ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    rep = plan_living(con, rid)
    print(f"=== PlacementPlan {rid} ({rep['room_name']}) -> {rep['result']} ===")
    print(f"  TV/rack -> parede {rep['tv_wall']}")
    for c in rep["candidates_sofa"]:
        print(f"  SOFA cand {c['wall_id']} score {c['score']} oppose {c['oppose']} "
              f"ang {c['face_angle_deg']} dist {c['view_dist_m']}m")
    for c in rep["rejected_sofa"][:6]:
        print(f"  x rej {c['wall_id']}: {c['rejects']}")
    if rep.get("plan"):
        print("  PLANO:", json.dumps(rep["plan"], ensure_ascii=False))
    out = ROOT / f"artifacts/review/interior/placement_plan_{rid}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  -> {out.relative_to(ROOT)}")
