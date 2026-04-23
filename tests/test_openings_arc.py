"""Tests transportados do main (test_openings_arc.py).

O `openings/service.py` no worktree `fix/dedup-colinear-planta74` ainda nao
evoluiu para os niveis 3 (arc-confirm) e 4 (room mapping) que o main ja tem.
Por isso esse arquivo transporta a ESTRUTURA dos tests originais mas pula
via `pytest.skip` os que dependem de simbolos ausentes (`_detect_arc_and_hinge`,
`_assign_rooms`, `_point_in_polygon`, campos `hinge_side`/`swing_deg`/`room_a`/
`room_b`/`confidence` em `Opening`). O intuito e que quando esses simbolos
chegarem na branch, os tests ja estao la prontos.

Fixtures sinteticos: 2 walls horizontais com gap de 70px no meio. Arco
quarter-circle pivotando no canto esquerdo quando aplicavel.
"""
from __future__ import annotations

import importlib

import cv2
import numpy as np
import pytest

from model.types import Wall
import openings.service as openings_service
from openings.service import Opening, detect_openings


# --- capability probes ---------------------------------------------------

_HAS_ARC = hasattr(openings_service, "_detect_arc_and_hinge")
_HAS_ASSIGN_ROOMS = hasattr(openings_service, "_assign_rooms")
_HAS_POINT_IN_POLY = hasattr(openings_service, "_point_in_polygon")
_OPENING_FIELDS = set(Opening.__dataclass_fields__.keys()) if hasattr(Opening, "__dataclass_fields__") else set()
_HAS_HINGE = "hinge_side" in _OPENING_FIELDS
_HAS_ROOM_AB = "room_a" in _OPENING_FIELDS and "room_b" in _OPENING_FIELDS
_HAS_CONFIDENCE_FIELD = "confidence" in _OPENING_FIELDS


# --- helpers -------------------------------------------------------------

def _blank(w: int = 600, h: int = 600) -> np.ndarray:
    return np.full((h, w, 3), 255, dtype=np.uint8)


def _draw_horizontal_walls_with_gap(
    canvas: np.ndarray,
    y: int = 300,
    gap_x_left: int = 265,
    gap_x_right: int = 335,
    extent: int = 250,
) -> tuple[Wall, Wall]:
    """Desenha duas walls horizontais com um gap entre x=gap_x_left e
    x=gap_x_right na linha y. Retorna os 2 Wall correspondentes."""
    cv2.line(canvas, (300 - extent, y), (gap_x_left, y), (0, 0, 0), 6)
    cv2.line(canvas, (gap_x_right, y), (300 + extent, y), (0, 0, 0), 6)
    a = Wall(
        wall_id="wall-1",
        page_index=0,
        start=(float(300 - extent), float(y)),
        end=(float(gap_x_left), float(y)),
        thickness=6.0,
        orientation="horizontal",
        source="extract",
        confidence=1.0,
    )
    b = Wall(
        wall_id="wall-2",
        page_index=0,
        start=(float(gap_x_right), float(y)),
        end=(float(300 + extent), float(y)),
        thickness=6.0,
        orientation="horizontal",
        source="extract",
        confidence=1.0,
    )
    return a, b


def _draw_quarter_arc(
    canvas: np.ndarray,
    pivot: tuple[int, int],
    radius: int,
    start_deg: float,
    end_deg: float,
) -> None:
    cv2.ellipse(
        canvas,
        pivot,
        (radius, radius),
        angle=0,
        startAngle=start_deg,
        endAngle=end_deg,
        color=(0, 0, 0),
        thickness=2,
    )


# ---------- detect_openings end-to-end (interface MINIMA, sempre roda) ----

def test_detect_openings_basic_gap_produces_opening():
    """Invariante basico: 2 walls colineares com gap viram 1 opening."""
    canvas = _blank()
    a, b = _draw_horizontal_walls_with_gap(canvas)
    # detect_openings tem interface diferente entre versoes; chamamos so
    # com walls (positional) que e o denominador comum.
    result = detect_openings([a, b])
    # Versao simples retorna (walls_estendidas, openings).
    assert isinstance(result, tuple)
    assert len(result) == 2
    _walls, ops = result
    assert len(ops) == 1
    op = ops[0]
    assert op.kind == "door"
    # centro do gap deve ficar em torno de x=300 (media de 265 e 335)
    assert 290.0 <= op.center[0] <= 310.0
    # largura do gap deve bater ~70 px
    assert 50.0 <= op.width <= 90.0


