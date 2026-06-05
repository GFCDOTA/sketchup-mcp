"""bedroom_designer.py — quarto KING "designer minimalista" (spec Felipe 2026-06-05).

UM quarto, lógica de interiores (não encher): cama king como ÂNCORA, centralizada
numa parede limpa; criados-mudos simétricos; TAPETE grande sob a cama; guarda-roupa
funcional; P1 banco aos pés + dresser; P2 poltrona/mesa só se sobrar. Hard gates +
soft score (pontos da spec) + múltiplos candidatos (top-3 paredes de cabeceira) +
JSON do layout + PNG top-down + relatório. Placeholders (caixas); SKP depois.
Geometria pura (shapely), sem SketchUp para validar. Reusa o brain de quarto.

Uso: python -m tools.bedroom_designer --room r000   (default planta_74 SUITE 01 king)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from shapely.affinity import translate
from shapely.geometry import box
from shapely.ops import unary_union

from tools.bedroom_layout import (M, _door_zones, _fbox, _headboard_candidates,
                                  _wall_setup, _window_zones, wall_footprint)
from tools.spatial_model import PT_TO_M, build_spatial_model

# --- móveis (m): (largura ao-longo da parede, profundidade perp, altura) ---
KING = (1.93, 2.03, 0.55)
NIGHTSTAND = (0.50, 0.45, 0.60)
RUG = (2.80, 3.40, 0.02)
WARDROBE_DEPTH, WARDROBE_H = 0.60, 2.20
BANCO = (1.40, 0.45, 0.45)          # ottoman aos pés
DRESSER = (1.60, 0.45, 0.80)        # cômoda baixa
POLTRONA = (0.80, 0.80, 0.80)
MESA_LAT = (0.40, 0.40, 0.45)

# clearances (m): (ideal, mínimo)
SIDE = (0.60, 0.45)                 # laterais da cama
FOOT = (0.80, 0.60)                 # pé da cama
WARD_FRONT = (0.90, 0.70)           # frente do guarda-roupa
CORRIDOR_MIN = 0.60                 # passagem livre

MARGIN_M = 0.03
TOL = 0.02
COMODO_FOLGA = 0.06

RGB = {"bed": [21, 101, 192], "nightstand": [0, 131, 143], "rug": [201, 185, 160],
       "wardrobe": [106, 27, 154], "bench": [120, 144, 156], "dresser": [141, 110, 99],
       "armchair": [0, 150, 136], "side_table": [255, 171, 64]}
HEIGHT = {"bed": 0.55, "nightstand": 0.60, "rug": 0.02, "wardrobe": 2.20,
          "bench": 0.45, "dresser": 0.80, "armchair": 0.80, "side_table": 0.45}


def _ward_width(area_m2):
    return 2.40 if area_m2 >= 16 else (1.80 if area_m2 >= 11 else 1.20)


def _clear(v):                      # m, arredonda
    return round(v, 2)


def _bbox_m(b):
    return [round(b.bounds[i] * PT_TO_M, 2) for i in range(4)]


def _wardrobe_walls(sm, exclude_id):
    """Paredes p/ guarda-roupa/dresser (!= cabeceira): limpa de porta; ranqueadas
    por comprimento + bônus se limpa de janela. Devolve setups."""
    by = {}
    for o in sm["openings"]:
        by.setdefault(o["wall_id"], []).append(o["kind"])
    door_kinds = {"interior_door", "interior_passage", "glazed_balcony"}
    out = []
    for wr in sm["walls"]:
        if wr["id"] == exclude_id or wr["length_m"] < 1.0:
            continue
        kinds = by.get(wr["id"], [])
        if any(k in door_kinds for k in kinds):
            continue
        ws = _wall_setup(sm, wr["id"])
        if ws is None:
            continue
        s = wr["length_m"] * 5 + (15 if "window" not in kinds else 0)
        out.append((s, ws, "window" in kinds))
    out.sort(key=lambda x: -x[0])
    return out


def _free_after(usable, solids):
    free = usable
    for it in solids:
        if not it.get("decorative"):
            free = free.difference(it["box"])
    return free


def build_layout(sm, hb, minimalist=True):
    """Monta um candidato com a cabeceira na parede hb (cama centralizada).
    minimalist (default, pos review GPT): P0 (cama+criados+tapete+guarda-roupa) +
    no MAXIMO o dresser. --full re-habilita banco/poltrona/mesa (vira showroom).
    Devolve (items, downgrades)."""
    g = sm["_geom"]
    cell, usable = g["cell"], g["usable"]
    comodo = cell.buffer(M(COMODO_FOLGA))
    circ = list(g["circ"] or [])
    dz = _door_zones(sm)
    if dz is not None:
        circ.append(dz)
    circ_u = unary_union(circ) if circ else None
    win_zone = _window_zones(sm)
    o, face, sgn, ac = hb["orient"], hb["face"], hb["sgn"], hb["along_c"]
    items, downgrades = [], []

    # --- P0: cama king CENTRALIZADA (desliza só se centralizada não couber) ---
    bw, bl, _ = KING
    bed = None
    for off in (0.0, 0.3, -0.3, 0.6, -0.6):
        b = _fbox(o, face, sgn, ac + M(off), M(MARGIN_M), M(bw), M(bl))
        if comodo.contains(b) and not _hit(b, circ_u) and not _hit(b, win_zone):
            bed = {"name": "cama_king", "type": "bed", "box": b, "facing": _facing(o, sgn),
                   "anchor_wall": hb["id"], "reason": "âncora; cabeceira em parede limpa; centralizada",
                   "off": off}
            ac = ac + M(off)
            break
    if bed is None:
        return None, ["cama king não coube na parede da cabeceira"]
    items.append(bed)

    # --- P0: TAPETE grande sob a cama (decorativo; sai da parede e estende no
    # pé/laterais; pode sobrepor cama/criados pois é piso) ---
    rug = _fbox(o, face, sgn, ac, M(MARGIN_M), M(RUG[0]), M(RUG[1]))
    if comodo.buffer(M(0.10)).contains(rug):
        items.append({"name": "tapete", "type": "rug", "box": rug, "decorative": True,
                      "anchor_wall": hb["id"], "reason": "sob a cama, sai nas laterais e no pé"})
    else:
        # encolhe pra caber (mantém proporção, tapete menor)
        items.append({"name": "tapete", "type": "rug",
                      "box": rug.intersection(comodo), "decorative": True,
                      "anchor_wall": hb["id"], "reason": "sob a cama (recortado ao quarto)"})

    # --- P0: criados-mudos simétricos ---
    nw, nd, _ = NIGHTSTAND
    placed_n = 0
    for side in (1, -1):
        ns_ac = ac + side * (M(bw) / 2 + M(nw) / 2)
        ns = _fbox(o, face, sgn, ns_ac, M(MARGIN_M), M(nw), M(nd))
        if comodo.contains(ns) and not _hit(ns, circ_u) and not _ov(ns, items):
            items.append({"name": f"criado_mudo_{'dir' if side > 0 else 'esq'}", "type": "nightstand",
                          "box": ns, "anchor_wall": hb["id"],
                          "reason": "flanqueando a cabeceira (simétrico)"})
            placed_n += 1
    if placed_n < 2:
        downgrades.append(f"criados-mudos: só {placed_n} coube(ram) (ideal 2)")

    # --- P0: guarda-roupa em parede alternativa (frente livre) ---
    ward_w = _ward_width(sm["area_m2"])
    ward = _place_against(sm, _wardrobe_walls(sm, hb["id"]), ward_w, WARDROBE_DEPTH,
                          items, comodo, circ_u, win_zone, front=WARD_FRONT[1], tall=True)
    if ward is not None:
        ward["name"] = "guarda_roupa"
        ward["type"] = "wardrobe"
        ward["reason"] = "parede lateral/oposta limpa, com frente livre"
        items.append(ward)
    else:
        downgrades.append("guarda-roupa não coube com frente livre")

    # --- secundario: dresser/comoda baixa numa parede livre (UNICO extra do
    # minimalista; GPT review 2026-06: nucleo + 'talvez dresser') ---
    used = {hb["id"]} | {it.get("anchor_wall") for it in items if it.get("type") == "wardrobe"}
    dresser = _place_against(sm, [c for c in _wardrobe_walls(sm, hb["id"]) if c[1]["id"] not in used],
                             DRESSER[0], DRESSER[1], items, comodo, circ_u, win_zone,
                             front=0.60, tall=False)
    if dresser is not None:
        dresser["name"] = "dresser"
        dresser["type"] = "dresser"
        dresser["reason"] = "comoda baixa em parede livre, sem competir com guarda-roupa"
        items.append(dresser)

    # --- extras (banco aos pes + poltrona/mesa): SO no modo --full. GPT review
    # 2026-06: no minimalista isso vira 'showroom'/excessivo, intencao fraca. ---
    if not minimalist:
        banco = _place_foot(o, face, sgn, ac, bl, BANCO, comodo, circ_u, items, usable)
        if banco is not None:
            items.append(banco)
        polt = _place_corner(sm, POLTRONA, comodo, circ_u, win_zone, items, near_window=True)
        if polt is not None:
            items.append(polt)
            mesa = _place_beside(polt, MESA_LAT, comodo, circ_u, items)
            if mesa is not None:
                items.append(mesa)

    return items, downgrades


def _facing(orient, sgn):
    return (sgn, 0.0) if orient == "v" else (0.0, sgn)


def _hit(b, geom):
    return geom is not None and b.intersection(geom).area > TOL / PT_TO_M ** 2


def _ov(b, items):
    tol = 0.01 / PT_TO_M ** 2          # tolera sliver de borda (encoste exato)
    return any(b.intersection(it["box"]).area > tol
               for it in items if not it.get("decorative"))


def _place_against(sm, wall_setups, w_m, d_m, items, comodo, circ_u, win_zone, front, tall):
    """Move encostado numa das paredes (com slide), frente livre >= front."""
    for _s, ws, _win in wall_setups:
        lo = ws["along_lo"] + M(w_m / 2 + 0.05)
        hi = ws["along_hi"] - M(w_m / 2 + 0.05)
        if hi <= lo:
            continue
        n = max(1, int((hi - lo) / M(0.15)))
        for i in range(n + 1):
            ac = lo + (hi - lo) * i / n
            b = _fbox(ws["orient"], ws["face"], ws["sgn"], ac, M(MARGIN_M), M(w_m), M(d_m))
            fr = _fbox(ws["orient"], ws["face"], ws["sgn"], ac, M(MARGIN_M + d_m), M(w_m), M(front))
            if not comodo.contains(b) or _hit(b, circ_u) or _ov(b, items):
                continue
            if tall and _hit(b, win_zone):
                continue
            if not comodo.contains(fr.buffer(-M(0.02))) or _ov(fr, items):
                continue
            return {"box": b, "anchor_wall": ws["id"], "facing": _facing(ws["orient"], ws["sgn"])}
    return None


def _place_foot(o, face, sgn, ac, bl, dims, comodo, circ_u, items, usable):
    """Banco aos pés: centralizado com a cama, logo após o pé; só se circulação ok."""
    bw_b, bd_b, _ = dims
    perp = M(MARGIN_M + bl + 0.05)
    b = _fbox(o, face, sgn, ac, perp, M(bw_b), M(bd_b))
    if not comodo.contains(b) or _hit(b, circ_u) or _ov(b, items):
        return None
    free = usable.difference(b)
    for it in items:
        if not it.get("decorative"):
            free = free.difference(it["box"])
    if free.buffer(-M(CORRIDOR_MIN) / 2).is_empty:
        return None
    return {"name": "banco", "type": "bench", "box": b, "anchor_wall": None,
            "facing": _facing(o, sgn), "reason": "aos pés da cama, centralizado"}


def _place_corner(sm, dims, comodo, circ_u, win_zone, items, near_window):
    """Poltrona num canto livre (perto da janela), nunca no caminho porta->cama."""
    g = sm["_geom"]
    cell = g["cell"]
    w_m, d_m, _ = dims
    minx, miny, maxx, maxy = cell.bounds
    win_pts = [o["center"] for o in sm["openings"] if o["kind"] == "window"]
    corners = [(minx, miny), (maxx, miny), (minx, maxy), (maxx, maxy)]
    if near_window and win_pts:
        wx, wy = win_pts[0]
        corners.sort(key=lambda c: (c[0] - wx) ** 2 + (c[1] - wy) ** 2)
    for cx, cy in corners:
        sx = 1 if cx < (minx + maxx) / 2 else -1
        sy = 1 if cy < (miny + maxy) / 2 else -1
        b = box(min(cx, cx + sx * M(w_m)), min(cy, cy + sy * M(d_m)),
                max(cx, cx + sx * M(w_m)), max(cy, cy + sy * M(d_m)))
        b = translate(b, sx * M(0.10), sy * M(0.10))
        if comodo.contains(b) and not _hit(b, circ_u) and not _hit(b, win_zone) and not _ov(b, items):
            return {"name": "poltrona", "type": "armchair", "box": b, "anchor_wall": None,
                    "facing": None, "reason": "canto livre perto da janela (leitura)"}
    return None


def _place_beside(polt, dims, comodo, circ_u, items):
    w_m, d_m, _ = dims
    pb = polt["box"]
    for dx, dy in ((M(0.85), 0), (-M(0.85), 0), (0, M(0.85)), (0, -M(0.85))):
        b = translate(box(pb.bounds[0], pb.bounds[1], pb.bounds[0] + M(w_m), pb.bounds[1] + M(d_m)), dx, dy)
        if comodo.contains(b) and not _hit(b, circ_u) and not _ov(b, items):
            return {"name": "mesa_lateral", "type": "side_table", "box": b, "anchor_wall": None,
                    "facing": None, "reason": "ao lado da poltrona"}
    return None


def _solids(items):
    return [it for it in items if not it.get("decorative")]


def _side_clearance(bed, hb, usable):
    """Menor folga lateral da cama (ao-longo da parede) ate a borda do usable."""
    b = bed["box"].bounds
    if hb["orient"] == "v":
        lo_r, hi_r, lo_b, hi_b = usable.bounds[1], usable.bounds[3], b[1], b[3]
    else:
        lo_r, hi_r, lo_b, hi_b = usable.bounds[0], usable.bounds[2], b[0], b[2]
    return round(max(0.0, min((lo_b - lo_r), (hi_r - hi_b)) * PT_TO_M), 2)


def _foot_clearance(bed, hb, usable):
    """Folga no pe da cama (perp) ate a parede oposta (borda do usable)."""
    b = bed["box"].bounds
    if hb["orient"] == "v":
        foot = (usable.bounds[2] - b[2]) if hb["sgn"] > 0 else (b[0] - usable.bounds[0])
    else:
        foot = (usable.bounds[3] - b[3]) if hb["sgn"] > 0 else (b[1] - usable.bounds[1])
    return round(max(0.0, foot * PT_TO_M), 2)


def score(items, sm, hb, downgrades):
    """Hard gates + soft score (pontos da spec)."""
    g = sm["_geom"]
    cell, usable, walls, room_walls = g["cell"], g["usable"], g["walls"], g["room_walls"]
    comodo = cell.buffer(M(COMODO_FOLGA))
    wfoot = unary_union([wall_footprint(walls[wid], extend_endpoints=True) for wid in room_walls])
    circ = list(g["circ"] or [])
    dz = _door_zones(sm)
    if dz is not None:
        circ.append(dz)
    circ_u = unary_union(circ) if circ else None
    win_zone = _window_zones(sm)
    solids = _solids(items)
    bed = next((it for it in items if it["type"] == "bed"), None)
    nights = [it for it in items if it["type"] == "nightstand"]
    ward = next((it for it in items if it["type"] == "wardrobe"), None)
    rug = next((it for it in items if it["type"] == "rug"), None)

    out_room = any(not comodo.contains(it["box"]) for it in solids)
    hits_wall = any(it["box"].intersection(wfoot).area > (0.06 / PT_TO_M ** 2) for it in solids)
    hits_door = any(_hit(it["box"], circ_u) for it in solids)
    hits_win = any(_hit(it["box"], win_zone) for it in solids)
    free = usable
    for it in solids:
        free = free.difference(it["box"])
    passage_ok = not free.buffer(-M(CORRIDOR_MIN) / 2).is_empty

    pts, bd, viol = 0, {}, []
    if out_room:
        viol.append("móvel fora do quarto")
    if hits_wall:
        viol.append("interseção com parede"); pts -= 50; bd["intersecao_parede"] = -50
    if hits_door:
        viol.append("bloqueio de porta"); pts -= 30; bd["bloqueio_porta"] = -30
    if hits_win:
        viol.append("bloqueio de janela"); pts -= 30; bd["bloqueio_janela"] = -30
    valid = not (out_room or hits_wall or hits_door or hits_win)
    hard = {"dentro_do_quarto": not out_room, "nao_invade_parede": not hits_wall,
            "nao_bloqueia_porta": not hits_door, "nao_bloqueia_janela": not hits_win,
            "passagem_min_060": passage_ok}

    side = _side_clearance(bed, hb, usable) if bed else 0.0
    foot = _foot_clearance(bed, hb, usable) if bed else 0.0
    if not hb.get("has_window") and not hb.get("has_door"):
        pts += 30; bd["cama_parede_limpa"] = 30
    if len(nights) == 2:
        pts += 20; bd["simetria_criados"] = 20
    elif len(nights) == 1:
        pts += 8; bd["simetria_criados"] = 8
    if side >= SIDE[1] and foot >= FOOT[1] and passage_ok:
        pts += 20; bd["circulacao"] = 20
    elif not passage_ok:
        pts -= 15; bd["circulacao_apertada"] = -15
    if ward is not None:
        pts += 15; bd["guarda_roupa"] = 15
    if rug is not None:
        pts += 10; bd["tapete"] = 10
    extras = sum(1 for it in items if it["type"] in ("bench", "dresser"))
    if extras:
        pts += 5 * min(extras, 2); bd["banco_dresser"] = 5 * min(extras, 2)
    return {"valid": valid, "score": round(pts, 1), "hard": hard, "violations": viol,
            "breakdown": bd,
            "clearances_m": {"lateral": _clear(side), "pe": _clear(foot), "passagem_ok": passage_ok}}


def _piece_json(it):
    b = it["box"].bounds
    return {"name": it["name"], "type": it["type"],
            "x_m": round((b[0] + b[2]) / 2 * PT_TO_M, 2),
            "y_m": round((b[1] + b[3]) / 2 * PT_TO_M, 2),
            "width_m": round((b[2] - b[0]) * PT_TO_M, 2),
            "depth_m": round((b[3] - b[1]) * PT_TO_M, 2),
            "rotation": 0, "anchor_wall": it.get("anchor_wall"), "reason": it.get("reason")}


def run(con, room_id, minimalist=True):
    sm = build_spatial_model(con, room_id)
    out = {"room_id": room_id, "room_name": sm.get("room_name"), "area_m2": sm["area_m2"],
           "minimalist": minimalist, "candidates": []}
    top, allhb = _headboard_candidates(sm, M(KING[0]), k=3)
    out["headboard_ranking"] = [{"wall": h["wall_id"], "score": h["score"], "clean": h["clean"],
                                 "has_window": h["has_window"], "has_door": h["has_door"]}
                                for h in allhb]
    if not top:
        out["result"] = "NO_VALID_LAYOUT"
        out["reason"] = "nenhuma parede comporta a cama king (1.93 m)"
        return sm, out
    for rank, h in enumerate(top):
        hb = _wall_setup(sm, h["wall_id"])
        if hb is None:
            continue
        hb["has_window"] = h["has_window"]
        hb["has_door"] = h["has_door"]
        items, downs = build_layout(sm, hb, minimalist)
        if items is None:
            out["candidates"].append({"headboard_wall": h["wall_id"], "rank": rank,
                                      "valid": False, "score": -999, "reason": downs})
            continue
        res = score(items, sm, hb, downs)
        out["candidates"].append({"headboard_wall": h["wall_id"], "rank": rank, **res,
                                  "downgrades": downs, "_items": items,
                                  "layout": [_piece_json(it) for it in items]})
    if not any(c.get("valid") for c in out["candidates"]):
        out["result"] = "NO_VALID_LAYOUT"
        out["reason"] = "nenhum candidato passou os hard gates"
        out["ranking"] = [{"wall": c["headboard_wall"], "score": c.get("score"),
                           "valid": False, "violations": c.get("violations")}
                          for c in out["candidates"]]
        return sm, out
    order = sorted(out["candidates"],
                   key=lambda c: (not c.get("valid"), -c.get("score", -999), c["rank"]))
    out["result"] = "OK"
    out["chosen"] = order[0]["headboard_wall"]
    out["chosen_score"] = order[0]["score"]
    out["winner_layout"] = order[0]["layout"]
    out["ranking"] = [{"rank": i + 1, "wall": c["headboard_wall"], "score": c.get("score"),
                       "valid": c.get("valid"), "breakdown": c.get("breakdown"),
                       "downgrades": c.get("downgrades")}
                      for i, c in enumerate(order)]
    out["_winner_items"] = order[0]["_items"]
    return sm, out


def plot(sm, out, out_png, tag=""):
    """PNG top-down do layout VENCEDOR (caixas coloridas, tapete sob, setas de
    orientacao). ARTEFATO DE VISUAL_REVIEW (humano julga)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    g = sm["_geom"]
    cell, usable, circ = g["cell"], g["usable"], g["circ"]
    items = out.get("_winner_items") or []
    fig, ax = plt.subplots(figsize=(8.5, 9))
    ax.fill(*cell.exterior.xy, color="0.92", zorder=1)
    if usable.geom_type == "Polygon":
        ax.fill(*usable.exterior.xy, color="#eef7ee", alpha=0.7, zorder=2)
    for r in circ:
        if r.geom_type == "Polygon":
            ax.fill(*r.exterior.xy, color="#ff8a80", alpha=0.4, hatch="//", zorder=3)
    for o in g["con"]["openings"]:
        if o["wall_id"] not in g["room_walls"]:
            continue
        kind = o.get("kind_v5") or o.get("kind")
        cx, cy = o["center"]
        ax.plot(cx, cy, marker="s", markersize=11, zorder=8,
                color="#00b0ff" if kind == "window" else "#8d6e63")
    for it in sorted(items, key=lambda x: 0 if x.get("decorative") else 1):
        b = it["box"]
        if b.is_empty or b.geom_type != "Polygon":
            continue
        rgb = [c / 255 for c in RGB.get(it["type"], [120, 120, 120])]
        deco = it.get("decorative")
        ax.fill(*b.exterior.xy, color=rgb, alpha=0.35 if deco else 0.85,
                zorder=4 if deco else 5)
        if not deco:
            ax.annotate(it["name"].replace("_", " "), (b.centroid.x, b.centroid.y),
                        color="white", fontsize=7, ha="center", va="center",
                        zorder=6, weight="bold")
        fac = it.get("facing")
        if fac:
            L = M(0.5)
            ax.annotate("", xy=(b.centroid.x + fac[0] * L, b.centroid.y + fac[1] * L),
                        xytext=(b.centroid.x, b.centroid.y),
                        arrowprops=dict(arrowstyle="-|>", color="#ffd600", lw=2.3), zorder=7)
    sub = f"Quarto KING designer {tag} ('{out.get('room_name')}') | {out['result']}"
    if out["result"] == "OK":
        win = next(c for c in out["candidates"] if c["headboard_wall"] == out["chosen"])
        cl = win.get("clearances_m", {})
        sub += (f"\ncabeceira {out['chosen']} | score {out['chosen_score']} | "
                f"lateral {cl.get('lateral')}m  pe {cl.get('pe')}m")
    ax.set_title(sub, fontsize=10)
    ax.set_aspect("equal")
    ax.invert_yaxis()
    fig.text(0.5, 0.015, "azul=cama  teal=criado  bege=tapete  roxo=guarda-roupa  "
             "cinza=banco  marrom=dresser  verde=poltrona  amarelo=mesa  "
             "seta amarela=frente  ciano=janela", ha="center", fontsize=7)
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    plt.savefig(out_png, dpi=90)
    plt.close(fig)


