"""Componentes geométricos e acabamento exclusivos da sala.

Extraídos sem alterar cálculos, tamanhos, cores ou formato dos boxes.
Os imports legados permanecem disponíveis em tools.furnish_apartment.
"""
from __future__ import annotations


def _oct_in(kind, cx, cy, r_m, z0_m, h_m, rgb, module):
    """Disco octogonal flat em INCHES (cx,cy do shell) — leitura circular low-poly
    (cúpula de pendente; mesma gramática dos discos do cooktop)."""
    import math
    M2IN = 39.3700787402
    r = r_m * M2IN
    pts = [(cx + r * math.cos(a), cy + r * math.sin(a))
           for a in (math.pi / 8 + i * math.pi / 4 for i in range(8))]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return {"kind": kind, "x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys),
            "corners": [[round(px, 2), round(py, 2)] for px, py in pts],
            "h_in": round(h_m * M2IN, 2), "z0_in": round(z0_m * M2IN, 2), "rgb": rgb,
            "label": kind, "module": module, "ambiguous": False,
            # octógono (aproximação circular low-poly) — não-retangular por
            # design (cúpula/anel de pendente), não bug de rotação. Achado
            # 2026-08-12: geometry_sanity.off_axis rejeitava (decorative
            # estava False por engano; todo uso de _oct_in é decor redondo).
            "decorative": True}


def _dining_table_rect(w=1.60, d=0.90, h=0.75, top_t=0.04, top_rgb=(108, 80, 58), leg_rgb=(30, 30, 33)):
    """Mesa de jantar RETANGULAR 6 lugares (1.60x0.90 real, joelho >=0.60): tampo
    sólido nogueira + saia + 4 pernas metal inset. Metros, origem no canto."""
    from tools.rooms.shared.parts import part as _p
    lt, ins = 0.08, 0.05
    parts = [_p("top", "top", 0.0, 0.0, w, d, h - top_t, h, top_rgb)]
    parts.append(_p("apron", "saia", ins, ins, w - ins, d - ins, h - top_t - 0.10, h - top_t, leg_rgb))
    for x0, y0 in ((ins, ins), (w - ins - lt, ins), (ins, d - ins - lt), (w - ins - lt, d - ins - lt)):
        parts.append(_p("leg", "foot", x0, y0, x0 + lt, y0 + lt, 0.0, h - top_t, leg_rgb))
    return parts


def _dining_table_square(side=0.92, h=0.76, top_t=0.045, top_rgb=(96, 70, 48), leg_rgb=(30, 30, 33)):
    """Mesa de jantar QUADRADA: tampo SÓLIDO (não fatias/palito) + 4 pernas grossas +
    saia fina. Metros, origem no canto. (preferência do Felipe: quadrada/canto alemão)."""
    from tools.rooms.shared.parts import part as _p
    lt, ins = 0.07, 0.05
    parts = [_p("top", "top", 0.0, 0.0, side, side, h - top_t, h, top_rgb)]          # tampo sólido
    sa = 0.07                                                                          # saia sob o tampo
    parts.append(_p("apron", "saia", ins, ins, side - ins, side - ins, h - top_t - sa, h - top_t, leg_rgb))
    for x0, y0 in ((ins, ins), (side - ins - lt, ins), (ins, side - ins - lt), (side - ins - lt, side - ins - lt)):
        parts.append(_p("leg", "foot", x0, y0, x0 + lt, y0 + lt, 0.0, h - top_t, leg_rgb))
    return parts


def _bwg_recolor(boxes):
    """Linguagem black_wood_gold (GOLDEN_SAMPLE_004) na SALA: madeira escura coordenada +
    preto/grafite controlado + tecido escuro + tapete neutro quente + LED quente. SO cor (rgb),
    NUNCA geometria/posicao -> o layout JA validado fica intacto. Coerente com a cozinha."""
    WOOD = [108, 80, 58]
    BLACK = [44, 44, 48]
    FABRIC = [74, 72, 78]
    RUG = [140, 128, 112]
    LED = [255, 240, 212]
    bk = ("foot", "leg", "perna", "pe", "frame", "base", "soculo", "bracket", "vidro", "boca", "door")
    fk = ("cushion", "seat", "back", "arm")
    wk = ("top", "corpo", "porta", "front", "body", "plank", "panel", "shelf", "tampo", "gaveta", "board", "stem")
    for b in boxes:
        mod = str(b.get("module", "")).lower()
        kind = str(b.get("kind", "")).lower()
        if kind.startswith(("rug_", "pend_", "tv_", "painel", "almofada", "lv_led")):
            continue                                        # peças novas já nascem na paleta certa
        if "spot" in kind:
            b["rgb"] = LED                                  # spot quente
        elif "rail" in kind or "trilho" in mod:
            b["rgb"] = BLACK                                # trilho preto
        elif "tapete" in mod:
            b["rgb"] = RUG
        elif "parede" in mod or "concreto" in mod:
            b["rgb"] = BLACK                                # painel de midia DARK (nao concreto claro)
        elif "planta" in mod or "foliage" in kind or "quadro" in mod:
            continue                                        # acento (verde/arte) — mantem
        elif "sofa" in mod:
            b["rgb"] = BLACK if any(k in kind for k in bk) else FABRIC
        elif "cadeira" in mod:
            b["rgb"] = BLACK if any(k in kind for k in bk) else FABRIC   # estofado = tecido do sofá
        elif any(k in kind for k in bk):
            b["rgb"] = BLACK
        elif any(k in kind for k in wk):
            b["rgb"] = WOOD
        elif any(k in kind for k in fk):
            b["rgb"] = FABRIC
    return boxes