def test_detect_openings_empty_returns_empty():
    walls, ops = detect_openings([])
    assert walls == []
    assert ops == []


def test_opening_to_dict_core_fields():
    """Regardless of version, Opening.to_dict deve carregar os campos-core."""
    canvas = _blank()
    a, b = _draw_horizontal_walls_with_gap(canvas)
    _walls, ops = detect_openings([a, b])
    assert len(ops) == 1
    d = ops[0].to_dict()
    for key in ("opening_id", "page_index", "orientation", "center", "width",
                "wall_a", "wall_b", "kind"):
        assert key in d, f"chave core ausente: {key}"


# ---------- _detect_arc_and_hinge (level 3) -------------------------------

@pytest.mark.skipif(not _HAS_ARC, reason="openings.service._detect_arc_and_hinge ausente nesta branch")
def test_arc_detected_left_pivot_horizontal():
    canvas = _blank()
    _a, _b = _draw_horizontal_walls_with_gap(canvas)
    _draw_quarter_arc(canvas, pivot=(265, 300), radius=70, start_deg=-90, end_deg=0)
    result = openings_service._detect_arc_and_hinge(
        image=canvas,
        opening_center=(300.0, 300.0),
        opening_width=70.0,
        orientation="horizontal",
    )
    assert result is not None, "arco existente deveria ser detectado"
    hinge, swing = result
    assert hinge == "left", f"esperava hinge=left, veio {hinge}"
    assert 60.0 <= swing <= 120.0, f"swing fora da faixa esperada: {swing}"


@pytest.mark.skipif(not _HAS_ARC, reason="openings.service._detect_arc_and_hinge ausente nesta branch")
def test_arc_detected_right_pivot_horizontal():
    canvas = _blank()
    _a, _b = _draw_horizontal_walls_with_gap(canvas)
    _draw_quarter_arc(canvas, pivot=(335, 300), radius=70, start_deg=180, end_deg=270)
    result = openings_service._detect_arc_and_hinge(
        image=canvas,
        opening_center=(300.0, 300.0),
        opening_width=70.0,
        orientation="horizontal",
    )
    assert result is not None
    hinge, _swing = result
    assert hinge == "right"


@pytest.mark.skipif(not _HAS_ARC, reason="openings.service._detect_arc_and_hinge ausente nesta branch")
def test_no_arc_returns_none():
    """Invariante critico: sem arco no raster, NAO chutar hinge_side."""
    canvas = _blank()
    _draw_horizontal_walls_with_gap(canvas)
    result = openings_service._detect_arc_and_hinge(
        image=canvas,
        opening_center=(300.0, 300.0),
        opening_width=70.0,
        orientation="horizontal",
    )
    assert result is None, "sem arco visivel, deve retornar None"


# ---------- detect_openings com image (level 3 end-to-end) ----------------

@pytest.mark.skipif(not (_HAS_ARC and _HAS_HINGE), reason="arc+hinge_side nao disponivel nesta branch")
def test_detect_openings_with_image_enriches_arc_fields():
    canvas = _blank()
    a, b = _draw_horizontal_walls_with_gap(canvas)
    _draw_quarter_arc(canvas, pivot=(265, 300), radius=70, start_deg=-90, end_deg=0)
    _walls, ops = detect_openings([a, b], image=canvas)  # type: ignore[arg-type]
    assert len(ops) == 1
    op = ops[0]
    assert op.kind == "door"
    assert op.hinge_side == "left"
    assert op.swing_deg is not None and 60.0 <= op.swing_deg <= 120.0
    assert op.confidence == 1.0


@pytest.mark.skipif(not _HAS_HINGE, reason="Opening.hinge_side nao existe nesta branch")
def test_detect_openings_without_image_keeps_fields_none():
    canvas = _blank()
    a, b = _draw_horizontal_walls_with_gap(canvas)
    _walls, ops = detect_openings([a, b])
    assert len(ops) == 1
    op = ops[0]
    assert op.hinge_side is None
    assert op.swing_deg is None
    assert op.confidence == 1.0


