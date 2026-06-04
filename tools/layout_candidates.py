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


def score(items, sm):
    g = sm["_geom"]
    walls, cell, usable, circ, room_walls = (g["walls"], g["cell"], g["usable"],
                                             g["circ"], g["room_walls"])
    wfoot = unary_union([wall_footprint(walls[wid], extend_endpoints=True) for wid in room_walls])
    circ_u = unary_union(circ) if circ else None
    tol_circ = TOL_CIRC_M2 / PT_TO_M ** 2
    tol_wall = TOL_WALL_M2 / PT_TO_M ** 2
    comodo = cell.buffer(M(COMODO_FOLGA_M))    # limite fisico do comodo (+folga)

    viol = []
    for it in items:
        if circ_u is not None and it["box"].intersection(circ_u).area > tol_circ:
            viol.append(f"{it['kind']} bloqueia circulacao/abertura")
        if it["box"].intersection(wfoot).area > tol_wall:
            viol.append(f"{it['kind']} atravessa parede")
        if not comodo.contains(it["box"]):
            viol.append(f"{it['kind']} fora do comodo")

    free = usable
    for it in items:
        free = free.difference(it["box"])
    passage_ok = not free.buffer(-M(PASSAGE_M) / 2).is_empty

    sofa = next((it for it in items if it["kind"].startswith("sofa")), None)
    facing_ok = bool(sofa and sofa.get("facing") == "tv")
    dist_m = sofa.get("dist_m") if sofa else None
    dist_ok = dist_m is not None and SOFA_TV_MIN <= dist_m <= SOFA_TV_MAX
    prop_ok = not viol                                    # cabe sem invadir nada

    valid = (not viol) and passage_ok
    sc = 0
    if valid:
        sc = 20 + (25 if passage_ok else 0) + (20 if facing_ok else 0) + \
             (20 if dist_ok else 0) + (15 if prop_ok else 0)
    return {"valid": valid, "score": min(sc, 100),
            "gates": {"sem_colisao": not viol, "passagem_080": passage_ok,
                      "sofa_para_tv": facing_ok, "dist_sofa_tv_ok": dist_ok,
                      "proporcao_ok": prop_ok},
            "sofa_tv_dist_m": dist_m, "violations": viol}


def run(con, room_id):
    sm = build_spatial_model(con, room_id)
    tv = _tv_setup(sm)
    out = {"stage": "BC_layout_candidates", "room_id": room_id,
           "tv_wall": sm["tv_wall_candidate"], "candidates": []}
    if tv is None:
        out["result"] = "NO_VALID_LAYOUT"
        out["reason"] = "sem parede-TV candidata (Etapa A)"
        return sm, out
    for name, fn in TEMPLATES:
        # busca leve: desliza o conjunto ao longo da parede-TV ate achar a
        # melhor posicao valida (designer ajusta pra fugir de porta/circulacao)
        best = None
        for off in (0.0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5, 2.0, -2.0):
            tv2 = dict(tv, along_c=tv["along_c"] + M(off))
            items = fn(tv2)
            res = score(items, sm)
            key = (res["valid"], res["score"])
            if best is None or key > best[0]:
                best = (key, off, items, res)
        _, off, items, res = best
        out["candidates"].append({
            "template": name, "along_offset_m": off, **res,
            "furniture": [{"kind": it["kind"],
                           "bbox_m": [round(it["box"].bounds[i] * PT_TO_M, 2) for i in range(4)],
                           "facing": it.get("facing")} for it in items],
            "_items": items,
        })
    valid = [c for c in out["candidates"] if c["valid"]]
    if not valid:
        out["result"] = "NO_VALID_LAYOUT"
        out["reason"] = "nenhum dos 3 templates passou nos gates duros"
    else:
        best = max(valid, key=lambda c: c["score"])
        out["result"] = "OK"
        out["best_template"] = best["template"]
        out["ranking"] = sorted([(c["template"], c["score"], c["valid"]) for c in out["candidates"]],
                                key=lambda x: -x[1])
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
    fig, axes = plt.subplots(1, len(cands), figsize=(6 * len(cands), 8))
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
            ax.annotate(it["kind"].replace("_", " "),
                        (b.centroid.x, b.centroid.y), color="white", fontsize=8,
                        ha="center", va="center", zorder=6)
        tag = "OK" if c["valid"] else "INVALIDO"
        ax.set_title(f"{c['template']}\nscore {c['score']} [{tag}]"
                     + ("" if c["valid"] else f"\n{'; '.join(c['violations'])[:60]}"),
                     fontsize=10)
        ax.set_aspect("equal")
        ax.invert_yaxis()
    res = out["result"]
    fig.suptitle(f"Etapa B+C — layout candidates {out['room_id']} | resultado: {res}"
                 + (f" (best: {out.get('best_template')})" if res == "OK" else ""),
                 fontsize=13)
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
        print(f"  {c['template']:26} score={c['score']:3} valid={c['valid']} "
              f"sofa->tv={c['sofa_tv_dist_m']}m gates={c['gates']}")
        for v in c["violations"]:
            print(f"      x {v}")
    print(f"=> RESULTADO: {out['result']}"
          + (f" | best={out.get('best_template')}" if out["result"] == "OK" else f" ({out.get('reason')})"))
    print(f"-> {out_dir}/")


if __name__ == "__main__":
    main()
