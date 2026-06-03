"""Micro-fixture do kitchen_wall_regression_gate (Felipe 2026-06-02).

Prova: passagem preservada passa; parede SOLIDA nova fechando o vao FALHA;
parede nova que hospeda abertura (porta/janela) NAO falha (tem passagem).
"""
from __future__ import annotations

from tools.kitchen_wall_regression_gate import audit

BBOX = (0.0, 400.0, 400.0, 700.0)


def _baseline():
    # baseline known-good: parede x128 partida em dois, com GAP (passagem) y613-683
    return {"walls": [
        {"id": "w0", "orientation": "v", "start": [128, 514], "end": [128, 613]},
        {"id": "w1", "orientation": "v", "start": [128, 683], "end": [128, 695]},
    ]}


def test_passagem_preservada_passa():
    base = _baseline()
    cur = {"walls": [
        {"id": "m0", "orientation": "v", "start": [128, 514], "end": [128, 613]},
        {"id": "m1", "orientation": "v", "start": [128, 683], "end": [128, 695]},
    ], "openings": []}
    assert audit(base, cur, bbox=BBOX)["overall"] == "PASS"


def test_parede_solida_nova_fecha_passagem_falha():
    base = _baseline()
    # regressao tipo #28: merge funde os dois + o gap numa parede SOLIDA continua
    cur = {"walls": [
        {"id": "m013", "orientation": "v", "start": [128, 514], "end": [128, 695]},
    ], "openings": []}
    res = audit(base, cur, bbox=BBOX)
    assert res["overall"] == "FAIL"
    assert any(f["wall_id"] == "m013" for f in res["findings"])


def test_parede_nova_com_abertura_nao_bloqueia_passa():
    base = _baseline()
    # parede nova continua, MAS hospeda uma porta -> tem passagem, nao bloqueia
    cur = {"walls": [
        {"id": "m013", "orientation": "v", "start": [128, 514], "end": [128, 695]},
    ], "openings": [
        {"id": "d", "wall_id": "m013", "kind_v5": "interior_door", "center": [128, 648]},
    ]}
    assert audit(base, cur, bbox=BBOX)["overall"] == "PASS"
