"""Arc detection for openings — completa nível 3.

PATCH #06 — expandir sketchup-mcp/openings/service.py

OBJETIVO: detectar quarter-circle arcs de portas no raster, inferir
hinge_side, swing_deg, rooms[A, B] para cada opening.

ANTES (openings/service.py):
    detect_openings(walls) → gaps colineares [8, 280] px classificados
    por width em door/window/passage.

DEPOIS:
    detect_openings(walls, raster_image, rooms) →
    openings com campos adicionais:
      - arc_center: (x, y) em pixels
      - arc_radius: pixels
      - hinge_side: "left" | "right"
      - swing_deg: 0..360
      - opens_to_room: [room_A_id, room_B_id]
      - confidence: gap_ok * arc_ok * room_mapping_ok
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np


# ==============================================================================
# ESTENDER Opening dataclass existente
# ==============================================================================

@dataclass
class OpeningLevel3:
    """Opening nível 3 com arc, hinge, swing, rooms."""
    # Campos nível 2 (existente)
    id: str
    wall_id: str
    offset_m: float
    width_m: float
    kind: str  # "door" | "window" | "passage"

    # Campos nível 3 (NOVOS)
    arc_center: Optional[tuple[float, float]] = None  # (x, y) em pixels
    arc_radius: Optional[float] = None  # em pixels
    hinge_side: Optional[str] = None  # "left" | "right"
    swing_deg: Optional[float] = None  # 0..360 graus
    opens_to_room: Optional[tuple[str, str]] = None  # (room_A_id, room_B_id)
    confidence: float = 0.0


# ==============================================================================
# DETECÇÃO DE ARCOS (nova função)
# ==============================================================================

_ARC_MIN_RADIUS_PX = 20
_ARC_MAX_RADIUS_PX = 150
_ARC_ANGLE_TOLERANCE_DEG = 20.0  # quarter circle ± tolerance
_ARC_CONFIDENCE_THRESHOLD = 0.5


def detect_door_arcs_in_raster(
    image: np.ndarray,
    expected_arc_hint: Optional[tuple[float, float, float]] = None,
) -> list[dict]:
    """Detecta arcos de portas via Circular Hough Transform + filtering.

    Parameters
    ----------
    image : np.ndarray
        Raster da página (BGR ou grayscale).
    expected_arc_hint : tuple or None
        Opcional: (cx, cy, radius) pra focar busca em região específica.

    Returns
    -------
    Lista de dicts com keys: center, radius, confidence, arc_points.
    """
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # Edge detection pra HoughCircles
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    # Circular Hough Transform
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=30,
        param1=80,  # Canny high threshold
        param2=25,  # Accumulator threshold (menor = mais falsos positivos)
        minRadius=_ARC_MIN_RADIUS_PX,
        maxRadius=_ARC_MAX_RADIUS_PX,
    )

    if circles is None:
        return []

    # HoughCircles retorna círculos completos, não arcs.
    # Pra validar que é um QUARTER circle (door), verificamos arc span.
    detected_arcs = []

    for circle in circles[0]:
        cx, cy, radius = float(circle[0]), float(circle[1]), float(circle[2])

        # Verificar presença real de arc points (Canny edges) próximos ao círculo
        arc_info = _verify_arc_on_edges(edges, cx, cy, radius)
        if arc_info is None:
            continue

        # Filtrar: door arcs são quarter-circles (~90 ± 20 deg span)
        arc_span_deg = arc_info["arc_span_deg"]
        if not (70 <= arc_span_deg <= 110):
            continue

        detected_arcs.append({
            "center": (cx, cy),
            "radius": radius,
            "confidence": arc_info["confidence"],
            "arc_span_deg": arc_span_deg,
            "start_angle_deg": arc_info["start_angle_deg"],
            "end_angle_deg": arc_info["end_angle_deg"],
        })

    return detected_arcs


def _verify_arc_on_edges(
    edges: np.ndarray,
    cx: float,
    cy: float,
    radius: float,
    n_samples: int = 72,
) -> Optional[dict]:
    """Sample ao redor do círculo, conta onde há edge = presença real do arc."""
    h, w = edges.shape

    present_angles = []
    for i in range(n_samples):
        angle_rad = 2 * math.pi * i / n_samples
        px = int(round(cx + radius * math.cos(angle_rad)))
        py = int(round(cy + radius * math.sin(angle_rad)))

        if 0 <= px < w and 0 <= py < h:
            # Check vizinhança 3x3 por tolerância a discretização
            neighborhood = edges[
                max(0, py - 1):min(h, py + 2),
                max(0, px - 1):min(w, px + 2),
            ]
            if neighborhood.any():
                present_angles.append(math.degrees(angle_rad))

    if len(present_angles) < n_samples * 0.2:  # < 20% of sampled angles have edge
        return None

    # Agrupar ângulos presentes em cluster contíguo (arc = sequência contígua)
    present_angles.sort()
    arc_spans = _find_contiguous_spans(present_angles, gap_threshold_deg=15.0)

    if not arc_spans:
        return None

    # Maior span = o arc principal
    best_span = max(arc_spans, key=lambda s: s["end"] - s["start"])
    span_deg = best_span["end"] - best_span["start"]

    # Confidence = proporção coberta / span total esperado
    expected_quarter = 90.0
    coverage = min(1.0, span_deg / expected_quarter)

    return {
        "arc_span_deg": span_deg,
        "start_angle_deg": best_span["start"],
        "end_angle_deg": best_span["end"],
        "confidence": coverage,
    }


def _find_contiguous_spans(
    angles: list[float], gap_threshold_deg: float = 15.0
) -> list[dict]:
    """Agrupa ângulos contíguos em spans."""
    if not angles:
        return []

    spans = []
    current_span_start = angles[0]
    last = angles[0]

    for angle in angles[1:]:
        if angle - last > gap_threshold_deg:
            # Fim de um span, início de outro
            spans.append({"start": current_span_start, "end": last})
            current_span_start = angle
        last = angle

    spans.append({"start": current_span_start, "end": last})
    return spans


# ==============================================================================
# MATCHING DOOR ↔ ARC
# ==============================================================================

def match_arcs_to_openings(
    openings: list,  # list of Opening (nível 2, gap-only)
    arcs: list[dict],  # output de detect_door_arcs_in_raster
    walls: list,  # list of Wall
    rooms: list,  # list of Room
) -> list[OpeningLevel3]:
    """Empareia cada opening (door candidate) com arc detectado,
    infere hinge_side, swing_deg, opens_to_room.
    """
    level3_openings = []

    for opening in openings:
        if opening.kind not in ("door", "passage"):
            # Windows não têm arc — copiar como nível 2
            level3_openings.append(
                OpeningLevel3(
                    id=opening.id,
                    wall_id=opening.wall_id,
                    offset_m=opening.offset_m,
                    width_m=opening.width_m,
                    kind=opening.kind,
                    confidence=0.8,  # nível 2 confidence
                )
            )
            continue

        # Para doors/passages: procurar arc cujo centro coincide com canto do gap
        wall = next((w for w in walls if w.id == opening.wall_id), None)
        if wall is None:
            level3_openings.append(_opening_to_level3_basic(opening))
            continue

        gap_corners = _compute_gap_corners(wall, opening)
        matched_arc = None
        best_distance = float('inf')

        for arc in arcs:
            arc_center = arc["center"]
            for corner in gap_corners:
                dist = math.hypot(arc_center[0] - corner[0], arc_center[1] - corner[1])
                # Arc deve ter centro próximo ao canto + raio similar ao width da porta
                radius_diff = abs(arc["radius"] - opening.width_m * _pixels_per_meter(150.0))
                if dist < 20 and radius_diff < 30 and dist < best_distance:
                    best_distance = dist
                    matched_arc = (arc, corner)

        if matched_arc is None:
            level3_openings.append(_opening_to_level3_basic(opening))
            continue

        arc, corner = matched_arc
        hinge_side = _infer_hinge_side(wall, corner, arc)
        swing_deg = _infer_swing_deg(arc)
        opens_to_rooms = _find_rooms_adjacent_to_opening(opening, wall, rooms)

        confidence = arc["confidence"] * 0.8 + (0.2 if opens_to_rooms else 0.0)

        level3_openings.append(
            OpeningLevel3(
                id=opening.id,
                wall_id=opening.wall_id,
                offset_m=opening.offset_m,
                width_m=opening.width_m,
                kind=opening.kind,
                arc_center=arc["center"],
                arc_radius=arc["radius"],
                hinge_side=hinge_side,
                swing_deg=swing_deg,
                opens_to_room=opens_to_rooms,
                confidence=confidence,
            )
        )

    return level3_openings


def _compute_gap_corners(wall, opening) -> list[tuple[float, float]]:
    """Retorna os 2 cantos do gap de opening dentro da wall."""
    import math
    p0 = wall.p0
    p1 = wall.p1

    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    wall_length = math.hypot(dx, dy)
    if wall_length == 0:
        return []

    unit_x = dx / wall_length
    unit_y = dy / wall_length

    offset_px = opening.offset_m * _pixels_per_meter(150.0)
    width_px = opening.width_m * _pixels_per_meter(150.0)

    corner_start = (p0[0] + offset_px * unit_x, p0[1] + offset_px * unit_y)
    corner_end = (
        corner_start[0] + width_px * unit_x,
        corner_start[1] + width_px * unit_y,
    )

    return [corner_start, corner_end]


def _infer_hinge_side(wall, corner, arc) -> str:
    """Determina lado do hinge baseado em posição do arc center.

    Se arc center está à "esquerda" da direção wall-parallel: hinge_side = "left"
    Senão: "right"

    Convenção: "esquerda" relativa à direção do wall apontando p0 → p1.
    """
    # Vector normal à wall (apontando para cima/esquerda relativa)
    wall_dx = wall.p1[0] - wall.p0[0]
    wall_dy = wall.p1[1] - wall.p0[1]
    normal_x = -wall_dy  # rotação 90° anti-horária
    normal_y = wall_dx

    # Vector do corner ao arc center
    arc_cx, arc_cy = arc["center"]
    dx = arc_cx - corner[0]
    dy = arc_cy - corner[1]

    # Dot product com normal → positivo = "esquerda"
    dot = dx * normal_x + dy * normal_y

    return "left" if dot > 0 else "right"


def _infer_swing_deg(arc) -> float:
    """Swing angle do arc (start → end)."""
    return float(arc["end_angle_deg"] - arc["start_angle_deg"])


def _find_rooms_adjacent_to_opening(opening, wall, rooms) -> Optional[tuple[str, str]]:
    """Encontra os 2 rooms que o opening conecta.

    Uma porta é fronteira entre 2 rooms. Se só 1 room está adjacente,
    significa que opening está no perímetro externo.
    """
    # Ponto central do opening
    wall_dx = wall.p1[0] - wall.p0[0]
    wall_dy = wall.p1[1] - wall.p0[1]
    wall_length = math.hypot(wall_dx, wall_dy)
    if wall_length == 0:
        return None

    offset_px = opening.offset_m * _pixels_per_meter(150.0)
    mid_x = wall.p0[0] + (offset_px + opening.width_m * _pixels_per_meter(150.0) / 2) * wall_dx / wall_length
    mid_y = wall.p0[1] + (offset_px + opening.width_m * _pixels_per_meter(150.0) / 2) * wall_dy / wall_length

    # Check qual rooms estão a ambos os lados do opening (offset pequeno perpendicular)
    normal_x = -wall_dy / wall_length
    normal_y = wall_dx / wall_length
    delta = 10  # pixels

    side_a_point = (mid_x + delta * normal_x, mid_y + delta * normal_y)
    side_b_point = (mid_x - delta * normal_x, mid_y - delta * normal_y)

    room_a = _find_room_containing_point(side_a_point, rooms)
    room_b = _find_room_containing_point(side_b_point, rooms)

    if room_a and room_b:
        return (room_a.id, room_b.id)
    elif room_a:
        return (room_a.id, "external")
    elif room_b:
        return (room_b.id, "external")
    else:
        return None


def _find_room_containing_point(point, rooms):
    """Busca room cujo polígono contém o ponto."""
    try:
        from shapely.geometry import Point, Polygon
    except ImportError:
        return None

    p = Point(point)
    for room in rooms:
        if hasattr(room, "polygon"):
            poly = Polygon(room.polygon)
            if poly.contains(p):
                return room
    return None


def _pixels_per_meter(dpi: float, scale: float = 100.0) -> float:
    """Conversão pixels → metros. Default: planta 1:100 @ 150 DPI = 59 px/m."""
    return dpi / 2.54 * scale / 100.0


def _opening_to_level3_basic(opening):
    """Converte Opening nível 2 em Level3 sem arc data (fallback)."""
    return OpeningLevel3(
        id=opening.id,
        wall_id=opening.wall_id,
        offset_m=opening.offset_m,
        width_m=opening.width_m,
        kind=opening.kind,
        confidence=0.6,  # baixa, sem arc
    )


# ==============================================================================
# INTEGRAÇÃO em openings/service.py
# ==============================================================================

# Expandir a função existente detect_openings:
#
# def detect_openings(
#     walls: list[Wall],
#     raster_image: np.ndarray = None,  # NOVO
#     rooms: list[Room] = None,  # NOVO
#     peitoris: list | None = None,
# ) -> tuple[list[Wall], list[OpeningLevel3]]:
#
#     # Level 2: gap detection (existente)
#     extended_walls, level2_openings = _detect_gap_openings(walls, peitoris)
#
#     # Level 3: arc detection + hinge + swing + rooms
#     if raster_image is not None and rooms is not None:
#         arcs = detect_door_arcs_in_raster(raster_image)
#         level3_openings = match_arcs_to_openings(
#             level2_openings, arcs, walls, rooms
#         )
#     else:
#         # Fallback: converter nível 2 → 3 sem arc data
#         level3_openings = [_opening_to_level3_basic(o) for o in level2_openings]
#
#     return extended_walls, level3_openings
