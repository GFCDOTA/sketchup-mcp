"""wall_affordance.py — Interior Common Sense Engine (slice 1b): WallAffordanceMap.
Pra um comodo, pontua CADA parede pra receber TV/rack e sofa. Captura a regra
profissional: TV vai em parede LIMPA, longa, ancorada — nao em parede de porta/
janela/passagem nem virada pra abertura de outro comodo. Vira RoomAffordanceReport
(melhores paredes pra TV + rejeitadas + por que). Deterministico, sem SU.

Uso: python interior/semantics/wall_affordance.py [r002]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from interior.semantics.room_graph import build_room_graph   # noqa: E402
from tools.spatial_model import build_spatial_model           # noqa: E402

DOORISH = ("interior_door", "interior_passage")


def wall_affordance(con, room_id, graph=None):
    sm = build_spatial_model(con, room_id)
    graph = graph or build_room_graph(con)
    by = {}
    for o in sm["openings"]:
        by.setdefault(o["wall_id"], []).append(o.get("kind"))
    wall_nb = {}   # wall_id -> comodos vizinhos via conector nessa parede
    for c in graph["connectors"]:
        if room_id in c["rooms"]:
            wall_nb.setdefault(c["wall_id"], []).extend(r for r in c["rooms"] if r != room_id)

    walls = []
    for w in sm["walls"]:
        wid, L, kinds = w["id"], w["length_m"], by.get(w["id"], [])
        has_door = any(k in DOORISH for k in kinds)
        has_win = "window" in kinds
        has_bal = "glazed_balcony" in kinds
        clean = not (has_door or has_win or has_bal)
        nb = sorted(set(wall_nb.get(wid, [])))
        # rack/TV exige parede LIMPA (regra profissional): porta/janela/passagem/
        # balcao DESQUALIFICA (nao basta penalizar por comprimento — senao uma
        # parede-corredor de 15m com porta "ganharia" de uma parede limpa).
        notes = []
        if not clean:
            if has_bal:
                notes.append("porta-balcao")
            if has_door:
                notes.append("porta/passagem")
            if has_win:
                notes.append("janela")
            if nb:
                notes.append(f"limiar p/ {nb}")
            tv = round(-100.0 + L, 1)          # rejeitada (ordena por tamanho entre rejeitadas)
        else:
            notes.append("limpa")
            tv = L * 14.0 + 20.0
            if L < 1.5:
                tv -= 50; notes.append("curta")
            tv = round(tv, 1)
        sofa = (L * 10.0 + (25 if clean else 0) - (50 if has_door else 0)
                - (20 if has_win else 0) - (60 if has_bal else 0))
        walls.append({"wall_id": wid, "length_m": round(L, 2), "openings": kinds,
                      "clean": clean, "neighbors": nb,
                      "tv_score": round(tv, 1), "sofa_score": round(sofa, 1), "notes": notes})
    walls.sort(key=lambda x: -x["tv_score"])
    best = [w for w in walls if w["tv_score"] > 0]
    rejected = [w for w in walls if w["tv_score"] <= 0]
    return {"room_id": room_id, "room_name": sm.get("room_name"),
            "best_tv_wall": best[0]["wall_id"] if best else None,
            "best_tv_walls": best[:3], "rejected_tv_walls": rejected, "walls": walls}


if __name__ == "__main__":
    rid = sys.argv[1] if len(sys.argv) > 1 else "r002"
    con = json.loads((ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    rep = wall_affordance(con, rid)
    print(f"=== {rid} ({rep['room_name']}) — WallAffordanceMap (TV) ===")
    for w in rep["walls"]:
        flag = "TV>" if w["wall_id"] == rep["best_tv_wall"] else "   "
        print(f"  {flag} {w['wall_id']:5} L{w['length_m']:.2f} tv={w['tv_score']:>6} "
              f"sofa={w['sofa_score']:>6} | {w['notes']}")
    print(f"  => melhor parede de TV: {rep['best_tv_wall']}")
    out = ROOT / f"artifacts/review/interior/affordance_{rid}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  -> {out.relative_to(ROOT)}")
