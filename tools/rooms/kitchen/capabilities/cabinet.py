"""Adapter da cozinha para o gabinete parametrico compartilhado (FP-043/P6a). L1: so planeja, nunca materializa.

A cozinha so recebe a peca DEPOIS de quatro gates, nesta ordem (o primeiro que falha para os demais):
1. `hydraulic_anchor`   — `anchor_rules.validate`: a pia continua na parede OESTE do PDF, dentro da cozinha;
2. `architecture`      — a pegada do gabinete cabe na celula da cozinha e nao toca a massa das paredes;
3. `furniture_overlap` — a pegada nao se sobrepoe a nenhum movel ja planejado pelo brain da cozinha;
4. `circulation`       — as zonas de porta ficam livres e o `circulation_gate` do projeto continua PASS com a peca.

Pose, medidas e materiais vem da requisicao (sem padrao inventado). Frame do projeto: metros = pontos do consensus
x `PT_TO_M` (sem espelhar). O resultado nunca autoriza execucao: `status != "OK"` impede `require_valid`.
"""
from __future__ import annotations


from tools.rooms.shared.cabinet import plan_cabinet
from tools.rooms.shared.cabinet.plan import to_world_xy

ADAPTER_VERSION = "1.0.0"
AREA_TOL_M2 = 1e-6          # tolerancia numerica de area (ponto flutuante), nao folga de projeto


def _gate(name: str, ok: bool, detail: str) -> dict:
    return {"gate": name, "result": "PASS" if ok else "FAIL", "detail": detail}


def _boxes_for_plan(plan: dict) -> list[dict]:
    """Uma caixa por peca, no formato dos brains (cantos em polegadas no quadro do projeto)."""
    out = []
    for part in plan["parts"]:
        (x0, y0, z0), (x1, y1, z1) = part["min_m"], part["max_m"]
        corners = [[v / 0.0254 for v in to_world_xy(plan, x, y)] for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        out.append({"kind": "cabinet", "label": part["name"], "module": plan["request_id"], "room": "kitchen",
                    "corners": corners, "z0_in": (z0 + plan["pose"]["z"]) / 0.0254, "h_in": (z1 - z0) / 0.0254})
    return out


def plan_kitchen_cabinet(consensus: dict, room_id: str, request: dict) -> dict:
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    from core.scale import PT_TO_M, assert_pt_to_m_for_source
    from tools.rooms.kitchen import anchor_rules
    from tools.rooms.kitchen.layout import build_boxes
    from tools.rooms.shared.spatial_model import build_spatial_model
    from tools.sketchup.shell.build_plan_shell_skp import wall_footprint
    from tools.validation import circulation_gate

    plan = plan_cabinet(request)
    plan["adapter"] = {"room": "kitchen", "room_id": room_id, "version": ADAPTER_VERSION}
    plan["gates"] = []
    if plan["status"] != "OK":                                        # recusa do shared: kitchen nem olha
        return plan
    assert_pt_to_m_for_source(consensus.get("source"))                # escala errada falha alto, nao gera area errada

    def refuse(gate: dict) -> dict:
        plan["gates"].append(gate)
        plan["status"], plan["stage"] = "REFUSED", "kitchen_gate:" + gate["gate"]
        plan["findings"] = plan["findings"] + [{"code": "KITCHEN_GATE_FAILED", "detail": f"{gate['gate']}: {gate['detail']}"}]
        return plan

    anchor = anchor_rules.validate(consensus, room_id)
    if anchor["result"] != "PASS":
        return refuse(_gate("hydraulic_anchor", False, "ancora da pia (parede oeste) nao esta integra neste consensus"))
    plan["gates"].append(_gate("hydraulic_anchor", True, "pia na parede oeste do PDF, dentro da cozinha"))

    s = PT_TO_M
    foot_pt = Polygon([(x / s, y / s) for x, y in (to_world_xy(plan, 0, 0), to_world_xy(plan, plan["envelope_m"][0], 0),
                                                    to_world_xy(plan, plan["envelope_m"][0], plan["envelope_m"][1]),
                                                    to_world_xy(plan, 0, plan["envelope_m"][1]))])
    sm = build_spatial_model(consensus, room_id)
    cell = sm["_geom"]["cell"]
    wall_mass = unary_union([wall_footprint(w, extend_endpoints=True) for w in consensus["walls"]])
    outside = foot_pt.difference(cell).area * s * s
    in_wall = foot_pt.intersection(wall_mass).area * s * s
    if outside > AREA_TOL_M2 or in_wall > AREA_TOL_M2:
        return refuse(_gate("architecture", False, f"fora da cozinha {outside:.6f} m2; dentro de parede {in_wall:.6f} m2"))
    plan["gates"].append(_gate("architecture", True, "pegada dentro da celula da cozinha, sem tocar parede"))

    existing, _meta = build_boxes(consensus, room_id)
    existing_fp = [Polygon([(c[0] * 0.0254 / s, c[1] * 0.0254 / s) for c in b["corners"]]).buffer(0)
                   for b in existing if b.get("corners") and not b.get("decorative")]
    clash = sum(foot_pt.intersection(p).area for p in existing_fp) * s * s
    if clash > AREA_TOL_M2:
        return refuse(_gate("furniture_overlap", False, f"sobrepoe movel ja planejado em {clash:.6f} m2"))
    plan["gates"].append(_gate("furniture_overlap", True, "sem sobreposicao com a mobilia planejada da cozinha"))

    circ = sm["_geom"].get("circ") or []
    blocked = sum(foot_pt.intersection(c).area for c in circ) * s * s
    if blocked > AREA_TOL_M2:
        return refuse(_gate("circulation", False, f"invade zona de porta em {blocked:.6f} m2"))
    verdict = circulation_gate.gate(consensus, [b for b in existing if not b.get("decorative")] + _boxes_for_plan(plan), room_id)
    if verdict["result"] != "PASS":
        return refuse(_gate("circulation", False, "circulation_gate do projeto reprova com a peca"))
    plan["gates"].append(_gate("circulation", True, "zonas de porta livres e circulation_gate PASS com a peca"))
    return plan


def materialize_kitchen_cabinet(consensus: dict, room_id: str, request: dict, out_skp, *, base_skp, mode=None, su=None) -> dict:
    """Plano da cozinha (4 gates) -> `require_valid` -> materializacao numa COPIA do `base_skp` (nunca o original).

    Um gate reprovado levanta `PlanRefused` antes de qualquer SketchUp. Nao altera paredes, janelas, portas nem a mobilia
    ja planejada: so acrescenta o grupo `Cabinet_<request_id>`."""
    from tools.rooms.shared.cabinet import require_valid
    from tools.rooms.shared.cabinet import sketchup as cabinet_sketchup

    plan = plan_kitchen_cabinet(consensus, room_id, request)
    require_valid(plan)
    return {"plan": plan, "materialization": cabinet_sketchup.materialize(plan, out_skp, base_skp=base_skp, mode=mode, su=su)}
