"""FP-056 P4a (contrato 2): apoio fisico declarado por peca, medido na proposta. Nao muda geometria nem limiar."""
from __future__ import annotations

import contextlib
import io
import json

import pytest

from tools.validation.support_check import check_support

IN = 39.3700787402


def box(kind, module, z0_m, z1_m, x0=0.0, x1=0.6, room="R"):
    return {"kind": kind, "module": module, "room": room, "z0_in": z0_m * IN, "h_in": (z1_m - z0_m) * IN,
            "corners": [[x0 * IN, 0], [x1 * IN, 0], [x1 * IN, 0.4 * IN], [x0 * IN, 0.4 * IN]]}


COUNTER = box("tampo", "Bancada", 0.0, 0.88, 0.0, 0.6)


def test_item_resting_on_the_counter_passes():
    assert check_support([COUNTER, box("kb_bandeja", "Enxoval", 0.88, 0.895, 0.1, 0.3)])["findings"] == []


def test_item_floating_above_the_counter_fails_with_the_measured_gap():
    f = check_support([COUNTER, box("kb_bandeja", "Enxoval", 0.90, 0.915, 0.1, 0.3)])["findings"]
    assert [(x["code"], x["gap_m"]) for x in f] == [("FLOATING", 0.02)]


def test_item_with_no_declared_support_underneath_fails_not_assumed():
    f = check_support([COUNTER, box("kb_bandeja", "Enxoval", 0.88, 0.895, 2.0, 2.2)])["findings"]
    assert [x["code"] for x in f] == ["NO_SUPPORT"]


def test_projection_beyond_the_support_top_is_an_overhang():
    f = check_support([COUNTER, box("kb_bandeja", "Enxoval", 0.88, 0.895, 0.5, 0.9)])["findings"]
    assert [x["code"] for x in f] == ["OVERHANG"]


def test_contact_within_eps_is_support_and_kinds_without_declaration_are_not_judged():
    ok = check_support([COUNTER, box("kb_bandeja", "Enxoval", 0.8802, 0.895, 0.1, 0.3), box("kb_x", "Z", 5.0, 5.1)])
    assert ok["findings"] == [] and ok["checked"] == 1


# Retrato medido em 2026-10-24 (develop@b60dc14): o tampo termina em 0,88 m e o enxoval foi posto em 0,90/0,915.
# Defeito conhecido R4 (FP-056 P4): nao se corrige aqui (mudaria a aparencia, exige o Felipe) e nao pode PIORAR nem
# ganhar item novo. Quando for corrigido, a entrada sai desta tabela.
KNOWN = {("LAVABO", "Enxoval kb_bandeja"): 0.0198, ("BANHO 01", "Enxoval kb_sabonete"): 0.0348,
         ("BANHO 02", "Enxoval kb_sabonete"): 0.0348}


@pytest.mark.planta74_scale
def test_planta74_floating_accessories_are_exactly_the_known_baseline_and_none_got_worse():
    from tools.furnish_apartment import collect_boxes
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    con = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _ = collect_boxes(con)
    got = {(f["room"], f["module"]): f["gap_m"] for f in check_support(boxes)["findings"]}
    assert set(got) <= set(KNOWN), f"defeito de apoio NOVO: {set(got) - set(KNOWN)}"
    for k, gap in got.items():
        assert gap <= KNOWN[k] + 0.0005, f"{k} piorou: {gap} > {KNOWN[k]}"
