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

from shapely.affinity import rotate as shp_rotate
from shapely.geometry import Point, box
from shapely.ops import unary_union

from tools.layout_rules import (FILL_IDEAL, RESPIRO_IDEAL, RULES, flag_anti_patterns)
from tools.layout_rules import IDEAL_SOFA_TV as SOFA_TV_IDEAL
from tools.layout_rules import MAX_SOFA_TV as SOFA_TV_MAX
from tools.layout_rules import MIN_SOFA_TV as SOFA_TV_MIN
from tools.layout_rules import PASSAGE_MIN_M as PASSAGE_M
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
    "aparador": (1.60, 0.32),
}
# thresholds de REGRA (SOFA_TV_*, FILL_IDEAL, RESPIRO_IDEAL, PASSAGE_M) vem de
# tools.layout_rules (fonte unica das regras). Aqui so os de implementacao:
MARGIN_M = 0.03        # recuo do movel da face da parede (encosta sem cravar)
TOL_CIRC_M2 = 0.02     # quase-zero: movel NAO pode bloquear circulacao/abertura
TOL_WALL_M2 = 0.06     # toque leve na parede e OK (movel encosta)
COMODO_FOLGA_M = 0.06  # folga p/ "dentro do comodo" (borda da celula)
SOFA_TV_TARGET_M = 2.8  # distancia-alvo sofa<->TV (centro), dentro do ideal

# programa de moveis por TAMANHO de sala (spec GPT 1.3): sala pequena nao entope
# (movel menor); grande nao boia (movel maior). (largura ao-longo, profund) em m.
SIZE_FURN = {
    "small":  {"sofa_3": (1.80, 0.88), "rack_tv": (1.40, 0.40), "mesa_centro": (0.80, 0.45)},
    "medium": {"sofa_3": (2.20, 0.95), "rack_tv": (1.80, 0.45), "mesa_centro": (1.00, 0.60)},
    "large":  {"sofa_3": (2.60, 0.98), "rack_tv": (2.20, 0.48), "mesa_centro": (1.20, 0.70)},
}


def _room_size(cell_area_pt2):
    a = cell_area_pt2 * PT_TO_M ** 2
    return "small" if a < 12 else ("medium" if a <= 25 else "large")


