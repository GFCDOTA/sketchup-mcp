"""auto_camera.py — CAMERA AUTO por cômodo (fix SISTEMICO de enquadramento).

Deriva eye/target/fov das bounds REAIS do cômodo + móveis (não coords hardcoded → nunca fica
stale quando o .skp é regenerado). Escolhe um ponto de vista eye-level com SIGHTLINE LIMPA pro
móvel-HEROI (cama / sofá), SEM oclusão de móvel grande (guarda-roupa/dresser) no primeiro plano,
e com a janela no campo (luz ao fundo). Conserta os 3 cômodos de uma vez — análogo ao fix
root-cause do piso (apartment-wide, não band-aid por cômodo).

Saída: VRAY_EYE / VRAY_TARGET / VRAY_FOV (p/ render_room.ps1) + CROP sugerido.
Uso: python tools/auto_camera.py <room_id> [eye_z]
"""
from __future__ import annotations

import json
import math
import sys

sys.path.insert(0, ".")
from shapely.geometry import LineString, Point, Polygon  # noqa: E402
from shapely.geometry import box as shp_box  # noqa: E402

from tools.furnish_apartment import BRAINS, CONSENSUS, classify_rooms  # noqa: E402
from tools.spatial_model import build_spatial_model  # noqa: E402

PT_TO_IN = (0.19 / 5.4) * 39.3700787402
# movel-HEROI por tipo de comodo (o que a camera deve enquadrar)
HERO = {"BEDROOM": ("estrado", "colchao", "headboard"), "LIVING": ("base", "seat_cushion", "arm"),
        "KITCHEN": ("bancada", "ilha"), "BATHROOM": ("bancada_banho", "box")}
# moveis GRANDES que NAO podem ficar entre a camera e o heroi (oclusao)
OCCLUDER = ("corpo", "dresser", "torre", "aereo", "porta", "rack_tv")


def _bbox(boxes, kinds):
    xs, ys = [], []
    for b in boxes:
        if b["kind"] in kinds:
            for c in b["corners"]:
                xs.append(c[0]); ys.append(c[1])
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def _fbox(b):
    xs = [c[0] for c in b["corners"]]; ys = [c[1] for c in b["corners"]]
    return shp_box(min(xs), min(ys), max(xs), max(ys))


