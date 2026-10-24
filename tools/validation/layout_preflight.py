"""layout_preflight.py — pre-voo OBRIGATORIO do layout antes de materializar (FP-054 F1-03, R-04 / #381).

`collect_boxes` junta o que cada brain de comodo devolve; so a sala chama o gate de circulacao e ninguem roda a sobreposicao
antes do SketchUp. Este pre-voo roda, para cada comodo que recebeu movel:

  - `circulation_gate.gate` (corredor entre portais + cadeiras), com o contrato tipado da F1-01;
  - a sobreposicao movel-sobre-movel do comodo (`furniture_overlap_gate.pairwise_overlap`, mesmo nucleo do gate MCP);
  - movel dentro de parede, sobre guarda-corpo/peitoril (FP-056 #434) e no giro de porta (`room_collisions.audit`, o mesmo da regressao FP-047) — acrescentado depois que
    uma variante da Suite 01 (#381) punha o criado-mudo 1,8 dm2 dentro da parede e passava;

e agrega por `core.constraint_result.combine`. Quem materializa so segue com PASS ou NOT_APPLICABLE. Gate que quebra (excecao)
vira BLOCKED_MISSING_INPUT com o erro — achado, nunca omissao. Nenhum limiar e definido aqui.

Complexidade: O(R * (G + M^2)) por apartamento — R comodos mobiliados, G custo do gate de circulacao, M modulos do comodo
(o par-a-par da sobreposicao; ver R-12 da F0). Na planta_74: 8 comodos, <= 76 caixas por comodo.
"""
from __future__ import annotations

from core.constraint_result import combine

GATES = ("circulation", "furniture_overlap", "room_collisions")


def _circulation(con: dict, boxes: list[dict], room_id: str) -> tuple[str, dict]:
    from tools.validation import circulation_gate
    res = circulation_gate.gate(con, boxes, room_id)
    checks = sorted(res["checks"].items())
    blocking = {k: v.get("reason_code") for k, v in checks if v.get("result") in ("FAIL", "BLOCKED_MISSING_INPUT")}
    return res["result"], blocking or {k: v.get("reason_code") for k, v in checks if v.get("result") != "PASS"}


def _overlap(room_boxes: list[dict]) -> tuple[str, dict]:
    from tools.validation.furniture_overlap_gate import _module_geom, pairwise_overlap
    fails, warns, n_modules = pairwise_overlap(_module_geom(room_boxes))
    if n_modules < 2:                                  # sem par para comparar: nada medido nao e PASS
        return "NOT_APPLICABLE", {"modules": n_modules}
    if fails:
        return "FAIL", {"fails": fails}
    return ("WARN", {"warns": warns}) if warns else ("PASS", {})


def _collisions(audit: dict, room_name: str, n_boxes: int) -> tuple[str, dict]:
    if not n_boxes:                                    # nada no comodo para colidir: nada medido nao e PASS
        return "NOT_APPLICABLE", {"boxes": 0}
    data = audit.get(room_name) or {}
    walls = [f"{x['module']}/{x['label']} {x['area_cm2']} cm2" for x in data.get("wall_penetration", [])]
    swings = [f"{x['door']}:{x['module']}/{x['label']} {x['area_cm2']} cm2" for x in data.get("door_swing_hits", [])]
    barriers = [f"{x['barrier']}:{x['module']}/{x['label']} {x['area_cm2']} cm2" for x in data.get("barrier_penetration", [])]
    if walls or swings or barriers:
        return "FAIL", {"wall_penetration": walls, "door_swing_hits": swings, "barrier_penetration": barriers}
    return "PASS", {}


def preflight(con: dict, boxes: list[dict], rooms) -> dict:
    """rooms = resumo do `collect_boxes`: (room_id, nome, tipo, resultado, n_caixas). So comodos com caixas entram."""
    import copy

    from tools.validation import room_collisions
    rows, blocking = [], []
    try:
        audit, audit_error = room_collisions.audit(con, copy.deepcopy(boxes)), None
    except Exception as exc:  # noqa: BLE001 — vira BLOCKED por comodo abaixo
        audit, audit_error = None, f"{type(exc).__name__}: {str(exc)[:160]}"
    for room_id, name, _type, _result, n_boxes in rooms:
        if not n_boxes:
            continue
        room_boxes = [b for b in boxes if b.get("room") == str(name or room_id)]
        def collisions(name=str(name or room_id)):
            if audit_error:
                raise RuntimeError(audit_error)
            return _collisions(audit, name, len(room_boxes))
        for gate, run in (("circulation", lambda: _circulation(con, boxes, room_id)),
                          ("furniture_overlap", lambda: _overlap(room_boxes)),
                          ("room_collisions", collisions)):
            try:
                status, reasons = run()
            except Exception as exc:  # noqa: BLE001 — gate quebrado e achado: bloqueia, nao some
                status, reasons = "BLOCKED_MISSING_INPUT", {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
            row = {"room_id": room_id, "gate": gate, "status": status, "reasons": reasons}
            rows.append(row)
            if status in ("FAIL", "BLOCKED_MISSING_INPUT"):
                blocking.append(row)
    return {"status": combine(r["status"] for r in rows), "rooms": rows, "blocking": blocking}


def allows_materialization(report: dict) -> bool:
    return report["status"] in ("PASS", "NOT_APPLICABLE")
