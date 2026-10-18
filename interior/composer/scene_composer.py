"""scene_composer.py — Intent-to-Scene slice 1: COMPILADOR de SceneIntentSpec em cena
3D procedural. O GPT (diretor de arte) emite o intent JSON (interior/schemas/
scene_intent.schema.json); este modulo valida, resolve StylePack + generators
procedurais (tools/sofa_builder, tools/decor_builders), POSICIONA por regra de
composicao (nao "joga movel") e emite a cena em parts world-space (metros) +
scene_report.json com posicoes/distancias.

Convencao da cena (sintetica — a intencao E' a fonte de verdade, distinto do track
PDF onde a consensus manda): metros, origem no canto SW do piso, X=leste, Y=norte.
Paredes: south y=0, north y=depth, west x=0, east x=width. Mobiliario local tem
frente=-Y; WALL_THETA gira a frente pro interior. Rotacoes restritas a 0/90/180/270
(exatas; verts8 acompanha). Deterministico, sem SU.

Uso: python -m interior.composer.scene_composer fixtures/scene_intents/<id>.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.decor_builders import BUILDERS as DECOR_BUILDERS          # noqa: E402
from tools.furniture_anatomy_spec import sofa_spec                   # noqa: E402
from tools.sofa_builder import build_sofa                            # noqa: E402
from tools.sofa_class import PREMIUM_LIVING_UPHOLSTERY               # noqa: E402

STYLE_DIR = ROOT / "interior" / "style_packs"

FURNITURE_TYPES = ("sofa", "rug", "coffee_table", "side_table", "floor_lamp",
                   "wall_art", "curtain", "plant_placeholder", "accent_seat")
ROLES = ("hero", "anchor", "companion", "textile", "light", "decor")
WALLS = ("north", "south", "east", "west")
PLACEMENT_HINTS = ("main_wall", "centered_under_hero", "front_of_hero", "beside_hero",
                   "near_window", "on_window", "above_hero", "corner", "opposite_hero")

# rotacao (graus CCW) pra frente local (-Y) apontar pro INTERIOR a partir da parede
WALL_THETA = {"north": 0, "south": 180, "east": 270, "west": 90}
# normal interior de cada parede
WALL_INWARD = {"north": (0.0, -1.0), "south": (0.0, 1.0),
               "east": (-1.0, 0.0), "west": (1.0, 0.0)}

WALL_T = 0.12          # espessura de parede (fora do interior)
FLOOR_T = 0.04
HERO_BACK_GAP = 0.05   # costas do hero ate a parede
TABLE_GAP = 0.40       # mesa de centro: alvo dentro de [0.35, 0.45]
RUG_TUCK = 0.15        # tapete entra esse tanto sob a frente do hero
ART_GAP = 0.25         # respiro entre topo do hero e base do quadro
SIDE_GAP = 0.05        # folga minima entre pecas vizinhas
OPPOSITE_GAP = 1.50    # frente do hero -> frente do accent_seat (conversa)
ACCENT_LATERAL = 0.55  # accent_seat desloca pro lado OPOSTO 'a janela (equilibrio)
ACCENT_TURN_DEG = 12   # cycle 003: poltrona gira de volta pro eixo do hero/mesa
                       # ("conversa de estar", nao "objeto colocado" paralelo)
CURTAIN_FRAME_OVER = 0.40   # paineis-moldura: transbordo da cortina por lado da janela
CURTAIN_SLIM_T = 0.025      # cycle 003: paineis abertos mais magros na profundidade
CURTAIN_SLIM_AMP = 0.04     # (na vista SU viravam barras fortes de primeiro plano)

# defaults de dims (W, D, H em m) quando o intent traz so size_hint
SIZE_HINTS = {
    "rug": {"small": (2.0, 1.4, 0.012), "medium": (2.4, 1.7, 0.012), "large": (3.0, 2.0, 0.012)},
    "coffee_table": {"small": (0.8, 0.5, 0.34), "medium": (1.1, 0.6, 0.36), "large": (1.3, 0.7, 0.36)},
    "side_table": {"small": (0.4, 0.4, 0.5), "medium": (0.45, 0.45, 0.55), "large": (0.55, 0.55, 0.6)},
    "floor_lamp": {"small": (0.35, 0.35, 1.45), "medium": (0.42, 0.42, 1.65), "large": (0.5, 0.5, 1.8)},
    "wall_art": {"small": (0.9, 0.05, 0.7), "medium": (1.2, 0.06, 0.85), "large": (1.4, 0.06, 0.95)},
    "plant_placeholder": {"small": (0.4, 0.4, 1.0), "medium": (0.55, 0.55, 1.5), "large": (0.7, 0.7, 1.8)},
    "sofa": {"small": (1.8, 0.9, 0.8), "medium": (2.2, 0.95, 0.85), "large": (2.8, 1.0, 0.85)},
    "accent_seat": {"small": (0.6, 0.65, 0.65), "medium": (0.75, 0.8, 0.72), "large": (0.9, 0.9, 0.78)},
}


# ------------------------------------------------------------------ validacao
def validate_furniture_intent(fi):
    """Validacao executavel do furniture_intent.schema.json. Devolve lista de erros."""
    errs = []
    if not isinstance(fi, dict):
        return ["furniture_intent nao e' objeto"]
    t = fi.get("type")
    if t not in FURNITURE_TYPES:
        errs.append(f"type invalido: {t!r}")
    if fi.get("role") not in ROLES:
        errs.append(f"role invalido: {fi.get('role')!r} (type {t})")
    p = fi.get("priority")
    if not (isinstance(p, int) and p >= 1):
        errs.append(f"priority deve ser int >= 1 (type {t})")
    d = fi.get("dimensions_m")
    if d is not None:
        if not isinstance(d, dict):
            errs.append(f"dimensions_m deve ser objeto (type {t})")
        else:
            for k, v in d.items():
                if k not in ("width", "depth", "height"):
                    errs.append(f"dimensions_m.{k} desconhecido (type {t})")
                elif not (isinstance(v, (int, float)) and v > 0):
                    errs.append(f"dimensions_m.{k} deve ser > 0 (type {t})")
    if d is None and fi.get("size_hint") not in (None, "small", "medium", "large"):
        errs.append(f"size_hint invalido: {fi.get('size_hint')!r} (type {t})")
    h = fi.get("placement_hint")
    if h is not None and h not in PLACEMENT_HINTS:
        errs.append(f"placement_hint invalido: {h!r} (type {t})")
    return errs


def validate_scene_intent(intent):
    """Validacao executavel do scene_intent.schema.json. Devolve lista de erros."""
    errs = []
    for k in ("scene_type", "style_id", "room_dimensions", "hero_piece",
              "furniture_intents", "composition_rules", "camera_goal", "render_goal"):
        if k not in intent:
            errs.append(f"campo obrigatorio ausente: {k}")
    rd = intent.get("room_dimensions") or {}
    for k, lo in (("width_m", 2.0), ("depth_m", 2.0), ("height_m", 2.2)):
        v = rd.get(k)
        if not (isinstance(v, (int, float)) and v >= lo):
            errs.append(f"room_dimensions.{k} deve ser numero >= {lo}")
    if rd.get("main_wall", "north") not in WALLS:
        errs.append(f"main_wall invalido: {rd.get('main_wall')!r}")
    for o in intent.get("openings", []):
        if o.get("wall") not in WALLS:
            errs.append(f"opening {o.get('id')}: wall invalido")
        if o.get("type") not in ("window", "door", "glass_door"):
            errs.append(f"opening {o.get('id')}: type invalido")
        L = rd.get("width_m", 0) if o.get("wall") in ("north", "south") else rd.get("depth_m", 0)
        c, w = o.get("center_along_m", 0), o.get("width_m", 0)
        if not (w > 0 and c - w / 2 >= -1e-9 and c + w / 2 <= L + 1e-9):
            errs.append(f"opening {o.get('id')}: nao cabe na parede ({c}+-{w / 2} em L={L})")
    fis = intent.get("furniture_intents") or []
    if not fis:
        errs.append("furniture_intents vazio")
    for fi in fis:
        errs.extend(validate_furniture_intent(fi))
    hero = intent.get("hero_piece")
    heroes = [fi for fi in fis if fi.get("type") == hero]
    if hero and not heroes:
        errs.append(f"hero_piece {hero!r} nao esta em furniture_intents")
    if hero and heroes and heroes[0].get("role") != "hero":
        errs.append(f"furniture_intent do hero_piece {hero!r} deve ter role=hero")
    cam = intent.get("camera_goal") or {}
    if cam.get("kind") not in ("three_quarter_human", "top", "front"):
        errs.append(f"camera_goal.kind invalido: {cam.get('kind')!r}")
    rg = intent.get("render_goal") or {}
    if not rg.get("views"):
        errs.append("render_goal.views vazio")
    if not (intent.get("composition_rules") or []):
        errs.append("composition_rules vazio")
    return errs


def load_style_pack(style_id):
    p = STYLE_DIR / f"{style_id}.json"
    assert p.exists(), f"StylePack nao encontrado: {p}"
    return json.loads(p.read_text("utf-8"))


def _rgb(style, role, default=(150, 150, 150)):
    m = (style.get("materials") or {}).get(role)
    return tuple(m["rgb"]) if m else tuple(default)


# ------------------------------------------------------------------ geometria
def _rot_pt(x, y, theta):
    """Rotacao CCW em graus. Multiplos de 90 sao EXATOS (sem float drift);
    qualquer outro angulo usa cos/sin (rotacao LIVRE — cycle 003)."""
    t = float(theta) % 360.0
    if t == 0.0:
        return x, y
    if t == 90.0:
        return -y, x
    if t == 180.0:
        return -x, -y
    if t == 270.0:
        return y, -x
    c, s = math.cos(math.radians(t)), math.sin(math.radians(t))
    return x * c - y * s, x * s + y * c


def _box_verts8(p):
    """verts8 sintetico de uma part-caixa: 4 de baixo CCW + 4 de cima (mesma
    convencao dos builders, ex. cupula da floor_lamp)."""
    return [(p["x0"], p["y0"], p["z0"]), (p["x1"], p["y0"], p["z0"]),
            (p["x1"], p["y1"], p["z0"]), (p["x0"], p["y1"], p["z0"]),
            (p["x0"], p["y0"], p["z1"]), (p["x1"], p["y0"], p["z1"]),
            (p["x1"], p["y1"], p["z1"]), (p["x0"], p["y1"], p["z1"])]


def place_parts(parts, theta, world_center, z_off=0.0):
    """Gira as parts (locais, m) em theta em torno do centro do bbox local e
    translada o centro pra world_center (x,y). Devolve parts world-space.
    Multiplos de 90: caixas continuam caixas (axis-aligned exato). Outros
    angulos (rotacao LIVRE): TODA part vira verts8 (footprint real girado pro
    render mpl e pro caminho SU via corners); x0..y1 = AABB dos verts —
    o gate opera nesse AABB (conservador por design)."""
    xs = [p["x0"] for p in parts] + [p["x1"] for p in parts]
    ys = [p["y0"] for p in parts] + [p["y1"] for p in parts]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    wx, wy = world_center
    exact = (float(theta) % 90.0) == 0.0
    out = []
    for p in parts:
        q = dict(p)
        if exact:
            corners = [_rot_pt(x - cx, y - cy, theta)
                       for x, y in ((p["x0"], p["y0"]), (p["x1"], p["y1"]))]
            nx = [c[0] + wx for c in corners]
            ny = [c[1] + wy for c in corners]
            q["x0"], q["x1"] = round(min(nx), 4), round(max(nx), 4)
            q["y0"], q["y1"] = round(min(ny), 4), round(max(ny), 4)
            q["z0"], q["z1"] = round(p["z0"] + z_off, 4), round(p["z1"] + z_off, 4)
            if p.get("verts8"):
                v8 = []
                for vx, vy, vz in p["verts8"]:
                    rx, ry = _rot_pt(vx - cx, vy - cy, theta)
                    v8.append((round(rx + wx, 4), round(ry + wy, 4), round(vz + z_off, 4)))
                q["verts8"] = v8
        else:
            v8 = []
            for vx, vy, vz in (p.get("verts8") or _box_verts8(p)):
                rx, ry = _rot_pt(vx - cx, vy - cy, theta)
                v8.append((round(rx + wx, 4), round(ry + wy, 4), round(vz + z_off, 4)))
            q["verts8"] = v8
            q["x0"] = round(min(v[0] for v in v8), 4)
            q["x1"] = round(max(v[0] for v in v8), 4)
            q["y0"] = round(min(v[1] for v in v8), 4)
            q["y1"] = round(max(v[1] for v in v8), 4)
            q["z0"] = round(min(v[2] for v in v8), 4)
            q["z1"] = round(max(v[2] for v in v8), 4)
        out.append(q)
    return out


def _bbox(parts):
    xs = [p["x0"] for p in parts] + [p["x1"] for p in parts]
    ys = [p["y0"] for p in parts] + [p["y1"] for p in parts]
    zs = [p["z0"] for p in parts] + [p["z1"] for p in parts]
    return [round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4),
            round(min(zs), 4), round(max(zs), 4)]


def _wall_face_point(room, wall, along):
    """Ponto (x,y) na FACE interior da parede, na posicao 'along' (da ponta de menor
    coordenada)."""
    W, D = room["width_m"], room["depth_m"]
    return {"north": (along, D), "south": (along, 0.0),
            "east": (W, along), "west": (0.0, along)}[wall]


def _wall_len(room, wall):
    return room["width_m"] if wall in ("north", "south") else room["depth_m"]


# ------------------------------------------------------------------ room shell
def _shell_box(label, x0, y0, x1, y1, z0, z1, rgb):
    kind = ("wall" if label.startswith("wall")
            else "ceiling" if label == "ceiling" else "floor")
    return {"label": label, "kind": kind,
            "x0": round(x0, 4), "y0": round(y0, 4), "x1": round(x1, 4), "y1": round(y1, 4),
            "z0": round(z0, 4), "z1": round(z1, 4), "rgb": list(rgb)}


def build_room_shell(room, openings, style):
    """Piso + 4 paredes (espessura WALL_T pra FORA do interior) com vaos reais
    (janela preserva peitoril+verga; porta vai ao chao — espelha a Hard Rule #2)
    + TETO (fase V-Ray: sem teto a luz de ceu lava o interior; os renders
    mpl/SU/gate escondem o ceiling junto com as hide_walls)."""
    W, D, H = room["width_m"], room["depth_m"], room["height_m"]
    wall_rgb = _rgb(style, "wall")
    floor_rgb = _rgb(style, "floor")
    ceil_rgb = _rgb(style, "ceiling", (242, 240, 234))
    parts = [_shell_box("floor", 0.0, 0.0, W, D, -FLOOR_T, 0.0, floor_rgb),
             _shell_box("ceiling", -WALL_T, -WALL_T, W + WALL_T, D + WALL_T,
                        H, H + FLOOR_T, ceil_rgb)]
    spans = {"north": (0.0, W), "south": (0.0, W), "east": (0.0, D), "west": (0.0, D)}
    rects = {  # (x0,y0,x1,y1) da parede por nome
        "south": (0.0 - WALL_T, -WALL_T, W + WALL_T, 0.0),
        "north": (0.0 - WALL_T, D, W + WALL_T, D + WALL_T),
        "west": (-WALL_T, 0.0, 0.0, D),
        "east": (W, 0.0, W + WALL_T, D),
    }
    by_wall = {w: [] for w in WALLS}
    for o in openings or []:
        by_wall[o["wall"]].append(o)
    for wall in WALLS:
        x0, y0, x1, y1 = rects[wall]
        horiz = wall in ("north", "south")
        lo, hi = spans[wall]
        segs = []          # trechos cheios (full height) ao longo da parede
        cur = lo
        for o in sorted(by_wall[wall], key=lambda o: o["center_along_m"]):
            a0 = o["center_along_m"] - o["width_m"] / 2.0
            a1 = o["center_along_m"] + o["width_m"] / 2.0
            if a0 > cur:
                segs.append((cur, a0, 0.0, H))
            sill = o.get("sill_m", 0.9 if o["type"] == "window" else 0.0)
            head = o.get("head_m", 2.1)
            if sill > 0:
                segs.append((a0, a1, 0.0, sill))      # peitoril preservado
            if head < H:
                segs.append((a0, a1, head, H))        # verga
            cur = a1
        if cur < hi:
            segs.append((cur, hi, 0.0, H))
        for i, (a0, a1, z0, z1) in enumerate(segs):
            if horiz:
                parts.append(_shell_box(f"wall_{wall}_{i + 1}", a0, y0, a1, y1, z0, z1, wall_rgb))
            else:
                parts.append(_shell_box(f"wall_{wall}_{i + 1}", x0, a0, x1, a1, z0, z1, wall_rgb))
    return parts


# ------------------------------------------------------------------ furniture
def _dims(fi):
    d = fi.get("dimensions_m")
    if d:
        return d.get("width"), d.get("depth"), d.get("height")
    hint = fi.get("size_hint", "medium")
    t = SIZE_HINTS.get(fi["type"])
    if t:
        w, dd, h = t.get(hint, t["medium"])
        return w, dd, h
    return None, None, None


def _build_furniture(fi, style, scene_ctx):
    """Resolve um FurnitureIntentSpec num (parts locais, spec_dict). Cores vem do
    StylePack via material_style (fallback material_defaults)."""
    t = fi["type"]
    w, d, h = _dims(fi)
    if t == "sofa":
        ov = {}
        if w:
            ov["width"] = w
        if d:
            ov["depth"] = d
        if h:
            ov["height"] = h
        ov["fabric_rgb"] = _rgb(style, fi.get("material_style", "hero_fabric"))
        ov["feet_rgb"] = _rgb(style, "hero_feet", (20, 18, 16))
        spec = sofa_spec(fi.get("style_family_variant", "straight"), 3, **ov)
        # estofaria premium aprovada (fonte única PREMIUM_LIVING_UPHOLSTERY) — o sofá
        # de sala é premium em QUALQUER caminho de produção, o composer inclusive.
        # Sem isto a cena embarca o sofá velho (pés + almofada empilhada), bug 2026-07-12.
        for k, v in PREMIUM_LIVING_UPHOLSTERY.items():
            setattr(spec, k, v)
        parts, _meta = build_sofa(spec)
        return parts, spec.to_dict()

    cls, fn = DECOR_BUILDERS[t]
    spec = cls()
    if t == "rug":
        spec.width, spec.depth = w or spec.width, d or spec.depth
        spec.field_rgb = _rgb(style, fi.get("material_style", "rug"))
        spec.border_rgb = tuple(int(c * 0.92) for c in spec.field_rgb)
    elif t == "coffee_table":
        spec.width, spec.depth, spec.height = w or spec.width, d or spec.depth, h or spec.height
        spec.top_rgb = _rgb(style, fi.get("material_style", "table_top"))
        spec.leg_rgb = _rgb(style, "metal_accent")
    elif t == "side_table":
        spec.diameter, spec.height = w or spec.diameter, h or spec.height
        mt = _rgb(style, fi.get("material_style", "metal_accent"))
        spec.top_rgb = spec.stem_rgb = spec.base_rgb = mt
    elif t == "floor_lamp":
        spec.height = h or spec.height
        if w:
            spec.shade_d = w
            spec.shade_top_d = min(spec.shade_top_d, w * 0.8)
        spec.stem_rgb = spec.base_rgb = _rgb(style, fi.get("material_style", "metal_accent"))
        spec.shade_rgb = _rgb(style, "lamp_shade")
    elif t == "wall_art":
        spec.width, spec.height = w or spec.width, h or spec.height
        spec.depth = d or spec.depth
        spec.canvas_rgb = _rgb(style, fi.get("material_style", "art_canvas"))
        spec.frame_rgb = _rgb(style, "metal_accent")
        spec.accent_rgb = _rgb(style, "art_accent", spec.accent_rgb)
    elif t == "curtain":
        win = scene_ctx.get("window")
        assert win is not None, "curtain pede uma janela em openings"
        split = int(fi.get("panel_split", 1))
        if split == 2:
            # cortina-moldura: paineis recolhidos nas pontas, transbordando a janela
            # (recuo lateral = painel cobre pouco vidro; o vao central fica aberto);
            # magros em profundidade pra nao virarem barras de primeiro plano na 3/4 SU
            spec.width = (w or win["width_m"] + 2 * CURTAIN_FRAME_OVER)
            spec.panel_split = 2
            spec.panel_w = float(fi.get("panel_w", 0.55))
            spec.thickness = CURTAIN_SLIM_T
            spec.fold_amp = CURTAIN_SLIM_AMP
        else:
            spec.width = (w or win["width_m"] + 0.4)
        head = win.get("head_m", 2.1)
        spec.height = h or (head + 0.10)
        spec.panel_rgb = _rgb(style, fi.get("material_style", "curtain"))
        spec.rod_rgb = _rgb(style, "metal_accent")
    elif t == "plant_placeholder":
        spec.height = h or spec.height
        if w:
            spec.foliage_w = w
        spec.foliage_rgb = _rgb(style, fi.get("material_style", "plant_green"))
        spec.pot_rgb = _rgb(style, "plant_pot")
        spec.trunk_rgb = _rgb(style, "wood_accent", spec.trunk_rgb)
    elif t == "accent_seat":
        spec.width, spec.depth, spec.height = w or spec.width, d or spec.depth, h or spec.height
        spec.seat_rgb = _rgb(style, fi.get("material_style", "accent_fabric"), spec.seat_rgb)
        spec.leg_rgb = _rgb(style, "hero_feet", spec.leg_rgb)
    parts, _meta = fn(spec.validate())
    return parts, spec.to_dict()


# ------------------------------------------------------------------ composicao
def compose_scene(intent, style=None):
    """Compila o SceneIntentSpec numa cena world-space + report. Levanta ValueError
    se o intent for invalido."""
    errs = validate_scene_intent(intent)
    if errs:
        raise ValueError("SceneIntentSpec invalido: " + "; ".join(errs))
    style = style or load_style_pack(intent["style_id"])
    room = dict(intent["room_dimensions"])
    room.setdefault("main_wall", "north")
    openings = intent.get("openings", [])
    main_wall = room["main_wall"]
    theta = WALL_THETA[main_wall]
    fwd = WALL_INWARD[main_wall]                      # frente do hero (pro interior)
    along_axis = (_rot_pt(1, 0, theta))               # eixo da largura do hero no mundo

    windows = [o for o in openings if o["type"] == "window"]
    ctx = {"window": windows[0] if windows else None,
           "openings": openings}

    shell = build_room_shell(room, openings, style)
    scene_parts = list(shell)
    placements = []
    report = {"scene_id": intent.get("scene_id", "scene"), "style_id": intent["style_id"],
              "main_wall": main_wall, "placements": [], "distances": {}, "notes": []}

    fis = sorted(intent["furniture_intents"], key=lambda f: f["priority"])
    hero_t = intent["hero_piece"]
    hero = None          # placement do hero (dict)
    rug_pl = None
    beside_used = []     # lados ja ocupados (+1 = along positivo, -1 = negativo)

    def _emit(fi, parts_local, spec_dict, th, center, z_off=0.0, anchor=None):
        wp = place_parts(parts_local, th, center, z_off)
        bb = _bbox(wp)
        fx, fy = (round(v, 4) for v in _rot_pt(0, -1, th))
        pl = {"type": fi["type"], "role": fi["role"], "label": fi["type"],
              "style_family": fi.get("style_family"), "material_style": fi.get("material_style"),
              "rotation_deg": th, "center": [round(center[0], 4), round(center[1], 4)],
              "facing": [fx, fy], "bbox": bb, "z_off": round(z_off, 4),
              "n_parts": len(wp), "anchor": anchor, "spec": spec_dict}
        for p in wp:
            p["item"] = fi["type"]
        scene_parts.extend(wp)
        placements.append(pl)
        report["placements"].append({k: pl[k] for k in
                                     ("type", "role", "rotation_deg", "center", "facing",
                                      "bbox", "z_off", "anchor")})
        return pl

    for fi in fis:
        t = fi["type"]
        parts_local, spec_dict = _build_furniture(fi, style, ctx)
        lw = max(p["x1"] for p in parts_local) - min(p["x0"] for p in parts_local)
        ld = max(p["y1"] for p in parts_local) - min(p["y0"] for p in parts_local)
        hint = fi.get("placement_hint") or ("main_wall" if fi["role"] == "hero" else None)

        if hint == "main_wall":
            face = _wall_face_point(room, main_wall, _wall_len(room, main_wall) / 2.0)
            c = (face[0] + fwd[0] * (HERO_BACK_GAP + ld / 2.0),
                 face[1] + fwd[1] * (HERO_BACK_GAP + ld / 2.0))
            pl = _emit(fi, parts_local, spec_dict, theta, c, anchor=f"parede {main_wall}")
            if t == hero_t:
                hero = pl

        elif hint == "centered_under_hero":
            assert hero, "centered_under_hero requer hero ja posicionado"
            hx, hy = hero["center"]
            hd = _depth_of(hero)
            front = (hx + fwd[0] * hd / 2.0, hy + fwd[1] * hd / 2.0)
            c = (front[0] + fwd[0] * (ld / 2.0 - RUG_TUCK),
                 front[1] + fwd[1] * (ld / 2.0 - RUG_TUCK))
            pl = _emit(fi, parts_local, spec_dict, theta, c,
                       anchor=f"centralizado com hero, tuck {RUG_TUCK}m sob a frente")
            if t == "rug":
                rug_pl = pl

        elif hint == "front_of_hero":
            assert hero, "front_of_hero requer hero ja posicionado"
            hx, hy = hero["center"]
            hd = _depth_of(hero)
            gap = TABLE_GAP
            c = (hx + fwd[0] * (hd / 2.0 + gap + ld / 2.0),
                 hy + fwd[1] * (hd / 2.0 + gap + ld / 2.0))
            z = _rug_lift(rug_pl, c, lw, ld)
            _emit(fi, parts_local, spec_dict, theta, c, z_off=z,
                  anchor=f"{gap}m da frente do hero")

        elif hint == "beside_hero":
            assert hero, "beside_hero requer hero ja posicionado"
            side = 1 if 1 not in beside_used else -1
            beside_used.append(side)
            hx, hy = hero["center"]
            ref = rug_pl or hero
            edge = _along_extent(ref, along_axis)      # meia-largura do conjunto
            off = edge + SIDE_GAP + lw / 2.0
            c = (hx + along_axis[0] * off * side, hy + along_axis[1] * off * side)
            _emit(fi, parts_local, spec_dict, theta, c,
                  anchor=f"lado {'+' if side > 0 else '-'} do hero, fora do tapete")

        elif hint == "above_hero":
            assert hero, "above_hero requer hero ja posicionado"
            hx, hy = hero["center"]
            hero_h = hero["bbox"][5]
            face = _wall_face_point(room, main_wall, 0)
            # plano do quadro encostado na face interior da parede principal
            c = (hx * abs(along_axis[0]) + face[0] * abs(fwd[0]) + fwd[0] * ld / 2.0,
                 hy * abs(along_axis[1]) + face[1] * abs(fwd[1]) + fwd[1] * ld / 2.0)
            _emit(fi, parts_local, spec_dict, theta, c, z_off=hero_h + ART_GAP,
                  anchor=f"acima do hero, respiro {ART_GAP}m")

        elif hint == "on_window":
            win = ctx["window"]
            assert win is not None, "on_window requer janela em openings"
            wwall = win["wall"]
            wth = WALL_THETA[wwall]
            wfwd = WALL_INWARD[wwall]
            face = _wall_face_point(room, wwall, win["center_along_m"])
            c = (face[0] + wfwd[0] * (0.02 + ld / 2.0),
                 face[1] + wfwd[1] * (0.02 + ld / 2.0))
            _emit(fi, parts_local, spec_dict, wth, c, z_off=0.05,
                  anchor=f"janela {win['id']} ({wwall})")

        elif hint == "near_window":
            win = ctx["window"]
            assert win is not None, "near_window requer janela em openings"
            wwall = win["wall"]
            wfwd = WALL_INWARD[wwall]
            walong = _rot_pt(1, 0, WALL_THETA[wwall])
            # window_side opcional no intent: 'plus' poe a peca do outro lado
            # do vao (util pra equilibrar massa por quadrante); default 'minus'
            # preserva o comportamento legado.
            if fi.get("window_side") == "plus":
                a = win["center_along_m"] + win["width_m"] / 2.0 + 0.15 + lw / 2.0
            else:
                a = win["center_along_m"] - win["width_m"] / 2.0 - 0.15 - lw / 2.0
            face = _wall_face_point(room, wwall, a)
            inset = 0.20 + ld / 2.0          # na frente da cortina, encostado na parede
            c = (face[0] + wfwd[0] * inset, face[1] + wfwd[1] * inset)
            _emit(fi, parts_local, spec_dict, WALL_THETA[wwall], c,
                  anchor=f"ao lado da janela {win['id']}, {abs(walong[0]) and 'x' or 'y'}={a:.2f}")

        elif hint == "opposite_hero":
            # contrapeso do hero (cycle 002): assento leve do lado oposto da zona de
            # estar, ENCARANDO o hero, deslocado pro lado contrario ao da janela —
            # quebra o vazio da metade oposta sem competir com o hero.
            assert hero, "opposite_hero requer hero ja posicionado"
            hx, hy = hero["center"]
            hd = _depth_of(hero)
            adv = hd / 2.0 + OPPOSITE_GAP + ld / 2.0
            c = [hx + fwd[0] * adv, hy + fwd[1] * adv]
            win = ctx["window"]
            turn = 0.0
            side = 0.0
            if win is not None:
                wn = WALL_INWARD[win["wall"]]
                s = wn[0] * along_axis[0] + wn[1] * along_axis[1]
                if s != 0:           # janela num dos lados do eixo -> afasta dela
                    side = 1.0 if s > 0 else -1.0
            if side == 0.0:
                # Janela na parede que o accent ENCARA (ou sem janela): sem
                # lateral a evitar, mas conversa de estar continua exigindo o
                # giro (gate accent_em_dialogo reprova poltrona paralela —
                # "objeto paralelo", cycle 003). Desloca pro lado oposto 'a
                # porta no eixo (se houver) e gira de volta pro hero.
                door = next((o for o in (ctx.get("openings") or [])
                             if o.get("type") == "door"), None)
                side = 1.0
                if door is not None and door.get("wall") in WALL_INWARD:
                    dn = WALL_INWARD[door["wall"]]
                    sd = dn[0] * along_axis[0] + dn[1] * along_axis[1]
                    if sd != 0:
                        side = 1.0 if sd > 0 else -1.0
            c = [c[0] + along_axis[0] * ACCENT_LATERAL * side,
                 c[1] + along_axis[1] * ACCENT_LATERAL * side]
            # deslocou lateral -> gira de volta pro eixo do hero (conversa)
            turn = side * ACCENT_TURN_DEG
            th = (theta + 180 + turn) % 360
            z = _rug_lift(rug_pl, c, lw, ld)
            _emit(fi, parts_local, spec_dict, th, tuple(c), z_off=z,
                  anchor=f"oposto ao hero, {OPPOSITE_GAP}m de conversa, "
                         f"girado {abs(turn):g} graus pro eixo")

        elif hint == "corner":
            c = (room["width_m"] - lw / 2.0 - 0.15, room["depth_m"] - ld / 2.0 - 0.15)
            _emit(fi, parts_local, spec_dict, theta, c, anchor="canto NE")
        else:
            report["notes"].append(f"{t}: sem placement_hint resolvivel — pulado")

    _distances(report, placements, room, ctx)
    cam = _camera(intent.get("camera_goal", {}), room, placements, hero_t,
                  win_wall=(ctx["window"] or {}).get("wall"))
    scene = {"scene_id": report["scene_id"], "intent": intent, "style": style,
             "room": room, "openings": openings, "parts": scene_parts,
             "placements": placements, "camera": cam, "report": report}
    return scene


def _depth_of(pl):
    """Profundidade do item no eixo da frente (apos rotacao)."""
    x0, y0, x1, y1 = pl["bbox"][:4]
    return (y1 - y0) if pl["facing"][1] != 0 else (x1 - x0)


def _along_extent(pl, along_axis):
    x0, y0, x1, y1 = pl["bbox"][:4]
    return ((x1 - x0) if along_axis[0] != 0 else (y1 - y0)) / 2.0


def _rug_lift(rug_pl, center, w, d):
    """Movel inteiramente sobre o tapete senta NO tapete (nao flutua/nao afunda)."""
    if rug_pl is None:
        return 0.0
    rx0, ry0, rx1, ry1 = rug_pl["bbox"][:4]
    x0, y0 = center[0] - w / 2.0, center[1] - d / 2.0
    x1, y1 = center[0] + w / 2.0, center[1] + d / 2.0
    if x0 >= rx0 and y0 >= ry0 and x1 <= rx1 and y1 <= ry1:
        return rug_pl["bbox"][5]
    return 0.0


def _distances(report, placements, room, ctx):
    by = {p["type"]: p for p in placements}
    d = report["distances"]
    hero = next((p for p in placements if p["role"] == "hero"), None)
    if hero and "coffee_table" in by:
        t = by["coffee_table"]
        fx, fy = hero["facing"]
        hd, td = _depth_of(hero), _depth_of(t)
        gap = (abs((t["center"][0] - hero["center"][0]) * fx +
                   (t["center"][1] - hero["center"][1]) * fy) - hd / 2.0 - td / 2.0)
        d["coffee_table_gap_m"] = round(gap, 3)
    if hero and "rug" in by:
        r = by["rug"]
        hx0, hy0, hx1, hy1 = hero["bbox"][:4]
        rx0, ry0, rx1, ry1 = r["bbox"][:4]
        if hero["facing"][1] != 0:      # frente em Y -> largura em X
            d["rug_overhang_m"] = [round(hx0 - rx0, 3), round(rx1 - hx1, 3)]
        else:
            d["rug_overhang_m"] = [round(hy0 - ry0, 3), round(ry1 - hy1, 3)]
    if hero and "wall_art" in by:
        a = by["wall_art"]
        if hero["facing"][1] != 0:
            d["art_offset_along_m"] = round(a["center"][0] - hero["center"][0], 3)
        else:
            d["art_offset_along_m"] = round(a["center"][1] - hero["center"][1], 3)
        d["art_gap_above_hero_m"] = round(a["bbox"][4] - hero["bbox"][5], 3)
    win = ctx.get("window")
    if win and "curtain" in by:
        c = by["curtain"]
        along = c["center"][1] if win["wall"] in ("east", "west") else c["center"][0]
        d["curtain_window_offset_m"] = round(along - win["center_along_m"], 3)
    if win and "plant_placeholder" in by:
        p = by["plant_placeholder"]
        face = _wall_face_point(room, win["wall"], win["center_along_m"])
        d["plant_to_window_m"] = round(math.hypot(p["center"][0] - face[0],
                                                  p["center"][1] - face[1]), 3)
    for t in ("side_table", "floor_lamp"):
        if hero and t in by:
            s = by[t]
            hx0, hy0, hx1, hy1 = hero["bbox"][:4]
            sx0, sy0, sx1, sy1 = s["bbox"][:4]
            gx = max(sx0 - hx1, hx0 - sx1, 0.0)
            gy = max(sy0 - hy1, hy0 - sy1, 0.0)
            d[f"{t}_gap_m"] = round(max(gx, gy) if (gx == 0 or gy == 0) else math.hypot(gx, gy), 3)
    if hero and "accent_seat" in by:
        a = by["accent_seat"]
        fx, fy = hero["facing"]
        gap = (abs((a["center"][0] - hero["center"][0]) * fx +
                   (a["center"][1] - hero["center"][1]) * fy)
               - _depth_of(hero) / 2.0 - _depth_of(a) / 2.0)
        d["accent_seat_gap_m"] = round(gap, 3)
        # encara o hero = facing do accent aponta pro hero (dot com a direcao
        # accent->hero; tolera a rotacao de conversa do cycle 003)
        dx, dy = hero["center"][0] - a["center"][0], hero["center"][1] - a["center"][1]
        n = math.hypot(dx, dy) or 1.0
        dot = a["facing"][0] * dx / n + a["facing"][1] * dy / n
        d["accent_facing_dot"] = round(dot, 3)
        d["accent_faces_hero"] = dot >= 0.90


def _camera(goal, room, placements, hero_t, win_wall=None):
    """Camera 3/4 humana deterministica: olho a eye_height na quadrante oposta ao
    hero, mirando o centroide da zona de estar. O 3/4 esconde as 2 paredes mais
    proximas do olho — entao o olho fica do lado OPOSTO 'a parede da janela (a
    janela/cortina compoe o fundo, nao some). Emite elev/azim (render mpl)."""
    kind = goal.get("kind", "three_quarter_human")
    eye_h = goal.get("eye_height_m", 1.60)
    W, D = room["width_m"], room["depth_m"]
    hero = next((p for p in placements if p["role"] == "hero"), None)
    zone = [p for p in placements if p["type"] in (hero_t, "rug", "coffee_table")] or placements
    tx = sum(p["center"][0] for p in zone) / len(zone)
    ty = sum(p["center"][1] for p in zone) / len(zone)
    tz = 0.55

    def _eye(side):
        if not hero:
            return W * 0.2, D * 0.2
        hx, hy = hero["center"]
        dirv = (tx - hx, ty - hy)
        n = math.hypot(*dirv) or 1.0
        dirv = (dirv[0] / n, dirv[1] / n)
        perp = (-dirv[1] * side, dirv[0] * side)
        ex = tx + dirv[0] * 2.6 + perp[0] * 1.8
        ey = ty + dirv[1] * 2.6 + perp[1] * 1.8
        return min(max(ex, 0.4), W - 0.4), min(max(ey, 0.4), D - 0.4)

    def _hide(ex, ey):
        return ["south" if ey < D / 2.0 else "north", "west" if ex < W / 2.0 else "east"]

    ex, ey = _eye(1.0)
    if win_wall and win_wall in _hide(ex, ey):
        ex2, ey2 = _eye(-1.0)
        if win_wall not in _hide(ex2, ey2):
            ex, ey = ex2, ey2
    dx, dy, dz = ex - tx, ey - ty, eye_h - tz
    azim = math.degrees(math.atan2(dy, dx))
    elev = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
    return {"kind": kind, "eye": [round(ex, 3), round(ey, 3), eye_h],
            "target": [round(tx, 3), round(ty, 3), tz],
            "elev_deg": round(elev, 1), "azim_deg": round(azim, 1),
            "hide_walls": _hide(ex, ey),
            "min_hero_coverage": goal.get("min_hero_coverage", 0.10)}


# ------------------------------------------------------------------ IO
def write_scene(scene, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    slim = {k: scene[k] for k in ("scene_id", "room", "openings", "placements", "camera")}
    slim["style_id"] = scene["report"]["style_id"]
    (out / "scene.json").write_text(json.dumps(slim, indent=2, ensure_ascii=False),
                                    encoding="utf-8")
    (out / "scene_parts.json").write_text(json.dumps(scene["parts"], ensure_ascii=False),
                                          encoding="utf-8")
    (out / "scene_report.json").write_text(
        json.dumps(scene["report"], indent=2, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    src = Path(sys.argv[1] if len(sys.argv) > 1
               else ROOT / "fixtures/scene_intents/living_room_modern_warm_minimal.json")
    intent = json.loads(src.read_text("utf-8"))
    scene = compose_scene(intent)
    out = write_scene(scene, ROOT / "runs" / "scenes" / scene["scene_id"])
    rep = scene["report"]
    print(f"=== SceneComposer: {scene['scene_id']} ({rep['style_id']}) ===")
    print(f"  {len(scene['placements'])} moveis, {len(scene['parts'])} parts (com shell)")
    for p in rep["placements"]:
        print(f"  {p['type']:18} c={p['center']} rot={p['rotation_deg']:3} "
              f"z+{p['z_off']} <- {p['anchor']}")
    print("  distancias:", json.dumps(rep["distances"], ensure_ascii=False))
    cam = scene["camera"]
    print(f"  camera {cam['kind']}: eye={cam['eye']} target={cam['target']} "
          f"elev={cam['elev_deg']} azim={cam['azim_deg']} hide={cam['hide_walls']}")
    print(f"  -> {out}")
