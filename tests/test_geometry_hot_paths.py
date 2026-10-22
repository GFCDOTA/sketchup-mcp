"""Caminhos quentes de geometria (complexidade): caches exatos, com invalidacao por conteudo. Sem teste de relogio (flaky);
a prova e de IGUALDADE de resultado e de CONTAGEM de trabalho evitado."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from shapely.geometry import Point, Polygon, box

from tools.validation import circulation_gate as cg

ROOT = Path(__file__).resolve().parents[1]
M2IN = cg.M2IN


def _u_room():
    """Comodo em U: dois bracos ligados por um corredor de 0,80 m (em polegadas, como o gate usa)."""
    w, h, corridor = 4.0 * M2IN, 3.0 * M2IN, 0.80 * M2IN
    left, right = box(0, 0, 1.2 * M2IN, h), box(w - 1.2 * M2IN, 0, w, h)
    bridge = box(1.2 * M2IN, h - corridor, w - 1.2 * M2IN, h)
    return left.union(bridge).union(right)


def test_eroded_regions_equal_a_direct_buffer_and_are_reused():
    room = _u_room()
    cg._eroded_regions.cache_clear()
    for width in (0.50, 0.75, 1.00):
        direct = room.buffer(-(width / 2) * M2IN)
        cached = cg._eroded_regions(room.wkb, width)
        merged = cached[0] if len(cached) == 1 else cached[0].union(cached[1]) if cached else Polygon()
        assert merged.symmetric_difference(direct).area == pytest.approx(0.0, abs=1e-6) or (direct.is_empty and not cached)
    before = cg._eroded_regions.cache_info()
    cg._eroded_regions(room.wkb, 0.75)
    assert cg._eroded_regions.cache_info().hits == before.hits + 1          # mesma (forma, largura) = sem novo buffer


def test_bottleneck_width_is_unchanged_by_the_cache():
    room = _u_room()
    a, b = Point(0.6 * M2IN, 0.5 * M2IN), Point(3.4 * M2IN, 0.5 * M2IN)
    cg._eroded_regions.cache_clear()
    first = cg._bottleneck_width(room, a, b)
    again = cg._bottleneck_width(room, a, b)                                  # 100% cache
    assert first == again == pytest.approx(0.80, abs=0.011)                    # o corredor de 0,80 m e o gargalo
    assert cg._eroded_regions.cache_info().misses <= 9                         # 2 extremos + <= 7 passos da busca binaria


@pytest.mark.planta74_scale
def test_spatial_model_cache_is_keyed_by_content_and_returns_the_same_model():
    from tools.rooms.shared import spatial_model as sm
    con = json.loads((ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json").read_text(encoding="utf-8"))
    room_id = con["rooms"][0]["id"]
    sm._GEOMETRY_CACHE.clear()
    first = sm.build_spatial_model(con, room_id)
    assert len(sm._GEOMETRY_CACHE) == 1
    second = sm.build_spatial_model(copy.deepcopy(con), room_id)              # outro objeto, mesmo conteudo: reaproveita
    assert len(sm._GEOMETRY_CACHE) == 1
    strip = lambda m: {k: v for k, v in m.items() if k != "_geom"}           # noqa: E731
    assert json.dumps(strip(first), sort_keys=True, default=str) == json.dumps(strip(second), sort_keys=True, default=str)
    edited = copy.deepcopy(con)
    edited["walls"][0]["end"] = [edited["walls"][0]["end"][0] + 1.0, edited["walls"][0]["end"][1]]
    sm.build_spatial_model(edited, room_id)                                   # conteudo diferente: nunca reaproveita
    assert len(sm._GEOMETRY_CACHE) == 2


def test_spatial_model_cache_is_bounded():
    from tools.rooms.shared import spatial_model as sm
    assert sm._GEOMETRY_CACHE_MAX <= 16