@pytest.mark.skipif(not (_HAS_ARC and _HAS_CONFIDENCE_FIELD), reason="arc+confidence fallback nao disponivel")
def test_detect_openings_with_image_no_arc_lowers_confidence():
    canvas = _blank()
    a, b = _draw_horizontal_walls_with_gap(canvas)
    _walls, ops = detect_openings([a, b], image=canvas)  # type: ignore[arg-type]
    assert len(ops) == 1
    op = ops[0]
    assert op.hinge_side is None
    assert op.swing_deg is None
    assert op.confidence == 0.5, "arco ausente -> confidence cai pra 0.5"


# ---------- _assign_rooms / point_in_polygon (level 4) --------------------

@pytest.mark.skipif(not _HAS_POINT_IN_POLY, reason="openings.service._point_in_polygon ausente")
def test_point_in_polygon_basic():
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    pip = openings_service._point_in_polygon
    assert pip((5.0, 5.0), square)
    assert not pip((15.0, 5.0), square)
    assert not pip((5.0, -1.0), square)


@pytest.mark.skipif(not _HAS_ASSIGN_ROOMS, reason="openings.service._assign_rooms ausente")
def test_assign_rooms_two_sides():
    # Importa Room so quando o simbolo existe (pode nao estar exportado ainda)
    try:
        from model.types import Room  # type: ignore
    except ImportError:
        pytest.skip("model.types.Room ausente nesta branch")
    # opening horizontal em y=100, x=200, width=70
    room_top = Room(
        room_id="room-A",
        polygon=[(150.0, 50.0), (250.0, 50.0), (250.0, 95.0), (150.0, 95.0)],
        area=4500.0,
        centroid=(200.0, 72.0),
    )
    room_bot = Room(
        room_id="room-B",
        polygon=[(150.0, 105.0), (250.0, 105.0), (250.0, 150.0), (150.0, 150.0)],
        area=4500.0,
        centroid=(200.0, 127.0),
    )
    a, b = openings_service._assign_rooms(
        center=(200.0, 100.0),
        orientation="horizontal",
        width=70.0,
        rooms=[room_top, room_bot],
    )
    assert a == "room-A"
    assert b == "room-B"


@pytest.mark.skipif(not _HAS_ASSIGN_ROOMS, reason="openings.service._assign_rooms ausente")
def test_assign_rooms_one_side_exterior():
    try:
        from model.types import Room  # type: ignore
    except ImportError:
        pytest.skip("model.types.Room ausente nesta branch")
    room = Room(
        room_id="room-A",
        polygon=[(150.0, 105.0), (250.0, 105.0), (250.0, 150.0), (150.0, 150.0)],
        area=4500.0,
        centroid=(200.0, 127.0),
    )
    a, b = openings_service._assign_rooms(
        center=(200.0, 100.0),
        orientation="horizontal",
        width=70.0,
        rooms=[room],
    )
    assert (a, b) == (None, "room-A")


@pytest.mark.skipif(not _HAS_ASSIGN_ROOMS, reason="openings.service._assign_rooms ausente")
def test_assign_rooms_empty_returns_none_none():
    assert openings_service._assign_rooms(
        center=(0.0, 0.0), orientation="horizontal", width=70.0, rooms=[]
    ) == (None, None)


@pytest.mark.skipif(not (_HAS_HINGE and _HAS_ROOM_AB), reason="hinge_side+room_a/room_b nao disponiveis")
def test_opening_to_dict_has_all_new_fields():
    op = Opening(
        opening_id="opening-1",
        page_index=0,
        orientation="horizontal",
        center=(100.0, 200.0),
        width=70.0,
        wall_a="wall-1",
        wall_b="wall-2",
        kind="door",
        hinge_side="left",
        swing_deg=90.0,
        room_a="room-1",
        room_b="room-2",
        confidence=1.0,
    )
    d = op.to_dict()
    for key in (
        "opening_id", "page_index", "orientation", "center", "width",
        "wall_a", "wall_b", "kind",
        "hinge_side", "swing_deg", "room_a", "room_b", "confidence",
    ):
        assert key in d, f"chave ausente: {key}"
    assert d["hinge_side"] == "left"
    assert d["swing_deg"] == 90.0
    assert d["room_a"] == "room-1"
    assert d["room_b"] == "room-2"
    assert d["confidence"] == 1.0