EXPECTED = {"bed": "cama king", "nightstand": "criados-mudos", "rug": "tapete",
            "wardrobe": "guarda-roupa", "bench": "banco", "dresser": "dresser",
            "armchair": "poltrona", "side_table": "mesa lateral"}


def to_markdown(out, tag):
    L = [f"# Quarto KING designer — relatório ({tag}, '{out.get('room_name')}')", "",
         f"área {out.get('area_m2')} m² | resultado **{out['result']}**", ""]
    if out["result"] == "OK":
        win = next(c for c in out["candidates"] if c["headboard_wall"] == out["chosen"])
        cl = win.get("clearances_m", {})
        L.append(f"## Vencedor: cabeceira `{out['chosen']}` — **{out['chosen_score']} pts**")
        L.append(f"- clearances: lateral {cl.get('lateral')} m, pé {cl.get('pe')} m, "
                 f"passagem {'OK' if cl.get('passagem_ok') else 'APERTADA'}")
        L.append("- score: " + ", ".join(f"{k}={v}" for k, v in win.get("breakdown", {}).items()))
        if win.get("downgrades"):
            L.append("- downgrades: " + "; ".join(win["downgrades"]))
        L.append("- móveis:")
        for p in out.get("winner_layout", []):
            L.append(f"  - **{p['name']}** ({p['type']}) {p['width_m']}×{p['depth_m']} m "
                     f"@({p['x_m']},{p['y_m']}) parede `{p.get('anchor_wall')}` — {p.get('reason')}")
        present = {p["type"] for p in out.get("winner_layout", [])}
        omit = [v for k, v in EXPECTED.items() if k not in present]
        if omit:
            L.append("- **omitidos** (não couberam com folga / sem espaço): " + ", ".join(omit))
    else:
        L.append(f"- {out.get('reason')}")
    L.append("")
    L.append("## Candidatos testados (paredes de cabeceira)")
    for c in sorted(out.get("candidates", []), key=lambda x: -x.get("score", -999)):
        viol = c.get("violations") or ([] if c.get("valid") else [c.get("reason")])
        L.append(f"- cabeceira `{c['headboard_wall']}` — score {c.get('score')}, "
                 f"valid={c.get('valid')}" + (f" — bloqueios: {viol}" if viol else ""))
    return "\n".join(L)


