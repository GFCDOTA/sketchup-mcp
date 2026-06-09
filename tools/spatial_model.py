"""Etapa A — spatial model do comodo (interior layout brain).

Deriva do consensus (geometria ja extraida do PDF, ZERO 3D Warehouse) o modelo
espacial de um comodo: celula, paredes (borda x interna), aberturas (porta /
janela / porta-vidro), zonas de circulacao, area util mobiliavel, paredes
cegas, e um RANKING da parede de TV (score + limitacoes, NUNCA regra unica;
marca AMBIGUOUS quando incerto).

Objetivo: provar que o cerebro sabe ONDE PODE e ONDE NAO PODE por movel — nao
"decorar bonito". Felipe 2026-06-04.

Uso: python -m tools.spatial_model --room r002   (default planta_74 / r002)
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from tools.build_plan_shell_skp import compute_room_floors, wall_footprint

# escala vem da FONTE ÚNICA (core.scale); re-export p/ quem faz
# `from tools.spatial_model import PT_TO_M`. NÃO redefinir escala aqui.
from core.scale import M, M_TO_IN, PT_TO_IN, PT_TO_M  # noqa: F401
CIRC_M = 0.85          # faixa de circulacao em frente a porta (m)
MIN_USEFUL_M = 1.2     # comprimento minimo de parede util (m)
SOFA_MIN_DEPTH_M = 2.2  # distancia minima sofa->TV pra a parede valer
CARVE_KINDS = ("interior_door", "interior_passage", "glazed_balcony")


def _envelope(con: dict, wp: list, wt: float):
    """Contorno do apE (paredes + guarda-corpos, buracos preenchidos)."""
    sb = [LineString([tuple(p) for p in s["polyline_pts"]]).buffer(
              wt / 2.0, cap_style=2, join_style=2)
          for s in con.get("soft_barriers", []) or []
          if len(s.get("polyline_pts") or []) >= 2]
    src = unary_union(wp + sb)
    geoms = list(src.geoms) if hasattr(src, "geoms") else [src]
    return unary_union([Polygon(g.exterior) for g in geoms])


def _wlen_m(w):
    return math.dist(w["start"], w["end"]) * PT_TO_M


def _wall_mid(w):
    return ((w["start"][0] + w["end"][0]) / 2.0, (w["start"][1] + w["end"][1]) / 2.0)


def _classify_border(w, cell, envelope, wt):
    """border (perimetro/fachada) se o lado OPOSTO a sala cai fora do envelope;
    internal (divisoria) se cai dentro (outro comodo)."""
    cx, cy = _wall_mid(w)
    d = wt / 2.0 + 2.0
    cands = ([(cx, cy + d), (cx, cy - d)] if w["orientation"] == "h"
             else [(cx + d, cy), (cx - d, cy)])
    far = max(cands, key=lambda p: Point(p).distance(cell))   # lado oposto a sala
    return "border" if not envelope.contains(Point(far)) else "internal"


def _tv_depth_m(w, usable):
    """Profundidade livre em frente a parede (perpendicular), p/ caber sofa->TV."""
    cx, cy = _wall_mid(w)
    L = 100000.0
    rays = ([LineString([(cx, cy), (cx, cy + L)]), LineString([(cx, cy), (cx, cy - L)])]
            if w["orientation"] == "h"
            else [LineString([(cx, cy), (cx + L, cy)]), LineString([(cx, cy), (cx - L, cy)])])
    best = 0.0
    for ray in rays:
        inter = ray.intersection(usable)
        if not inter.is_empty:
            best = max(best, inter.length * PT_TO_M)
    return best


def build_spatial_model(con: dict, room_id: str) -> dict:
    wt = float(con.get("wall_thickness_pts") or 5.4)
    walls = {w["id"]: w for w in con["walls"]}
    wp = [wall_footprint(w, extend_endpoints=True) for w in con["walls"]]
    foot = {w["id"]: wp[i] for i, w in enumerate(con["walls"])}
    envelope = _envelope(con, wp, wt)

    e = compute_room_floors(con)[room_id]
    cell = Polygon(e["outer"], holes=e.get("holes") or [])

    room_walls = [wid for wid, f in foot.items() if f.distance(cell) < 0.8]
    ops_by_wall: dict = {}
    for o in con["openings"]:
        if o["wall_id"] in room_walls:
            ops_by_wall.setdefault(o["wall_id"], []).append(o)

    wall_recs = []
    for wid in room_walls:
        w = walls[wid]
        wall_recs.append({
            "id": wid,
            "type": _classify_border(w, cell, envelope, wt),
            "length_m": round(_wlen_m(w), 2),
            "orientation": w["orientation"],
            "openings": [o["id"] for o in ops_by_wall.get(wid, [])],
            "blind": wid not in ops_by_wall,
        })

    # --- circulacao (frente das portas/passagens/porta-vidro) ---
    circ = []
    depth = CIRC_M / PT_TO_M
    for o in con["openings"]:
        if o["wall_id"] not in room_walls or o["kind_v5"] not in CARVE_KINDS:
            continue
        w = walls[o["wall_id"]]
        cx, cy = o["center"]
        hw = (o["opening_width_pts"] + wt) / 2.0
        for sgn in (1, -1):
            r = (box(cx - hw, cy, cx + hw, cy + sgn * depth) if w["orientation"] == "h"
                 else box(cx, cy - hw, cx + sgn * depth, cy + hw))
            inter = r.intersection(cell)
            if inter.area > r.area * 0.25:
                circ.append(inter)
    circ_u = unary_union(circ) if circ else None
    usable = cell.difference(circ_u) if circ_u else cell
    if hasattr(usable, "geoms"):
        usable = max(usable.geoms, key=lambda g: g.area)

    # --- ranking da parede de TV (score, nao regra unica) ---
    blind = [r for r in wall_recs if r["blind"] and r["length_m"] >= MIN_USEFUL_M]
    door_centers = [o["center"] for o in con["openings"]
                    if o["wall_id"] in room_walls and o["kind_v5"] in CARVE_KINDS]
    scored = []
    for r in blind:
        w = walls[r["id"]]
        s, reasons = 0.0, []
        if r["type"] == "border":
            s += 40; reasons.append("parede de borda/perimetro (+40)")
        else:
            s -= 10; reasons.append("parede interna/divisoria (-10)")
        s += r["length_m"] * 5
        reasons.append(f"comprimento {r['length_m']}m (+{r['length_m']*5:.0f})")
        # arco de giro de porta perto das pontas
        ends = [Point(w["start"]), Point(w["end"])]
        near_door = any(min(Point(dc).distance(ep) for ep in ends) < 1.0 / PT_TO_M
                        for dc in door_centers)
        if near_door:
            s -= 15; reasons.append("porta/arco de giro perto da ponta (-15)")
        # distancia sofa->TV
        dep = _tv_depth_m(w, usable)
        if dep < SOFA_MIN_DEPTH_M:
            s -= 30; reasons.append(f"profundidade so {dep:.1f}m p/ sofa->TV (-30)")
        else:
            s += 15; reasons.append(f"profundidade {dep:.1f}m ok p/ sofa->TV (+15)")
        scored.append({"wall_id": r["id"], "score": round(s, 1), "type": r["type"],
                       "length_m": r["length_m"], "depth_m": round(dep, 2),
                       "reasons": reasons})
    scored.sort(key=lambda x: -x["score"])

    if not scored:
        tv = {"confidence": "none", "best": None, "candidates": [],
              "limitations": ["nenhuma parede cega util >= 1.2 m"]}
    else:
        top = scored[0]
        runner = scored[1]["score"] if len(scored) > 1 else -1e9
        ambiguous = top["score"] < 30 or (top["score"] - runner) < 15
        tv = {
            "confidence": "ambiguous" if ambiguous else "ok",
            "best": top["wall_id"] if not ambiguous else None,
            "best_candidate": top["wall_id"],   # melhor palpite, mesmo se ambiguo
            "candidates": scored,
            "limitations": [
                "score heuristico — validar no SketchUp / olho humano",
                "nao considera vista, iluminacao natural nem estilo",
                "AMBIGUOUS = nao cravar; oferecer top-2 ao humano",
            ],
        }

    return {
        "stage": "A_spatial_model",
        "room_id": room_id,
        "room_name": next((r.get("name") for r in con["rooms"] if r["id"] == room_id), ""),
        "area_m2": round(cell.area * PT_TO_M ** 2, 1),
        "usable_area_m2": round(usable.area * PT_TO_M ** 2, 1),
        "walls": wall_recs,
        "wall_counts": {
            "border": sum(1 for r in wall_recs if r["type"] == "border"),
            "internal": sum(1 for r in wall_recs if r["type"] == "internal"),
            "blind_useful": len(blind),
        },
        "openings": [{"id": o["id"], "kind": o["kind_v5"], "wall_id": o["wall_id"],
                      "center": o["center"]}
                     for o in con["openings"] if o["wall_id"] in room_walls],
        "circulation_area_m2": round((circ_u.area if circ_u else 0) * PT_TO_M ** 2, 1),
        "blind_wall_candidates": [r["id"] for r in blind],
        "tv_wall_candidate": tv,
        "note": ("Etapa A: NAO decide mobilia. Mapeia onde PODE/NAO PODE por movel. "
                 "tv_wall_candidate e palpite ranqueado, nao decisao final."),
        "_geom": {"cell": cell, "usable": usable, "circ": circ, "walls": walls,
                  "room_walls": room_walls, "con": con},
    }


def plot_model(model: dict, out_png: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    g = model["_geom"]
    cell, usable, circ, walls, room_walls = (g["cell"], g["usable"], g["circ"],
                                             g["walls"], g["room_walls"])
    con = g["con"]
    tv = model["tv_wall_candidate"]
    best = tv.get("best") or tv.get("best_candidate")
    blind = set(model["blind_wall_candidates"])
    fig, ax = plt.subplots(figsize=(12, 11))
    ax.fill(*cell.exterior.xy, color="0.85", zorder=1)
    if usable.geom_type == "Polygon":
        ax.fill(*usable.exterior.xy, color="#b9f6ca", alpha=0.7, zorder=2,
                label=f"area util {model['usable_area_m2']} m2")
    for r in circ:
        if r.geom_type == "Polygon":
            ax.fill(*r.exterior.xy, color="#ff8a80", alpha=0.6, zorder=3, hatch="//")
    clip = cell.buffer(walls[room_walls[0]].get("thickness", 5.4) * 1.6)
    for wid in room_walls:
        w = walls[wid]
        seg = LineString([tuple(w["start"]), tuple(w["end"])]).intersection(clip)
        if seg.is_empty:
            continue
        is_border = next(r["type"] for r in model["walls"] if r["id"] == wid) == "border"
        if wid == best:
            col, lw = "#1565c0", 6
        elif wid in blind:
            col, lw = ("#2e7d32" if is_border else "#9ccc65"), 3.5
        else:
            col, lw = ("0.25" if is_border else "0.55"), 2
        xs, ys = (seg.xy if seg.geom_type == "LineString"
                  else ([], []))
        if xs:
            ax.plot(xs, ys, color=col, lw=lw, zorder=4)
    for o in con["openings"]:
        if o["wall_id"] not in room_walls:
            continue
        cx, cy = o["center"]
        c = {"interior_door": "red", "window": "#1e88e5",
             "glazed_balcony": "purple"}.get(o["kind_v5"], "orange")
        ax.plot([cx], [cy], "o", ms=11, color=c, zorder=6)
    if best:
        w = walls[best]
        ax.annotate(f"TV? ({tv['confidence']})", _wall_mid(w), color="#1565c0",
                    fontsize=14, fontweight="bold", zorder=7)
    ax.set_title(f"Etapa A — spatial model {model['room_id']} | verde=util · "
                 f"azul=TV candidate ({tv['confidence']}) · verde-escuro=cega borda · "
                 f"verde-claro=cega interna · vermelho=circulacao")
    ax.set_aspect("equal"); ax.invert_yaxis(); ax.legend(loc="upper right")
    plt.tight_layout(); plt.savefig(out_png, dpi=85)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus", default=r"fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
    ap.add_argument("--room", default="r002")
    ap.add_argument("--out-dir", default="artifacts/review/planta_74/spatial_model")
    args = ap.parse_args()

    con = json.loads(Path(args.consensus).read_text("utf-8"))
    model = build_spatial_model(con, args.room)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_model(model, out_dir / f"{args.room}_spatial_map.png")
    model.pop("_geom", None)
    (out_dir / f"{args.room}_spatial_model.json").write_text(
        json.dumps(model, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"SALA {model['room_id']} ({model['room_name']}) — {model['area_m2']} m2, "
          f"util {model['usable_area_m2']} m2")
    print(f"paredes: {model['wall_counts']}")
    print(f"aberturas: {len(model['openings'])} | circulacao {model['circulation_area_m2']} m2")
    tv = model["tv_wall_candidate"]
    print(f"TV candidate: confidence={tv['confidence']} best={tv.get('best')} "
          f"(palpite {tv.get('best_candidate')})")
    for c in tv.get("candidates", []):
        print(f"  {c['wall_id']} score={c['score']} {c['type']} len={c['length_m']}m "
              f"depth={c['depth_m']}m")
    print(f"-> {out_dir}/")


if __name__ == "__main__":
    main()
