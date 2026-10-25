"""FP-056 P4a (contrato 2): apoio fisico declarado por peca, medido na proposta. Nao muda geometria nem limiar."""
from __future__ import annotations

import contextlib
import io
import json
import pathlib

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

# ---------------------------------------------------------------------------------------------------------------------
# P4b: apoio por MODULO (FLOOR e WALL_MOUNTED)
def _con():
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    return json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))


def mbox(module, z0_m, z1_m, cx_m, cy_m, room="R", half=0.10):
    d = half * IN
    cx, cy = cx_m * IN, cy_m * IN
    return {"kind": "k", "module": module, "room": room, "z0_in": z0_m * IN, "h_in": (z1_m - z0_m) * IN,
            "corners": [[cx - d, cy - d], [cx + d, cy - d], [cx + d, cy + d], [cx - d, cy + d]]}


def _on_wall_and_in_the_air(con):
    """(x, y) em metros de um ponto SOBRE a massa de parede e de um ponto a mais de 0,8 m de qualquer parede."""
    from core.scale import PT_TO_M
    from tools.rooms.shared.clearance import wall_mass_pt
    walls = wall_mass_pt(con)
    on = walls.representative_point()
    room = next(r for r in con["rooms"] if "SALA" in r["name"])
    from shapely.geometry import Polygon
    from shapely.ops import polylabel
    air = polylabel(Polygon(room["polygon_pts"]).difference(walls), 1.0)    # ponto mais longe de qualquer parede
    assert air.distance(walls) * PT_TO_M > 0.8
    return (on.x * PT_TO_M, on.y * PT_TO_M), (air.x * PT_TO_M, air.y * PT_TO_M)


@pytest.mark.planta74_scale
def test_floor_module_off_the_floor_fails_and_one_resting_on_it_passes():
    from tools.validation.support_check import check_modules
    con = _con()
    rep = check_modules([mbox("Cama", 0.05, 0.6, 1, 1), mbox("Sofa", 0.0003, 0.8, 3, 3)], con)
    assert [(f["module"], f["code"], f["gap_m"]) for f in rep["findings"]] == [("Cama", "NOT_ON_FLOOR", 0.05)]
    assert rep["evaluated"] == 2 and rep["undeclared"] == []


@pytest.mark.planta74_scale
def test_wall_mounted_module_must_touch_the_wall_and_the_gap_is_measured():
    from tools.validation.support_check import check_modules
    con = _con()
    (wx, wy), (ax, ay) = _on_wall_and_in_the_air(con)
    ok = check_modules([mbox("Espelho", 1.0, 1.6, wx, wy)], con)
    assert ok["findings"] == []
    bad = check_modules([mbox("Espelho", 1.0, 1.6, ax, ay)], con)
    assert [f["code"] for f in bad["findings"]] == ["NOT_IN_CONTACT"] and bad["findings"][0]["gap_m"] > 0.7


@pytest.mark.planta74_scale
def test_undeclared_modules_are_reported_never_judged():
    from tools.validation.support_check import check_modules
    con = _con()
    rep = check_modules([mbox("Modulo novo", 0.5, 0.9, 1, 1)], con)
    assert rep["findings"] == [] and rep["evaluated"] == 0 and rep["not_evaluated"] == []
    assert rep["undeclared"] == ["R · Modulo novo"]


@pytest.mark.planta74_scale
def test_ceiling_module_must_reach_the_ceiling_and_the_gap_is_measured():
    from tools.validation.support_check import CEILING_Z_M, check_modules
    con = _con()
    ok = check_modules([mbox("PeleTeto", 2.64, CEILING_Z_M, 1, 1)], con)
    assert ok["findings"] == [] and ok["evaluated"] == 1
    bad = check_modules([mbox("Varal de teto", 2.02, 2.08, 1, 1)], con)
    assert [(f["code"], f["gap_m"]) for f in bad["findings"]] == [("NOT_AT_CEILING", 0.62)]


@pytest.mark.planta74_scale
def test_suspended_module_is_valid_only_if_some_part_reaches_the_ceiling():
    from tools.validation.support_check import check_modules
    con = _con()
    hung = [mbox("Pendente", 1.85, 2.10, 2, 2), {**mbox("Pendente", 2.10, 2.70, 2, 2, half=0.01), "kind": "pend_cabo"}]
    assert check_modules(hung, con)["findings"] == []
    floating = check_modules([mbox("Pendente", 1.85, 2.10, 2, 2)], con)
    assert [f["code"] for f in floating["findings"]] == ["NOT_CONNECTED"] and floating["findings"][0]["gap_m"] == 0.6


def test_ceiling_height_constant_is_the_one_the_shell_builder_uses():
    import re

    from tools.validation.support_check import CEILING_Z_M
    rb = (pathlib.Path(__file__).resolve().parents[1] / "tools/sketchup/shell/build_plan_shell_skp.rb").read_text(encoding="utf-8")
    assert float(re.search(r"WALL_HEIGHT_M\s*=\s*([0-9.]+)", rb).group(1)) == CEILING_Z_M


# Retrato medido em 2026-10-24 (develop@911d745): modulos fixados na parede que NAO a tocam. Defeito conhecido (FP-056 P4):
# nao corrigido aqui (muda posicao/aparencia; A.S. depende da decisao AS-1). Nao pode piorar nem ganhar item novo.
KNOWN_MODULES = {("A.S. | TERRACO SOCIAL | TERRACO TECNICO", "Varal de teto"): 0.62, ("BANHO 01", "PeleTeto"): 0.1399,
                 ("BANHO 02", "PeleTeto"): 0.1399, ("LAVABO", "PeleTeto"): 0.1399,
                 ("A.S. | TERRACO SOCIAL | TERRACO TECNICO", "Coifa"): 0.7533, ("A.S. | TERRACO SOCIAL | TERRACO TECNICO", "Prateleira servico"): 0.3465,
                 ("COZINHA", "hood"): 0.0632, ("COZINHA", "upper_cabinet_02"): 0.0172, ("SALA DE JANTAR | SALA DE ESTAR", "Painel TV"): 0.0111,
                 ("SUITE 01", "Painel cabeceira"): 0.005, ("SUITE 02", "Painel cabeceira"): 0.005}


@pytest.mark.planta74_scale
def test_planta74_module_support_findings_are_exactly_the_known_baseline_and_none_got_worse():
    from tools.furnish_apartment import collect_boxes
    from tools.validation.support_check import check_modules
    con = _con()
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _ = collect_boxes(con)
    rep = check_modules(boxes, con)
    got = {(f["room"], f["module"]): f["gap_m"] for f in rep["findings"]}
    assert set(got) <= set(KNOWN_MODULES), f"defeito de apoio NOVO: {set(got) - set(KNOWN_MODULES)}"
    for k, gap in got.items():
        assert gap <= KNOWN_MODULES[k] + 0.0005, f"{k} piorou: {gap} > {KNOWN_MODULES[k]}"
    assert rep["evaluated"] >= 30      # o que ja e julgado nao pode voltar a ficar sem declaracao
