"""Adapter da cozinha para a porta Shaker compartilhada (FP-046/P4). L1: so planeja, nunca materializa.

A cozinha so recebe a Shaker DEPOIS de dois blocos de gates, nesta ordem (o primeiro que falha para os demais):
1. o gabinete PAI passa pelos 4 gates do adapter de frentes lisas (`plan_kitchen_cabinet`: ancora hidraulica, arquitetura,
   mobilia planejada, circulacao) — reutilizado SEM alteracao; o fluxo de frentes lisas nao muda;
2. a composicao FINAL (pai sem a frente substituida + as 5 pecas Shaker) repete ancora, arquitetura, sobreposicao com a mobilia
   planejada e `circulation_gate`, porque o que o SketchUp vai receber e essa composicao, nao o pai.
A Shaker ocupa o mesmo envelope da frente que substitui, entao os gates 2 normalmente repetem o resultado do pai; rodam mesmo assim
(um recuo ou uma peca nova nao podem escapar so porque o pai passou).

O resultado nunca autoriza execucao: `shaker_plan.status != "OK"` impede `require_valid_shaker`. Este adapter NAO promove nada:
o binding `bind.kitchen.shaker` segue sem capability no catalogo (D46-09) e `specialists.plan` continua `BLOCKED_CAPABILITY_MISSING`.
"""
from __future__ import annotations

from tools.rooms.shared.cabinet.plan import to_world_xy
from tools.rooms.shared.cabinet.shaker import plan_shaker_door

from .cabinet import AREA_TOL_M2, _boxes_for_plan, _gate, plan_kitchen_cabinet

ADAPTER_VERSION = "1.0.0"
SCHEMA = "kitchen_shaker_plan.v1"


def _part_polygons(plan: dict, parts: list[dict], scale: float):
    """Pegada (pontos do consensus) de cada peca no quadro do projeto."""
    from shapely.geometry import Polygon

    out = []
    for p in parts:
        (x0, y0, _), (x1, y1, _) = p["min_m"], p["max_m"]
        out.append(Polygon([(x / scale, y / scale) for x, y in (to_world_xy(plan, x0, y0), to_world_xy(plan, x1, y0),
                                                                 to_world_xy(plan, x1, y1), to_world_xy(plan, x0, y1))]))
    return out


def composed_gates(consensus: dict, room_id: str, parent: dict, shaker: dict) -> list[dict]:
    """Gates da composicao final; devolve a lista de gates ate o primeiro que falha (inclusive)."""
    from shapely.ops import unary_union

    from core.scale import PT_TO_M, assert_pt_to_m_for_source
    from tools.rooms.kitchen import anchor_rules
    from tools.rooms.kitchen.layout import build_boxes
    from tools.rooms.shared.spatial_model import build_spatial_model
    from tools.sketchup.shell.build_plan_shell_skp import wall_footprint
    from tools.validation import circulation_gate

    assert_pt_to_m_for_source(consensus.get("source"))
    gates: list[dict] = []
    s = PT_TO_M

    if anchor_rules.validate(consensus, room_id)["result"] != "PASS":
        return gates + [_gate("hydraulic_anchor", False, "ancora da pia (parede oeste) nao esta integra neste consensus")]
    gates.append(_gate("hydraulic_anchor", True, "pia na parede oeste do PDF, dentro da cozinha"))

    polys = _part_polygons(shaker, shaker["parts"], s)
    sm = build_spatial_model(consensus, room_id)
    cell = sm["_geom"]["cell"]
    wall_mass = unary_union([wall_footprint(w, extend_endpoints=True) for w in consensus["walls"]])
    outside = sum(p.difference(cell).area for p in polys) * s * s
    in_wall = sum(p.intersection(wall_mass).area for p in polys) * s * s
    if outside > AREA_TOL_M2 or in_wall > AREA_TOL_M2:
        return gates + [_gate("architecture", False, f"pecas Shaker fora da cozinha {outside:.6f} m2; dentro de parede {in_wall:.6f} m2")]
    gates.append(_gate("architecture", True, "pecas Shaker dentro da celula da cozinha, sem tocar parede"))

    existing, _meta = build_boxes(consensus, room_id)
    from shapely.geometry import Polygon
    existing_fp = [Polygon([(c[0] * 0.0254 / s, c[1] * 0.0254 / s) for c in b["corners"]]).buffer(0)
                   for b in existing if b.get("corners") and not b.get("decorative")]
    clash = sum(p.intersection(e).area for p in polys for e in existing_fp) * s * s
    if clash > AREA_TOL_M2:
        return gates + [_gate("furniture_overlap", False, f"pecas Shaker sobrepoem movel ja planejado em {clash:.6f} m2")]
    gates.append(_gate("furniture_overlap", True, "sem sobreposicao com a mobilia planejada da cozinha"))

    blocked = sum(p.intersection(c).area for p in polys for c in (sm["_geom"].get("circ") or [])) * s * s
    if blocked > AREA_TOL_M2:
        return gates + [_gate("circulation", False, f"pecas Shaker invadem zona de porta em {blocked:.6f} m2")]
    kept = {"parts": [p for p in parent["parts"] if p["id"] != shaker["replaces_part"]], "pose": parent["pose"],
            "request_id": parent["request_id"]}
    composed = [b for b in existing if not b.get("decorative")] + _boxes_for_plan(kept) + _boxes_for_plan(shaker)
    if circulation_gate.gate(consensus, composed, room_id)["result"] != "PASS":
        return gates + [_gate("circulation", False, "circulation_gate do projeto reprova com a composicao final")]
    gates.append(_gate("circulation", True, "zonas de porta livres e circulation_gate PASS com a composicao final"))
    return gates


def plan_kitchen_shaker(consensus: dict, room_id: str, cabinet_request: dict, shaker_request: dict) -> dict:
    """{"parent_plan", "shaker_plan", "gates", "status", "stage"}. So `status == "OK"` pode seguir para a materializacao."""
    parent = plan_kitchen_cabinet(consensus, room_id, cabinet_request)       # 4 gates do pai, codigo existente intacto
    out = {"schema_version": SCHEMA, "adapter": {"room": "kitchen", "room_id": room_id, "version": ADAPTER_VERSION},
           "parent_plan": parent, "shaker_plan": None, "gates": [], "status": "OK", "stage": "plan",
           "execution_authorized": False}
    if parent["status"] != "OK":
        out.update(status="REFUSED", stage="parent_cabinet:" + str(parent.get("stage")))
        return out
    shaker = plan_shaker_door(shaker_request, parent)
    out["shaker_plan"] = shaker
    if shaker["status"] != "OK":
        out.update(status="REFUSED", stage="shaker_plan:" + str(shaker.get("stage")))
        return out
    gates = composed_gates(consensus, room_id, parent, shaker)
    out["gates"] = shaker["gates"] = gates
    shaker["adapter"] = out["adapter"]
    failed = next((g for g in gates if g["result"] != "PASS"), None)
    if failed is not None:
        shaker["status"], shaker["stage"] = "REFUSED", "kitchen_gate:" + failed["gate"]
        shaker["findings"] = shaker["findings"] + [{"code": "KITCHEN_GATE_FAILED", "detail": f"{failed['gate']}: {failed['detail']}"}]
        out.update(status="REFUSED", stage=shaker["stage"])
    return out
