#!/usr/bin/env python3
"""furniture_wall_gap.py — detector determinístico de "planejado mal planejado":
mede o VÃO perpendicular entre um móvel PLANEJADO (embutido) e a parede que ele
deveria encostar. Marcenaria sob medida = encostada (gap ~0); vão = erro.

Raiz do bug (bedroom_designer._place_against, ~L268): o móvel é posto a MARGIN_M=0.03
da parede (folga perpendicular) e CENTRALIZADO no trecho livre (prefer_center) — então
planejado fica com vão atrás e/ou dos lados. RL-15 (layout_rules) + este detector pegam.

Geometria axis-aligned (a planta é retilínea). Stdlib pura. Unit-agnóstico: mede no
sistema das caixas; o caller passa to_m p/ reportar em metros.
"""
from __future__ import annotations

# kinds de marcenaria PLANEJADA (embutida) que DEVEM encostar na parede.
# "corpo" é ambíguo (guarda-roupa E criado-mudo) -> desambigua por altura.
PLANNED_KINDS = {"corpo", "porta", "rodape", "bancada", "aereo", "torre", "headboard"}
WARDROBE_MIN_H_IN = 40.0   # corpo mais alto que isso = guarda-roupa (planejado); menor = criado-mudo (free-standing)


def is_planned(box) -> bool:
    k = box.get("kind")
    if k not in PLANNED_KINDS:
        return False
    if k == "corpo":                       # desambigua guarda-roupa (alto) vs criado-mudo (baixo)
        return float(box.get("h_in", 0)) >= WARDROBE_MIN_H_IN
    return True


def perp_gap(box, seg):
    """Vão perpendicular (>=0) entre a caixa e um segmento de parede AXIS-ALIGNED
    (ax,ay,bx,by), ou None se a parede não está de frente p/ a caixa (sem overlap no
    eixo paralelo). 0 = encostado/sobreposto."""
    ax, ay, bx, by = seg
    x0, y0, x1, y1 = box["x0"], box["y0"], box["x1"], box["y1"]
    if abs(ax - bx) < 1e-9:                 # parede VERTICAL em x=ax
        wlo, whi = min(ay, by), max(ay, by)
        if y1 <= wlo or y0 >= whi:          # sem overlap em Y -> não encara
            return None
        if x0 >= ax:
            return x0 - ax                  # caixa à direita da parede
        if x1 <= ax:
            return ax - x1                  # caixa à esquerda
        return 0.0                          # straddle (sobrepõe)
    if abs(ay - by) < 1e-9:                 # parede HORIZONTAL em y=ay
        wlo, whi = min(ax, bx), max(ax, bx)
        if x1 <= wlo or x0 >= whi:
            return None
        if y0 >= ay:
            return y0 - ay
        if y1 <= ay:
            return ay - y1
        return 0.0
    return None                             # parede diagonal: fora do escopo (planta retilínea)


def audit(boxes, walls, *, tol=0.02, to_m=1.0):
    """Pra cada móvel PLANEJADO, acha a parede mais perto que ele encara e mede o vão.
    Flag se vão > tol (mesma unidade das caixas). to_m converte o gap reportado p/ metros.
    Devolve findings ordenados pelo maior vão."""
    findings = []
    for b in boxes:
        if not is_planned(b):
            continue
        gaps = [g for g in (perp_gap(b, w) for w in walls) if g is not None]
        if not gaps:
            continue
        g = min(gaps)
        if g > tol:
            findings.append({"label": b.get("label"), "kind": b.get("kind"),
                             "gap_m": round(g * to_m, 3), "gap_units": round(g, 2)})
    findings.sort(key=lambda f: -f["gap_m"])
    return findings
