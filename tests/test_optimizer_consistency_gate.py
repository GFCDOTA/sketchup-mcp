"""Regressão do optimizer_consistency_gate — optimizer e CI NUNCA podem
divergir (achado 2026-08-12, revisão GPT-Docker: provenance sozinha não
prova nada, só a REAVALIAÇÃO do gate canônico no estado final prova).
Hermético (usa evaluate_decisions com circulation_gate_fn injetado — não
depende do consensus real)."""
from __future__ import annotations

from tools.optimizer_consistency_gate import _EXPECTED_CANONICAL_GATE_PREFIX, evaluate_decisions

GOOD_CANONICAL = _EXPECTED_CANONICAL_GATE_PREFIX + "/test-version"


def _fake_gate(result):
    def _f(con, boxes, room_id):
        return {"result": result, "room": room_id, "checks": {}}
    return _f


def test_consistent_pass_has_no_findings():
    decisions = [{"candidate_id": "mesa", "canonical_gate": GOOD_CANONICAL,
                  "gate_result": "PASS", "score": 0}]
    findings = evaluate_decisions({}, "r002", [], decisions, circulation_gate_fn=_fake_gate("PASS"))
    assert findings == []


def test_divergence_between_recorded_and_live_fails():
    # exatamente o bug que este gate existe pra pegar: optimizer registrou
    # PASS na escolha, mas o estado FINAL do cômodo reavaliado agora falha.
    decisions = [{"candidate_id": "mesa", "canonical_gate": GOOD_CANONICAL,
                  "gate_result": "PASS", "score": 0}]
    findings = evaluate_decisions({}, "r002", [], decisions, circulation_gate_fn=_fake_gate("FAIL"))
    assert len(findings) == 1
    assert findings[0]["check"] == "optimizer_ci_divergence"


def test_recorded_fail_and_live_fail_is_not_a_new_divergence():
    # se o optimizer já sabia que não passou (gate_result != PASS), a
    # reavaliação bater FAIL de novo não é uma DIVERGÊNCIA nova — é
    # consistente (nada mudou). Só recorded=PASS -> live=FAIL é o alarme.
    decisions = [{"candidate_id": "mesa", "canonical_gate": GOOD_CANONICAL,
                  "gate_result": "FAIL", "score": 5}]
    findings = evaluate_decisions({}, "r002", [], decisions, circulation_gate_fn=_fake_gate("FAIL"))
    assert findings == []


def test_omitted_decision_never_reevaluated():
    decisions = [{"candidate_id": "mesa_de_centro", "canonical_gate": GOOD_CANONICAL,
                  "gate_result": "OMITTED_NO_VALID_CANDIDATE", "score": 3}]
    calls = []

    def _spy_gate(con, boxes, room_id):
        calls.append(1)
        return {"result": "PASS", "checks": {}}
    findings = evaluate_decisions({}, "r002", [], decisions, circulation_gate_fn=_spy_gate)
    assert findings == []
    assert calls == []   # nunca chamou o gate — nada foi colocado, nada pra reavaliar


def test_wrong_canonical_gate_is_flagged():
    # optimizer usando proxy/heuristica em vez do gate real declarado —
    # detectado SEM precisar rodar nada (contrato quebrado na origem).
    decisions = [{"candidate_id": "mesa", "canonical_gate": "some_heuristic_proxy_v1",
                  "gate_result": "PASS", "score": 0}]
    findings = evaluate_decisions({}, "r002", [], decisions, circulation_gate_fn=_fake_gate("PASS"))
    assert len(findings) == 1
    assert findings[0]["check"] == "canonical_gate_declared"
