"""Interface funcional EXPLICITA da cozinha (FP-054 F1C): a face de trabalho da bancada.

A bancada corre ao longo da parede da pia, que e ancora HIDRAULICA vinda do PDF (`anchor_rules.validate` -> `sink_wall`,
`sink_anchor_source = PDF_WEST_WALL`). A face de trabalho e o lado da bancada OPOSTO a essa parede. Nada aqui e inferido pela
pegada: sem ancora valida ou com parede fora de LEFT/RIGHT/TOP/BOTTOM a interface nao e emitida (o avaliador bloqueia).
Nao altera `kitchen.layout.build_boxes` (simbolo com prova L2) nem nenhuma caixa.
"""
from __future__ import annotations

from shapely.ops import unary_union

# lado da parede de apoio -> (lado oposto na pegada, normal da face de trabalho) em coordenadas do plano (x para a direita,
# y crescente como no consensus)
_FACE_OF_WALL = {"LEFT": ("max_x", (1.0, 0.0)), "RIGHT": ("min_x", (-1.0, 0.0)),
                 "BOTTOM": ("max_y", (0.0, 1.0)), "TOP": ("min_y", (0.0, -1.0))}
COUNTER_MODULE = "countertop"


def functional_interfaces(con: dict, room_id: str, boxes: list[dict]) -> list[dict]:
    from tools.rooms.kitchen import anchor_rules
    from tools.validation.circulation_gate import _footprint
    anchor = anchor_rules.validate(con, room_id)
    wall = (anchor.get("checks") or {}).get("sink_wall")
    if anchor.get("result") != "PASS" or wall not in _FACE_OF_WALL:
        return []
    parts = [b for b in boxes if b.get("module") == COUNTER_MODULE and b.get("corners")]
    if not parts:
        return []
    x0, y0, x1, y1 = unary_union([_footprint(b) for b in parts]).bounds
    side, normal = _FACE_OF_WALL[wall]
    seg = {"max_x": ((x1, y0), (x1, y1)), "min_x": ((x0, y0), (x0, y1)),
           "max_y": ((x0, y1), (x1, y1)), "min_y": ((x0, y0), (x1, y0))}[side]
    return [{"module": COUNTER_MODULE, "object_type": "kitchen_counter", "interface": "work_face",
             "segment_in": [[round(p[0], 3), round(p[1], 3)] for p in seg], "normal": list(normal),
             "basis": "SEMANTIC_PDF_ANCHOR", "source": "tools.rooms.kitchen.functional_interfaces (anchor_rules.validate)",
             "note": f"bancada apoiada na parede da pia ({wall}, {anchor['checks'].get('sink_anchor_source')}); "
                     "face de trabalho = lado oposto"}]
