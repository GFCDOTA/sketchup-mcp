"""Testes do detector automatico de peitoris.

Fixtures sinteticas: pintamos retangulos marrons (mureta) e diamantes
marrons pequenos (ruido) num canvas branco com paredes vermelhas, e
verificamos que o detector pega os retangulos e descarta o ruido.
"""
from __future__ import annotations

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from peitoris.service import (
    DEFAULT_HEIGHT_M,
    PeitorilDetectionConfig,
    detect_peitoris,
    merge_with_manual,
)


# ---------- helpers ----------

# Cores em BGR (cv2 default). HSV-equivalentes ja calibrados pela faixa
# (8-25 hue, S>=80, V 40-180).
WHITE_BGR = (255, 255, 255)
RED_BGR = (40, 40, 200)       # alvenaria
BROWN_BGR = (40, 80, 140)     # peitoril/mureta
DIAMOND_BROWN_BGR = (50, 90, 150)  # variacao p ruido


def _blank(w: int = 400, h: int = 400) -> np.ndarray:
    return np.full((h, w, 3), 255, dtype=np.uint8)


def _draw_peitoril(img: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> None:
    cv2.rectangle(img, (x1, y1), (x2, y2), BROWN_BGR, thickness=-1)


def _draw_red_wall(img: np.ndarray, p1: tuple[int, int], p2: tuple[int, int]) -> None:
    cv2.line(img, p1, p2, RED_BGR, thickness=8)


def _draw_brown_diamond(img: np.ndarray, cx: int, cy: int, r: int = 6) -> None:
    pts = np.array(
        [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], dtype=np.int32
    )
    cv2.fillPoly(img, [pts], DIAMOND_BROWN_BGR)


# ---------- testes ----------

def test_blank_canvas_returns_empty():
    img = _blank()
    assert detect_peitoris(img) == []


def test_monochrome_input_returns_empty():
    # Imagem ja filtrada (sem cor) -> nao da pra detectar marrom.
    gray = np.full((200, 200), 255, dtype=np.uint8)
    assert detect_peitoris(gray) == []


def test_none_or_empty_returns_empty():
    assert detect_peitoris(None) == []  # type: ignore[arg-type]
    assert detect_peitoris(np.empty((0, 0, 3), dtype=np.uint8)) == []


def test_single_peitoril_is_detected():
    img = _blank()
    # mureta horizontal alongada: 200 px largura x 8 px altura
    _draw_peitoril(img, x1=80, y1=300, x2=280, y2=308)
    result = detect_peitoris(img)
    assert len(result) == 1
    p = result[0]
    assert p["kind"] == "peitoril"
    assert p["height_m"] == DEFAULT_HEIGHT_M
    assert p["peitoril_id"].startswith("peitoril-")
    x1, y1, x2, y2 = p["bbox"]
    # bbox deve cobrir o retangulo desenhado (com tolerancia minima)
    assert x1 <= 82 and x2 >= 278
    assert y1 <= 302 and y2 >= 306
    assert p["area_px"] >= 200


def test_two_peitoris_detected_independently():
    img = _blank()
    _draw_peitoril(img, 80, 300, 280, 308)
    _draw_peitoril(img, 80, 340, 280, 348)
    result = detect_peitoris(img)
    assert len(result) == 2
    # ambos com height padrao
    assert all(p["height_m"] == DEFAULT_HEIGHT_M for p in result)
    # ids unicos
    ids = {p["peitoril_id"] for p in result}
    assert len(ids) == 2


def test_brown_diamonds_are_filtered_out_by_aspect_and_size():
    """Diamantes marrons pequenos (hachura/marker) NAO devem virar peitoril.

    Eles tem aspect ratio ~1:1 e tamanho ~12 px lado — ambos os filtros
    devem rejeita-los.
    """
    img = _blank()
    for cx, cy in [(100, 100), (150, 100), (200, 100), (250, 100)]:
        _draw_brown_diamond(img, cx, cy, r=6)
    result = detect_peitoris(img)
    assert result == []


def test_peitoril_survives_among_red_walls_and_diamonds():
    img = _blank()
    # paredes vermelhas
    _draw_red_wall(img, (50, 50), (350, 50))
    _draw_red_wall(img, (50, 50), (50, 350))
    _draw_red_wall(img, (350, 50), (350, 350))
    _draw_red_wall(img, (50, 350), (350, 350))
    # ruido marrom (deve ser filtrado)
    for cx in range(120, 281, 30):
        _draw_brown_diamond(img, cx, 120, r=5)
    # peitoril real (deve ser detectado)
    _draw_peitoril(img, 80, 280, 280, 290)
    result = detect_peitoris(img)
    assert len(result) == 1, f"esperado 1 peitoril, veio {len(result)}: {result}"


def test_short_brown_blob_below_threshold_filtered():
    img = _blank()
    # blob marrom 50x10 — passa em area mas falha em min_long_side (default 80)
    _draw_peitoril(img, 100, 100, 150, 110)
    assert detect_peitoris(img) == []


def test_thick_square_brown_filtered_by_aspect():
    img = _blank()
    # quadrado marrom 90x90 — passa area e long_side, mas aspect=1
    _draw_peitoril(img, 100, 100, 190, 190)
    assert detect_peitoris(img) == []


def test_custom_config_lowers_threshold():
    img = _blank()
    _draw_peitoril(img, 100, 100, 150, 110)  # 50x10
    cfg = PeitorilDetectionConfig(
        min_long_side_px=40, min_aspect_ratio=3.0, min_area_px=50
    )
    result = detect_peitoris(img, config=cfg)
    assert len(result) == 1


def test_bbox_padding_applied():
    img = _blank(400, 400)
    _draw_peitoril(img, 80, 200, 280, 208)
    cfg = PeitorilDetectionConfig(bbox_pad_px=5)
    result = detect_peitoris(img, config=cfg)
    assert len(result) == 1
    x1, y1, x2, y2 = result[0]["bbox"]
    # padding de 5px deve expandir o bbox em ~5 em cada lado
    assert x1 <= 75 and x2 >= 285
    assert y1 <= 195 and y2 >= 213


def test_page_index_propagated():
    img = _blank()
    _draw_peitoril(img, 80, 200, 280, 208)
    result = detect_peitoris(img, page_index=3)
    assert len(result) == 1
    assert result[0]["page_index"] == 3


def test_merge_with_manual_appends_without_overwriting():
    auto = [{
        "peitoril_id": "peitoril-1",
        "bbox": [0, 0, 10, 10],
        "area_px": 100,
        "kind": "peitoril",
        "height_m": 1.10,
    }]
    manual = [{
        "bbox": [50, 50, 100, 100],
        "kind": "peitoril",
        "height_m": 0.70,
    }]
    merged = merge_with_manual(auto, manual)
    assert len(merged) == 2
    # auto preservado
    assert merged[0]["peitoril_id"] == "peitoril-1"
    # manual recebeu novo id
    assert merged[1]["peitoril_id"] == "peitoril-2"
    assert merged[1]["height_m"] == 0.70


def test_merge_with_manual_none_returns_copy():
    auto = [{"peitoril_id": "peitoril-1", "bbox": [0, 0, 10, 10]}]
    merged = merge_with_manual(auto, None)
    assert merged == auto
    assert merged is not auto  # copia, nao mesma referencia