def _items_to_boxes(items):
    """Converte os items do designer pro formato place_layout (boxes SU inches)."""
    pt_to_in = (0.19 / 5.4) * 39.3700787402
    boxes = []
    for it in items:
        b = it["box"]
        if b.is_empty or b.geom_type != "Polygon":
            continue
        x0, y0, x1, y1 = b.bounds
        corners = [[round(px * pt_to_in, 2), round(py * pt_to_in, 2)]
                   for px, py in list(b.exterior.coords)[:-1]]
        boxes.append({"kind": it["type"], "x0": x0 * pt_to_in, "y0": y0 * pt_to_in,
                      "x1": x1 * pt_to_in, "y1": y1 * pt_to_in, "corners": corners,
                      "h_in": HEIGHT.get(it["type"], 0.5) * 39.3700787402,
                      "rgb": RGB.get(it["type"], [120, 120, 120]), "label": it["name"],
                      "ambiguous": False, "decorative": bool(it.get("decorative"))})
    return boxes


def build_skp(out_dir, tag, items):
    """Materializa o quarto (coords planta_74) no shell real via place_layout_skp.rb.
    Só faz sentido p/ comodo real (r000); sintético não tem shell. Launch SU."""
    import os
    import subprocess
    import time
    root = Path(__file__).resolve().parents[1]
    su = r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
    base = root / "artifacts/planta_74/planta_74.skp"
    rb = root / "tools/place_layout_skp.rb"
    boxes = _items_to_boxes(items)
    skp = out_dir / f"bedroom_designer_{tag}.skp"
    paths = {"LAYOUT_OUT": skp, "LAYOUT_BEFORE": out_dir / f"bedroom_designer_{tag}_before.png",
             "LAYOUT_AFTER_TOP": out_dir / f"bedroom_designer_{tag}_after_top.png",
             "LAYOUT_AFTER_ISO": out_dir / f"bedroom_designer_{tag}_after_iso.png",
             "LAYOUT_LOG": out_dir / f"bedroom_designer_{tag}_skp_log.txt"}
    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)
    time.sleep(1)
    for p in list(paths.values()):
        try:
            if p.exists():
                p.unlink()
        except PermissionError:
            pass
    env = os.environ.copy()
    env["LAYOUT_BOXES"] = json.dumps(boxes)
    for k, p in paths.items():
        env[k] = str(p).replace("\\", "/")
    subprocess.Popen([su, str(base), "-RubyStartup", str(rb)], env=env,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    log = paths["LAYOUT_LOG"]
    deadline = time.time() + 240
    while time.time() < deadline:
        if log.exists():
            time.sleep(2)
            break
        time.sleep(1)
    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)
    return skp if skp.exists() else None