def auto_camera(con, room_id, eye_z=60.0):
    rooms = {x["id"]: x for x in classify_rooms(con)}
    r = rooms[room_id]
    boxes, _ = BRAINS[r["room_type"]](con, room_id)
    hero = _bbox(boxes, HERO.get(r["room_type"], ())) or _bbox(boxes, tuple({b["kind"] for b in boxes}))
    # mira o CENTRO DO CLUSTER de estar/dormir (heroi + apoios), nao so o heroi — senao o angulo fica
    # torto e o movel de apoio (rack/mesa) cai na lateral. Exclui guarda-roupa/dresser (occluder).
    look_kinds = tuple(HERO.get(r["room_type"], ())) + ("mesa_centro", "tapete", "rug", "rack_tv",
                                                         "criado", "nightstand", "travesseiro", "manta")
    look = _bbox(boxes, look_kinds) or hero
    hx, hy = (look[0] + look[2]) / 2, (look[1] + look[3]) / 2
    occ = [_fbox(b) for b in boxes if b["kind"] in OCCLUDER]
    furn = [_fbox(b) for b in boxes]

    cell = build_spatial_model(con, room_id)["_geom"]["cell"]
    poly = Polygon([(x * PT_TO_IN, y * PT_TO_IN) for x, y in cell.exterior.coords])
    bx0, by0, bx1, by1 = [v * PT_TO_IN for v in cell.bounds]

    wins = []
    for o in con.get("openings", []):
        if (o.get("type") or o.get("kind")) != "window":
            continue
        pos = o.get("position") or o.get("center")
        if not pos:
            continue
        wx, wy = pos[0] * PT_TO_IN, pos[1] * PT_TO_IN
        if bx0 - 20 <= wx <= bx1 + 20 and by0 - 20 <= wy <= by1 + 20:
            wins.append((wx, wy))

    # varre candidatos a EYE no piso aberto: dentro do poligono, >=10in da parede, fora de movel,
    # distancia 80-210in do heroi, com SIGHTLINE LIMPA (linha eye->heroi nao cruza occluder).
    best = None
    step = 7.0
    y = by0
    while y <= by1:
        x = bx0
        while x <= bx1:
            p = Point(x, y)
            if poly.contains(p) and poly.exterior.distance(p) >= 10 and not any(f.distance(p) < 3 for f in furn):
                d = math.hypot(hx - x, hy - y)
                if 80 <= d <= 210:
                    line = LineString([(x, y), (hx, hy)])
                    if not any(line.intersects(o) for o in occ):
                        score = -abs(d - 145)                       # distancia ~145in = enquadra o comodo
                        dh = (hx - x, hy - y); nh = math.hypot(*dh) or 1
                        for wx, wy in wins:                          # bonus: janela no campo de visao
                            dw = (wx - x, wy - y); nw = math.hypot(*dw) or 1
                            cos = (dh[0] * dw[0] + dh[1] * dw[1]) / (nh * nw)
                            if cos > 0.25:
                                score += cos * 45
                        for o in occ:                                # penaliza occluder GRANDE no 1o plano DENTRO do campo
                            ocx, ocy = o.centroid.x, o.centroid.y
                            do = math.hypot(ocx - x, ocy - y)
                            if do < d:                               # mais perto que o heroi = primeiro plano
                                dvo = (ocx - x, ocy - y); nvo = math.hypot(*dvo) or 1
                                coso = (dh[0] * dvo[0] + dh[1] * dvo[1]) / (nh * nvo)
                                if coso > 0.72:                      # dentro de ~44deg do eixo de visao -> em quadro
                                    score -= (coso - 0.72) * 170 * (1 - do / d)
                        if best is None or score > best[0]:
                            best = (score, x, y, d)
            x += step
        y += step

    if best is None:                                                 # fallback: canto mais aberto, eye-level
        ex = (bx1 - 20) if abs(bx1 - hx) > abs(hx - bx0) else (bx0 + 20)
        ey = (by1 - 20) if abs(by1 - hy) > abs(hy - by0) else (by0 + 20)
        best = (0, ex, ey, math.hypot(hx - ex, hy - ey))

    _, ex, ey, d = best
    hw = max(hero[2] - hero[0], hero[3] - hero[1])
    fov = max(52.0, min(66.0, math.degrees(2 * math.atan((hw * 0.85) / max(d, 1))) + 10))
    # AUTO-CROP rule (GPT NEXT_ACTION validado): a camera eye-level deixa foreground morto embaixo +
    # teto/shell aberto em cima. Crop p/ o cluster ocupar o quadro: ~28% baixo (piso vazio) + ~11% topo.
    # Razoes p/ um render de altura H (px = round(ratio*H)). Aplicar com tools/crop_render.py.
    crop = {"top_ratio": 0.11, "bottom_ratio": 0.28}
    return {"room": room_id, "type": r["room_type"], "eye": (round(ex, 1), round(ey, 1), round(eye_z, 1)),
            "target": (round(hx, 1), round(hy, 1), 36.0), "fov": round(fov, 1), "crop": crop,
            "dist": round(d), "n_occluders": len(occ)}


if __name__ == "__main__":
    rid = sys.argv[1] if len(sys.argv) > 1 else "r002"
    ez = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
    con = json.loads(CONSENSUS.read_text("utf-8"))
    cam = auto_camera(con, rid, ez)
    e = cam["eye"]; t = cam["target"]
    print(f"ROOM {cam['room']} ({cam['type']}) dist={cam['dist']}in occluders={cam['n_occluders']}")
    print(f"VRAY_EYE={e[0]},{e[1]},{e[2]}")
    print(f"VRAY_TARGET={t[0]},{t[1]},{t[2]}")
    print(f"VRAY_FOV={cam['fov']}")
    h = 1000
    print(f"CROP_TOP={round(cam['crop']['top_ratio'] * h)} CROP_BOTTOM={round(cam['crop']['bottom_ratio'] * h)}  (render H={h})")