def _sofa_perp(dep, sd):
    """Distancia (perp) da face da TV ate onde o sofa COMECA. Mira o ideal
    (~2.8 m de centro): flutua quando a sala e funda, encosta na parede oposta
    quando e rasa, nunca mais perto que SOFA_TV_MIN. Generaliza — antes os
    templates 'colavam o sofa na parede oposta' (sp=dep-sd), que so dava
    distancia plausivel na profundidade especifica da planta_74."""
    target = M(SOFA_TV_TARGET_M) - sd / 2.0
    near = M(SOFA_TV_MIN) - sd / 2.0
    return min(max(target, near), dep - sd - M(MARGIN_M))


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
    sx, sy = w["start"]
    ex, ey = w["end"]
    wall_len_m = ((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5 * PT_TO_M
    return {"id": tid, "wall": w, "orient": w["orientation"], "sgn": sgn,
            "face": face, "along_c": along_c,
            "depth": _tv_depth_m(w, g["usable"]) / PT_TO_M,
            "wall_len_m": wall_len_m,
            "ambiguous": sm["tv_wall_candidate"].get("confidence") == "ambiguous",
            "_geom": g}


def _item(kind, b, **kw):
    return {"kind": kind, "box": b, **kw}


def template_sofa_wall(s):
    """T1: rack na parede-TV, sofa 3-lug encostado na parede OPOSTA, mesa no meio."""
    o, f, sg, ac, dep = s["orient"], s["face"], s["sgn"], s["along_c"], s["depth"]
    rw, rd = M(FURN["rack_tv"][0]), M(FURN["rack_tv"][1])
    sw, sd = M(FURN["sofa_3"][0]), M(FURN["sofa_3"][1])
    sp = _sofa_perp(dep, sd)
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
    sp = _sofa_perp(dep, sd)
    pw, pd = M(FURN["poltrona"][0]), M(FURN["poltrona"][1])
    items = [_item("rack_tv", _fbox(o, f, sg, ac, M(MARGIN_M), rw, rd)),
             _item("sofa_3", _fbox(o, f, sg, ac, sp, sw, sd), facing="tv", dist_m=round((sp + sd / 2) * PT_TO_M, 2))]
    # poltrona ao lado do sofa (deslocada no eixo ao-longo), recuada
    items.append(_item("poltrona", _fbox(o, f, sg, ac + sw / 2 + pw / 2 + M(0.2), sp - M(0.4), pw, pd), facing="tv"))
    return items


def template_estar_ancorado(s):
    """T4 (spec GPT, docs/interiors/gpt_composition_spec.md): CORE ANCORADO +
    peca secundaria. rack (peso visual maior se parede-TV ambigua) + mesa 0.45 da
    frente do sofa + TAPETE grande (une o conjunto) + aparador condicional +
    POLTRONA na lateral, sobre o tapete e ANGULADA ~35deg (fecha a conversa).
    Tapete e decorativo (chao), nao bloqueante."""
    o, f, sg, ac, dep = s["orient"], s["face"], s["sgn"], s["along_c"], s["depth"]
    g = s.get("_geom")
    size = _room_size(g["cell"].area) if g is not None else "medium"
    fr = SIZE_FURN[size]                                       # dimensoes por tamanho de sala
    rd = M(fr["rack_tv"][1])
    sw, sd = M(fr["sofa_3"][0]), M(fr["sofa_3"][1])
    mw, md = M(fr["mesa_centro"][0]), M(fr["mesa_centro"][1])
    # P2 (GPT): parede-TV ambigua/curta -> rack mais largo (peso visual), ate 75%
    # da parede / 1.3x a base do size; nunca menor que a base.
    rack_w_m = fr["rack_tv"][0]
    if s.get("ambiguous"):
        rack_w_m = min(fr["rack_tv"][0] * 1.3, max(rack_w_m, s.get("wall_len_m", rack_w_m) * 0.75))
    rw = M(rack_w_m)
    sp = _sofa_perp(dep, sd)                                   # sofa a distancia-alvo (flutua se funda)
    pw, pd = M(FURN["poltrona"][0]), M(FURN["poltrona"][1])
    pol_off = M(0.12)                                          # poltrona pro canto SEM vazar (gate)
    # tapete: do respiro do rack (0.20) ate entrar 0.30 sob a frente do sofa;
    # excede 0.30 de cada lado E estende +pol_off pro lado da poltrona, pra
    # mante-la conectada (>=20% sobre o tapete; "rug supports" da spec GPT).
    rug_start = M(MARGIN_M) + rd + M(0.20)
    rug_perp = max(M(0.40), (sp + M(0.30)) - rug_start)
    rug_w = sw + 2 * M(0.30) + pol_off
    items = [_item("tapete", _fbox(o, f, sg, ac - pol_off / 2, rug_start, rug_w, rug_perp),
                   decorative=True)]
    items.append(_item("rack_tv", _fbox(o, f, sg, ac, M(MARGIN_M), rw, rd)))
    mp = max(M(MARGIN_M) + rd + M(0.20), sp - M(0.45) - md)     # mesa 0.45 da frente
    items.append(_item("mesa_centro", _fbox(o, f, sg, ac, mp, mw, md)))
    items.append(_item("sofa_3", _fbox(o, f, sg, ac, sp, sw, sd),
                       facing="tv", dist_m=round((sp + sd / 2) * PT_TO_M, 2)))
    apw, apd = M(FURN["aparador"][0]), M(FURN["aparador"][1])   # aparador condicional
    if dep - (sp + sd) >= apd + M(0.80):
        items.append(_item("aparador", _fbox(o, f, sg, ac, sp + sd + M(0.05), apw, apd)))
    # P3 (GPT refino): poltrona no canto lateral, angulada ~35deg. CONDICIONAL:
    # so entra se NAO bloquear circulacao nem sair do comodo (regra GPT "core
    # valido > opcional bonito" — nao forca poltrona jogada).
    pol = shp_rotate(_fbox(o, f, sg, ac - sw / 2 - pw * 0.2 - pol_off,
                           mp + md / 2 - pd / 2, pw, pd), 35, origin="centroid")
    g = s.get("_geom")
    blocks = False
    if g is not None:
        circ_u = unary_union(g["circ"]) if g["circ"] else None
        comodo = g["cell"].buffer(M(COMODO_FOLGA_M))
        tol = TOL_CIRC_M2 / PT_TO_M ** 2
        blocks = (circ_u is not None and pol.intersection(circ_u).area > tol) \
            or (not comodo.contains(pol))
    if not blocks:
        items.append(_item("poltrona", pol, facing="tv", rotated_deg=35))
    return items


TEMPLATES = [("sofa_contra_parede", template_sofa_wall),
             ("sofa_flutuante_setoriza", template_sofa_float),
             ("sofa_mais_poltrona", template_sofa_poltrona),
             ("estar_ancorado", template_estar_ancorado)]

# tambem acessivel por nome p/ materializacao direta (place_layout --template)
EXTRA_TEMPLATES = {"estar_ancorado": template_estar_ancorado}


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
    # tapete e decorativo (chao): NAO conta como obstaculo de parede/circulacao/
    # passagem (a pessoa anda sobre ele). So moveis solidos bloqueiam.
    solid = [it for it in items if not it.get("decorative")]
    hits_wall = hits_circ = out_room = False
    for it in solid:
        if circ_u is not None and it["box"].intersection(circ_u).area > tol_circ:
            hits_circ = True
        if it["box"].intersection(wfoot).area > tol_wall:
            hits_wall = True
        if not comodo.contains(it["box"]):
            out_room = True
    free = usable
    for it in solid:
        free = free.difference(it["box"])
    passage_ok = not free.buffer(-M(PASSAGE_M) / 2).is_empty
    # gate: o rack/TV deve ficar ENCOSTADO na parede-TV (o along-search nao pode
    # desliza-lo pra fora da parede focal pra burlar os outros gates).
    rack_it = next((it for it in items if it["kind"] == "rack_tv"), None)
    rack_on_wall = True
    if rack_it is not None and tv.get("id") in walls:
        tvwall = wall_footprint(walls[tv["id"]], extend_endpoints=True)
        rack_on_wall = rack_it["box"].distance(tvwall) < M(0.15)
    hard = {"nao_invade_parede": not hits_wall,
            "nao_bloqueia_circulacao": not hits_circ,
            "nao_bloqueia_porta_janela": not hits_circ,   # circ ja inclui aberturas
            "dentro_do_comodo": not out_room,
            "passagem_min_080": passage_ok,
            "rack_na_parede_tv": rack_on_wall}
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
    fill = round(sum(it["box"].area for it in items if not it.get("decorative")) / usable.area, 2)
    flo, fhi = FILL_IDEAL
    if flo <= fill <= fhi:
        soft["proporcao"] = 10.0
    else:
        dev = min(abs(fill - flo), abs(fill - fhi))
        soft["proporcao"] = round(max(0.0, 10 - dev * 50), 1)
        pen.append(f"proporcao moveis/sala {fill} fora de {flo}-{fhi}")

    # composicao (spec GPT slice 2): premia ANCORAGEM (tapete unindo o grupo) +
    # EIXO FOCAL (rack-mesa-sofa centros alinhados). Explica por que a composicao
    # vence — nao so "tem mais movel".
    rug = next((it for it in items if it.get("decorative")), None)
    mesa = next((it for it in items if it["kind"] == "mesa_centro"), None)
    comp, comp_bits = 0.0, []
    if rug is not None:
        on_rug = [it for it in items
                  if it["kind"] in ("sofa_3", "sofa_2", "mesa_centro", "poltrona")
                  and it["box"].intersection(rug["box"]).area > 0.3 * it["box"].area]
        if on_rug:
            comp += min(8.0, 4.0 * len(on_rug))        # ate 8: tapete ancora 2+ pecas
            comp_bits.append(f"tapete ancora {len(on_rug)}")
    if rack and sofa and mesa is not None:
        ax = (lambda p: p.x) if tv["orient"] == "h" else (lambda p: p.y)
        cc = [ax(rack["box"].centroid), ax(mesa["box"].centroid), ax(sofa["box"].centroid)]
        spread = (max(cc) - min(cc)) * PT_TO_M
        fa = round(7.0 * max(0.0, 1 - spread / 0.4), 1)  # ate 7: eixo focal alinhado
        comp += fa
        if fa >= 4:
            comp_bits.append(f"eixo focal {round(spread, 2)}m")
    soft["composicao"] = round(comp, 1)
    if comp_bits:
        reasons.append("composicao: " + ", ".join(comp_bits) + f" (+{round(comp,1)})")
    else:
        pen.append("composicao fraca (sem tapete ancorando / eixo focal)")

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


def _aggregate_flags(out):
    """Agrega os anti-patterns flagrados em todos os candidatos -> resumo."""
    seen = {}
    for c in out.get("candidates", []):
        for a in c.get("anti_patterns", []):
            e = seen.setdefault(a["rule_id"], {"rule_id": a["rule_id"], "name": a["name"],
                                               "severity": a["severity"], "count": 0})
            e["count"] += 1
    return sorted(seen.values(), key=lambda x: (-x["count"], x["rule_id"]))


def _tv_uncertainty_note(tv_wall):
    """RL-11: se a parede-TV for AMBIGUOUS, explica a incerteza (nao crava)."""
    conf = tv_wall.get("confidence")
    if conf == "ambiguous":
        cands = tv_wall.get("candidates") or tv_wall.get("ranking") or []
        return (f"RL-11: parede-TV AMBIGUOUS - usando best_candidate "
                f"{tv_wall.get('best_candidate')} mas ha {len(cands)} candidatas "
                f"proximas; layout gerado COM ressalva, nao cravado.")
    if conf == "none":
        return "RL-11: sem parede-TV confiavel - orientacao do sofa fica indefinida."
    return None


def run(con, room_id):
    sm = build_spatial_model(con, room_id)
    tv = _tv_setup(sm)
    out = {"stage": "BC_layout_candidates", "room_id": room_id,
           "tv_wall": sm["tv_wall_candidate"], "candidates": [],
           "rules_source": "tools/layout_rules.py",
           "rules": [{"id": r["id"], "kind": r["kind"], "name": r["name"]} for r in RULES]}
    note = _tv_uncertainty_note(sm["tv_wall_candidate"])
    if note:
        out["tv_wall_uncertainty"] = note
    if tv is None:
        out["result"] = "NO_VALID_LAYOUT"
        out["reason"] = "sem parede-TV candidata (Etapa A)"
        out["anti_patterns_flagged"] = []
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
            "anti_patterns": flag_anti_patterns(res),   # regras violadas (feedback loop)
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
                           "valid": False, "blocked_by": c["violations"],
                           "anti_patterns": [a["rule_id"] for a in c["anti_patterns"]]}
                          for c in out["candidates"]]
        out["anti_patterns_flagged"] = _aggregate_flags(out)
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
                       "anti_patterns": [a["rule_id"] for a in c["anti_patterns"]],
                       "tie_break": {"offset_m": abs(c["along_offset_m"]),
                                     "template_order": c["template_order"]}}
                      for i, c in enumerate(order)]
    tops = [c for c in order if c["total_score"] == order[0]["total_score"]]
    if len(tops) > 1:
        out["tie_note"] = (f"{len(tops)} candidatos empataram em {order[0]['total_score']} pts; "
                           f"desempate deterministico (menor offset lateral -> ordem do template) "
                           f"-> {order[0]['template']}")
    out["anti_patterns_flagged"] = _aggregate_flags(out)
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
        aps = c.get("anti_patterns", [])
        if aps:
            ids = sorted({a["rule_id"] for a in aps})
            title += "\nregras: " + ", ".join(ids)[:58]
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
    if out.get("tv_wall_uncertainty"):
        print(f"  /!\\ {out['tv_wall_uncertainty']}")
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
        for a in c["anti_patterns"]:
            print(f"      ! {a['rule_id']} [{a['severity']}] {a['name']}: {a['evidence']}")
    print(f"=> RESULTADO: {out['result']}")
    if out["result"] == "OK":
        print(f"   RANKING: " + " > ".join(f"{r['template']}={r['total_score']}" for r in out["ranking"]))
        print(f"   CHOSEN: {out['chosen_candidate']}")
        if out.get("tie_note"):
            print(f"   TIE: {out['tie_note']}")
    else:
        print(f"   ({out.get('reason')})")
    if out.get("anti_patterns_flagged"):
        print("   REGRAS DISPARADAS (feedback loop):")
        for a in out["anti_patterns_flagged"]:
            print(f"     {a['rule_id']} [{a['severity']:4}] {a['name']} x{a['count']}")
    print(f"-> {out_dir}/")


if __name__ == "__main__":
    main()
