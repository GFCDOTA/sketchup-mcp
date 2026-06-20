"""kitchen_ergonomics.py — ESPECIALISTA EM MEDIDAS / KITCHEN_DIMENSIONAL_AUDIT.

REFERENCE_PACK do Felipe (2026-06-19): a referência influencia LINGUAGEM e MEDIDA, nunca a
POSIÇÃO (pia/parede/porta = PDF). Mede a cozinha CONSTRUÍDA (constantes + boxes reais) contra
os padrões ergonômicos e reporta PASS/WARN/FAIL por métrica. NÃO altera a cozinha — só audita.

Uso: PT_TO_M=0.0259 python -m tools.kitchen_ergonomics [room_id]
"""
from __future__ import annotations

import sys
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

IN2CM = 2.54

# padrões (cm) — (min, max). Faixas do REFERENCE_PACK de medidas (Felipe).
ERGO = {
    "countertop_height": (85, 92),
    "toe_kick_height": (10, 15),
    "base_depth": (55, 60),
    "upper_depth": (30, 35),
    "upper_clearance": (50, 60),         # bancada -> base do aéreo
    "hood_clearance": (45, 65),          # cooktop -> coifa under-cabinet (tipo aprovado); chaminé seria 70-80
    "fridge_tower_width": (55, 75),      # ~60 ref; geladeira freestanding 60-75
    "fridge_vent_gap": (6, 12),          # respiro lateral TOTAL >=6cm (>=3cm/LADO, fridge.md §5). NAO afrouxar.
    "cooktop_fridge_sep": (60, 400),     # frio longe do calor (spec §0.3): cooktop<->geladeira >=60cm
    "base_module_width": (35, 65),       # módulos comuns ~60 (40/50/60 ok)
    "upper_module_width": (35, 65),
    "filler_width": (15, 18),            # quando necessário
    "sink_rim_height": (85, 92),
}


def _ext_cm(parts, axis):
    """extensão (cm) no eixo 'x0/x1' ou 'y0/y1' do conjunto de parts (corners em inches)."""
    if not parts:
        return 0.0
    lo = min(p[axis + "0"] for p in parts)
    hi = max(p[axis + "1"] for p in parts)
    return round((hi - lo) * IN2CM, 1)


def audit(room_id="r004"):
    import json
    from tools import kitchen_layout as K
    con = json.loads((ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    boxes, _ = K.build_boxes(con, room_id)
    by_mod = {}
    for b in boxes:
        by_mod.setdefault(b["module"], []).append(b)

    # parede oeste = vertical -> largura do módulo corre em y; profundidade em x
    def door_widths(mod, kinds):
        return [_ext_cm([p], "y") for p in by_mod.get(mod, []) if p["kind"] in kinds]

    base_doors = door_widths("base_cabinet_01", {"kc_porta", "kc_gaveta"})
    upper_doors = door_widths("upper_cabinet_01", {"kc_porta_sup"})
    fridge_body = [p for p in by_mod.get("fridge", []) if p["kind"] == "kc_geladeira"]
    fridge_w = _ext_cm(by_mod.get("fridge", []), "y")
    fridge_body_w = _ext_cm(fridge_body, "y") if fridge_body else fridge_w

    # separação térmica cooktop<->geladeira (frio longe do calor) — centros no eixo y (parede oeste vertical)
    def _cy(parts):
        if not parts:
            return None
        return (min(p["y0"] for p in parts) + max(p["y1"] for p in parts)) / 2
    cook_parts = [b for bs in by_mod.values() for b in bs if b["kind"] in {"kc_boca", "kc_vidro"}]
    cook_cy, fridge_cy = _cy(cook_parts), _cy(by_mod.get("fridge", []))
    cooktop_fridge_sep = round(abs(cook_cy - fridge_cy) * IN2CM, 1) if (cook_cy is not None and fridge_cy is not None) else 0.0

    measured = {
        "countertop_height": round(K.COUNTER_H * 100, 1),
        "toe_kick_height": round(K.TOE_KICK * 100, 1),
        "base_depth": round(K.COUNTER_DEPTH * 100, 1),
        "upper_depth": round(K.AEREO_DEPTH * 100, 1),
        "upper_clearance": round((K.AEREO_Z0 - K.COUNTER_H) * 100, 1),
        "hood_clearance": round(((K.AEREO_Z0 - 0.05) - (K.COOK_Z0 + 0.015)) * 100, 1),
        "fridge_tower_width": fridge_w,
        "fridge_vent_gap": round(K.GEL_W * 100 - fridge_body_w, 1),   # nicho (GEL_W) vs corpo inset = respiro real
        "cooktop_fridge_sep": cooktop_fridge_sep,
        "base_module_width": round(median(base_doors), 1) if base_doors else 0.0,
        "upper_module_width": round(median(upper_doors), 1) if upper_doors else 0.0,
        "filler_width": _ext_cm(by_mod.get("filler", []), "y"),
        "sink_rim_height": round(K.PIA_Z0 * 100, 1),
    }
    rows, worst = [], "PASS"
    rank = {"PASS": 0, "WARN": 1, "FAIL": 2}
    for key, (lo, hi) in ERGO.items():
        v = measured[key]
        if v == 0.0:
            tag = "FAIL"           # métrica não encontrada = falha de medição
        elif lo <= v <= hi:
            tag = "PASS"
        elif lo - 6 <= v <= hi + 6:
            tag = "WARN"           # perto da faixa = aviso
        else:
            tag = "FAIL"
        if rank[tag] > rank[worst]:
            worst = tag
        rows.append((key, v, lo, hi, tag))
    return worst, rows, by_mod


def main():
    room = sys.argv[1] if len(sys.argv) > 1 else "r004"
    worst, rows, _ = audit(room)
    # gates de POSIÇÃO (duros) — anexados ao relatório
    import json
    con = json.loads((ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    from tools.geometry_sanity import sanity_room
    from tools.kitchen_validation import validate
    sink_pdf = validate(con, room)["result"]
    try:
        door_clear = sanity_room(con, room)["status"]   # door-clearance da peça (NAO é circulação de corredor da cozinha)
    except Exception:  # noqa: BLE001
        door_clear = "?"

    print("KITCHEN_DIMENSIONAL_AUDIT_RESULT:")
    for key, v, lo, hi, tag in rows:
        print(f"- {key} = {v} cm  ({lo}-{hi})  {tag}")
    print(f"- sink_anchor_pdf = {sink_pdf}")
    print(f"- door_clearance = {door_clear}   # circulação de corredor real precisa da parede oposta (não modelada na cozinha isolada)")
    print(f"\nKITCHEN_DIMENSIONAL_AUDIT => {worst}")
    sys.exit(0)


if __name__ == "__main__":
    main()
