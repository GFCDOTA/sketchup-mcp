"""scene_spatial_gate.py — SpatialGate do Intent-to-Scene: valida a CENA composta
(scene.json do SceneComposer) com checks DETERMINISTICOS, sem SU. A regra: a
composicao nao pode parecer "moveis jogados" — cada relacao espacial declarada nas
composition_rules e' verificada numericamente.

HARD (qualquer falha -> FAIL):
  dentro_da_sala       — nenhum movel atravessa parede (bbox dentro do interior)
  nao_flutua           — tudo assenta no chao / tapete / parede (por tipo)
  sem_colisao          — nenhum par de moveis com interseccao 3D (tapete e' underlay)
  mesa_distancia       — mesa de centro a [0.35, 0.45] m da frente do hero
  tapete_maior_que_hero— tapete excede a largura do hero nos 2 lados
  quadro_centralizado  — quadro centrado no hero (+-5cm) e respiro [0.10, 0.45]
  cortina_na_janela    — cortina no eixo da janela (+-5cm), cobre a largura, na parede
  cortina_moldura      — cortina nao-protagonista: paineis cobrem <=55% do proprio
                         vao (abertos = moldura da janela, nao parede listrada).
                         Regra do cycle 002 (GPT WARN: cortina dominava a 3/4)
  equilibrio_quadrantes— massa de mobiliario (footprint, SEM tapete) presente nos 4
                         quadrantes da sala: quadrante mais vazio >= 7% do total.
                         Regra do cycle 002 (GPT WARN: metade sul vazia)
  circulacao           — porta livre + corredor >=0.7m da porta ate a zona de estar
  bbox_plausivel       — bbox de cada tipo dentro da faixa (DECOR_PLAUSIBLE_BBOX_M)
  camera_enquadra      — hero no frame da camera 3/4 (cobertura >= min, centrado)

SOFT (falha -> WARN):
  hero_ancorado        — costas do hero a <=0.45m da parede
  respiro_lateral      — side_table/floor_lamp com folga >=0.05m do hero
  planta_perto_janela  — planta a <=0.35m da parede da janela e <=0.6m do vao
  accent_em_dialogo    — accent_seat ROTACIONADO (nao paralelo aos eixos) e
                         apontando pro hero (dot>=0.9). Regra do cycle 003
                         (GPT: "objeto colocado" vs "conversa de estar")

Uso: python -m interior.validators.scene_spatial_gate [runs/scenes/<id>]
     (sem arg: compoe a fixture canonica em memoria + roda 6 sabotagens que
      DEVEM falhar — o gate prova que pega o erro, nao so aprova o certo)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.decor_anatomy_spec import DECOR_PLAUSIBLE_BBOX_M   # noqa: E402

TABLE_GAP_RANGE = (0.35, 0.45)
ART_CENTER_TOL = 0.05
ART_GAP_RANGE = (0.10, 0.45)
CURTAIN_TOL = 0.05
CURTAIN_MAX_COVER = 0.55       # paineis cobrem no maximo isso do vao da cortina
QUADRANT_MIN_SHARE = 0.07      # quadrante mais vazio >= 7% do footprint (sem tapete)
                               # (canonica cycle002: min=0.087 SE; sabotagem sem accent: ~0.0)
ANCHOR_MAX_M = 0.45
CORRIDOR_W = 0.70
EPS = 1e-6

# tipos que assentam no CHAO (z0 ~ 0 ou sobre o tapete)
FLOOR_TYPES = ("sofa", "rug", "coffee_table", "side_table", "floor_lamp",
               "plant_placeholder", "accent_seat")
WALL_MOUNTED = {"wall_art": (0.3, 2.2), "curtain": (0.0, 0.12)}   # faixa valida de z0


def _olap1d(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _local_dims(pl):
    """(W, D, H) no frame LOCAL do movel (desfaz rotacao 90/270)."""
    x0, y0, x1, y1, z0, z1 = pl["bbox"]
    w, d = x1 - x0, y1 - y0
    if int(pl.get("rotation_deg", 0)) % 180 == 90:
        w, d = d, w
    return w, d, z1 - z0


def _wall_face(room, wall):
    W, D = room["width_m"], room["depth_m"]
    return {"north": D, "south": 0.0, "east": W, "west": 0.0}[wall]


def _rug_of(placements):
    return next((p for p in placements if p["type"] == "rug"), None)


def _hero_of(placements):
    return next((p for p in placements if p["role"] == "hero"), None)


# ------------------------------------------------------------------ camera proj
def _proj_xy(pt, eye, target):
    """Projecao ortografica de pt no plano da camera (right/up). Deterministica."""
    dx, dy, dz = (target[i] - eye[i] for i in range(3))
    n = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    d = (dx / n, dy / n, dz / n)
    rx, ry = d[1], -d[0]                      # right = d x up(0,0,1), normalizado em xy
    rn = math.hypot(rx, ry) or 1.0
    r = (rx / rn, ry / rn, 0.0)
    u = (r[1] * d[2] - r[2] * d[1], r[2] * d[0] - r[0] * d[2], r[0] * d[1] - r[1] * d[0])
    return (sum(pt[i] * r[i] for i in range(3)), sum(pt[i] * u[i] for i in range(3)))


def _proj_bbox(bb3, eye, target):
    x0, y0, x1, y1, z0, z1 = bb3
    pts = [_proj_xy((x, y, z), eye, target)
           for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    us = [p[0] for p in pts]
    vs = [p[1] for p in pts]
    return min(us), min(vs), max(us), max(vs)


# ------------------------------------------------------------------ gate
def scene_spatial_gate(scene, parts=None):
    """Valida a cena composta. Devolve {result, checks, why, metrics}."""
    room = scene["room"]
    W, D, H = room["width_m"], room["depth_m"], room["height_m"]
    pls = scene["placements"]
    openings = scene.get("openings", [])
    cam = scene.get("camera", {})
    checks, why, metrics = {}, [], {}
    hero = _hero_of(pls)
    rug = _rug_of(pls)
    rug_top = rug["bbox"][5] if rug else 0.0

    # 1. dentro_da_sala
    bad = [p["type"] for p in pls
           if p["bbox"][0] < -EPS or p["bbox"][1] < -EPS
           or p["bbox"][2] > W + EPS or p["bbox"][3] > D + EPS or p["bbox"][5] > H + EPS]
    checks["dentro_da_sala"] = not bad
    if bad:
        why.append(f"atravessa parede/teto: {bad}")

    # 2. nao_flutua
    floaters = []
    for p in pls:
        z0 = p["bbox"][4]
        if p["type"] in WALL_MOUNTED:
            lo, hi = WALL_MOUNTED[p["type"]]
            ok = lo - EPS <= z0 <= hi + EPS
            if p["type"] == "wall_art":   # precisa estar COLADO numa parede
                gaps = [abs(p["bbox"][0] - 0.0), abs(W - p["bbox"][2]),
                        abs(p["bbox"][1] - 0.0), abs(D - p["bbox"][3])]
                ok = ok and min(gaps) <= 0.02
        else:
            ok = z0 <= EPS or abs(z0 - rug_top) <= 1e-3
        if not ok:
            floaters.append(f"{p['type']}(z0={z0})")
    checks["nao_flutua"] = not floaters
    if floaters:
        why.append(f"flutuando/afundado: {floaters}")

    # 3. sem_colisao (3D, tapete = underlay permitido)
    hits = []
    solids = [p for p in pls if p["type"] != "rug"]
    for i, a in enumerate(solids):
        for b in solids[i + 1:]:
            ox = _olap1d(a["bbox"][0], a["bbox"][2], b["bbox"][0], b["bbox"][2])
            oy = _olap1d(a["bbox"][1], a["bbox"][3], b["bbox"][1], b["bbox"][3])
            oz = _olap1d(a["bbox"][4], a["bbox"][5], b["bbox"][4], b["bbox"][5])
            if ox * oy > 0.003 and oz > 0.01:
                hits.append(f"{a['type']}x{b['type']} ({ox * oy:.3f}m2)")
    checks["sem_colisao"] = not hits
    if hits:
        why.append(f"colisao 3D: {hits}")

    # 4. mesa_distancia
    table = next((p for p in pls if p["type"] == "coffee_table"), None)
    if hero and table:
        fx, fy = hero["facing"]
        hx0, hy0, hx1, hy1 = hero["bbox"][:4]
        tx0, ty0, tx1, ty1 = table["bbox"][:4]
        if fy < 0:
            gap = hy0 - ty1
        elif fy > 0:
            gap = ty0 - hy1
        elif fx < 0:
            gap = hx0 - tx1
        else:
            gap = tx0 - hx1
        metrics["coffee_table_gap_m"] = round(gap, 3)
        checks["mesa_distancia"] = TABLE_GAP_RANGE[0] - EPS <= gap <= TABLE_GAP_RANGE[1] + EPS
        if not checks["mesa_distancia"]:
            why.append(f"mesa de centro a {gap:.2f}m do hero (regra {TABLE_GAP_RANGE})")
    else:
        checks["mesa_distancia"] = table is None    # sem mesa = regra nao se aplica
        if hero is None:
            checks["mesa_distancia"] = False
            why.append("sem hero na cena")

    # 5. tapete_maior_que_hero (na largura do hero)
    if hero and rug:
        if hero["facing"][1] != 0:
            o1, o2 = hero["bbox"][0] - rug["bbox"][0], rug["bbox"][2] - hero["bbox"][2]
        else:
            o1, o2 = hero["bbox"][1] - rug["bbox"][1], rug["bbox"][3] - hero["bbox"][3]
        metrics["rug_overhang_m"] = [round(o1, 3), round(o2, 3)]
        checks["tapete_maior_que_hero"] = o1 > EPS and o2 > EPS
        if not checks["tapete_maior_que_hero"]:
            why.append(f"tapete nao excede o hero ({o1:.2f}/{o2:.2f})")
    else:
        checks["tapete_maior_que_hero"] = rug is None

    # 6. quadro_centralizado
    art = next((p for p in pls if p["type"] == "wall_art"), None)
    if hero and art:
        if hero["facing"][1] != 0:
            off = (art["bbox"][0] + art["bbox"][2]) / 2 - (hero["bbox"][0] + hero["bbox"][2]) / 2
        else:
            off = (art["bbox"][1] + art["bbox"][3]) / 2 - (hero["bbox"][1] + hero["bbox"][3]) / 2
        gap = art["bbox"][4] - hero["bbox"][5]
        metrics["art_offset_m"] = round(off, 3)
        metrics["art_gap_m"] = round(gap, 3)
        checks["quadro_centralizado"] = (abs(off) <= ART_CENTER_TOL
                                         and ART_GAP_RANGE[0] <= gap <= ART_GAP_RANGE[1])
        if not checks["quadro_centralizado"]:
            why.append(f"quadro off={off:.2f}m gap={gap:.2f}m (tol {ART_CENTER_TOL}/{ART_GAP_RANGE})")
    else:
        checks["quadro_centralizado"] = art is None

    # 7. cortina_na_janela
    curt = next((p for p in pls if p["type"] == "curtain"), None)
    wins = [o for o in openings if o["type"] == "window"]
    if curt and wins:
        win = wins[0]
        horiz = win["wall"] in ("north", "south")
        c_along = ((curt["bbox"][0] + curt["bbox"][2]) / 2 if horiz
                   else (curt["bbox"][1] + curt["bbox"][3]) / 2)
        c_w = (curt["bbox"][2] - curt["bbox"][0]) if horiz else (curt["bbox"][3] - curt["bbox"][1])
        face = _wall_face(room, win["wall"])
        c_perp = (curt["bbox"][1], curt["bbox"][3]) if horiz else (curt["bbox"][0], curt["bbox"][2])
        dist_wall = min(abs(c_perp[0] - face), abs(c_perp[1] - face))
        off = c_along - win["center_along_m"]
        metrics["curtain_offset_m"] = round(off, 3)
        checks["cortina_na_janela"] = (abs(off) <= CURTAIN_TOL
                                       and c_w >= win["width_m"] - EPS and dist_wall <= 0.25)
        if not checks["cortina_na_janela"]:
            why.append(f"cortina off={off:.2f} largura={c_w:.2f} dist_parede={dist_wall:.2f}")
    else:
        checks["cortina_na_janela"] = curt is None

    # 7b. cortina_moldura — paineis cobrem <= CURTAIN_MAX_COVER do proprio vao
    # (cortina aberta = moldura da janela; fechada = parede listrada protagonista).
    # Mede pelas parts (folds) quando disponiveis; fallback: spec do placement.
    if curt and wins:
        win = wins[0]
        spec = curt.get("spec") or {}
        span = spec.get("width")
        folds_w = None
        if parts:
            horiz = win["wall"] in ("north", "south")
            folds = [p for p in parts
                     if p.get("item") == "curtain" and p.get("kind") == "panel_fold"]
            if folds:
                ext = [(p["x0"], p["x1"]) if horiz else (p["y0"], p["y1"]) for p in folds]
                folds_w = sum(b - a for a, b in ext)
                span = span or (max(b for _, b in ext) - min(a for a, _ in ext))
        if folds_w is None and span:
            split = int(spec.get("panel_split", 1))
            folds_w = 2 * float(spec.get("panel_w", span / 2)) if split == 2 else span
        if folds_w is not None and span:
            cover = folds_w / span
            metrics["curtain_cover_frac"] = round(cover, 3)
            checks["cortina_moldura"] = cover <= CURTAIN_MAX_COVER + EPS
            if not checks["cortina_moldura"]:
                why.append(f"cortina cobre {cover:.0%} do vao (max {CURTAIN_MAX_COVER:.0%}) "
                           "— protagonista errada, abrir em paineis")
        else:
            checks["cortina_moldura"] = False
            why.append("cortina sem spec/parts pra medir cobertura")
    else:
        checks["cortina_moldura"] = curt is None

    # 7c. equilibrio_quadrantes — massa de mobiliario presente nos 4 quadrantes.
    # Footprint SEM o tapete (underlay dilui; o que pesa visualmente e' o que esta
    # de pe). Quadrante mais vazio >= QUADRANT_MIN_SHARE do total.
    qx, qy = W / 2.0, D / 2.0
    quads = ((0.0, 0.0, qx, qy), (qx, 0.0, W, qy), (0.0, qy, qx, D), (qx, qy, W, D))
    areas = [0.0, 0.0, 0.0, 0.0]
    for p in pls:
        if p["type"] == "rug":
            continue
        x0, y0, x1, y1 = p["bbox"][:4]
        for i, (a0, b0, a1, b1) in enumerate(quads):
            areas[i] += _olap1d(x0, x1, a0, a1) * _olap1d(y0, y1, b0, b1)
    tot = sum(areas)
    shares = [a / tot for a in areas] if tot > EPS else [0.0] * 4
    metrics["quadrant_shares"] = [round(s, 3) for s in shares]   # SW, SE, NW, NE
    checks["equilibrio_quadrantes"] = tot > EPS and min(shares) >= QUADRANT_MIN_SHARE
    if not checks["equilibrio_quadrantes"]:
        names = ("SW", "SE", "NW", "NE")
        worst = min(range(4), key=lambda i: shares[i])
        why.append(f"massa esmagada: quadrante {names[worst]} com "
                   f"{shares[worst]:.0%} do mobiliario (min {QUADRANT_MIN_SHARE:.0%})")

    # 8. circulacao — porta livre + corredor 0.7m ate a zona de estar
    blocked = []
    doors = [o for o in openings if o["type"] in ("door", "glass_door")]
    for o in doors:
        horiz = o["wall"] in ("north", "south")
        a0 = o["center_along_m"] - max(o["width_m"], CORRIDOR_W) / 2
        a1 = o["center_along_m"] + max(o["width_m"], CORRIDOR_W) / 2
        depth = max(o["width_m"], CORRIDOR_W)
        face = _wall_face(room, o["wall"])
        sgn = 1.0 if face == 0.0 else -1.0
        if horiz:
            zone = (a0, min(face, face + sgn * depth), a1, max(face, face + sgn * depth))
        else:
            zone = (min(face, face + sgn * depth), a0, max(face, face + sgn * depth), a1)
        # corredor: prolonga a faixa da porta ate a borda da zona de estar (tapete/hero)
        target_edge = None
        seat = rug or hero
        if seat is not None:
            sb = seat["bbox"]
            target_edge = sb[1] if (horiz and face == 0.0) else \
                sb[3] if horiz else sb[0] if face == 0.0 else sb[2]
        if horiz:
            corr = (o["center_along_m"] - CORRIDOR_W / 2, min(face, target_edge or face),
                    o["center_along_m"] + CORRIDOR_W / 2, max(face, target_edge or face))
        else:
            corr = (min(face, target_edge or face), o["center_along_m"] - CORRIDOR_W / 2,
                    max(face, target_edge or face), o["center_along_m"] + CORRIDOR_W / 2)
        for p in pls:
            if p["type"] == "rug" or p["bbox"][4] > 0.3:   # underlay/altos nao bloqueiam passo? nao: so tapete
                if p["type"] == "rug":
                    continue
            for zr, tag in ((zone, "porta"), (corr, "corredor")):
                ox = _olap1d(p["bbox"][0], p["bbox"][2], zr[0], zr[2])
                oy = _olap1d(p["bbox"][1], p["bbox"][3], zr[1], zr[3])
                if ox * oy > 0.01:
                    blocked.append(f"{p['type']} na zona da {tag} {o['id']}")
    checks["circulacao"] = not blocked
    if blocked:
        why.append("; ".join(sorted(set(blocked))))

    # 9. bbox_plausivel
    implaus = []
    for p in pls:
        rng = DECOR_PLAUSIBLE_BBOX_M.get(p["type"])
        if not rng:
            continue
        w, d, h = _local_dims(p)
        for v, (lo, hi), tag in ((w, rng[0], "W"), (d, rng[1], "D"), (h, rng[2], "H")):
            if not (lo - EPS <= v <= hi + EPS):
                implaus.append(f"{p['type']}.{tag}={v:.2f} fora [{lo},{hi}]")
    checks["bbox_plausivel"] = not implaus
    if implaus:
        why.append(f"bbox implausivel: {implaus}")

    # 10. camera_enquadra (hero coberto e centrado no frame 3/4)
    if hero and cam.get("eye"):
        eye, target = cam["eye"], cam["target"]
        if parts:
            # mesmo dollhouse do render: paredes escondidas + teto fora do frame
            hidden = tuple(f"wall_{w}" for w in cam.get("hide_walls", [])) + ("ceiling",)
            vis = [p for p in parts if not str(p.get("label", "")).startswith(hidden)]
            fx0 = min(p["x0"] for p in vis); fy0 = min(p["y0"] for p in vis)
            fx1 = max(p["x1"] for p in vis); fy1 = max(p["y1"] for p in vis)
            fz0 = min(p["z0"] for p in vis); fz1 = max(p["z1"] for p in vis)
            frame3 = (fx0, fy0, fx1, fy1, fz0, fz1)
        else:
            frame3 = (0.0, 0.0, W, D, 0.0, H)
        fu0, fv0, fu1, fv1 = _proj_bbox(frame3, eye, target)
        hu0, hv0, hu1, hv1 = _proj_bbox(hero["bbox"], eye, target)
        farea = max((fu1 - fu0) * (fv1 - fv0), EPS)
        cov = ((hu1 - hu0) * (hv1 - hv0)) / farea
        hcx = (hu0 + hu1) / 2
        hcy = (hv0 + hv1) / 2
        cen_x = (hcx - fu0) / max(fu1 - fu0, EPS)
        cen_y = (hcy - fv0) / max(fv1 - fv0, EPS)
        min_cov = cam.get("min_hero_coverage", 0.10)
        metrics["hero_coverage"] = round(cov, 3)
        metrics["hero_frame_pos"] = [round(cen_x, 2), round(cen_y, 2)]
        checks["camera_enquadra"] = (cov >= min_cov
                                     and 0.15 <= cen_x <= 0.85 and 0.15 <= cen_y <= 0.85)
        if not checks["camera_enquadra"]:
            why.append(f"camera nao enquadra hero (cov={cov:.2f}<{min_cov} ou pos {cen_x:.2f},{cen_y:.2f})")
    else:
        checks["camera_enquadra"] = False
        why.append("sem camera/hero pra enquadrar")

    # SOFT
    if hero:
        fx, fy = hero["facing"]
        back = (D - hero["bbox"][3] if fy < 0 else hero["bbox"][1] if fy > 0
                else W - hero["bbox"][2] if fx < 0 else hero["bbox"][0])
        metrics["hero_back_gap_m"] = round(back, 3)
        checks["hero_ancorado"] = back <= ANCHOR_MAX_M
        if not checks["hero_ancorado"]:
            why.append(f"hero flutuando: costas a {back:.2f}m da parede")
    else:
        checks["hero_ancorado"] = False

    gaps_ok = True
    for t in ("side_table", "floor_lamp"):
        p = next((q for q in pls if q["type"] == t), None)
        if p and hero:
            ox = _olap1d(p["bbox"][0], p["bbox"][2], hero["bbox"][0], hero["bbox"][2])
            oy = _olap1d(p["bbox"][1], p["bbox"][3], hero["bbox"][1], hero["bbox"][3])
            if ox > 0 and oy > 0:
                gaps_ok = False
                why.append(f"{t} grudado/sobreposto ao hero")
    checks["respiro_lateral"] = gaps_ok

    acc = next((p for p in pls if p["type"] == "accent_seat"), None)
    if acc and hero:
        ax, ay = acc["facing"]
        rotated = min(abs(ax), abs(ay)) > 0.05      # nao paralelo aos eixos
        dx = hero["center"][0] - acc["center"][0]
        dy = hero["center"][1] - acc["center"][1]
        n = math.hypot(dx, dy) or 1.0
        dot = ax * dx / n + ay * dy / n
        metrics["accent_facing_dot"] = round(dot, 3)
        checks["accent_em_dialogo"] = rotated and dot >= 0.90
        if not checks["accent_em_dialogo"]:
            why.append(f"accent_seat sem dialogo: rotacionado={rotated} dot={dot:.2f}")
    else:
        checks["accent_em_dialogo"] = acc is None

    plant = next((p for p in pls if p["type"] == "plant_placeholder"), None)
    if plant and wins:
        win = wins[0]
        face = _wall_face(room, win["wall"])
        horiz = win["wall"] in ("north", "south")
        dist_wall = (min(abs(plant["bbox"][1] - face), abs(plant["bbox"][3] - face)) if horiz
                     else min(abs(plant["bbox"][0] - face), abs(plant["bbox"][2] - face)))
        w0 = win["center_along_m"] - win["width_m"] / 2
        w1 = win["center_along_m"] + win["width_m"] / 2
        p_along = (plant["bbox"][0], plant["bbox"][2]) if horiz else (plant["bbox"][1], plant["bbox"][3])
        d_along = max(w0 - p_along[1], p_along[0] - w1, 0.0)
        metrics["plant_wall_gap_m"] = round(dist_wall, 3)
        metrics["plant_window_along_gap_m"] = round(d_along, 3)
        checks["planta_perto_janela"] = dist_wall <= 0.35 and d_along <= 0.6
        if not checks["planta_perto_janela"]:
            why.append(f"planta longe da janela (parede {dist_wall:.2f}m, vao {d_along:.2f}m)")
    else:
        checks["planta_perto_janela"] = plant is None

    HARD = ("dentro_da_sala", "nao_flutua", "sem_colisao", "mesa_distancia",
            "tapete_maior_que_hero", "quadro_centralizado", "cortina_na_janela",
            "cortina_moldura", "equilibrio_quadrantes",
            "circulacao", "bbox_plausivel", "camera_enquadra")
    SOFT = ("hero_ancorado", "respiro_lateral", "planta_perto_janela", "accent_em_dialogo")
    if not all(checks[k] for k in HARD):
        result = "FAIL"
    elif all(checks[k] for k in SOFT):
        result = "PASS"
    else:
        result = "WARN"
    return {"result": result, "checks": checks, "why": why, "metrics": metrics,
            "hard": list(HARD), "soft": list(SOFT)}


# ------------------------------------------------------------------ sabotagens
def _sabotages(scene):
    """Cenas deliberadamente quebradas (a partir da boa) que o gate DEVE reprovar."""
    import copy

    def mut(name, expect, fn):
        s = copy.deepcopy(scene)
        fn(s)
        return name, expect, s

    def _mv(pl, dx=0.0, dy=0.0, dz=0.0):
        pl["bbox"] = [pl["bbox"][0] + dx, pl["bbox"][1] + dy, pl["bbox"][2] + dx,
                      pl["bbox"][3] + dy, pl["bbox"][4] + dz, pl["bbox"][5] + dz]
        pl["center"] = [pl["center"][0] + dx, pl["center"][1] + dy]

    def table_far(s):
        t = next(p for p in s["placements"] if p["type"] == "coffee_table")
        fy = _hero_of(s["placements"])["facing"][1]
        _mv(t, dy=fy * 0.5)

    def sofa_through_wall(s):
        _mv(_hero_of(s["placements"]), dy=0.6)

    def sofa_floating(s):
        _mv(_hero_of(s["placements"]), dz=0.3)

    def rug_small(s):
        r = _rug_of(s["placements"])
        r["bbox"][0] += 0.6
        r["bbox"][2] -= 0.6

    def art_off(s):
        a = next(p for p in s["placements"] if p["type"] == "wall_art")
        _mv(a, dx=0.4)

    def table_in_door(s):
        t = next(p for p in s["placements"] if p["type"] == "coffee_table")
        door = next(o for o in s["openings"] if o["type"] == "door")
        w, d = t["bbox"][2] - t["bbox"][0], t["bbox"][3] - t["bbox"][1]
        _mv(t, dx=door["center_along_m"] - (t["bbox"][0] + w / 2), dy=0.3 - (t["bbox"][1] + d / 2))

    def curtain_closed(s):
        c = next(p for p in s["placements"] if p["type"] == "curtain")
        sp = dict(c.get("spec") or {})
        sp["panel_split"] = 1
        c["spec"] = sp

    def accent_removed(s):
        s["placements"] = [p for p in s["placements"] if p["type"] != "accent_seat"]

    return [
        mut("mesa longe (0.9m)", "FAIL", table_far),
        mut("sofa atravessa parede", "FAIL", sofa_through_wall),
        mut("sofa flutuando", "FAIL", sofa_floating),
        mut("tapete menor que sofa", "FAIL", rug_small),
        mut("quadro descentralizado", "FAIL", art_off),
        mut("mesa na porta", "FAIL", table_in_door),
        mut("cortina fechada (protagonista)", "FAIL", curtain_closed),
        mut("sem accent_seat (sul vazio)", "FAIL", accent_removed),
    ]


if __name__ == "__main__":
    if len(sys.argv) > 1:
        d = Path(sys.argv[1])
        scene = json.loads((d / "scene.json").read_text("utf-8"))
        parts = json.loads((d / "scene_parts.json").read_text("utf-8")) \
            if (d / "scene_parts.json").exists() else None
        r = scene_spatial_gate(scene, parts)
        (d / "spatial_gate_report.json").write_text(
            json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"=== SceneSpatialGate {scene['scene_id']} -> {r['result']} ===")
        for k, v in r["checks"].items():
            print(f"  {'OK ' if v else 'XXX'} {k}")
        if r["why"]:
            print("  porque:", "; ".join(r["why"]))
        print("  metrics:", json.dumps(r["metrics"], ensure_ascii=False))
        sys.exit(0 if r["result"] == "PASS" else (2 if r["result"] == "WARN" else 1))

    # modo fixture: compoe a cena canonica + prova as sabotagens
    from interior.composer.scene_composer import compose_scene
    intent = json.loads((ROOT / "fixtures/scene_intents/living_room_modern_warm_minimal.json")
                        .read_text("utf-8"))
    scene = compose_scene(intent)
    good = scene_spatial_gate(scene, scene["parts"])
    print(f"=== SceneSpatialGate fixtures ===")
    ok = good["result"] == "PASS"
    print(f"  {'OK ' if ok else 'XXX'} cena canonica -> {good['result']} "
          f"(cov={good['metrics'].get('hero_coverage')})")
    if good["why"]:
        print("        porque:", "; ".join(good["why"]))
    for name, expect, s in _sabotages(scene):
        r = scene_spatial_gate(s, None)
        hit = r["result"] == expect
        ok = ok and hit
        mark = "[ok]" if hit else f"[X ESPERAVA {expect}]"
        print(f"  {'XXX' if r['result'] == 'FAIL' else 'OK '} {name:26} -> {r['result']:4} {mark}")
    print("TODOS OK" if ok else "FALHOU: gate nao bate com o esperado")
    sys.exit(0 if ok else 1)
