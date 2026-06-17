"""dining_table_class.py — a TEORIA EXECUTAVEL da classe MESA DE JANTAR
(6a classe; 2o builder 100% novo do programa — nao existia nada no repo).

DNA: a mesa de jantar SERVE PESSOAS — tudo deriva do numero de LUGARES.
Ancoras ergonomicas FIXAS pelo corpo (nao escalam com a peca):
  - lugar a mesa: 0.60m de frente (min absoluto 0.55) x 0.40m de profundidade;
  - altura do tampo 0.72-0.78 com delta tampo-assento 0.27-0.33 (cadeira 0.45);
  - JOELHO LIVRE: face inferior (tampo/saia) >= 0.60 do chao;
  - alcance do braco: raio util ~0.75 => redonda SATURA em diametro 1.50;
  - circulacao: 0.90m alem da borda p/ cadeira afastada + passagem.
O que escala com lugares: footprint do tampo. O que NAO escala: altura,
profundidade do lugar, joelho, circulacao (corpo humano e' o mesmo).

Satelites (PADRAO INSTITUCIONAL — visiveis na matriz, nao so no label):
  - CADEIRA PROXY em cada lugar (assento+encosto guide, 0.45x0.42, h 0.45/0.90);
  - ENVELOPE de uso por cadeira (pad de piso 0.55x0.75 desde a borda);
  - ANEL DE CIRCULACAO 0.90m ao redor do footprint (area minima de uso humano).

Uso: python -m tools.dining_table_class            (prova + sabotagens)
     python -m tools.dining_table_class --matrix   (matriz 9 pro juiz)
"""
from __future__ import annotations

import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.sofa_builder import _darker, _p   # noqa: E402

# ------------------------------------------------- cadeira servida (satelite)
CHAIR = {"w": 0.45, "d": 0.42, "seat_h": 0.45, "back_h": 0.90, "tuck": 0.05}
PLACE_W = 0.62          # frente por lugar (conforto); MIN ergonomico duro 0.55
PLACE_W_MIN = 0.55
PLACE_D = 0.40          # profundidade do lugar sobre o tampo
CLEAR_USE = 0.90        # circulacao alem da borda (cadeira afastada + passar)

# ----------------------------------------------------------------- faixas duras
DINING_RANGES = {
    "height": (0.72, 0.78),
    "top_thickness": (0.025, 0.06),
    "length": (0.75, 2.60),          # saturacao: sala nao escala infinito
    "width_rect_oval": (0.80, 1.10),  # servico: 2x lugar (0.35) + faixa central
    "diameter_round": (0.75, 1.50),   # alcance do braco controla a redonda
}
SEAT_DELTA = (0.27, 0.33)             # tampo - assento da cadeira
KNEE_MIN = 0.60                       # chao -> face inferior (tampo/saia)

RELATIONS = {
    "joelho_livre": (
        lambda s: s.height - s.top_thickness
        - (s.apron_h if s.support == "legs" else 0.02),
        KNEE_MIN, 0.78,
        "face inferior fora — saia/tampo esmaga o joelho ou mesa-bancada"),
    "tampo_em_proporcao": (
        lambda s: 1.5 if s.shape == "round" else s.length / s.width,
        1.10, 2.60,
        "tampo prancha (fino demais p/ servir) ou quadrado atarracado"),
}


