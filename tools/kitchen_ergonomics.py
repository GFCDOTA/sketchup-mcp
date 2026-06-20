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
    "hood_clearance": (45, 65),          # cooktop -> coifa (slim integrada: 45-65; range-hood tradicional: 70-80)
    "fridge_tower_width": (55, 75),      # ~60 ref; geladeira freestanding 60-75
    "fridge_vent_gap": (6, 12),          # respiro lateral TOTAL: ≥6 = 2×≥3cm/lado (fridge.md §5-6); >12 = nicho desperdiçado
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


def _center_m(parts, axis):
    """centro (m) de um módulo no eixo dado ('x'/'y'); None se vazio."""
    if not parts:
        return None
    lo = min(p[axis + "0"] for p in parts)
    hi = max(p[axis + "1"] for p in parts)
    return (lo + hi) / 2 * IN2CM / 100.0


def _top_z_m(parts, kind):
    """topo (m) das parts de um kind = max(z0_in + h_in); None se kind ausente."""
    zs = [p["z0_in"] + p["h_in"] for p in parts if p["kind"] == kind]
    return max(zs) / 39.3700787402 if zs else None


def _min_tag(v, lo):
    """rótulo (str, tag) p/ uma medida com piso mínimo: WARN se < lo, n/a se None."""
    if v is None:
        return "n/a", "?"
    return f"{v} m", ("PASS" if v >= lo else "WARN")


def module_gap_m(by_mod, mod_a, mod_b):
    """Distância centro-a-centro (m) entre dois módulos no eixo da parede oeste (y).

    A cozinha é LINEAR na parede OESTE (vertical) -> módulos correm em y (mesma
    convenção do resto do audit). None se faltar qualquer um dos módulos."""
    a = _center_m(by_mod.get(mod_a, []), "y")
    b = _center_m(by_mod.get(mod_b, []), "y")
    return None if a is None or b is None else round(abs(a - b), 2)


def work_triangle_fridge_cooktop_m(by_mod):
    """Perna geladeira↔cooktop do triângulo de trabalho (m). Ergonomia: ≥1.2 m
    (door-clearance NÃO cobre isto — é o gap que faltava no relatório)."""
    return module_gap_m(by_mod, "fridge", "cooktop_module")


def faucet_to_upper_clearance_m(by_mod, aereo_z0):
    """Folga topo-da-torneira → base do aéreo (m). Torneira gourmet alta pode bater
    no aéreo baixo (spec §8). Ergonomia: ≥0.35 m. None se torneira ausente."""
    top = _top_z_m(by_mod.get("sink_module", []), "kc_torneira")
    return None if top is None else round(aereo_z0 - top, 2)


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

    measured = {
        "countertop_height": round(K.COUNTER_H * 100, 1),
        "toe_kick_height": round(K.TOE_KICK * 100, 1),
        "base_depth": round(K.COUNTER_DEPTH * 100, 1),
        "upper_depth": round(K.AEREO_DEPTH * 100, 1),
        "upper_clearance": round((K.AEREO_Z0 - K.COUNTER_H) * 100, 1),
        "hood_clearance": round(((K.AEREO_Z0 - 0.05) - (K.COOK_Z0 + 0.015)) * 100, 1),
        "fridge_tower_width": fridge_w,
        "fridge_vent_gap": round(K.GEL_W * 100 - fridge_body_w, 1),   # respiro TOTAL = nicho(GEL_W) − corpo inset (soma dos 2 lados; /2 = por-lado)
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
    worst, rows, by_mod = audit(room)
    # gates de POSIÇÃO (duros) — anexados ao relatório
    import json
    con = json.loads((ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    from tools import kitchen_layout as K
    from tools.geometry_sanity import sanity_room
    from tools.kitchen_validation import validate
    sink_pdf = validate(con, room)["result"]
    try:
        door_clear = sanity_room(con, room)["status"]   # door-clearance (NÃO é triângulo de trabalho)
    except Exception:  # noqa: BLE001
        door_clear = "?"
    # clearances de POSIÇÃO/uso — cada um separado do door-clearance (eixo da parede / alturas)
    tri_str, tri_tag = _min_tag(work_triangle_fridge_cooktop_m(by_mod), 1.2)          # triângulo de trabalho
    cook_sink_str, cook_sink_tag = _min_tag(module_gap_m(by_mod, "cooktop_module", "sink_module"), 0.5)  # térmico/respingo
    faucet_str, faucet_tag = _min_tag(faucet_to_upper_clearance_m(by_mod, K.AEREO_Z0), 0.35)             # torneira gourmet x aéreo

    print("KITCHEN_DIMENSIONAL_AUDIT_RESULT:")
    for key, v, lo, hi, tag in rows:
        print(f"- {key} = {v} cm  ({lo}-{hi})  {tag}")
    print(f"- sink_anchor_pdf = {sink_pdf}")
    print(f"- door_clearance = {door_clear}")
    print(f"- work_triangle_fridge_cooktop = {tri_str}  (>=1.2 m)  {tri_tag}")
    print(f"- cooktop_sink_separation = {cook_sink_str}  (>=0.5 m)  {cook_sink_tag}")
    print(f"- faucet_to_upper_clearance = {faucet_str}  (>=0.35 m)  {faucet_tag}")
    print(f"\nKITCHEN_DIMENSIONAL_AUDIT => {worst}")
    sys.exit(0)


if __name__ == "__main__":
    main()
