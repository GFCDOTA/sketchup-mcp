"""Auditoria L1 de colisao por comodo sobre os boxes PLANEJADOS (sem SketchUp): parede e giro de porta.

Mesma geometria e classificacao do `planta_check` do L2 FP-042 (que mede o `.skp` reaberto), para que o antes/depois do
planner seja reproduzivel em segundos e protegido por teste. `FURNITURE`/`FIXTURE` nao podem entrar na parede nem ficar no
giro de uma porta; pecas `STRUCTURAL` (laje/pele/teto) entram sob a parede POR DESENHO (tuck 0,4*espessura) e nao sao auditadas
aqui; piso e acabamento rente ao chao (topo <= 2 cm) sao caminhaveis.
"""
from __future__ import annotations

from collections import defaultdict

from tools.rooms.shared.clearance import EPS_AREA_PT2, box_footprint_pt, depth_cm, door_swings_pt, wall_mass_pt

IN_TO_M = 0.0254
WALKABLE_TOP_M = 0.02          # topo ate 2 cm = piso/acabamento: nao bloqueia giro de porta
DOOR_LEAF_TOP_M = 2.10         # a folha vai ate 2,10 m
AUDITED_INTENTS = ("FURNITURE", "FIXTURE")


def audit(consensus: dict, boxes: list[dict]) -> dict[str, dict[str, list[dict]]]:
    """{comodo: {"wall_penetration": [...], "door_swing_hits": [...]}} — so FURNITURE/FIXTURE (nao hospedados)."""
    from core.scale import PT_TO_IN, PT_TO_M
    walls = wall_mass_pt(consensus)
    swings = door_swings_pt(consensus)
    out: dict[str, dict[str, list[dict]]] = defaultdict(lambda: {"wall_penetration": [], "door_swing_hits": []})
    for b in boxes:
        room = str(b.get("room"))
        out[room]                                              # garante a chave mesmo sem achado
        if b.get("geometry_intent") not in AUDITED_INTENTS:
            continue
        fp = box_footprint_pt(b, PT_TO_IN)
        if fp is None or fp.is_empty:
            continue
        z0 = float(b.get("z0_in") or 0.0) * IN_TO_M
        z1 = z0 + float(b["h_in"]) * IN_TO_M
        ip = b.get("interaction_policy") or {}
        hosted = (b.get("host") or {}).get("relationship", "NONE") != "NONE" or ip.get("furniture_overlap") != "EXCLUSIVE"
        inter = fp.intersection(walls)
        if inter.area > EPS_AREA_PT2 and not hosted:
            out[room]["wall_penetration"].append({"module": b.get("module"), "label": b.get("label") or b.get("kind"),
                                                  "area_cm2": round(inter.area * PT_TO_M**2 * 1e4, 1), "depth_cm": depth_cm(inter, PT_TO_M)})
        if ip.get("circulation") != "WALKABLE" and z1 > WALKABLE_TOP_M and z0 < DOOR_LEAF_TOP_M:
            for door_id, sw in swings.items():
                hit = fp.intersection(sw)
                if hit.area * PT_TO_M**2 > 1e-4:
                    out[room]["door_swing_hits"].append({"door": door_id, "module": b.get("module"), "label": b.get("label") or b.get("kind"),
                                                         "area_cm2": round(hit.area * PT_TO_M**2 * 1e4, 1)})
    return dict(out)


def findings(consensus: dict, boxes: list[dict]) -> list[str]:
    """Lista plana e ordenada de achados (para comparar antes/depois e para mensagem de teste)."""
    rows = []
    for room, d in audit(consensus, boxes).items():
        rows += [f"{room}: parede {x['module']}/{x['label']} {x['depth_cm']} cm ({x['area_cm2']} cm2)" for x in d["wall_penetration"]]
        rows += [f"{room}: giro {x['door']} {x['module']}/{x['label']} {x['area_cm2']} cm2" for x in d["door_swing_hits"]]
    return sorted(rows)
