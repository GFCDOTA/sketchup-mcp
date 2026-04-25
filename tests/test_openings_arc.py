"""Tests para o nivel 3 (arc-confirm) e nivel 4 (room mapping) do
detector de openings. Fixture sintetico: 2 walls horizontais com gap
de 70px no meio, arco quarter-circle desenhado pivotando no canto
esquerdo, raio = largura do gap. Mais um teste sem arco pra confirmar
o invariante (NAO chuta hinge_side, marca confidence baixo).
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from model.types import Room, Wall
from openings.service import (
    Opening,
    _assign_rooms,
    _detect_arc_and_hinge,
    _point_in_polygon,
    detect_openings,
)


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


# ---------- _detect_arc_and_hinge ----------

def test_arc_detected_left_pivot_horizontal():
    canvas = _blank()
    a, b = _draw_horizontal_walls_with_gap(canvas)
    # arco quarter-circle pivotando no canto LEFT (gap_x_left=265, y=300),
    # raio = largura do gap = 70 px, varrendo de 0 a -90 (pra cima).
    # OpenCV ellipse: angles em deg, sentido horario, 0 = +X.
    # Pra varrer pra cima (-Y), startAngle=-90 endAngle=0 (90 deg).
    _draw_quarter_arc(canvas, pivot=(265, 300), radius=70, start_deg=-90, end_deg=0)

    result = _detect_arc_and_hinge(
        image=canvas,
        opening_center=(300.0, 300.0),
        opening_width=70.0,
        orientation="horizontal",
    )
    assert result is not None, "arco existente deveria ser detectado"
    hinge, swing = result
    assert hinge == "left", f"esperava hinge=left (pivo no canto esq), veio {hinge}"
    assert 60.0 <= swing <= 120.0, f"swing fora da faixa esperada: {swing}"


def test_arc_detected_right_pivot_horizontal():
    canvas = _blank()
    a, b = _draw_horizontal_walls_with_gap(canvas)
    # pivo no canto direito (gap_x_right=335)
    _draw_quarter_arc(canvas, pivot=(335, 300), radius=70, start_deg=180, end_deg=270)

    result = _detect_arc_and_hinge(
        image=canvas,
        opening_center=(300.0, 300.0),
        opening_width=70.0,
        orientation="horizontal",
    )
    assert result is not None
    hinge, _swing = result
    assert hinge == "right"


def test_no_arc_returns_none():
    """Invariante critico: sem arco no raster, NAO chutar hinge_side."""
    canvas = _blank()
    _draw_horizontal_walls_with_gap(canvas)
    # nada de arco desenhado.
    result = _detect_arc_and_hinge(
        image=canvas,
        opening_center=(300.0, 300.0),
        opening_width=70.0,
        orientation="horizontal",
    )
    assert result is None, "sem arco visivel, deve retornar None"


# ---------- detect_openings end-to-end ----------

def test_detect_openings_with_image_enriches_arc_fields():
    canvas = _blank()
    a, b = _draw_horizontal_walls_with_gap(canvas)
    _draw_quarter_arc(canvas, pivot=(265, 300), radius=70, start_deg=-90, end_deg=0)

    walls, openings = detect_openings([a, b], image=canvas)
    assert len(openings) == 1
    op = openings[0]
    assert op.kind == "door"
    assert op.hinge_side == "left"
    assert op.swing_deg is not None and 60.0 <= op.swing_deg <= 120.0
    assert op.confidence == 1.0


def test_detect_openings_without_image_keeps_fields_none():
    canvas = _blank()
    a, b = _draw_horizontal_walls_with_gap(canvas)
    walls, openings = detect_openings([a, b])  # sem image
    assert len(openings) == 1
    op = openings[0]
    assert op.hinge_side is None
    assert op.swing_deg is None
    # confidence intacto pois nivel 3 nao foi chamado
    assert op.confidence == 1.0


def test_detect_openings_with_image_no_arc_lowers_confidence():
    canvas = _blank()
    a, b = _draw_horizontal_walls_with_gap(canvas)
    walls, openings = detect_openings([a, b], image=canvas)
    assert len(openings) == 1
    op = openings[0]
    assert op.hinge_side is None
    assert op.swing_deg is None
    assert op.confidence == 0.5, "arco ausente -> confidence cai pra 0.5"


# ---------- _assign_rooms / point_in_polygon ----------

def test_point_in_polygon_basic():
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    assert _point_in_polygon((5.0, 5.0), square)
    assert not _point_in_polygon((15.0, 5.0), square)
    assert not _point_in_polygon((5.0, -1.0), square)


def test_assign_rooms_two_sides():
    # opening horizontal em y=100, x=200, width=70
    # room_a acima (y<100), room_b abaixo (y>100)
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
    a, b = _assign_rooms(
        center=(200.0, 100.0),
        orientation="horizontal",
        width=70.0,
        rooms=[room_top, room_bot],
    )
    # offset = max(70*0.6, 8) = 42; probes em y=58 e y=142
    assert a == "room-A"
    assert b == "room-B"


def test_assign_rooms_one_side_exterior():
    room = Room(
        room_id="room-A",
        polygon=[(150.0, 105.0), (250.0, 105.0), (250.0, 150.0), (150.0, 150.0)],
        area=4500.0,
        centroid=(200.0, 127.0),
    )
    a, b = _assign_rooms(
        center=(200.0, 100.0),
        orientation="horizontal",
        width=70.0,
        rooms=[room],
    )
    # so o probe abaixo cai em room
    assert (a, b) == (None, "room-A")


def test_assign_rooms_empty_returns_none_none():
    assert _assign_rooms(
        center=(0.0, 0.0), orientation="horizontal", width=70.0, rooms=[]
    ) == (None, None)


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
