"""FP-054 F1-05 (R-06): a busca da mesa de jantar confere o arco da porta para a mesa E para as cadeiras.

Antes so o tampo (`Mesa de jantar`) era testado contra o arco: uma cadeira dentro do giro da porta passava. Contraprova: um arco
artificial que cobre so a cadeira do layout atual (o tampo fica fora) — o codigo antigo mantinha o layout; agora nenhuma peca do
conjunto de jantar pode tocar arco nenhum."""
from __future__ import annotations

import contextlib
import io
import json

import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union

pytestmark = pytest.mark.planta74_scale

DINING = ("Mesa de jantar", "Cadeira jantar")


def _living(con):
    from tools.rooms.living.furnishing import living_room_boxes
    with contextlib.redirect_stdout(io.StringIO()):
        return living_room_boxes(con, "r002")


def _swings_in(con):
    from core.scale import PT_TO_IN
    from tools.rooms.shared import geometry
    from tools.spatial_model import build_spatial_model
    walls = build_spatial_model(con, "r002")["_geom"]["room_walls"]
    sw = geometry.door_swing_polygons(con)
    from shapely import affinity
    return [affinity.scale(sw[o["id"]], PT_TO_IN, PT_TO_IN, origin=(0, 0))
            for o in con["openings"] if o["id"] in sw and o["wall_id"] in walls]


def _hits(boxes, swings):
    return [(b["module"], b.get("kind")) for b in boxes if b.get("module") in DINING and b.get("corners")
            for s in swings if Polygon(b["corners"]).intersection(s).area > 1e-8]


@pytest.fixture(scope="module")
def con():
    from tools.furnish_apartment import CONSENSUS
    return json.loads(CONSENSUS.read_text("utf-8"))


def test_real_layout_has_no_dining_piece_in_any_door_swing(con):
    boxes, _ = _living(con)
    assert [b for b in boxes if b.get("module") == "Mesa de jantar"]
    assert _hits(boxes, _swings_in(con)) == []


def test_a_swing_covering_only_a_chair_moves_or_drops_the_set(con, monkeypatch):
    from core.scale import PT_TO_IN
    from tools.rooms.shared import geometry
    boxes, _ = _living(con)
    seat = next(b for b in boxes if b.get("module") == "Cadeira jantar" and b.get("kind") == "seat")
    table = unary_union([Polygon(b["corners"]) for b in boxes if b.get("module") == "Mesa de jantar" and b.get("corners")])
    chair = Polygon(seat["corners"])
    patch_in = chair.buffer(1.0).difference(table.buffer(0.5))          # cobre a cadeira, nunca o tampo
    assert patch_in.area > 0 and patch_in.intersection(table).area == 0
    patch_pt = Polygon([(x / PT_TO_IN, y / PT_TO_IN) for x, y in patch_in.exterior.coords]) \
        if patch_in.geom_type == "Polygon" else max(patch_in.geoms, key=lambda g: g.area)
    real = geometry.door_swing_polygons

    def fake(c):
        out = dict(real(c))
        out["h_o006"] = patch_pt          # troca o arco de OUTRA porta do comodo pelo arco artificial (Polygon simples)
        return out
    monkeypatch.setattr(geometry, "door_swing_polygons", fake)
    boxes2, _ = _living(con)
    assert _hits(boxes2, _swings_in(con)) == [], "uma peca do conjunto de jantar ficou dentro do arco"
