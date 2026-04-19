from __future__ import annotations

import cv2
import numpy as np


def blank_canvas(width: int = 240, height: int = 240) -> np.ndarray:
    return np.full((height, width, 3), 255, dtype=np.uint8)


def draw_polyline(points: list[tuple[int, int]], thickness: int = 8) -> np.ndarray:
    canvas = blank_canvas()
    for start, end in zip(points, points[1:]):
        cv2.line(canvas, start, end, color=(0, 0, 0), thickness=thickness)
    return canvas


def simple_square() -> np.ndarray:
    points = [(40, 40), (200, 40), (200, 200), (40, 200), (40, 40)]
    return draw_polyline(points)


def two_rooms_shared_wall() -> np.ndarray:
    canvas = simple_square()
    cv2.line(canvas, (120, 40), (120, 200), color=(0, 0, 0), thickness=8)
    return canvas


def l_shape_room() -> np.ndarray:
    points = [(40, 40), (200, 40), (200, 100), (120, 100), (120, 200), (40, 200), (40, 40)]
    return draw_polyline(points)


def t_junction() -> np.ndarray:
    canvas = blank_canvas()
    cv2.line(canvas, (40, 120), (200, 120), color=(0, 0, 0), thickness=8)
    cv2.line(canvas, (120, 40), (120, 120), color=(0, 0, 0), thickness=8)
    return canvas


def disconnected_walls() -> np.ndarray:
    canvas = blank_canvas()
    cv2.line(canvas, (40, 40), (100, 40), color=(0, 0, 0), thickness=8)
    cv2.line(canvas, (160, 160), (220, 160), color=(0, 0, 0), thickness=8)
    return canvas
