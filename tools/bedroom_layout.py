"""bedroom_layout.py — bedroom layout brain (Etapa B+C pra QUARTOS).

Espelha tools/layout_candidates.py (sala), mas pra DORMITORIO: posiciona
PLACEHOLDERS (cama + criados-mudos + guarda-roupa; bounding boxes, NAO assets
3D) e scoreia por gates DUROS (dentro do comodo; cabeceira encostada na parede;
nao bloquear porta/giro; passagem >= 0.60 m) e SUAVES (folga lateral/pe da cama,
cama centralizada, 2 criados, guarda-roupa com frente livre, evitar cabeceira
sob janela). Pecas que nao cabem (criado/guarda-roupa) sao OMITIDAS com penalty
(degrada gracioso, spec GPT), nao forcam layout invalido. Se nem a cama passa
-> NO_VALID_LAYOUT.

Reusa build_spatial_model (Etapa A) pra celula/circulacao/paredes (generico).
So mobilia comodos BEDROOM (tools/room_type). Dimensoes de movel + regras
validadas com ChatGPT (consult "Prioridade Quartos e Layout", 2026-06-05;
registro local em .ai_bridge/responses/). Felipe 2026-06-05. NAO usa 3DW/SKP.

Uso: python -m tools.bedroom_layout --room r003   (default planta_74)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from shapely.geometry import Point, box
from shapely.ops import unary_union

from tools.spatial_model import (PT_TO_M, _wall_mid, build_spatial_model,
                                 wall_footprint)


def M(m):           # metros -> pdf-points
    return m / PT_TO_M


# --- dimensoes de movel (m) validadas com ChatGPT (Consult 2) ---
# cama: (largura ao-longo da parede, comprimento perp = entra no comodo, altura)
BED_SIZES = {
    "single": (0.88, 1.88, 0.55),
    "double": (1.38, 1.88, 0.55),
    "queen":  (1.58, 1.98, 0.55),
    "king":   (1.93, 2.03, 0.55),
}
WARDROBE_DEPTH = 0.60
WARDROBE_HEIGHT = 2.20
WARDROBE_W_BY_SIZE = {"small": 1.20, "medium": 1.80, "large": 2.40}
NIGHTSTAND = (0.50, 0.40)   # largura, profundidade

# clearances (m) — Consult 1
SIDE_MIN, SIDE_TGT = 0.60, 0.75       # folga lateral da cama
FOOT_MIN, FOOT_TGT = 0.60, 0.90       # folga no pe da cama
WARDROBE_FRONT_MIN = 0.75             # folga util na frente do guarda-roupa
PASSAGE_M = 0.60                      # corredor livre (quarto; sala usa 0.80)

MARGIN_M = 0.03         # encosta na parede sem cravar
TOL_CIRC_M2 = 0.02      # quase-zero: movel solido NAO pode bloquear circulacao
TOL_WALL_M2 = 0.06      # toque leve na parede e OK
COMODO_FOLGA_M = 0.06   # folga p/ "dentro do comodo"
KING_MIN_ROOM_DIM_M = 3.60


def _room_size(area_m2):
    return "small" if area_m2 < 12 else ("medium" if area_m2 <= 20 else "large")


def _bed_key(area_m2, min_dim_m):
    """Consult 2: cama por area. king so se o comodo for largo o suficiente."""
    if area_m2 < 10:
        return "single"
    if area_m2 < 14:
        return "double"
    if area_m2 >= 22 and min_dim_m >= KING_MIN_ROOM_DIM_M:
        return "king"
    return "queen"


def _fbox(orient, face, sgn, along_c, perp_d, w_along, w_perp):
    """Box axis-aligned encostado numa parede (h/v). face = coord da face interna;
    sgn = sentido pra dentro do comodo; perp_d = recuo da face; along_c = centro
    ao longo da parede; w_along/w_perp = dimensoes (ao-longo / perpendicular)."""
    p0, p1 = face + sgn * perp_d, face + sgn * (perp_d + w_perp)
    pa, pb = min(p0, p1), max(p0, p1)
    a0, a1 = along_c - w_along / 2, along_c + w_along / 2
    return box(pa, a0, pb, a1) if orient == "v" else box(a0, pa, a1, pb)


def _wall_setup(sm, wall_id):
    """Geometria pra posicionar movel encostado na parede wall_id."""
    g = sm["_geom"]
    walls, cell = g["walls"], g["cell"]
    if wall_id not in walls:
        return None
    w = walls[wall_id]
    wt = float(g["con"]["wall_thickness_pts"])
    cx, cy = _wall_mid(w)
    d = wt / 2 + 2
    if w["orientation"] == "v":
        sgn = 1 if cell.distance(Point(cx + d, cy)) < cell.distance(Point(cx - d, cy)) else -1
        face, along_c = cx + sgn * wt / 2, cy
        along_lo, along_hi = min(w["start"][1], w["end"][1]), max(w["start"][1], w["end"][1])
    else:
        sgn = 1 if cell.distance(Point(cx, cy + d)) < cell.distance(Point(cx, cy - d)) else -1
        face, along_c = cy + sgn * wt / 2, cx
        along_lo, along_hi = min(w["start"][0], w["end"][0]), max(w["start"][0], w["end"][0])
    return {"id": wall_id, "orient": w["orientation"], "sgn": sgn, "face": face,
            "along_c": along_c, "along_lo": along_lo, "along_hi": along_hi,
            "depth": _perp_depth(w, g["usable"]), "_w": w}


def _perp_depth(w, usable):
    """Profundidade livre perpendicular a parede (quanto cabe entrando no comodo)."""
    from shapely.geometry import LineString
    cx, cy = _wall_mid(w)
    L = 100000.0
    rays = ([LineString([(cx, cy), (cx, cy + L)]), LineString([(cx, cy), (cx, cy - L)])]
            if w["orientation"] == "h"
            else [LineString([(cx, cy), (cx + L, cy)]), LineString([(cx, cy), (cx - L, cy)])])
    best = 0.0
    for ray in rays:
        inter = ray.intersection(usable)
        if not inter.is_empty:
            best = max(best, inter.length)
    return best


def _openings_by_wall(sm):
    by = {}
    for o in sm["openings"]:
        by.setdefault(o["wall_id"], []).append(o["kind"])
    return by


def _headboard_candidates(sm, bed_along_pts, k=3):
    """Ranqueia paredes pra cabeceira: limpa > so-janela > com-porta; mais longa
    e melhor (cabe cama + criados). So paredes que comportam a largura da cama."""
    by = _openings_by_wall(sm)
    door_kinds = {"interior_door", "interior_passage", "glazed_balcony"}
    scored = []
    for wr in sm["walls"]:
        if wr["length_m"] < bed_along_pts * PT_TO_M + 0.05:
            continue   # parede curta demais pra cabeceira da cama
        kinds = by.get(wr["id"], [])
        has_door = any(kk in door_kinds for kk in kinds)
        has_window = "window" in kinds
        s, reasons = 0.0, []
        if not kinds:
            s += 40; reasons.append("parede limpa (+40)")
        elif has_door:
            s -= 30; reasons.append("parede com porta/passagem (-30)")
        elif has_window:
            s += 12; reasons.append("parede so com janela (+12)")
        s += wr["length_m"] * 5
        reasons.append(f"comprimento {wr['length_m']}m (+{wr['length_m'] * 5:.0f})")
        if wr["type"] == "border":
            s += 5; reasons.append("parede de borda (+5)")
        scored.append({"wall_id": wr["id"], "score": round(s, 1), "clean": not kinds,
                       "has_window": has_window, "has_door": has_door,
                       "length_m": wr["length_m"], "reasons": reasons})
    scored.sort(key=lambda x: -x["score"])
    return scored[:k], scored


def _window_zones(sm):
    """Uniao das pegadas (no plano) das janelas do comodo — pra guarda-roupa NAO
    cobrir janela (hard pro armario; a cama sob janela e soft, tratada a parte)."""
    g = sm["_geom"]
    walls = g["walls"]
    rw = set(g["room_walls"])
    wt = float(g["con"]["wall_thickness_pts"])
    zs = []
    for o in g["con"]["openings"]:
        if o["wall_id"] not in rw or (o.get("kind_v5") or o.get("kind")) != "window":
            continue
        w = walls[o["wall_id"]]
        cx, cy = o["center"]
        hw = (o["opening_width_pts"] + wt) / 2.0
        if w["orientation"] == "h":
            zs.append(box(cx - hw, cy - wt, cx + hw, cy + wt))
        else:
            zs.append(box(cx - wt, cy - hw, cx + wt, cy + hw))
    return unary_union(zs) if zs else None


def _inside(itbox, comodo):
    return comodo.contains(itbox)


def _hits(itbox, geom, tol_m2):
    return geom is not None and itbox.intersection(geom).area > tol_m2 / PT_TO_M ** 2


def _wardrobe_candidates(sm, headboard_id, ward_w_pts):
    """Paredes pra guarda-roupa (!= cabeceira): limpa e longa; evita parede com
    porta; opcional bonus se for oposta a cabeceira. Devolve setups ordenados."""
    by = _openings_by_wall(sm)
    door_kinds = {"interior_door", "interior_passage", "glazed_balcony"}
    hb = _wall_setup(sm, headboard_id)
    out = []
    for wr in sm["walls"]:
        if wr["id"] == headboard_id or wr["length_m"] < ward_w_pts * PT_TO_M + 0.05:
            continue
        kinds = by.get(wr["id"], [])
        if any(kk in door_kinds for kk in kinds):
            continue   # nao poe guarda-roupa em parede de porta (giro/passagem)
        s = wr["length_m"] * 5 + (30 if not kinds else 0)
        ws = _wall_setup(sm, wr["id"])
        if ws is None:
            continue
        # bonus se oposta (mesma orientacao da cabeceira)
        if hb and ws["orient"] == hb["orient"]:
            s += 10
        out.append((s, ws, "window" in kinds))
    out.sort(key=lambda x: -x[0])
    return out


def build_arrangement(sm, hb, bed_key, bed_off, win_zone, comodo, circ_u):
    """Monta cama (cabeceira em hb, deslizada por bed_off) + criados flanqueando
    (condicional) + guarda-roupa (condicional, melhor parede alternativa)."""
    o, face, sgn, ac = hb["orient"], hb["face"], hb["sgn"], hb["along_c"] + M(bed_off)
    bw, bl, _ = BED_SIZES[bed_key]
    items = [{"kind": "bed", "box": _fbox(o, face, sgn, ac, M(MARGIN_M), M(bw), M(bl)),
              "size": bed_key}]
    # criados-mudos flanqueando, encostados na MESMA parede (condicional)
    nw, nd = NIGHTSTAND
    for side in (1, -1):
        ns_ac = ac + side * (M(bw) / 2 + M(nw) / 2)
        ns = _fbox(o, face, sgn, ns_ac, M(MARGIN_M), M(nw), M(nd))
        if _inside(ns, comodo) and not _hits(ns, circ_u, TOL_CIRC_M2) \
                and not ns.intersection(items[0]["box"]).area > 0:
            items.append({"kind": "nightstand", "box": ns, "side": side})
    # guarda-roupa (condicional): melhor parede alternativa, frente livre, sem janela
    size = _room_size(comodo.area * PT_TO_M ** 2)
    ward_w = WARDROBE_W_BY_SIZE[size]
    placed = [it["box"] for it in items]
    for _s, ws, _has_win in _wardrobe_candidates(sm, hb["id"], M(ward_w)):
        for woff in (0.0, 0.5, -0.5, 1.0, -1.0):
            wac = ws["along_c"] + M(woff)
            wbox = _fbox(ws["orient"], ws["face"], ws["sgn"], wac, M(MARGIN_M),
                         M(ward_w), M(WARDROBE_DEPTH))
            front = _fbox(ws["orient"], ws["face"], ws["sgn"], wac,
                          M(MARGIN_M + WARDROBE_DEPTH), M(ward_w), M(WARDROBE_FRONT_MIN))
            if not _inside(wbox, comodo):
                continue
            if _hits(wbox, circ_u, TOL_CIRC_M2) or _hits(wbox, win_zone, TOL_CIRC_M2):
                continue
            if any(wbox.intersection(p).area > 0 for p in placed):
                continue
            # frente do guarda-roupa precisa estar livre (dentro do comodo, sem movel)
            if not comodo.contains(front.buffer(-M(0.02))):
                continue
            if any(front.intersection(p).area > M(0.02) ** 2 for p in placed):
                continue
            items.append({"kind": "wardrobe", "box": wbox, "wall": ws["id"]})
            break
        if any(it["kind"] == "wardrobe" for it in items):
            break
    return items


def score(items, sm, hb):
    """HARD gates (binarios) separados de SOFT (continuo). total = soft se valido."""
    g = sm["_geom"]
    cell, usable, circ = g["cell"], g["usable"], g["circ"]
    room_walls = g["room_walls"]
    walls = g["walls"]
    wfoot = unary_union([wall_footprint(walls[wid], extend_endpoints=True) for wid in room_walls])
    circ_u = unary_union(circ) if circ else None
    comodo = cell.buffer(M(COMODO_FOLGA_M))
    win_zone = _window_zones(sm)

    bed = next(it for it in items if it["kind"] == "bed")
    nights = [it for it in items if it["kind"] == "nightstand"]
    ward = next((it for it in items if it["kind"] == "wardrobe"), None)
    solid = items

    # ---------- HARD GATES ----------
    out_room = any(not _inside(it["box"], comodo) for it in solid)
    hits_circ = any(_hits(it["box"], circ_u, TOL_CIRC_M2) for it in solid)
    hits_wall = any(it["box"].intersection(wfoot).area > TOL_WALL_M2 / PT_TO_M ** 2 for it in solid)
    hb_foot = wall_footprint(walls[hb["id"]], extend_endpoints=True)
    headboard_touches = bed["box"].distance(hb_foot) < M(0.15)
    free = usable
    for it in solid:
        free = free.difference(it["box"])
    passage_ok = not free.buffer(-M(PASSAGE_M) / 2).is_empty

    hard = {"dentro_do_comodo": not out_room,
            "nao_bloqueia_circulacao": not hits_circ,
            "nao_bloqueia_porta": not hits_circ,    # circ ja inclui giro de porta
            "cabeceira_na_parede": headboard_touches,
            "nao_invade_parede": not hits_wall,
            "passagem_min_060": passage_ok}
    valid = all(hard.values())

    # ---------- SOFT (continuo) ----------
    soft, pen, reasons = {}, [], []

    # folga lateral da cama (cada lado livre ate parede/movel) (20)
    side_clear = _bed_side_clearance(bed, hb, items, usable)
    if side_clear is None:
        soft["folga_lateral"] = 0.0
    elif side_clear >= SIDE_TGT:
        soft["folga_lateral"] = 20.0; reasons.append(f"folga lateral {side_clear}m (+20)")
    else:
        soft["folga_lateral"] = round(max(0.0, 20 * side_clear / SIDE_TGT), 1)
        if side_clear < SIDE_MIN:
            pen.append(f"folga lateral {side_clear}m < {SIDE_MIN}m")

    # folga no pe da cama (15)
    foot = _bed_foot_clearance(bed, hb, usable)
    if foot is None:
        soft["folga_pe"] = 0.0
    elif foot >= FOOT_TGT:
        soft["folga_pe"] = 15.0; reasons.append(f"folga pe {foot}m (+15)")
    else:
        soft["folga_pe"] = round(max(0.0, 15 * foot / FOOT_TGT), 1)
        if foot < FOOT_MIN:
            pen.append(f"folga pe {foot}m < {FOOT_MIN}m")

    # cama centralizada na parede da cabeceira (15)
    off_m = abs(bed["box"].centroid.x - _wall_center_along(hb)) * PT_TO_M if hb["orient"] == "h" \
        else abs(bed["box"].centroid.y - _wall_center_along(hb)) * PT_TO_M
    soft["centralizada"] = round(max(0.0, 15 - off_m * 12), 1)
    if off_m > 0.3:
        pen.append(f"cama descentralizada {round(off_m,2)}m")

    # criados-mudos (20: 10 cada) (15)
    soft["criados"] = round(min(2, len(nights)) * 7.5, 1)
    if len(nights) < 2:
        pen.append(f"so {len(nights)} criado-mudo (ideal 2)")
    else:
        reasons.append("2 criados-mudos (+15)")

    # guarda-roupa presente com frente livre (20)
    if ward is not None:
        soft["guarda_roupa"] = 20.0; reasons.append("guarda-roupa com frente livre (+20)")
    else:
        soft["guarda_roupa"] = 0.0; pen.append("sem guarda-roupa que coube com folga")

    # evitar cabeceira sob janela (15) — soft, nao hard (Consult 1)
    if hb.get("has_window"):
        soft["cabeceira_sem_janela"] = 0.0
        pen.append("cabeceira sob/na parede da janela (-15)")
    else:
        soft["cabeceira_sem_janela"] = 15.0

    soft_score = round(sum(soft.values()), 1)
    return {"valid": valid, "hard_gates": hard, "soft": soft, "soft_score": soft_score,
            "total_score": soft_score if valid else 0.0,
            "penalties": pen, "reasons": reasons,
            "violations": [k for k, v in hard.items() if not v],
            "metrics": {"bed_size": bed["size"], "side_clear_m": side_clear,
                        "foot_clear_m": foot, "center_off_m": round(off_m, 2),
                        "n_nightstands": len(nights), "has_wardrobe": ward is not None,
                        "headboard_has_window": bool(hb.get("has_window"))}}


def _wall_center_along(hb):
    return (hb["along_lo"] + hb["along_hi"]) / 2.0


def _bed_side_clearance(bed, hb, items, usable):
    """Menor folga livre nas duas LATERAIS da cama (ao longo da parede da
    cabeceira) ate parede/movel. Aproxima medindo o vao livre lateral."""
    b = bed["box"].bounds  # (minx,miny,maxx,maxy)
    others = [it["box"] for it in items if it is not bed and it["kind"] != "nightstand"]
    # lateral = eixo ao-longo da parede
    if hb["orient"] == "v":   # parede vertical -> along = y -> laterais em y
        lo_room, hi_room = usable.bounds[1], usable.bounds[3]
        lo_b, hi_b = b[1], b[3]
    else:
        lo_room, hi_room = usable.bounds[0], usable.bounds[2]
        lo_b, hi_b = b[0], b[2]
    left = (lo_b - lo_room) * PT_TO_M
    right = (hi_room - hi_b) * PT_TO_M
    return round(max(0.0, min(left, right)), 2)


def _bed_foot_clearance(bed, hb, usable):
    """Folga do PE da cama (perpendicular a parede da cabeceira) ate a parede
    oposta (borda do usable)."""
    b = bed["box"].bounds
    if hb["orient"] == "v":   # cama entra em x
        if hb["sgn"] > 0:
            foot = (usable.bounds[2] - b[2]) * PT_TO_M
        else:
            foot = (b[0] - usable.bounds[0]) * PT_TO_M
    else:                      # cama entra em y
        if hb["sgn"] > 0:
            foot = (usable.bounds[3] - b[3]) * PT_TO_M
        else:
            foot = (b[1] - usable.bounds[1]) * PT_TO_M
    return round(max(0.0, foot), 2)


def run(con, room_id):
    sm = build_spatial_model(con, room_id)
    g = sm["_geom"]
    comodo = g["cell"].buffer(M(COMODO_FOLGA_M))
    circ_u = unary_union(g["circ"]) if g["circ"] else None
    win_zone = _window_zones(sm)
    area = sm["area_m2"]
    bx = g["cell"].bounds
    min_dim_m = min(bx[2] - bx[0], bx[3] - bx[1]) * PT_TO_M
    bed_key = _bed_key(area, min_dim_m)
    bw = BED_SIZES[bed_key][0]

    out = {"stage": "bedroom_layout", "room_id": room_id,
           "room_name": sm.get("room_name"), "area_m2": area,
           "bed_size": bed_key, "candidates": []}

    top_hb, all_hb = _headboard_candidates(sm, M(bw), k=3)
    out["headboard_ranking"] = [{"wall_id": h["wall_id"], "score": h["score"],
                                 "clean": h["clean"], "has_window": h["has_window"],
                                 "has_door": h["has_door"]}
                                for h in all_hb]
    if not top_hb:
        out["result"] = "NO_VALID_LAYOUT"
        out["reason"] = f"nenhuma parede comporta a cabeceira (cama {bed_key} {bw}m)"
        return sm, out

    for rank, h in enumerate(top_hb):
        hb = _wall_setup(sm, h["wall_id"])
        if hb is None:
            continue
        hb["has_window"] = h["has_window"]
        best = None
        for off in (0.0, 0.4, -0.4, 0.8, -0.8, 1.2, -1.2):
            items = build_arrangement(sm, hb, bed_key, off, win_zone, comodo, circ_u)
            res = score(items, sm, hb)
            key = (res["valid"], res["total_score"], -abs(off))
            if best is None or key > best[0]:
                best = (key, off, items, res)
        _, off, items, res = best
        out["candidates"].append({
            "headboard_wall": h["wall_id"], "headboard_rank": rank,
            "along_offset_m": round(off, 2), **res,
            "furniture": [{"kind": it["kind"],
                           "bbox_m": [round(it["box"].bounds[i] * PT_TO_M, 2) for i in range(4)]}
                          for it in items],
            "_items": items})

    valid = [c for c in out["candidates"] if c["valid"]]
    if not valid:
        out["result"] = "NO_VALID_LAYOUT"
        out["reason"] = "nenhum candidato passou os hard gates"
        out["ranking"] = [{"headboard_wall": c["headboard_wall"], "total_score": 0.0,
                           "valid": False, "blocked_by": c["violations"]}
                          for c in out["candidates"]]
        return sm, out

    def rk(c):
        return (-c["total_score"], c["headboard_rank"], abs(c["along_offset_m"]))
    order = sorted(out["candidates"], key=rk)
    out["result"] = "OK"
    out["chosen"] = {"headboard_wall": order[0]["headboard_wall"],
                     "total_score": order[0]["total_score"]}
    out["ranking"] = [{"rank": i + 1, "headboard_wall": c["headboard_wall"],
                       "total_score": c["total_score"], "valid": c["valid"],
                       "soft": c["soft"], "penalties": c["penalties"],
                       "metrics": c["metrics"]}
                      for i, c in enumerate(order)]
    return sm, out


def plot(sm, out, out_png):
    """Diagrama (plan) dos candidatos de quarto, espelhando layout_candidates.plot.
    Vencedor com borda azul. Marca janela (ciano) e porta (marrom) pra revisao
    da relacao cabeceira<->janela. ARTEFATO DE VISUAL_REVIEW (humano julga)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    g = sm["_geom"]
    cell, usable, circ = g["cell"], g["usable"], g["circ"]
    COL = {"bed": "#1565c0", "nightstand": "#00838f", "wardrobe": "#6a1b9a"}
    cands = out["candidates"][:3]
    if not cands:
        return
    chosen_wall = out.get("chosen", {}).get("headboard_wall")
    rank_of = {r["headboard_wall"]: r.get("rank", "?") for r in out.get("ranking", [])}
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
        for o in g["con"]["openings"]:                 # janela (ciano) / porta (marrom)
            if o["wall_id"] not in g["room_walls"]:
                continue
            kind = o.get("kind_v5") or o.get("kind")
            cx, cy = o["center"]
            ax.plot(cx, cy, marker="s", markersize=9, zorder=7,
                    color="#00b0ff" if kind == "window" else "#8d6e63")
        for it in c["_items"]:
            b = it["box"]
            ax.fill(*b.exterior.xy, color=COL.get(it["kind"], "0.4"), alpha=0.85, zorder=5)
            ax.annotate(it["kind"], (b.centroid.x, b.centroid.y), color="white",
                        fontsize=7, ha="center", va="center", zorder=6)
        win = c["headboard_wall"] == chosen_wall
        tag = "OK" if c["valid"] else "INVALIDO"
        title = (f"#{rank_of.get(c['headboard_wall'], '?')}{'  WINNER' if win else ''}  "
                 f"cabeceira {c['headboard_wall']}\ntotal {c['total_score']} [{tag}]")
        if c["valid"] and c["penalties"]:
            title += "\n-: " + "; ".join(c["penalties"][:2])[:60]
        elif not c["valid"]:
            title += "\nblocked: " + "; ".join(c["violations"])[:58]
        ax.set_title(title, fontsize=9, fontweight="bold" if win else "normal",
                     color="#0d47a1" if win else "black")
        if win:
            for sp in ax.spines.values():
                sp.set_edgecolor("#0d47a1")
                sp.set_linewidth(3.5)
        ax.set_aspect("equal")
        ax.invert_yaxis()
    sub = (f"Bedroom layout {out['room_id']} ('{out.get('room_name')}') | "
           f"{out['result']} | cama {out['bed_size']}")
    if out["result"] == "OK":
        sub += f" | WINNER cabeceira {chosen_wall}"
    fig.suptitle(sub, fontsize=12)
    fig.text(0.5, 0.01, "azul=cama  teal=criado-mudo  roxo=guarda-roupa  "
             "ciano=janela  marrom=porta  vermelho=circulacao", ha="center", fontsize=8)
    plt.tight_layout(rect=[0, 0.02, 1, 1])
    plt.savefig(out_png, dpi=85)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus",
                    default="fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
    ap.add_argument("--room", default="r003")
    ap.add_argument("--out-dir", default=None, help="salva PNG + JSON do diagrama")
    args = ap.parse_args()
    con = json.loads(Path(args.consensus).read_text("utf-8"))
    sm, out = run(con, args.room)
    print(f"QUARTO {args.room} ('{out.get('room_name')}') | area {out['area_m2']}m2 "
          f"| cama {out['bed_size']} | {out['result']}")
    print(f"  cabeceira ranking: " + ", ".join(
        f"{h['wall_id']}={h['score']}{'(limpa)' if h['clean'] else ''}"
        for h in out.get("headboard_ranking", [])))
    for c in out["candidates"]:
        m = c["metrics"]
        print(f"  hb={c['headboard_wall']:5} off={c['along_offset_m']:+.1f} "
              f"total={c['total_score']:5} valid={c['valid']} "
              f"lateral={m['side_clear_m']}m pe={m['foot_clear_m']}m "
              f"criados={m['n_nightstands']} armario={m['has_wardrobe']}")
        for v in c["violations"]:
            print(f"      x HARD: {v}")
        for p in c["penalties"]:
            print(f"      - {p}")
    if out["result"] == "OK":
        print(f"  => CHOSEN: cabeceira {out['chosen']['headboard_wall']} "
              f"({out['chosen']['total_score']} pts)")
    else:
        print(f"  => {out.get('reason')}")


if __name__ == "__main__":
    main()
