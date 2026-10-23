"""#381 — Suite 01: decisao do Felipe (2026-10-23): sem a cadeira da escrivaninha e so o criado-mudo de baixo 1 in para cima
na planta (-y). (A 1a escolha, conjunto da cama 2 in, invadia a parede e foi recusada com medidas.) Antes: corredor mobiliado
0,00 m e o pre-voo recusava o apartamento. Depois: corredor >= 0,90 m, nada na parede, so a Suite 01 muda, e a decisao fica
registrada com origem `user_request` (nao e medida inventada)."""
from __future__ import annotations

import contextlib
import io
import json

import pytest

from tools.rooms.bedroom import layout_decisions as ld

pytestmark = pytest.mark.planta74_scale


@pytest.fixture(scope="module")
def apartment():
    from tools.furnish_apartment import CONSENSUS, collect_boxes
    con = json.loads(CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, summary = collect_boxes(con)
    return con, boxes, summary


def test_decision_is_declared_as_user_request_with_its_measures():
    d = ld.decisions_for({"source": "planta_74.pdf"}, "r000")
    assert len(d) == 1
    d = d[0]
    assert d["origin"] == "user_request" and d["issue"] == "#381"
    assert d["drop_types"] == ["desk_chair"]
    assert d["shift"] == {"names": ["criado_mudo_dir"], "dy": {"value": -1.0, "unit": "in", "origin": "user_request"}}
    assert ld.decisions_for({"source": "planta_74.pdf"}, "r003") == []
    assert ld.decisions_for({"source": "outra.pdf"}, "r000") == []


def test_suite01_corridor_passes_and_the_desk_chair_is_gone(apartment):
    from tools.validation import circulation_gate as cg
    con, boxes, _ = apartment
    g = cg.gate(con, boxes, "r000")
    assert g["result"] == "PASS", g["checks"]["corredor_principal"]
    widths = [p["w_furnished_m"] for p in g["checks"]["corredor_principal"]["portais"] if p.get("w_furnished_m") is not None]
    assert min(widths) >= 0.90
    assert not [b for b in boxes if b.get("room") == "SUITE 01" and b.get("module") == "Cadeira escrivaninha"]
    assert [b for b in boxes if b.get("room") == "SUITE 01" and b.get("module") == "Escrivaninha"]


def test_apartment_preflight_now_allows_materialization(apartment):
    from tools.validation.layout_preflight import allows_materialization, preflight
    con, boxes, summary = apartment
    pre = preflight(con, boxes, summary)
    assert allows_materialization(pre), pre["blocking"]


def test_only_the_lower_nightstand_moved_and_by_exactly_one_inch():
    from tools.furnish_apartment import CONSENSUS
    from tools.rooms.bedroom import designer
    con = json.loads(CONSENSUS.read_text("utf-8"))
    _sm, out = designer.run(con, "r000", minimalist=True)
    before = {it["name"]: it["box"].bounds for it in out["_winner_items"]}
    items, applied = ld.apply(con, "r000", out["_winner_items"])
    after = {it["name"]: it["box"].bounds for it in items}
    from core.scale import PT_TO_IN
    assert "cadeira_escrivaninha" not in after and applied[0]["id"] == "suite01-circulation-2026-10-23"
    for name, b in before.items():
        if name == "cadeira_escrivaninha":
            continue
        dy_in = (after[name][1] - b[1]) * PT_TO_IN
        assert abs(dy_in - (-1.0 if name == "criado_mudo_dir" else 0.0)) < 1e-9, name
        assert abs(after[name][0] - b[0]) < 1e-12, name


def test_suite01_furniture_stays_out_of_the_walls_and_off_the_bed(apartment):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    from core.scale import PT_TO_IN, PT_TO_M
    from tools.rooms.shared.spatial_model import build_spatial_model, wall_footprint
    con, boxes, _ = apartment
    sm = build_spatial_model(con, "r000")
    walls = unary_union([wall_footprint(sm["_geom"]["walls"][w], extend_endpoints=True) for w in sm["_geom"]["room_walls"]])
    suite = [b for b in boxes if b.get("room") == "SUITE 01" and b.get("corners") and b.get("module") != "rug"]
    for b in suite:
        fp = Polygon([(x / PT_TO_IN, y / PT_TO_IN) for x, y in b["corners"]])
        assert fp.intersection(walls).area * PT_TO_M ** 2 < 1e-6, (b["module"], b.get("kind"))
    bed = unary_union([Polygon(b["corners"]) for b in suite if b["module"] == "Cama"])
    ns = unary_union([Polygon(b["corners"]) for b in suite if b["module"] == "Criado-mudo 1"])
    assert ns.intersection(bed).area == 0 and ns.distance(bed) * 0.0254 >= 0.01      # >= 1 cm da cama
