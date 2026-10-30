"""armchair_builder.py — geometria PROPRIA da classe POLTRONA (cycle 002:
"emancipar do sofa"). Gramatica SHELL-WRAPAROUND: uma CONCHA continua em U
(costas full-width + bracos que encostam nela + OMBROS que sobem na traseira)
abracando almofadas INTERNAS (assento + encosto) — a "cavidade" que o juiz
pediu: objeto unitario, nao "modulo de sofa cortado".

Diferencas estruturais vs sofa_builder:
  - costas do shell FULL-WIDTH (x 0..W): os bracos ENCOSTAM nela -> U continuo
    (no sofa o encosto fica ENTRE os bracos = leitura modular)
  - OMBRO: segmento traseiro do braco sobe ate wrap_frac da altura do encosto
    (abraco lateral; wrap alto = club/concha, wrap baixo = braco classico)
  - cor UNITARIA no shell (bracos+costas+ombros mesma cor); almofadas internas
    um tom MAIS CLARO (destaca a cavidade — inverte a linguagem do sofa)
  - shell pode ser BAIXO com encosto-almofada subindo acima (lounge nesting)

Reusa helpers primitivos do sofa_builder (_p/_darker/_seat_row/_shear_y) —
primitivas compartilhadas, gramatica propria. Contrato parts/kinds identico
(foot/base/arm/seat_cushion/back_cushion) p/ gates e renderers existentes.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from tools.rooms.shared.parts import darker as _darker, part as _p
from tools.rooms.shared.sofa import _seat_row, _shear_y   # estofado: familia do sofa


def _lighter(rgb, f):
    return [min(255, int(c * f)) for c in rgb]


# Origem de cada proporcao de classe acima: valor declarado no codigo (nao vem do PDF nem de pedido); pode ser sobrescrito.
ARMCHAIR_MEASURE_ORIGINS = {name: "default_declared" for name in (
    "cushion_tint", "base_shade", "pivot_offset", "foot_side", "foot_inset", "arm_cap_t", "arm_cap_over", "shoulder_min_rise",
    "back_cushion_inset", "min_cavity_width")}


@dataclass
class ArmchairSpec:
    """Anatomia parametrica da poltrona. Metros; X=largura, Y=profundidade
    (frente=0, costas=Y maior), Z=altura; frente = -Y na sala."""
    width: float = 0.90
    depth: float = 0.85
    height: float = 0.96            # topo do ENCOSTO (almofada interna)
    seat_height: float = 0.43
    seat_depth: float = 0.52
    arm_width: float = 0.18
    arm_height: float = 0.64
    foot_height: float = 0.14
    cushion_thickness: float = 0.14
    cushion_bevel: float = 0.04
    backrest_rake: float = 13.0
    shell_back_h: float = 0.0       # altura do shell traseiro; 0 = ate height
    wrap_frac: float = 0.30         # ombro: fracao da subida do encosto que o
                                    # braco atinge na traseira (abraco lateral)
    shoulder_len: float = 0.24      # comprimento Y do ombro
    shell_t: float = 0.14           # espessura Y das costas do shell
    back_cushion_t: float = 0.12    # espessura da almofada interna do encosto
    arm_cap: bool = False           # tampo proud (linguagem standard/limpa)
    seat_overhang: float = 0.0
    base_recess: float = 0.06
    # Proporcoes de CLASSE (antes literais no builder); origem em ARMCHAIR_MEASURE_ORIGINS.
    cushion_tint: float = 1.07      # almofada interna mais clara que o shell (fator)
    base_shade: float = 0.62        # base mais escura que o tecido (fator)
    pivot_offset: float = 0.03      # o encosto gira numa altura abaixo do assento
    foot_side: float = 0.08         # lado da secao quadrada do pe
    foot_inset: float = 0.04        # recuo dos pes em relacao aos cantos
    arm_cap_t: float = 0.04         # espessura do tampo proud do braco
    arm_cap_over: float = 0.015     # quanto o tampo avanca alem do braco
    shoulder_min_rise: float = 0.02  # subida minima acima do braco para existir ombro
    back_cushion_inset: float = 0.01  # recuo lateral da almofada do encosto
    min_cavity_width: float = 0.30  # largura minima da cavidade do assento entre os bracos (validacao)
    fabric_rgb: tuple = (182, 172, 153)
    feet_rgb: tuple = (48, 40, 32)

    def validate(self):
        assert self.height > self.seat_height > self.foot_height
        assert self.width > 2 * self.arm_width + self.min_cavity_width, "cavidade precisa de assento"
        assert 0.0 <= self.wrap_frac <= 1.0
        assert self.depth > self.seat_depth + self.shell_t
        return self

    def effective_shell_h(self):
        return self.shell_back_h if self.shell_back_h > 0 else self.height

    def bbox_m(self):
        pivot = self.seat_height - self.pivot_offset
        rake_over = (self.height - pivot) * math.tan(math.radians(self.backrest_rake))
        return (round(self.width, 3), round(self.depth + max(0.0, rake_over), 3),
                round(self.height, 3))

    def to_dict(self):
        d = asdict(self)
        d["bbox_m"] = self.bbox_m()
        return d


def build_armchair(spec: ArmchairSpec):
    """Devolve (parts, meta) no contrato do sofa_builder."""
    spec.validate()
    W, D, H = spec.width, spec.depth, spec.height
    aw, ah, fh = spec.arm_width, spec.arm_height, spec.foot_height
    sh, sd, ct = spec.seat_height, spec.seat_depth, spec.cushion_thickness
    st, bct = spec.shell_t, spec.back_cushion_t
    sb_h = spec.effective_shell_h()
    fab = tuple(spec.fabric_rgb)
    cush_rgb = _lighter(fab, spec.cushion_tint)          # cavidade CLARA dentro do shell
    base_rgb = _darker(fab, spec.base_shade)
    base_top = sh - ct
    pivot = sh - spec.pivot_offset
    rec = spec.base_recess
    parts = []

    # pes (4 cantos)
    foot, fi = spec.foot_side, spec.foot_inset
    for i, (fx, fy) in enumerate([(fi, fi), (W - foot - fi, fi),
                                  (fi, D - foot - fi), (W - foot - fi, D - foot - fi)]):
        parts.append(_p(f"foot_{i + 1}", "foot", fx, fy, fx + foot, fy + foot,
                        0.0, fh, spec.feet_rgb))

    # base/plataforma sob o assento (recuada na frente)
    parts.append(_p("base", "base", aw, rec, W - aw, D - st, fh, base_top, base_rgb))

    # SHELL — costas full-width (os bracos encostam nela: U continuo)
    parts.append(_p("shell_back", "back_cushion", 0.0, D - st, W, D, fh, sb_h, fab))

    # SHELL — bracos + ombros (abraco lateral)
    shoulder_h = sh + spec.wrap_frac * (sb_h - sh)
    cap_t, cap_over = spec.arm_cap_t, spec.arm_cap_over
    for side, (x0a, x1a) in (("left", (0.0, aw)), ("right", (W - aw, W))):
        body_z1 = ah - (cap_t if spec.arm_cap else 0.0)
        parts.append(_p(f"arm_{side}", "arm", x0a, 0.0, x1a, D - st, fh, body_z1, fab))
        if spec.arm_cap:
            parts.append(_p(f"arm_{side}_cap", "arm", x0a - cap_over, 0.0 - cap_over,
                            x1a + cap_over, D - st + cap_over, body_z1, ah, fab))
        if shoulder_h > ah + spec.shoulder_min_rise:
            parts.append(_p(f"arm_{side}_shoulder", "arm",
                            x0a, D - st - spec.shoulder_len, x1a, D - st,
                            ah, shoulder_h, fab))

    # CAVIDADE — almofadas internas (mais claras)
    seat_back = D - st - bct
    seat_front = seat_back - sd
    over = spec.seat_overhang
    parts += _seat_row("seat_cushion", "seat", aw, W - aw,
                       seat_front - over, seat_back, base_top, sh, 1, 0.0,
                       cush_rgb, bevel=spec.cushion_bevel)
    bi = spec.back_cushion_inset
    parts.append(_p("back_cushion", "back_cushion", aw + bi, seat_back,
                    W - aw - bi, D - st, pivot, H, cush_rgb))

    # rake: shell_back + almofada do encosto cisalham juntos (mesma inclinacao)
    rake = math.radians(spec.backrest_rake or 0.0)
    if rake:
        k = math.tan(rake)
        for p in parts:
            if p["label"] in ("shell_back", "back_cushion"):
                v = _shear_y(p, k, pivot)
                p["verts8"] = v
                ys = [c[1] for c in v]
                p["y0"], p["y1"] = round(min(ys), 4), round(max(ys), 4)

    meta = {"type": "armchair", "n_parts": len(parts), "bbox_m": spec.bbox_m(),
            "front_axis": "-Y", "kinds": sorted({p["kind"] for p in parts})}
    return parts, meta
