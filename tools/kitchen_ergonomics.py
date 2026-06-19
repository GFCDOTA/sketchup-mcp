"""kitchen_ergonomics.py — ESPECIALISTA EM MEDIDAS de cozinha planejada (ergonomia).

REFERENCE_PACK do Felipe (2026-06-19): a referência visual (Pinterest etc.) influencia
LINGUAGEM e MEDIDA, nunca a POSIÇÃO (pia/parede/porta = PDF). Este módulo guarda os padrões
ergonômicos reais de marcenaria residencial e AUDITA a cozinha construída contra eles.

Uso: PT_TO_M=0.0259 python -m tools.kitchen_ergonomics
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# padrões ergonômicos (cm) — (min, max). Fonte: REFERENCE_PACK de medidas (Felipe).
ERGO = {
    "countertop_height": (88, 92),          # altura da bancada
    "toe_kick_recess": (8, 15),             # recuo do sóculo
    "tampo_thickness": (2, 4),              # espessura do tampo (borda fina)
    "upper_clearance": (50, 60),            # bancada -> base do aéreo
    "upper_height": (50, 92),               # altura do armário aéreo
    "lower_depth": (50, 60),                # profundidade do módulo inferior
    "hood_clearance_cooktop": (45, 80),     # coifa sobre cooktop (under-cabinet 45-65 / chaminé 70-80)
}


def audit():
    """Mede a cozinha (constantes do builder) contra os padrões. Devolve (result, rows)."""
    from tools import kitchen_layout as K
    cm = lambda m: round(m * 100, 1)
    counter_top = K.COUNTER_H
    measured = {
        "countertop_height": cm(K.COUNTER_H),
        "toe_kick_recess": cm(K.TOE_KICK),
        "tampo_thickness": cm(K.TAMPO_THK),
        "upper_clearance": cm(K.AEREO_Z0 - counter_top),
        "upper_height": cm(K.AEREO_H),
        "lower_depth": cm(K.COUNTER_DEPTH),
        # coifa slim fica em AEREO_Z0-0.05; topo do cooktop ~ COOK_Z0+0.015
        "hood_clearance_cooktop": cm((K.AEREO_Z0 - 0.05) - (K.COOK_Z0 + 0.015)),
    }
    rows, worst = [], "PASS"
    for key, (lo, hi) in ERGO.items():
        v = measured[key]
        if lo <= v <= hi:
            tag = "ok"
        else:
            tag = "WARN"
            worst = "WARN" if worst == "PASS" else worst
        rows.append((key, v, lo, hi, tag))
    return worst, rows


def main():
    result, rows = audit()
    print("KITCHEN_ERGONOMICS (cm):")
    for key, v, lo, hi, tag in rows:
        print(f"  [{tag:4}] {key:24} = {v:6}  (alvo {lo}-{hi})")
    print(f"\nkitchen_ergonomics => {result}")
    # WARN não derruba o build (ergonomia é guia); só informa.
    sys.exit(0)


if __name__ == "__main__":
    main()
