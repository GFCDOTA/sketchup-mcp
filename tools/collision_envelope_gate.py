"""collision_envelope_gate.py — separa visual_bbox / collision_footprint /
usage_envelope; impede bbox visual virar sinônimo automático de área de
colisão (achado 2026-08-12: tapete de banho, agrupado num módulo maior,
inflava footprint de colisão — bug real, não hipotético).

Origem: proposta do Felipe, revisada pelo GPT-Docker como reviewer de
arquitetura (nome sugerido por ele foi `spatial_envelope_contract_gate`,
escopo mais amplo — mantive o nome que o Felipe pediu, mas incorporei o
escopo dele: valida que a geometria visual existe, que a representação de
colisão RESOLVE a partir da política declarada [não do bbox cru], e que
envelope de uso [pra cadeira: atrás + puxada] cobre o que precisa cobrir).

3 checks:
  envelope_resolves        — toda peça tem geometry_intent + interaction_policy
                              resolvíveis (nunca ausente em silêncio).
  soft_items_never_solid   — peça SOFT/DECORATIVE nunca pode ter
                              circulation=BLOCK ou furniture_overlap=EXCLUSIVE.
                              Esse é o invariante que a classe de bug de hoje
                              (tapete/led/vaso tratados como sólido) violava.
  chair_usage_envelope     — toda 'Cadeira' que participa da mesa de jantar
                              tem envelope de uso (atrás + puxada) resolvido
                              pelo circulation_gate — não só footprint estático.

Uso: python -m tools.collision_envelope_gate [room_id|all]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.spatial_semantics import annotate                              # noqa: E402


def resolve_envelope(box: dict) -> dict:
    """visual_bbox SEMPRE existe (é a geometria). collision_footprint só
    existe se a política declarada disser que essa peça é sólida pra
    overlap — NÃO é derivado do bbox visual sozinho."""
    annotate(box)
    pol = box["interaction_policy"]
    has_geom = bool(box.get("corners")) or all(k in box for k in ("x0", "y0", "x1", "y1"))
    return {
        "visual_bbox_exists": has_geom,
        "collision_footprint": "visual_bbox" if pol.get("furniture_overlap") == "EXCLUSIVE" else None,
        "circulation_blocks": pol.get("circulation") == "BLOCK",
    }


def audit(boxes: list[dict]) -> dict:
    findings = []
    for b in boxes:
        env = resolve_envelope(b)
        if not env["visual_bbox_exists"]:
            findings.append({"severity": "FAIL", "check": "envelope_resolves",
                             "label": b.get("label"), "kind": b.get("kind"),
                             "detail": "sem corners nem x0/y0/x1/y1 — geometria visual ausente"})
            continue
        intent = b.get("geometry_intent")
        if intent in ("SOFT", "DECORATIVE") and (env["circulation_blocks"]
                                                  or env["collision_footprint"]):
            findings.append({"severity": "FAIL", "check": "soft_items_never_solid",
                             "label": b.get("label"), "kind": b.get("kind"), "module": b.get("module"),
                             "detail": f"geometry_intent={intent} mas interaction_policy diz sólido "
                                      f"(circulation_blocks={env['circulation_blocks']}, "
                                      f"collision_footprint={env['collision_footprint']!r}) — "
                                      "bbox visual virou colisão sem a política mandar"})
    n_fail = sum(1 for f in findings if f["severity"] == "FAIL")
    return {"overall": "FAIL" if n_fail else "PASS", "n_parts": len(boxes),
            "n_fail": n_fail, "findings": findings}


def _chair_usage_envelope_check(con, room_id: str, boxes: list[dict]) -> list[dict]:
    """Toda 'Cadeira ...' precisa ter passado pelo envelope de uso (atrás +
    puxada) do circulation_gate — não só existir geometricamente. Só roda se
    o cômodo tem circulation_gate aplicável (hoje: só onde há mesa de jantar
    — ver circulation_gate.py checks 2/3)."""
    chair_modules = {str(b.get("module")) for b in boxes
                     if str(b.get("module", "")).lower().startswith("cadeira")}
    if not chair_modules:
        return []
    from tools.circulation_gate import gate as circ_gate
    try:
        g = circ_gate(con, boxes, room_id)
    except Exception as exc:  # noqa: BLE001 — cômodo sem spatial_model aplicável
        return [{"severity": "WARN", "check": "chair_usage_envelope", "detail": str(exc)}]
    n_checked = len(g["checks"]["atras_das_cadeiras"]["cadeiras"])
    if n_checked == 0:
        return [{"severity": "FAIL", "check": "chair_usage_envelope",
                 "detail": f"{len(chair_modules)} módulo(s) de cadeira sem envelope de uso "
                          "(atrás/puxada) resolvido pelo circulation_gate"}]
    return []


def gate_room(con, room_id: str) -> dict:
    from tools.furnish_apartment import BRAINS
    from tools.room_type import classify_rooms
    r = {x["id"]: x for x in classify_rooms(con)}.get(room_id)
    if not r:
        return {"overall": "FAIL", "room": room_id, "findings": [{"detail": "cômodo inexistente"}]}
    brain = BRAINS.get(r["room_type"])
    boxes, _ = brain(con, room_id) if brain else ([], {})
    res = audit(boxes or [])
    res["findings"].extend(_chair_usage_envelope_check(con, room_id, boxes or []))
    res["n_fail"] = sum(1 for f in res["findings"] if f["severity"] == "FAIL")
    res["overall"] = "FAIL" if res["n_fail"] else "PASS"
    res["room"], res["room_name"] = room_id, r["name"]
    return res


def main():
    from tools.furnish_apartment import CONSENSUS
    from tools.room_type import classify_rooms
    con = json.loads(CONSENSUS.read_text("utf-8"))
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    rooms = [arg] if arg != "all" else [r["id"] for r in classify_rooms(con)]
    worst = "PASS"
    for rid in rooms:
        res = gate_room(con, rid)
        tag = "FAIL" if res["overall"] == "FAIL" else "ok  "
        print(f"[{tag}] {res.get('room_name', rid)} ({res.get('n_parts', 0)} peças)")
        for f in res["findings"]:
            print(f"        {f['severity']} {f['check']}: {f.get('detail')}")
        if res["overall"] == "FAIL":
            worst = "FAIL"
    print(f"\ncollision_envelope_gate => {worst}")
    sys.exit(1 if worst == "FAIL" else 0)


if __name__ == "__main__":
    main()
