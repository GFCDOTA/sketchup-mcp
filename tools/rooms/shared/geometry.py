"""Geometria 2D/box comum a vários cômodos — única implementação.

Extraído dos brains legados SEM mudanças de comportamento. Não altera .skp.
Não depende de especialistas de um cômodo nem do orquestrador.
"""
from __future__ import annotations

from shapely.geometry import Point, box
from shapely.ops import unary_union

from tools.spatial_model import _wall_mid


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

def _door_zones(sm):
    """Pegadas (no plano) das aberturas de PORTA/passagem/porta-vidro — nenhum
    movel pode invadir (cama em cima da abertura da porta = hard gate)."""
    g = sm["_geom"]
    walls = g["walls"]
    rw = set(g["room_walls"])
    wt = float(g["con"]["wall_thickness_pts"])
    door_kinds = {"interior_door", "interior_passage", "glazed_balcony"}
    zs = []
    for o in g["con"]["openings"]:
        k = o.get("kind_v5") or o.get("kind")
        if o["wall_id"] not in rw or k not in door_kinds:
            continue
        w = walls[o["wall_id"]]
        cx, cy = o["center"]
        hw = o["opening_width_pts"] / 2.0
        if w["orientation"] == "h":
            zs.append(box(cx - hw, cy - wt, cx + hw, cy + wt))
        else:
            zs.append(box(cx - wt, cy - hw, cx + wt, cy + hw))
    return unary_union(zs) if zs else None

def _oriented_box(kind, center_in, facing, w_m, d_m, z0_m, h_m, rgb, label=None, module=None,
                  decorative=False):
    """Caixa (rack/mesa/tapete) centrada em center_in (shell inches) com a FRENTE
    (-Y local) apontando 'facing'. Mesma rotacao do place_sofa_boxes -> qualquer
    angulo. w=largura (perp ao facing), d=profundidade (ao longo do facing)."""
    import math
    M2IN = 39.3700787402
    cx, cy = center_in
    fx, fy = facing
    nrm = math.hypot(fx, fy) or 1.0
    fx, fy = fx / nrm, fy / nrm
    theta = math.atan2(fx, -fy)
    ct, st = math.cos(theta), math.sin(theta)
    corners = []
    for lx, ly in ((-w_m / 2, -d_m / 2), (w_m / 2, -d_m / 2),
                   (w_m / 2, d_m / 2), (-w_m / 2, d_m / 2)):
        wx, wy = lx * ct - ly * st, lx * st + ly * ct
        corners.append([round(cx + wx * M2IN, 2), round(cy + wy * M2IN, 2)])
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return {"kind": kind, "x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys),
            "corners": corners, "h_in": round(h_m * M2IN, 2), "z0_in": round(z0_m * M2IN, 2),
            "rgb": rgb, "label": label or kind, "module": module or kind,
            "ambiguous": False, "decorative": decorative}

