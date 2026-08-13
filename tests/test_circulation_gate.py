"""P1 do VERDICT 6.5 (Felipe 2026-08-03): circulação COMPROVADA em produção.

"Não basta o móvel entrar geometricamente" — o gate exige 90cm contínuo entre
os portais do social, >=0.70m atrás de cada cadeira e envelope de cadeira
PUXADA sem colisão. Este teste pina que o furnish REAL passa — se uma mesa
futura voltar a bloquear o corredor, isto fica vermelho.
"""
from __future__ import annotations

import json

import pytest

from tools.circulation_gate import gate
from tools.furnish_apartment import CONSENSUS, collect_boxes


@pytest.fixture(scope="module")
def sala_gate():
    con = json.loads(CONSENSUS.read_text("utf-8"))
    boxes, _ = collect_boxes(con)
    return gate(con, boxes, "r002")


def test_circulation_passes_in_production(sala_gate):
    assert sala_gate["result"] == "PASS", sala_gate


def test_corridor_connects_all_portals(sala_gate):
    for p in sala_gate["checks"]["corredor_principal"]["portais"]:
        assert p.get("conectado"), f"portal desconectado: {p}"


def test_every_chair_has_room_behind(sala_gate):
    cad = sala_gate["checks"]["atras_das_cadeiras"]["cadeiras"]
    assert cad, "gate sem cadeiras — mesa sumiu?"
    for c in cad:
        # atras_ok é o veredito CALIBRADO do gate (a métrica é medida de um ponto
        # 0.25m atrás do encosto — 0.59 medido = 0.84 real de folga)
        assert c["atras_ok"], f"sem folga atrás: {c}"
        assert c["puxada_ok"], f"cadeira não puxa: {c}"


def test_portal_role_is_explicit_not_inferred(sala_gate):
    # achado 2026-08-12 (revisão GPT-Docker): portal_role vem do PAPEL
    # arquitetônico da abertura (kind_v5), nunca da largura medida. A varanda
    # (glazed_balcony, destino terminal) tem que ser SECONDARY mesmo tendo
    # 1.0m de largura vazia (mais larga que qualquer porta PRIMARY da sala).
    portais = sala_gate["checks"]["corredor_principal"]["portais"]
    for p in portais:
        assert p.get("portal_role") in ("PRIMARY", "SECONDARY"), f"portal sem role: {p}"
    varanda = [p for p in portais if p.get("w_empty_m") == 1.0]
    assert varanda and varanda[0]["portal_role"] == "SECONDARY", \
        "varanda (maior largura vazia) deveria ser SECONDARY (destino terminal), não PRIMARY"