def main():
    from tools.make_synthetic_bedrooms import rect_bedroom
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", default="r000")
    ap.add_argument("--synthetic", action="store_true", help="quarto king sintetico limpo")
    ap.add_argument("--skp", action="store_true", help="gera SKP placeholder (so comodo real)")
    ap.add_argument("--full", action="store_true", help="modo cheio (banco/poltrona/mesa); default = minimalista")
    ap.add_argument("--out-dir", default="artifacts/planta_74/furnished")
    args = ap.parse_args()
    if args.synthetic:
        con = rect_bedroom("SUITE MASTER KING", w_m=4.6, d_m=5.0)
        room, tag = "bedroom", "synthetic_king"
    else:
        con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                         .read_text("utf-8"))
        room, tag = args.room, args.room
    sm, out = run(con, room, minimalist=not args.full)
    mode = "FULL" if args.full else "MINIMALISTA"
    print(f"QUARTO {tag} ('{out.get('room_name')}') {out['area_m2']}m2 | {out['result']} | {mode}")
    if out["result"] == "OK":
        print(f"  vencedor cabeceira {out['chosen']} | score {out['chosen_score']}")
        for p in out["winner_layout"]:
            print(f"    {p['type']:10} {p['name']:18} {p['width_m']}x{p['depth_m']} "
                  f"@({p['x_m']},{p['y_m']}) [{p.get('anchor_wall')}]")
        win = next(c for c in out["candidates"] if c["headboard_wall"] == out["chosen"])
        if win.get("downgrades"):
            print("  downgrades:", win["downgrades"])
        print("  clearances:", win.get("clearances_m"), "| breakdown:", win.get("breakdown"))
    else:
        print("  ", out.get("reason"))
    od = Path(args.out_dir)
    od.mkdir(parents=True, exist_ok=True)
    if out["result"] == "OK":
        plot(sm, out, od / f"bedroom_designer_{tag}.png", tag)
        print(f"  -> {od}/bedroom_designer_{tag}.png")
    clean = {k: v for k, v in out.items() if not k.startswith("_")}
    for c in clean.get("candidates", []):
        c.pop("_items", None)
    (od / f"bedroom_designer_{tag}.json").write_text(
        json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    (od / f"bedroom_designer_{tag}.md").write_text(to_markdown(out, tag), encoding="utf-8")
    print(f"  -> {od}/bedroom_designer_{tag}.json + .md")
    if args.skp and out["result"] == "OK" and not args.synthetic:
        skp = build_skp(od, tag, out["_winner_items"])
        print(f"  -> SKP: {skp.name if skp else 'FALHOU (sem log do SU)'}")


if __name__ == "__main__":
    main()

