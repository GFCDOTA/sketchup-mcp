"""FP-047/F3: gates L1 de parede, giro de porta e circulacao rodados SOBRE o snapshot, comparados antes x depois.

Reutiliza os gates existentes sem alterar semantica nem limiar (R-13): `room_collisions.audit` (FURNITURE/FIXTURE na parede,
FURNITURE/FIXTURE/DECORATIVE no giro, com Z e excecoes de hospedagem/walkable) e `circulation_gate.gate` por comodo do consensus.

Politica: o que importa para a regressao e o que a mudanca INTRODUZ. Achado que ja existia na base e continua igual e
`preexisting` (listado, nunca escondido, nao reprova a mudanca); achado novo ou pior e `introduced` e reprova (R-07, R-08).
Erro de um gate e achado (`GATE_ERROR`), nunca omissao.
"""
from __future__ import annotations

import copy

WORSEN_EPS = 0.1                    # cm2 / contagem: abaixo disto e ruido de arredondamento do relatorio (round(...,1))


def run(consensus: dict, boxes: list[dict]) -> dict:
    """{"findings": {chave: {"gate","room","metric","detail"}}, "rooms_checked": [...]}; nao altera `boxes` (copia)."""
    from tools.validation import circulation_gate, room_collisions

    boxes = copy.deepcopy(boxes)
    findings: dict[str, dict] = {}

    for room, data in sorted(room_collisions.audit(consensus, boxes).items()):
        for hit in data["wall_penetration"]:
            findings[f"WALL|{room}|{hit['module']}|{hit['label']}"] = {
                "gate": "wall_penetration", "room": room, "metric": hit["area_cm2"], "detail": hit}
        for hit in data["door_swing_hits"]:
            findings[f"DOOR|{room}|{hit['door']}|{hit['module']}|{hit['label']}"] = {
                "gate": "door_swing", "room": room, "metric": hit["area_cm2"], "detail": hit}

    checked = []
    for room in consensus.get("rooms", []):
        rid = room["id"]
        checked.append(rid)
        try:
            result = circulation_gate.gate(consensus, boxes, rid)
        except Exception as exc:                       # noqa: BLE001 - gate quebrado e achado, nao omissao
            findings[f"GATE_ERROR|{rid}|circulation"] = {"gate": "circulation", "room": room.get("name", rid), "metric": None,
                                                         "detail": f"{type(exc).__name__}: {str(exc)[:120]}"}
            continue
        for name, check in sorted(result["checks"].items()):
            if check.get("result") == "PASS":
                continue
            failing = [p for p in check.get("portais", []) if str(p.get("status", "PASS")).startswith("FAIL")]
            findings[f"CIRC|{rid}|{name}"] = {
                "gate": "circulation", "room": result.get("room") or room.get("name", rid),
                "metric": float(len(failing) or 1), "detail": {"result": check.get("result"), "failing_portals": failing}}
    return {"findings": findings, "rooms_checked": checked}


def delta(before: dict, after: dict) -> dict:
    """introduced = novo ou pior; preexisting = igual na base; resolved = sumiu."""
    b, a = before["findings"], after["findings"]
    introduced, preexisting = [], []
    for key, now in sorted(a.items()):
        was = b.get(key)
        if was is None:
            introduced.append({"key": key, "why": "NEW", **_brief(now)})
        elif (now["metric"] or 0.0) > (was["metric"] or 0.0) + WORSEN_EPS:
            introduced.append({"key": key, "why": "WORSE", "was": was["metric"], **_brief(now)})
        else:
            preexisting.append({"key": key, **_brief(now)})
    resolved = [{"key": k, **_brief(v)} for k, v in sorted(b.items()) if k not in a]
    return {"state": "FAIL" if introduced else "PASS", "introduced": introduced, "preexisting": preexisting, "resolved": resolved,
            "rooms_checked": {"before": before["rooms_checked"], "after": after["rooms_checked"]}}


def _brief(f: dict) -> dict:
    return {"gate": f["gate"], "room": f["room"], "metric": f["metric"]}
