"""Etapa B+C — layout candidates (interior layout brain).

A partir do spatial_model (Etapa A), posiciona MOVEIS PLACEHOLDER (bounding
boxes, NAO assets 3D) em 3 templates de sala, e scoreia cada candidato por
gates DUROS (nao invadir parede/circulacao/porta/janela; passagem >= 0.80 m) e
SUAVES (orientacao sofa->TV, distancia plausivel, proporcao). Se nenhum passa
-> NO_VALID_LAYOUT (nao forca sofa aleatorio).

Objetivo: provar que o cerebro sabe POSICIONAR movel basico sem bloquear
circulacao/portas/janelas/varanda. NAO usa 3D Warehouse, NAO baixa asset, NAO
aplica estilo, NAO insere no SKP. Felipe 2026-06-04.

Uso: python -m tools.layout_candidates --room r002
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from shapely.geometry import Point, box
from shapely.ops import unary_union

from tools.spatial_model import (PT_TO_M, _tv_depth_m, _wall_mid,
                                 build_spatial_model, wall_footprint)


def M(m):           # metros -> pdf-points
    return m / PT_TO_M


# moveis placeholder: (largura ao-longo, profundidade perp) em metros
FURN = {
    "sofa_3": (2.20, 0.95),
    "sofa_2": (1.80, 0.90),
    "rack_tv": (1.80, 0.45),
    "mesa_centro": (1.00, 0.60),
    "poltrona": (0.85, 0.85),
}
PASSAGE_M = 0.80
SOFA_TV_MIN, SOFA_TV_MAX = 2.3, 4.0
SOFA_TV_IDEAL = (2.6, 3.0)   # faixa ideal de distancia sofa<->TV (m)
FILL_IDEAL = (0.25, 0.45)    # area de moveis / area util ideal
RESPIRO_IDEAL = 0.60         # fracao de area livre alvo (sobra sem ficar vazio)
MARGIN_M = 0.03        # recuo do movel da face da parede (encosta sem cravar)
TOL_CIRC_M2 = 0.02     # quase-zero: movel NAO pode bloquear circulacao/abertura
TOL_WALL_M2 = 0.06     # toque leve na parede e OK (movel encosta)
COMODO_FOLGA_M = 0.06  # folga p/ "dentro do comodo" (borda da celula)


def _fbox(orient, face, sgn, along_c, perp_d, w_along, w_perp):
    """Box axis-aligned de um movel, alinhado a parede de referencia (h/v).
    face = coord da face interna da parede; sgn = sentido pra dentro da sala;
    perp_d = recuo da face; along_c = centro ao longo da parede."""
    p0, p1 = face + sgn * perp_d, face + sgn * (perp_d + w_perp)
    pa, pb = min(p0, p1), max(p0, p1)
    a0, a1 = along_c - w_along / 2, along_c + w_along / 2
    return box(pa, a0, pb, a1) if orient == "v" else box(a0, pa, a1, pb)


def _tv_setup(sm):
    g = sm["_geom"]
    walls, cell = g["walls"], g["cell"]
    tid = sm["tv_wall_candidate"].get("best_candidate")
    if not tid:
        return None
    w = walls[tid]
    wt = float(g["con"]["wall_thickness_pts"])
    cx, cy = _wall_mid(w)
    d = wt / 2 + 2
    if w["orientation"] == "v":
        sgn = 1 if cell.distance(Point(cx + d, cy)) < cell.distance(Point(cx - d, cy)) else -1
        face, along_c = cx + sgn * wt / 2, cy
    else:
        sgn = 1 if cell.distance(Point(cx, cy + d)) < cell.distance(Point(cx, cy - d)) else -1
        face, along_c = cy + sgn * wt / 2, cx
    return {"id": tid, "wall": w, "orient": w["orientation"], "sgn": sgn,
            "face": face, "along_c": along_c,
            "depth": _tv_depth_m(w, g["usable"]) / PT_TO_M}


def _item(kind, b, **kw):
    return {"kind": kind, "box": b, **kw}


def template_sofa_wall(s):
    """T1: rack na parede-TV, sofa 3-lug encostado na parede OPOSTA, mesa no meio."""
    o, f, sg, ac, dep = s["orient"], s["face"], s["sgn"], s["along_c"], s["depth"]
    rw, rd = M(FURN["rack_tv"][0]), M(FURN["rack_tv"][1])
    sw, sd = M(FURN["sofa_3"][0]), M(FURN["sofa_3"][1])
    sp = max(dep - sd - M(MARGIN_M), M(SOFA_TV_MIN))
    mw, md = M(FURN["mesa_centro"][0]), M(FURN["mesa_centro"][1])
    mp = (rd + sp) / 2 - md / 2
    return [_item("rack_tv", _fbox(o, f, sg, ac, M(MARGIN_M), rw, rd)),
            _item("sofa_3", _fbox(o, f, sg, ac, sp, sw, sd), facing="tv", dist_m=round((sp + sd / 2) * PT_TO_M, 2)),
            _item("mesa_centro", _fbox(o, f, sg, ac, mp, mw, md))]


def template_sofa_float(s):
    """T2: sofa flutuante a ~1.9 m da TV (setoriza estar/jantar), mesa entre."""
    o, f, sg, ac, dep = s["orient"], s["face"], s["sgn"], s["along_c"], s["depth"]
    rw, rd = M(FURN["rack_tv"][0]), M(FURN["rack_tv"][1])
    sw, sd = M(FURN["sofa_3"][0]), M(FURN["sofa_3"][1])
    sp = min(M(1.9), max(dep - sd - M(0.6), M(SOFA_TV_MIN)))
    mw, md = M(FURN["mesa_centro"][0]), M(FURN["mesa_centro"][1])
    mp = (rd + sp) / 2 - md / 2
    return [_item("rack_tv", _fbox(o, f, sg, ac, M(MARGIN_M), rw, rd)),
            _item("sofa_3", _fbox(o, f, sg, ac, sp, sw, sd), facing="tv", dist_m=round((sp + sd / 2) * PT_TO_M, 2)),
            _item("mesa_centro", _fbox(o, f, sg, ac, mp, mw, md))]


def template_sofa_poltrona(s):
    """T3: rack-TV + sofa 3-lug na parede oposta + poltrona deslocada ao lado."""
    o, f, sg, ac, dep = s["orient"], s["face"], s["sgn"], s["along_c"], s["depth"]
    rw, rd = M(FURN["rack_tv"][0]), M(FURN["rack_tv"][1])
    sw, sd = M(FURN["sofa_3"][0]), M(FURN["sofa_3"][1])
    sp = max(dep - sd - M(MARGIN_M), M(SOFA_TV_MIN))
    pw, pd = M(FURN["poltrona"][0]), M(FURN["poltrona"][1])
    items = [_item("rack_tv", _fbox(o, f, sg, ac, M(MARGIN_M), rw, rd)),
             _item("sofa_3", _fbox(o, f, sg, ac, sp, sw, sd), facing="tv", dist_m=round((sp + sd / 2) * PT_TO_M, 2))]
    # poltrona ao lado do sofa (deslocada no eixo ao-longo), recuada
    items.append(_item("poltrona", _fbox(o, f, sg, ac + sw / 2 + pw / 2 + M(0.2), sp - M(0.4), pw, pd), facing="tv"))
    return items


TEMPLATES = [("sofa_contra_parede", template_sofa_wall),
             ("sofa_flutuante_setoriza", template_sofa_float),
             ("sofa_mais_poltrona", template_sofa_poltrona)]


def score(items, sm, tv):
    """HARD gates (binarios, reprovam) SEPARADOS de SOFT (continuo, ranqueia).
    total_score = soft_score se valido, senao 0."""
    g = sm["_geom"]
    walls, cell, usable, circ, room_walls, con = (g["walls"], g["cell"], g["usable"],
                                                  g["circ"], g["room_walls"], g["con"])
    wfoot = unary_union([wall_footprint(walls[wid], extend_endpoints=True) for wid in room_walls])
    circ_u = unary_union(circ) if circ else None
    tol_circ = TOL_CIRC_M2 / PT_TO_M ** 2
    tol_wall = TOL_WALL_M2 / PT_TO_M ** 2
    comodo = cell.buffer(M(COMODO_FOLGA_M))

    # ---------- HARD GATES (binarios) ----------
    hits_wall = hits_circ = out_room = False
    for it in items:
        if circ_u is not None and it["box"].intersection(circ_u).area > tol_circ:
            hits_circ = True
        if it["box"].intersection(wfoot).area > tol_wall:
            hits_wall = True
        if not comodo.contains(it["box"]):
            out_room = True
    free = usable
    for it in items:
        free = free.difference(it["box"])
    passage_ok = not free.buffer(-M(PASSAGE_M) / 2).is_empty
    hard = {"nao_invade_parede": not hits_wall,
            "nao_bloqueia_circulacao": not hits_circ,
            "nao_bloqueia_porta_janela": not hits_circ,   # circ ja inclui aberturas
            "dentro_do_comodo": not out_room,
            "passagem_min_080": passage_ok}
    valid = all(hard.values())

    # ---------- SOFT (continuo) ----------
    sofa = next((it for it in items if it["kind"].startswith("sofa")), None)
    rack = next((it for it in items if it["kind"] == "rack_tv"), None)
    dist = sofa.get("dist_m") if sofa else None
    door_pts = [Point(o["center"]) for o in con["openings"] if o["wall_id"] in room_walls]
    soft, pen, reasons = {}, [], []

    # orientacao sofa -> TV (15)
    if sofa and sofa.get("facing") == "tv":
        soft["orientacao_sofa_tv"] = 15.0
        reasons.append("sofa orientado para a TV (+15)")
    else:
        soft["orientacao_sofa_tv"] = 0.0
        pen.append("sofa NAO orientado para a TV (-15)")

    # distancia sofa<->TV no ideal 2.6-3.0 (25)
    lo, hi = SOFA_TV_IDEAL
    if dist is None:
        soft["dist_sofa_tv"] = 0.0
    elif lo <= dist <= hi:
        soft["dist_sofa_tv"] = 25.0
        reasons.append(f"sofa-TV {dist}m no ideal {lo}-{hi} (+25)")
    else:
        dev = min(abs(dist - lo), abs(dist - hi))
        soft["dist_sofa_tv"] = round(max(0.0, 25 - dev * 30), 1)
        pen.append(f"sofa-TV {dist}m fora do ideal (dev {dev:.2f}m, {soft['dist_sofa_tv']-25:.0f})")

    # sofa longe de porta/passagem (15)
    md = round(min((sofa["box"].distance(p) for p in door_pts), default=1e9) * PT_TO_M, 2) if sofa else None
    if md is None or md >= 0.6:
        soft["sofa_longe_porta"] = 15.0
    else:
        soft["sofa_longe_porta"] = round(max(0.0, 15 * md / 0.6), 1)
        pen.append(f"sofa colado em porta ({md}m < 0.6m, {soft['sofa_longe_porta']-15:.0f})")

    # alinhamento lateral sofa<->TV (10)
    off_m = None
    if sofa and rack:
        off = (abs(rack["box"].centroid.x - sofa["box"].centroid.x) if tv["orient"] == "h"
               else abs(rack["box"].centroid.y - sofa["box"].centroid.y))
        off_m = round(off * PT_TO_M, 2)
        soft["alinhamento_sofa_tv"] = round(max(0.0, 10 - off_m * 18), 1)
        if off_m > 0.2:
            pen.append(f"offset lateral sofa-TV {off_m}m ({soft['alinhamento_sofa_tv']-10:.0f})")
    else:
        soft["alinhamento_sofa_tv"] = 0.0

    # parede-TV plausivel: profundidade + bonus se for parede de fundo (borda) (15)
    depth_m = round(tv["depth"] * PT_TO_M, 2)
    tvtype = next((w["type"] for w in sm["walls"] if w["id"] == tv["id"]), "internal")
    soft["parede_tv"] = round(min(12.0, depth_m / 3.0 * 12) + (3.0 if tvtype == "border" else 0.0), 1)
    if tvtype != "border":
        pen.append("parede-TV interna/divisoria (nao e parede de fundo, -3)")

    # respiro: nao comprimir demais jantar/circulacao (10)
    free_ratio = round(free.area / usable.area, 2)
    soft["respiro"] = round(10 * max(0.0, 1 - abs(free_ratio - RESPIRO_IDEAL) / 0.45), 1)
    if free_ratio < 0.45:
        pen.append(f"comprime o comodo (area livre {free_ratio} < 0.45)")

    # proporcao moveis/sala (10)
    fill = round(sum(it["box"].area for it in items) / usable.area, 2)
    flo, fhi = FILL_IDEAL
    if flo <= fill <= fhi:
        soft["proporcao"] = 10.0
    else:
        dev = min(abs(fill - flo), abs(fill - fhi))
        soft["proporcao"] = round(max(0.0, 10 - dev * 50), 1)
        pen.append(f"proporcao moveis/sala {fill} fora de {flo}-{fhi}")

    soft_score = round(sum(soft.values()), 1)
    return {
        "valid": valid,
        "hard_gates": hard,
        "soft": soft,
        "soft_score": soft_score,
        "total_score": soft_score if valid else 0.0,
        "penalties": pen,
        "reasons": reasons,
        "metrics": {"sofa_tv_dist_m": dist, "sofa_door_min_m": md, "lateral_offset_m": off_m,
                    "tv_depth_m": depth_m, "tv_wall_type": tvtype,
                    "free_ratio": free_ratio, "fill_ratio": fill},
        "violations": [k for k, v in hard.items() if not v],
    }


def run(con, room_id):
    sm = build_spatial_model(con, room_id)
    tv = _tv_setup(sm)
    out = {"stage": "BC_layout_candidates", "room_id": room_id,
           "tv_wall": sm["tv_wall_candidate"], "candidates": []}
    if tv is None:
        out["result"] = "NO_VALID_LAYOUT"
        out["reason"] = "sem parede-TV candidata (Etapa A)"
        return sm, out
    for ti, (name, fn) in enumerate(TEMPLATES):
        # busca leve: desliza o conjunto ao longo da parede-TV ate a melhor
        # posicao valida (designer ajusta pra fugir de porta/circulacao)
        best = None
        for off in (0.0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5, 2.0, -2.0):
            tv2 = dict(tv, along_c=tv["along_c"] + M(off))
            items = fn(tv2)
            res = score(items, sm, tv2)
            key = (res["valid"], res["total_score"], -abs(off))
            if best is None or key > best[0]:
                best = (key, off, items, res)
        _, off, items, res = best
        out["candidates"].append({
            "template": name, "template_order": ti, "along_offset_m": round(off, 2), **res,
            "furniture": [{"kind": it["kind"],
                           "bbox_m": [round(it["box"].bounds[i] * PT_TO_M, 2) for i in range(4)],
                           "facing": it.get("facing")} for it in items],
            "_items": items,
        })

    valid = [c for c in out["candidates"] if c["valid"]]
    if not valid:
        out["result"] = "NO_VALID_LAYOUT"
        out["reason"] = "nenhum dos 3 templates passou nos gates duros"
        out["ranking"] = [{"template": c["template"], "total_score": 0.0,
                           "valid": False, "blocked_by": c["violations"]}
                          for c in out["candidates"]]
        return sm, out

    # ranking DETERMINISTICO: total_score desc; tie-break -> menor offset lateral
    # (mais central), depois ordem do template (estavel).
    def rk(c):
        return (-c["total_score"], abs(c["along_offset_m"]), c["template_order"])
    order = sorted(out["candidates"], key=rk)
    out["result"] = "OK"
    out["chosen_candidate"] = order[0]["template"]
    out["ranking"] = [{"rank": i + 1, "template": c["template"],
                       "total_score": c["total_score"], "valid": c["valid"],
                       "soft_breakdown": c["soft"], "penalties": c["penalties"],
                       "tie_break": {"offset_m": abs(c["along_offset_m"]),
                                     "template_order": c["template_order"]}}
                      for i, c in enumerate(order)]
    tops = [c for c in order if c["total_score"] == order[0]["total_score"]]
    if len(tops) > 1:
        out["tie_note"] = (f"{len(tops)} candidatos empataram em {order[0]['total_score']} pts; "
                           f"desempate deterministico (menor offset lateral -> ordem do template) "
                           f"-> {order[0]['template']}")
    return sm, out


def plot(sm, out, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    g = sm["_geom"]
    cell, usable, circ = g["cell"], g["usable"], g["circ"]
    COL = {"sofa_3": "#1565c0", "sofa_2": "#1565c0", "rack_tv": "#6a1b9a",
           "mesa_centro": "#ef6c00", "poltrona": "#00838f"}
    cands = out["candidates"]
    chosen = out.get("chosen_candidate")
    rank_of = {r["template"]: r.get("rank", "?") for r in out.get("ranking", [])}
    fig, axes = plt.subplots(1, len(cands), figsize=(6 * len(cands), 8.5))
    if len(cands) == 1:
        axes = [axes]
    for ax, c in zip(axes, cands):
        ax.fill(*cell.exterior.xy, color="0.88", zorder=1)
        if usable.geom_type == "Polygon":
            ax.fill(*usable.exterior.xy, color="#c8f7c5", alpha=0.6, zorder=2)
        for r in circ:
            if r.geom_type == "Polygon":
                ax.fill(*r.exterior.xy, color="#ff8a80", alpha=0.55, hatch="//", zorder=3)
        for it in c["_items"]:
            b = it["box"]
            ax.fill(*b.exterior.xy, color=COL.get(it["kind"], "0.4"), alpha=0.85, zorder=5)
            ax.annotate(it["kind"].replace("_", " "), (b.centroid.x, b.centroid.y),
                        color="white", fontsize=8, ha="center", va="center", zorder=6)
        win = c["template"] == chosen
        tag = "OK" if c["valid"] else "INVALIDO"
        title = f"#{rank_of.get(c['template'], '?')}{'  WINNER' if win else ''}  {c['template']}\n" \
                f"total {c['total_score']} [{tag}]"
        if c["valid"] and c["penalties"]:
            title += "\n-: " + "; ".join(p.split("(")[0].strip() for p in c["penalties"][:2])[:62]
        elif not c["valid"]:
            title += "\nblocked: " + "; ".join(c["violations"])[:58]
        ax.set_title(title, fontsize=9,
                     fontweight="bold" if win else "normal",
                     color="#0d47a1" if win else "black")
        if win:
            for sp in ax.spines.values():
                sp.set_edgecolor("#0d47a1")
                sp.set_linewidth(3.5)
        ax.set_aspect("equal")
        ax.invert_yaxis()
    res = out["result"]
    sub = f"Etapa B+C — layout candidates {out['room_id']} | {res}"
    if res == "OK":
        sub += f" | WINNER: {chosen} ({max(c['total_score'] for c in cands)} pts)"
        if out.get("tie_note"):
            sub += "  [empate resolvido por tie-break deterministico]"
    fig.suptitle(sub, fontsize=12)
    plt.tight_layout()
    plt.savefig(out_png, dpi=85)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus", default=r"fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
    ap.add_argument("--room", default="r002")
    ap.add_argument("--out-dir", default="artifacts/review/planta_74/spatial_model")
    args = ap.parse_args()
    con = json.loads(Path(args.consensus).read_text("utf-8"))
    sm, out = run(con, args.room)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if out["candidates"]:
        plot(sm, out, out_dir / f"{args.room}_layout_candidates.png")
    for c in out["candidates"]:
        c.pop("_items", None)
    (out_dir / f"{args.room}_layout_candidates.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"SALA {args.room} | TV candidate: {out['tv_wall']['confidence']} "
          f"({out['tv_wall'].get('best_candidate')})")
    for c in out["candidates"]:
        m = c["metrics"]
        print(f"  {c['template']:24} total={c['total_score']:5} valid={c['valid']} "
              f"soft={c['soft']}")
        print(f"      metrics: sofa-tv={m['sofa_tv_dist_m']}m porta={m['sofa_door_min_m']}m "
              f"offset={m['lateral_offset_m']}m fill={m['fill_ratio']} livre={m['free_ratio']}")
        for v in c["violations"]:
            print(f"      x HARD: {v}")
        for p in c["penalties"]:
            print(f"      - {p}")
    print(f"=> RESULTADO: {out['result']}")
    if out["result"] == "OK":
        print(f"   RANKING: " + " > ".join(f"{r['template']}={r['total_score']}" for r in out["ranking"]))
        print(f"   CHOSEN: {out['chosen_candidate']}")
        if out.get("tie_note"):
            print(f"   TIE: {out['tie_note']}")
    else:
        print(f"   ({out.get('reason')})")
    print(f"-> {out_dir}/")


if __name__ == "__main__":
    main()
