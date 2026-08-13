"""optimizer_consistency_gate.py — garante que optimizer (busca de posição) e
CI nunca divergem: "posição parece boa" (heurística/proxy) != "posição É boa"
(gate canônico). Achado 2026-08-12, consulta GPT-Docker: provenance sozinha
NÃO PROVA nada — só responde "como essa posição foi escolhida?", não "essa
posição ainda é válida?". A 2ª pergunta SEMPRE precisa ser respondida pela
execução ATUAL do gate canônico contra o estado FINAL — nunca por confiar no
resultado gravado no momento da escolha (podia ter sido invalidado por algo
colocado DEPOIS no mesmo cômodo).

3 camadas (GPT-Docker):
  1. implementação canônica única — optimizer e CI importam a MESMA função
     (tools.circulation_gate.gate); nunca reimplementada em paralelo. Este
     gate verifica isso lendo out["placement_decisions"][i]["canonical_gate"].
  2. provenance persistida — candidate_id/optimizer/canonical_gate/gate_result/
     score, gravada em furnish_apartment.py no momento da escolha.
  3. CI REAVALIA — este gate roda circulation_gate.gate() de novo no estado
     FINAL (todos os móveis já colocados) e compara com o que a provenance
     disse. Divergência (provenance disse PASS, reavaliação diz FAIL) = FAIL
     duro — é exatamente "optimizer aprovou, CI reprovou" acontecendo de novo.

Uso: python -m tools.optimizer_consistency_gate [room_id|all]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_EXPECTED_CANONICAL_GATE_PREFIX = "circulation_gate.py::gate"


def evaluate_decisions(con, room_id: str, boxes: list[dict], decisions: list[dict],
                       circulation_gate_fn=None) -> list[dict]:
    """Núcleo puro (testável por injeção de circulation_gate_fn — achado
    2026-08-12: sem isso, testar a divergência exige monkeypatch de import
    dentro de função, frágil). Devolve findings (lista, pode ser vazia)."""
    if circulation_gate_fn is None:
        from tools.circulation_gate import gate as circulation_gate_fn
    findings = []
    for d in decisions:
        cg = str(d.get("canonical_gate", ""))
        if not cg.startswith(_EXPECTED_CANONICAL_GATE_PREFIX):
            findings.append({"severity": "FAIL", "check": "canonical_gate_declared",
                             "candidate_id": d.get("candidate_id"),
                             "detail": f"canonical_gate={cg!r} não é o gate canônico esperado "
                                      f"({_EXPECTED_CANONICAL_GATE_PREFIX}*) — optimizer pode "
                                      "estar usando proxy/heurística em vez do gate real"})
            continue
        if d.get("gate_result") == "OMITTED_NO_VALID_CANDIDATE":
            continue    # honesto: optimizer decidiu NÃO colocar, nada pra reavaliar
        # CAMADA 3 — reavalia o CANÔNICO contra o estado FINAL (todos os
        # móveis já colocados), não confia no gate_result gravado na escolha.
        live = circulation_gate_fn(con, boxes, room_id)
        recorded_ok = d.get("gate_result") == "PASS"
        live_ok = live["result"] == "PASS"
        if recorded_ok and not live_ok:
            findings.append({"severity": "FAIL", "check": "optimizer_ci_divergence",
                             "candidate_id": d.get("candidate_id"),
                             "detail": f"provenance disse gate_result=PASS na escolha, mas "
                                      f"reavaliação no estado final diz {live['result']} — "
                                      "optimizer e CI DIVERGIRAM (a classe de bug que este "
                                      "gate existe pra pegar)"})
    return findings


def gate_room(con, room_id: str) -> dict:
    from tools.furnish_apartment import BRAINS
    from tools.room_type import classify_rooms
    r = {x["id"]: x for x in classify_rooms(con)}.get(room_id)
    if not r:
        return {"overall": "FAIL", "room": room_id, "findings": [{"detail": "cômodo inexistente"}]}
    brain = BRAINS.get(r["room_type"])
    if brain is None:
        return {"overall": "PASS", "room": room_id, "room_name": r["name"],
                "findings": [], "n_decisions": 0,
                "note": "sem brain — não aplicável"}
    boxes, out = brain(con, room_id)
    decisions = out.get("placement_decisions") or []
    if not decisions:
        # GAP HONESTO (achado 2026-08-12): hoje só a sala (mesa de jantar +
        # mesa de centro) tem busca de posição validada pelo gate canônico
        # DURANTE a escolha. Quarto/cozinha/banheiro ainda não — não é FAIL
        # (esses cômodos podem genuinamente não ter busca de posição, ex.
        # bancada de cozinha é ancorada por regra fixa, não busca), mas fica
        # registrado pra visibilidade, não escondido.
        return {"overall": "PASS", "room": room_id, "room_name": r["name"],
                "findings": [], "n_decisions": 0,
                "note": "nenhuma placement_decision registrada — ou não há busca "
                        "de posição nesse cômodo, ou o optimizer ainda não migrou "
                        "pro contrato de provenance (ver HANDOFF.md)"}
    findings = evaluate_decisions(con, room_id, boxes, decisions)
    n_fail = sum(1 for f in findings if f["severity"] == "FAIL")
    return {"overall": "FAIL" if n_fail else "PASS", "room": room_id, "room_name": r["name"],
            "findings": findings, "n_decisions": len(decisions)}


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
        note = f" — {res['note']}" if res.get("note") else ""
        print(f"[{tag}] {res.get('room_name', rid)} ({res.get('n_decisions', 0)} decisões){note}")
        for f in res.get("findings", []):
            print(f"        {f['severity']} {f['check']}: {f.get('detail')}")
        if res["overall"] == "FAIL":
            worst = "FAIL"
    print(f"\noptimizer_consistency_gate => {worst}")
    sys.exit(1 if worst == "FAIL" else 0)


if __name__ == "__main__":
    main()