@dataclass
class DiningTableSpec:
    """X=comprimento, Y=largura (lados longos em y=0/y=W), Z=altura.
    round: length == width == diametro."""
    shape: str = "rect"            # rect | round | oval
    seats: int = 6
    length: float = 1.84
    width: float = 0.95
    height: float = 0.75
    top_thickness: float = 0.04
    support: str = "legs"          # legs | pedestal
    apron_h: float = 0.10          # so legs: saia sob o tampo
    leg_section: float = 0.08
    leg_inset: float = 0.05        # recuo do canto (cadeira senta ENTRE pernas)
    leg_taper: bool = False        # oval_soft: perna conica verts8
    place_w: float = PLACE_W
    heads: bool = True             # cabeceiras ocupadas (rect>=6; oval sempre)
    round_facets: int = 24         # round: lados do disco do tampo (>=16 le circulo)
    end_depth: float = 0.0         # oval: profundidade de cada ponta curva
    oval_facets: int = 8           # oval: bandas por ponta (semielipse; >=6 le curva)
    col_r: float = 0.075           # pedestal: raio da coluna
    plate_r: float = 0.0           # pedestal: raio do prato da base
    plate_h: float = 0.10          # pedestal: altura do prato (canela passa)
    clearance_use: float = CLEAR_USE
    top_rgb: tuple = (118, 92, 68)
    base_rgb: tuple = (96, 76, 58)

    def n_side(self):
        """lugares por lado longo (rect/oval)."""
        if self.shape == "round":
            return 0
        n = self.seats - (2 if self.heads else 0)
        return max(1, n // 2)

    def knee_clearance(self):
        return self.height - self.top_thickness - (
            self.apron_h if self.support == "legs" else 0.02)

    def validate(self):
        assert self.shape in ("rect", "round", "oval")
        assert self.support in ("legs", "pedestal")
        assert self.seats >= 2
        if self.shape == "round":
            assert abs(self.length - self.width) < 1e-9, "round: length==width==D"
        return self

    def bbox_m(self):
        return (round(self.length, 3), round(self.width, 3),
                round(self.height, 3))

    def to_dict(self):
        d = asdict(self)
        d["bbox_m"] = self.bbox_m()
        return d


def _rot_box(label, kind, cx, cy, w, d, z0, z1, ang_rad, rgb):
    """caixa rotacionada em planta (verts8): w perpendicular, d ao longo do
    eixo de orientacao ang (0 = +X). Usada p/ cadeiras radiais e bases."""
    c, s = math.cos(ang_rad), math.sin(ang_rad)
    quad = []
    for lx, ly in ((-d / 2, -w / 2), (d / 2, -w / 2),
                   (d / 2, w / 2), (-d / 2, w / 2)):
        quad.append((cx + lx * c - ly * s, cy + lx * s + ly * c))
    p = _p(label, kind, min(q[0] for q in quad), min(q[1] for q in quad),
           max(q[0] for q in quad), max(q[1] for q in quad), z0, z1, rgb)
    p["verts8"] = [(x, y, z0) for x, y in quad] + [(x, y, z1) for x, y in quad]
    return p


def _disc_bands(prefix, kind, cx, cy, R, z0, z1, rgb, nb=12):
    """disco REDONDO como nb bandas trapezoidais (verts8): silhueta curva real
    dentro da primitiva caixa (o renderer so desenha quad de topo/base). nb
    bandas ~ poligono de 2*nb lados — >=12 le como circulo, nao octogono."""
    parts = []
    for i in range(nb):
        ya = cy - R + (2 * R) * i / nb
        yb = cy - R + (2 * R) * (i + 1) / nb
        wa = math.sqrt(max(0.0, R * R - (ya - cy) ** 2))
        wb = math.sqrt(max(0.0, R * R - (yb - cy) ** 2))
        quad = [(cx - wa, ya), (cx + wa, ya), (cx + wb, yb), (cx - wb, yb)]
        hw = max(wa, wb)
        p = _p(f"{prefix}_{i}", kind, cx - hw, ya, cx + hw, yb, z0, z1, rgb)
        p["verts8"] = ([(x, y, z0) for x, y in quad]
                       + [(x, y, z1) for x, y in quad])
        parts.append(p)
    return parts


def _oval_end_bands(prefix, x_full, x_tip, cy, W, z0, z1, rgb, nb=8):
    """ponta de oval (racetrack) como SEMIELIPSE de nb bandas em x: meia-largura
    em y = (W/2)*sqrt(1-t^2), do bordo cheio (t=0, largura W) ao bico (t=1).
    Curva CONTINUA — nao o trapezio reto que lia 'retangulo chanfrado'."""
    parts = []
    depth = x_tip - x_full                       # com sinal (E: +, W: -)
    for i in range(nb):
        ta, tb = i / nb, (i + 1) / nb
        xa, xb = x_full + depth * ta, x_full + depth * tb
        ha = (W / 2.0) * math.sqrt(max(0.0, 1.0 - ta * ta))
        hb = (W / 2.0) * math.sqrt(max(0.0, 1.0 - tb * tb))
        quad = [(xa, cy - ha), (xa, cy + ha), (xb, cy + hb), (xb, cy - hb)]
        hh = max(ha, hb)
        p = _p(f"{prefix}_{i}", "top", min(xa, xb), cy - hh, max(xa, xb),
               cy + hh, z0, z1, rgb)
        p["verts8"] = ([(x, y, z0) for x, y in quad]
                       + [(x, y, z1) for x, y in quad])
        parts.append(p)
    return parts


def build_dining_table(spec: DiningTableSpec):
    """(parts, meta) no contrato padrao. rect = 4 pernas + saia; round =
    tampo DISCO redondo (bandas verts8) + pedestal redondo (hub + coluna fina +
    prato baixo); oval = tampo racetrack com pontas CURVAS semielipse (bandas
    verts8) + pernas conicas."""
    spec.validate()
    L, W, h, tt = spec.length, spec.width, spec.height, spec.top_thickness
    top, base = tuple(spec.top_rgb), tuple(spec.base_rgb)
    dark = _darker(base, 0.7)
    parts = []
    z_top0 = h - tt

    if spec.shape == "rect":
        parts.append(_p("top", "top", 0.0, 0.0, L, W, z_top0, h, top))
        az0 = z_top0 - spec.apron_h
        parts.append(_p("apron_f", "base", 0.04, 0.04, L - 0.04, 0.07, az0, z_top0, dark))
        parts.append(_p("apron_b", "base", 0.04, W - 0.07, L - 0.04, W - 0.04, az0, z_top0, dark))
        parts.append(_p("apron_l", "base", 0.04, 0.04, 0.07, W - 0.04, az0, z_top0, dark))
        parts.append(_p("apron_r", "base", L - 0.07, 0.04, L - 0.04, W - 0.04, az0, z_top0, dark))
        sec, ins = spec.leg_section, spec.leg_inset
        for tag, (fx, fy) in (("fl", (ins, ins)), ("fr", (L - ins - sec, ins)),
                              ("bl", (ins, W - ins - sec)),
                              ("br", (L - ins - sec, W - ins - sec))):
            parts.append(_p(f"leg_{tag}", "foot", fx, fy, fx + sec, fy + sec,
                            0.0, z_top0, base))

    elif spec.shape == "round":
        D = L
        cx = cy = R = D / 2.0
        nb = max(8, spec.round_facets // 2)
        # tampo: DISCO redondo por bandas (le circulo, nao octogono facetado)
        parts += _disc_bands("top", "top", cx, cy, R, z_top0, h, top, nb)
        # hub fino e redondo sob o tampo (liga tampo -> coluna, sem bloco quadrado)
        parts += _disc_bands("hub", "base", cx, cy, 0.12 * D,
                             z_top0 - 0.035, z_top0, dark, 8)
        # coluna do pedestal: FINA e redonda (libera a zona dos pes)
        parts += _disc_bands("column", "foot", cx, cy, spec.col_r,
                             spec.plate_h, z_top0 - 0.035, base, 8)
        # prato da base: redondo, MENOR e BAIXO (canela/cadeira passam)
        parts += _disc_bands("foot", "foot", cx, cy, spec.plate_r,
                             0.0, spec.plate_h, _darker(base, 0.85), 10)

    else:  # oval (racetrack): centro reto + 2 pontas CURVAS (semielipse)
        ed = spec.end_depth
        x0s, x1s = ed, L - ed
        cy = W / 2.0
        nb = max(6, spec.oval_facets)
        parts.append(_p("top_c", "top", x0s, 0.0, x1s, W, z_top0, h, top))
        parts += _oval_end_bands("top_w", x0s, 0.0, cy, W, z_top0, h, top, nb)
        parts += _oval_end_bands("top_e", x1s, L, cy, W, z_top0, h, top, nb)
        az0 = z_top0 - spec.apron_h
        parts.append(_p("apron_f", "base", x0s + 0.02, 0.05, x1s - 0.02, 0.08,
                        az0, z_top0, dark))
        parts.append(_p("apron_b", "base", x0s + 0.02, W - 0.08, x1s - 0.02,
                        W - 0.05, az0, z_top0, dark))
        sec, ins = spec.leg_section, spec.leg_inset
        for tag, (fx, fy) in (("fl", (x0s + 0.02, ins)),
                              ("fr", (x1s - 0.02 - sec, ins)),
                              ("bl", (x0s + 0.02, W - ins - sec)),
                              ("br", (x1s - 0.02 - sec, W - ins - sec))):
            p = _p(f"leg_{tag}", "foot", fx, fy, fx + sec, fy + sec,
                   0.0, z_top0, base)
            sh = sec * 0.18  # conica leve: pe presente (oval longa nao pode fragil)
            p["verts8"] = [
                (fx + sh, fy + sh, 0.0), (fx + sec - sh, fy + sh, 0.0),
                (fx + sec - sh, fy + sec - sh, 0.0), (fx + sh, fy + sec - sh, 0.0),
                (fx, fy, z_top0), (fx + sec, fy, z_top0),
                (fx + sec, fy + sec, z_top0), (fx, fy + sec, z_top0)]
            parts.append(p)

    meta = {"type": "dining_table", "shape": spec.shape, "seats": spec.seats,
            "n_parts": len(parts), "bbox_m": spec.bbox_m(),
            "kinds": sorted({p["kind"] for p in parts})}
    return parts, meta


# ------------------------------------------- lugares: ancoras borda + normal
def _seat_anchors(spec: DiningTableSpec):
    """[(ex, ey, nx, ny)] — ponto na borda do tampo + normal p/ FORA, um por
    lugar. rect/oval: lados longos espalhados + cabeceiras; round: radial."""
    L, W = spec.length, spec.width
    out = []
    if spec.shape == "round":
        cx = cy = L / 2.0
        for k in range(spec.seats):
            a = 2 * math.pi * k / spec.seats
            nx, ny = math.cos(a), math.sin(a)
            out.append((cx + nx * L / 2.0, cy + ny * L / 2.0, nx, ny))
        return out
    n_side = spec.n_side()
    if spec.shape == "oval":
        # a curva participa do lugar lateral: espalha sobre S + 0.20*W
        span = (L - 2 * spec.end_depth) + 0.20 * W
    else:
        span = n_side * spec.place_w
    x0 = (L - span) / 2.0
    for i in range(n_side):
        x = x0 + (i + 0.5) * span / n_side
        out.append((x, 0.0, 0.0, -1.0))
        out.append((x, W, 0.0, 1.0))
    if spec.heads:
        out.append((0.0, W / 2.0, -1.0, 0.0))
        out.append((L, W / 2.0, 1.0, 0.0))
    return out


def _chair_proxy_parts(spec: DiningTableSpec):
    """PADRAO INSTITUCIONAL (satelite VISIVEL): cadeira proxy em cada lugar
    (assento+encosto guide), ENVELOPE de uso por cadeira (pad de piso) e ANEL
    de circulacao 0.90m ao redor do footprint."""
    g, pad_rgb, ring_rgb = (120, 122, 126), (206, 200, 190), (170, 60, 50)
    cw, cd, sh, bh, tuck = (CHAIR["w"], CHAIR["d"], CHAIR["seat_h"],
                            CHAIR["back_h"], CHAIR["tuck"])
    parts = []
    for i, (ex, ey, nx, ny) in enumerate(_seat_anchors(spec), 1):
        a = math.atan2(ny, nx)
        scx, scy = ex + nx * (cd / 2 - tuck), ey + ny * (cd / 2 - tuck)
        bcx, bcy = ex + nx * (cd - tuck + 0.03), ey + ny * (cd - tuck + 0.03)
        pcx, pcy = ex + nx * 0.375, ey + ny * 0.375
        parts.append(_rot_box(f"chair_{i}_seat", "chair", scx, scy, cw, cd,
                              sh - 0.03, sh, a, g))
        parts.append(_rot_box(f"chair_{i}_back", "chair", bcx, bcy, cw, 0.05,
                              sh, bh, a, g))
        parts.append(_rot_box(f"chair_{i}_env", "guide", pcx, pcy,
                              cw + 0.10, 0.75, 0.002, 0.010, a, pad_rgb))
    # anel de circulacao (area minima de uso humano) no bbox + clearance
    cu, t, zb = spec.clearance_use, 0.03, 0.014
    x0, y0 = -cu, -cu
    x1, y1 = spec.length + cu, spec.width + cu
    parts.append(_p("use_ring_s", "guide", x0, y0, x1, y0 + t, 0.004, zb, ring_rgb))
    parts.append(_p("use_ring_n", "guide", x0, y1 - t, x1, y1, 0.004, zb, ring_rgb))
    parts.append(_p("use_ring_w", "guide", x0, y0, x0 + t, y1, 0.004, zb, ring_rgb))
    parts.append(_p("use_ring_e", "guide", x1 - t, y0, x1, y1, 0.004, zb, ring_rgb))
    return parts


# ----------------------------------------------------------- gates da classe
def dining_class_gate(spec: DiningTableSpec, parts=None):
    errors, warnings, metrics = [], [], {}
    lo, hi = DINING_RANGES["height"]
    if not (lo - 1e-9 <= spec.height <= hi + 1e-9):
        errors.append(f"height={spec.height:.3f} fora da faixa [{lo},{hi}]")
    lo, hi = DINING_RANGES["top_thickness"]
    if not (lo - 1e-9 <= spec.top_thickness <= hi + 1e-9):
        errors.append(f"top_thickness={spec.top_thickness:.3f} fora [{lo},{hi}]")
    if spec.shape == "round":
        lo, hi = DINING_RANGES["diameter_round"]
        if not (lo - 1e-9 <= spec.length <= hi + 1e-9):
            errors.append(f"diametro={spec.length:.2f} fora [{lo},{hi}] — "
                          "alcance do braco nao escala (centro inalcancavel)")
    else:
        lo, hi = DINING_RANGES["width_rect_oval"]
        if not (lo - 1e-9 <= spec.width <= hi + 1e-9):
            errors.append(f"width={spec.width:.2f} fora [{lo},{hi}] — sem faixa "
                          "central de servico (2 lugares 0.35 + 0.10)")
        lo, hi = DINING_RANGES["length"]
        if not (lo - 1e-9 <= spec.length <= hi + 1e-9):
            errors.append(f"length={spec.length:.2f} fora [{lo},{hi}] — "
                          "prancha infinita: sala/servico nao escala")
    for name, (fn, lo, hi, msg) in RELATIONS.items():
        v = fn(spec)
        metrics[name] = round(v, 3)
        if not (lo - 1e-9 <= v <= hi + 1e-9):
            errors.append(f"{name}={v:.3f}: {msg}")
    if spec.shape == "round":
        if spec.round_facets < 16:
            errors.append(f"redonda facetada ({spec.round_facets} lados <16) — "
                          "le poligono, nao circulo")
        if spec.plate_r > 0.36 * spec.length:
            errors.append(f"prato da base {spec.plate_r:.2f} > 0.36*D — base "
                          "central pesada: rouba a zona dos pes/cadeiras")
        if spec.plate_r < 0.24 * spec.length:
            errors.append("prato < 0.24*D — pedestal instavel (tombamento)")
        if spec.col_r > 0.085 * spec.length:
            errors.append(f"coluna {spec.col_r:.3f} > 0.085*D — pedestal grosso "
                          "(rouba a zona dos pes)")
        if spec.plate_h > 0.10:
            errors.append("prato alto (>0.10) — canela bate na base")
    if spec.shape == "oval":
        if spec.oval_facets < 6:
            errors.append(f"oval com ponta reta ({spec.oval_facets} bandas <6) — "
                          "le retangulo chanfrado, nao curva continua")
        if spec.end_depth < 0.35 * spec.width:
            errors.append("ponta rasa (end<0.35*W) — oval lendo retangulo")
    if spec.shape != "round" and spec.support == "legs":
        span = spec.length - 2 * (spec.leg_inset + spec.leg_section)
        need = spec.n_side() * PLACE_W_MIN
        if spec.shape == "oval":
            span = (spec.length - 2 * spec.end_depth) + 0.25 * spec.width \
                - 2 * spec.leg_section
        metrics["vao_entre_pernas"] = round(span, 3)
        if span + 1e-9 < need:
            errors.append(f"vao entre pernas {span:.2f} < {need:.2f} — "
                          "perna bloqueia o lugar (cadeira nao entra)")
    if parts is not None:
        kinds = {p["kind"] for p in parts}
        need_k = {"top", "foot"}
        if not need_k <= kinds:
            errors.append(f"partes ausentes: {sorted(need_k - kinds)}")
    result = "FAIL" if errors else ("WARN" if warnings else "PASS")
    return {"result": result, "errors": errors, "warnings": warnings,
            "metrics": metrics}


def chair_satellite_gate(spec: DiningTableSpec, seat_h=CHAIR["seat_h"]):
    """Mesa contra a CADEIRA servida: delta de altura, frente por lugar,
    joelho, e (round) arco por lugar + folga de pe ate o prato."""
    errors, metrics = [], {}
    delta = spec.height - seat_h
    metrics["delta_tampo_assento"] = round(delta, 3)
    if not (SEAT_DELTA[0] - 1e-9 <= delta <= SEAT_DELTA[1] + 1e-9):
        errors.append(f"delta tampo-assento {delta:.2f} (regra {SEAT_DELTA}) — "
                      "cotovelo alto ou coxa presa")
    knee = spec.knee_clearance()
    metrics["joelho_m"] = round(knee, 3)
    if knee + 1e-9 < KNEE_MIN:
        errors.append(f"joelho {knee:.2f} < {KNEE_MIN} — saia/tampo no joelho")
    if spec.shape == "round":
        arc = math.pi * spec.length / spec.seats
        metrics["frente_por_lugar"] = round(arc, 3)
        if arc + 1e-9 < PLACE_W_MIN:
            errors.append(f"arco {arc:.2f}/lugar < {PLACE_W_MIN} — cadeiras "
                          "se tocam na redonda")
        foot = spec.length / 2.0 - spec.plate_r
        metrics["folga_pe_prato"] = round(foot, 3)
        if foot + 1e-9 < 0.10:
            errors.append(f"borda->prato {foot:.2f} < 0.10 — pe esbarra na base")
    else:
        metrics["frente_por_lugar"] = round(spec.place_w, 3)
        if spec.place_w + 1e-9 < PLACE_W_MIN:
            errors.append(f"lugar {spec.place_w:.2f} < {PLACE_W_MIN} — "
                          "cadeira proxy nao cabe (cotovelo no vizinho)")
        if spec.heads and spec.width - 2 * (spec.leg_inset
                                            + spec.leg_section) < CHAIR["w"]:
            errors.append("cabeceira sem vao p/ cadeira entre as pernas")
    return {"result": "FAIL" if errors else "PASS", "errors": errors,
            "metrics": metrics}


def circulation_gate(spec: DiningTableSpec, parts_vis=None):
    """Uso humano AO REDOR: clearance >= 0.45 (passagem minima) e, na matriz,
    os satelites VISIVEIS (cadeiras + envelope + anel) — clearance invisivel
    e' FAIL institucional."""
    errors, metrics = [], {}
    metrics["clearance_use_m"] = spec.clearance_use
    metrics["area_uso_m"] = (round(spec.length + 2 * spec.clearance_use, 2),
                             round(spec.width + 2 * spec.clearance_use, 2))
    if spec.clearance_use + 1e-9 < 0.45:
        errors.append(f"clearance {spec.clearance_use:.2f} < 0.45 — nem "
                      "passagem de lado")
    if parts_vis is not None:
        kinds = {p["kind"] for p in parts_vis}
        if "chair" not in kinds or "guide" not in kinds:
            errors.append("satelite INVISIVEL na matriz (sem cadeira proxy/"
                          "anel de uso) — padrao institucional violado")
        else:
            n_chairs = sum(1 for p in parts_vis
                           if p["kind"] == "chair" and "seat" in p["label"])
            if n_chairs != spec.seats:
                errors.append(f"{n_chairs} cadeiras proxy p/ {spec.seats} "
                              "lugares — lugar sem cadeira")
    return {"result": "FAIL" if errors else "PASS", "errors": errors,
            "metrics": metrics}


# ------------------------------------------------------- arquetipos + derive
ARCHETYPES = {
    "rect_family": dict(shape="rect", support="legs", top_thickness=0.04,
                        apron_h=0.10, leg_section=0.08, leg_inset=0.05,
                        base_w=0.90, seats_ok=(4, 6, 8),
                        top_rgb=(118, 92, 68), base_rgb=(96, 76, 58)),
    "round_compact": dict(shape="round", support="pedestal",
                          top_thickness=0.035, seats_ok=(2, 4, 6),
                          top_rgb=(96, 80, 70), base_rgb=(70, 60, 54)),
    "oval_soft": dict(shape="oval", support="legs", top_thickness=0.03,
                      apron_h=0.05, leg_section=0.06, leg_inset=0.08,
                      seats_ok=(4, 6, 8),
                      top_rgb=(142, 118, 92), base_rgb=(110, 92, 72)),
}
ROUND_MIN_D = {2: 0.80, 4: 1.05, 6: 1.35}


def derive_dining_spec(seats=6, archetype="rect_family",
                       **overrides) -> DiningTableSpec:
    """A mesa se DERIVA dos LUGARES: footprint = lugares x frente 0.62
    (+ cabeceiras), SATURADO em 2.60m — quando satura, a frente comprime ate
    o minimo ergonomico 0.55 (abaixo disso a derivacao nao serve os lugares
    e o gate reprova). Redonda: D = max(arco, minimo de servico), teto 1.50
    pelo ALCANCE. Altura NUNCA deriva dos lugares (corpo humano governa)."""
    assert archetype in ARCHETYPES
    a = ARCHETYPES[archetype]
    assert seats in a["seats_ok"], f"{archetype}: lugares {a['seats_ok']}"
    pw = PLACE_W
    kw = dict(shape=a["shape"], seats=seats, support=a["support"],
              top_thickness=a["top_thickness"],
              top_rgb=a["top_rgb"], base_rgb=a["base_rgb"])
    if a["shape"] == "rect":
        heads = seats >= 6
        n_side = max(1, (seats - (2 if heads else 0)) // 2)
        ends = 0.60 if heads else 0.16
        length = n_side * pw + ends
        if length > DINING_RANGES["length"][1]:           # saturacao honesta
            pw = max(PLACE_W_MIN, (DINING_RANGES["length"][1] - ends) / n_side)
            length = n_side * pw + ends
        width = 0.90 + 0.05 * ((n_side - 2) + (1 if heads else 0))
        kw.update(length=round(length, 3), width=round(width, 3), heads=heads,
                  apron_h=a["apron_h"], leg_section=a["leg_section"],
                  leg_inset=a["leg_inset"], place_w=round(pw, 3))
    elif a["shape"] == "round":
        D = max(seats * 0.68 / math.pi, ROUND_MIN_D[seats])
        D = round(min(D, DINING_RANGES["diameter_round"][1]), 3)
        kw.update(length=D, width=D, heads=False, place_w=round(pw, 3),
                  round_facets=24, col_r=round(max(0.045, 0.05 * D), 3),
                  plate_r=round(0.28 * D, 3), plate_h=0.06)
    else:  # oval
        n_side = max(1, (seats - 2) // 2)
        width = 0.95 + 0.035 * (n_side - 1)
        end_depth = 0.45 * width
        credit = 0.25 * width if n_side >= 2 else 0.0
        straight = n_side * pw - credit if n_side >= 2 else pw + 0.16
        length = straight + 2 * end_depth
        if length > DINING_RANGES["length"][1]:           # saturacao honesta
            pw = max(PLACE_W_MIN,
                     (DINING_RANGES["length"][1] - 2 * end_depth + credit) / n_side)
            straight = n_side * pw - credit
            length = straight + 2 * end_depth
        kw.update(length=round(length, 3), width=round(width, 3), heads=True,
                  apron_h=a["apron_h"], leg_section=a["leg_section"],
                  leg_inset=a["leg_inset"], leg_taper=True,
                  end_depth=round(end_depth, 3), oval_facets=8,
                  place_w=round(pw, 3))
    spec = DiningTableSpec(**kw)
    for k, v in overrides.items():
        setattr(spec, k, v)
    return spec.validate()


# ------------------------------------------------------------------ sabotagens
def _sabotages():
    """as 9 obrigatorias do programa — toda sabotagem DEVE reprovar."""
    return [
        ("cadeira proxy nao cabe (lugar 0.48)", lambda: (
            derive_dining_spec(6, "rect_family", place_w=0.48), None)),
        ("perna/base bloqueia joelho (pernas no meio do vao)", lambda: (
            derive_dining_spec(6, "rect_family", leg_inset=0.42), None)),
        ("tampo estreito p/ servico (0.68)", lambda: (
            derive_dining_spec(6, "rect_family", width=0.68), None)),
        ("prancha infinita (3.20 x 0.90)", lambda: (
            derive_dining_spec(8, "rect_family", length=3.20, width=0.90), None)),
        ("redonda sem controle de alcance (D 1.75)", lambda: (
            derive_dining_spec(6, "round_compact", length=1.75, width=1.75),
            None)),
        ("base central pesada em mesa pequena (prato 0.34 em D 0.80)", lambda: (
            derive_dining_spec(2, "round_compact", plate_r=0.34), None)),
        ("altura incompativel com cadeira (0.84)", lambda: (
            derive_dining_spec(6, "rect_family", height=0.84), None)),
        ("clearance/satelite invisivel na matriz", lambda: (
            derive_dining_spec(6, "rect_family"), "no_proxies")),
        ("oval que le como retangulo (ponta rasa end 0.18)", lambda: (
            derive_dining_spec(6, "oval_soft", end_depth=0.18), None)),
        ("redonda facetada (round_facets 8) le poligono", lambda: (
            derive_dining_spec(4, "round_compact", round_facets=8), None)),
        ("oval com ponta reta (oval_facets 1) le retangulo", lambda: (
            derive_dining_spec(6, "oval_soft", oval_facets=1), None)),
    ]


def _apply_sab(mk):
    spec, mode = mk()
    g = dining_class_gate(spec)
    c = chair_satellite_gate(spec)
    if mode == "no_proxies":
        parts, _ = build_dining_table(spec)
        u = circulation_gate(spec, parts_vis=parts)   # SEM proxies => FAIL
    else:
        u = circulation_gate(spec)
    return (g["result"] == "FAIL" or c["result"] == "FAIL"
            or u["result"] == "FAIL")


# ------------------------------------------------------------------ matriz
MATRIX = [(f"{arch}@{seats}p", arch, seats)
          for arch, seats_all in (("rect_family", (4, 6, 8)),
                                  ("round_compact", (2, 4, 6)),
                                  ("oval_soft", (4, 6, 8)))
          for seats in seats_all]


def build_matrix(out_dir):
    from tools.render_parts_iso import render_parts
    from tools.sofa_class_matrix import _grid_sheet
    import json as _json
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report, cells = [], []
    for name, arch, seats in MATRIX:
        spec = derive_dining_spec(seats, arch)
        parts, meta = build_dining_table(spec)
        parts_vis = parts + _chair_proxy_parts(spec)     # satelite VISIVEL
        cls = dining_class_gate(spec, parts)
        sat_c = chair_satellite_gate(spec)
        sat_u = circulation_gate(spec, parts_vis=parts_vis)
        png = out / f"cell_{name.replace('@', '_')}.png"
        render_parts(parts_vis, png, elev=24, azim=-58,
                     title=f"{name}  {spec.length:.2f}x{spec.width:.2f}  "
                           f"joelho={spec.knee_clearance():.2f}")
        report.append({"cell": name, "bbox_m": meta["bbox_m"],
                       "class_gate": cls["result"], "class_errors": cls["errors"],
                       "chair_sat": sat_c["result"], "use_sat": sat_u["result"],
                       "frente_por_lugar": sat_c["metrics"]["frente_por_lugar"],
                       "n_parts": meta["n_parts"]})
        cells.append((name, png, cls["result"], f"chair:{sat_c['result']}"))
    sheet = _grid_sheet(cells, out / "dining_table_class_matrix.png",
                        "CLASSE MESA DE JANTAR — derivada de LUGARES (frente "
                        "0.62/min 0.55; joelho>=0.60; delta assento 0.27-0.33); "
                        "cadeira proxy + envelope + anel de uso 0.90 VISIVEIS")
    (out / "matrix_report.json").write_text(
        _json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"sheet": sheet, "report": report}


if __name__ == "__main__":
    if "--matrix" in sys.argv:
        res = build_matrix(ROOT / "runs/dining_table_class/matrix")
        print(f"=== matriz da classe mesa de jantar: {len(res['report'])} ===")
        for r in res["report"]:
            print(f"  {r['cell']:22} class={r['class_gate']:4} "
                  f"chair={r['chair_sat']:4} uso={r['use_sat']:4} "
                  f"frente={r['frente_por_lugar']:.2f}m")
        print(f"  -> {res['sheet']}")
        bad = [r for r in res["report"] if "FAIL" in
               (r["class_gate"], r["chair_sat"], r["use_sat"])]
        sys.exit(1 if bad else 0)
    print("=== dining_table_class: arquetipos x lugares ===")
    bad = 0
    for name, arch, seats in MATRIX:
        spec = derive_dining_spec(seats, arch)
        g = dining_class_gate(spec)
        c = chair_satellite_gate(spec)
        if g["result"] == "FAIL" or c["result"] == "FAIL":
            bad += 1
            print(f"  XXX {name:22} {g['errors'][:1]} {c['errors'][:1]}")
    print(f"  derivados validos: {len(MATRIX) - bad}/{len(MATRIX)}")
    print("=== sabotagens (devem FALHAR) ===")
    ok = bad == 0
    for name, mk in _sabotages():
        hit = _apply_sab(mk)
        ok = ok and hit
        print(f"  {'XXX' if hit else '!!! PASSOU'} {name}")
    print("TODOS OK" if ok else "FALHOU")
    sys.exit(0 if ok else 1)
