"""Opening detector.

Para cada par de walls colineares com gap pequeno entre eles, registra um
"opening" (vao/porta) e cria uma wall fantasma preenchendo o gap. A wall
fantasma carrega `source="opening_bridge"` pra ser identificada mais tarde
e tem `confidence` reduzida.

Por que: o `polygonize` do shapely so fecha um poligono se as walls de
fato se tocam. Gaps de porta deixam o poligono aberto e nenhuma sala e
detectada. Esse modulo "fecha" os gaps semanticamente sem perder a
informacao de onde estava o vao.

Niveis do detector (cascata):
    Nivel 1-2: gap-detection colinear puro (este modulo desde sempre)
    Nivel 3:  confirmacao por arco (quarter-circle) -> hinge_side + swing_deg
    Nivel 4:  mapeamento rooms[A,B] via point-in-polygon

Niveis 3-4 so disparam se `image` (raster da pagina) e `rooms` forem
fornecidos a `detect_openings`. Caso contrario o detector degrada para
nivel 1-2 mantendo retro-compatibilidade.

INVARIANTE: se o arco nao for confirmado, hinge_side/swing_deg ficam
None e a confidence do opening cai para 0.5. Nunca chutar.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from model.types import Room, Wall

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    _HAS_CV2 = True
except Exception:  # pragma: no cover - cv2 always present in repo
    _HAS_CV2 = False


# Faixa tipica de porta arquitetonica em pixel @ 150 DPI (planta padrao):
# - porta interna 0.6-0.9 m -> ~50-100 px
# - porta dupla / porta-de-acesso  ate 1.4 m -> ~150 px
# Gaps maiores ja entram em "passagem aberta" / vao de janela e nao
# devem virar opening (provavelmente sao paredes nao detectadas, nao
# portas reais).
_MIN_OPENING_PX = 8.0
_MAX_OPENING_PX = 280.0
_PERP_TOLERANCE = 6.0

# Classificacao por largura (px @ 150 DPI):
#   < 110 px (~73 cm)        -> door (porta padrao)
#   110-200 px (73-133 cm)   -> door (porta dupla / acesso)
#   200-280 px (133-186 cm)  -> window OU passage (depende de peitoril)
#   > 280                     -> passage (vao aberto largo)
_DOOR_MAX_PX = 200.0
_PEITORIL_PROXIMITY_PX = 30.0

# Corner-extension: distancia maxima que um endpoint pode ser puxado pra
# encontrar uma wall perpendicular proxima. Cobre L-corners abertos por
# imprecisao do desenho a mao.
_CORNER_SNAP_PX = 60.0

# Nivel 3: parametros do arc-confirm.
# Raio esperado ~ largura do gap. Tolerancia +-30% cobre escala/desenho.
_ARC_RADIUS_TOL = 0.30
# Box de busca ao redor do gap: 1.5x a largura em cada direcao perp,
# o suficiente pra englobar um quarter-circle de raio ~width.
_ARC_BBOX_PAD_RATIO = 1.6
# Hough: threshold de acumulacao baixo porque o arco e' so 1/4 do circulo.
_ARC_HOUGH_PARAM2 = 18
# Quanto da circunferencia ideal precisa estar coberto por pixels pretos
# pra confirmar como arco real (proximo de 1/4 = 0.25; usamos 0.18 pra
# tolerar arco quebrado/com folha desenhada).
_ARC_COVERAGE_MIN = 0.18
# Distancia maxima do centro do arco ate um dos 2 cantos do gap (em px),
# em fracao da largura do gap. Pivo precisa ser claramente um canto.
_ARC_PIVOT_TOL_RATIO = 0.35


@dataclass(frozen=True)
class Opening:
    opening_id: str
    page_index: int
    orientation: str
    center: tuple[float, float]
    width: float
    wall_a: str
    wall_b: str
    kind: str = "door"  # "door" | "window" | "passage"
    # Nivel 3: arc-confirm. None se arco nao localizado no raster.
    hinge_side: Optional[str] = None    # "left" | "right" | "top" | "bottom"
    swing_deg: Optional[float] = None   # tipicamente ~90.0
    # Nivel 4: rooms vizinhos. None se nao mapeavel.
    room_a: Optional[str] = None
    room_b: Optional[str] = None
    # Confidence cai pra 0.5 quando o arco nao e' confirmado.
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "opening_id": self.opening_id,
            "page_index": self.page_index,
            "orientation": self.orientation,
            "center": [round(self.center[0], 3), round(self.center[1], 3)],
            "width": round(self.width, 3),
            "wall_a": self.wall_a,
            "wall_b": self.wall_b,
            "kind": self.kind,
            "hinge_side": self.hinge_side,
            "swing_deg": (
                round(self.swing_deg, 1) if self.swing_deg is not None else None
            ),
            "room_a": self.room_a,
            "room_b": self.room_b,
            "confidence": round(self.confidence, 3),
        }


def detect_openings(
    walls: list[Wall],
    peitoris: list[dict] | None = None,
    image=None,
    rooms: list[Room] | None = None,
) -> tuple[list[Wall], list[Opening]]:
    """Retorna (walls_estendidas, openings_detectados).

    walls_estendidas inclui as originais + walls fantasma "opening_bridge"
    que conectam pares colineares com gap pequeno.

    `peitoris`: lista opcional de dicts com `bbox=[x1,y1,x2,y2]`. Openings
    proximos a um peitoril (centro do opening dentro do bbox expandido
    em _PEITORIL_PROXIMITY_PX) sao classificados como "window" em vez de
    "door"/"passage".

    `image`: raster opcional (np.ndarray BGR ou GRAY) da pagina. Quando
    fornecido, dispara o nivel 3 (arc-confirm) que preenche hinge_side
    e swing_deg. Sem imagem, esses campos ficam None.

    `rooms`: lista opcional de Room ja polygonizados. Quando fornecida,
    dispara o nivel 4 (room mapping) que preenche room_a/room_b por
    point-in-polygon nos dois lados perpendiculares ao opening.
    """
    peitoris = peitoris or []
    rooms = rooms or []
    if not walls:
        return list(walls), []

    # antes de detectar gaps colineares, fecha cantos abertos (extensao
    # perpendicular). Isso aumenta a chance de polygonize fechar rooms.
    walls = _extend_to_perpendicular(walls)

    by_group: dict[tuple[int, str], list[Wall]] = {}
    for w in walls:
        by_group.setdefault((w.page_index, w.orientation), []).append(w)

    extended: list[Wall] = list(walls)
    openings: list[Opening] = []
    bridge_counter = 1
    opening_counter = 1
    next_wall_id = max((_wall_id_num(w.wall_id) for w in walls), default=0) + 1

    for (page_index, orientation), group in by_group.items():
        # cluster por coord perpendicular
        clusters = _cluster_by_perp(group, orientation, _PERP_TOLERANCE)
        for cluster in clusters:
            if len(cluster) < 2:
                continue
            # ordena pelo inicio paralelo
            cluster_sorted = sorted(
                cluster, key=lambda w: _para_range(w, orientation)[0]
            )
            for a, b in zip(cluster_sorted, cluster_sorted[1:]):
                a_range = _para_range(a, orientation)
                b_range = _para_range(b, orientation)
                gap = b_range[0] - a_range[1]
                if gap < _MIN_OPENING_PX or gap > _MAX_OPENING_PX:
                    continue
                # cria wall fantasma preenchendo o gap
                bridge_wall = _make_bridge(
                    a=a,
                    b=b,
                    a_end=a_range[1],
                    b_start=b_range[0],
                    orientation=orientation,
                    new_id=f"wall-{next_wall_id}",
                )
                next_wall_id += 1
                extended.append(bridge_wall)
                # registra opening
                center_para = (a_range[1] + b_range[0]) / 2.0
                center_perp = (
                    _perp_coord(a, orientation) + _perp_coord(b, orientation)
                ) / 2.0
                if orientation == "horizontal":
                    center = (round(center_para, 3), round(center_perp, 3))
                else:
                    center = (round(center_perp, 3), round(center_para, 3))
                kind = _classify_opening(center, gap, peitoris)

                hinge_side: Optional[str] = None
                swing_deg: Optional[float] = None
                confidence = 1.0
                # Nivel 3: arc-confirm. So pra portas (window/passage nao
                # tem arco). Pula silenciosamente se cv2 indisponivel.
                if image is not None and kind == "door" and _HAS_CV2:
                    arc_result = _detect_arc_and_hinge(
                        image=image,
                        opening_center=center,
                        opening_width=gap,
                        orientation=orientation,
                    )
                    if arc_result is not None:
                        hinge_side, swing_deg = arc_result
                    else:
                        # Invariante: arco nao confirmado -> nao chutar.
                        confidence = 0.5

                # Nivel 4: room mapping (independe do arco).
                room_a_id, room_b_id = _assign_rooms(
                    center=center,
                    orientation=orientation,
                    width=gap,
                    rooms=rooms,
                )

                openings.append(
                    Opening(
                        opening_id=f"opening-{opening_counter}",
                        page_index=page_index,
                        orientation=orientation,
                        center=center,
                        width=gap,
                        wall_a=a.wall_id,
                        wall_b=b.wall_id,
                        kind=kind,
                        hinge_side=hinge_side,
                        swing_deg=swing_deg,
                        room_a=room_a_id,
                        room_b=room_b_id,
                        confidence=confidence,
                    )
                )
                opening_counter += 1
                bridge_counter += 1

    return extended, openings


# ---------- helpers ----------

def _extend_to_perpendicular(walls: list[Wall]) -> list[Wall]:
    """Estende endpoints de walls que estao a < _CORNER_SNAP_PX de uma
    wall perpendicular. Resolve L-corners abertos onde uma horizontal
    quase encontra uma vertical mas nao chega.

    Implementacao: para cada wall W e cada um dos seus 2 endpoints E,
    procura walls perpendiculares cuja linha (infinita) passa a < snap_px
    de E E cujo range inclui (ou quase inclui) o ponto de projecao.
    Se achar, move E pro ponto de intersecao.
    """
    by_page: dict[int, list[Wall]] = {}
    for w in walls:
        by_page.setdefault(w.page_index, []).append(w)

    out: list[Wall] = []
    for page_index, group in by_page.items():
        h_walls = [w for w in group if w.orientation == "horizontal"]
        v_walls = [w for w in group if w.orientation == "vertical"]
        for w in group:
            new_start = w.start
            new_end = w.end
            others = v_walls if w.orientation == "horizontal" else h_walls
            new_start = _snap_endpoint(new_start, w.orientation, others)
            new_end = _snap_endpoint(new_end, w.orientation, others)
            if new_start == w.start and new_end == w.end:
                out.append(w)
            else:
                out.append(
                    Wall(
                        wall_id=w.wall_id,
                        page_index=w.page_index,
                        start=new_start,
                        end=new_end,
                        thickness=w.thickness,
                        orientation=w.orientation,
                        source=w.source,
                        confidence=w.confidence,
                    )
                )
    return out


def _snap_endpoint(
    point: tuple[float, float], orientation: str, perpendiculars: list[Wall]
) -> tuple[float, float]:
    """Move point pra interseccao com a wall perpendicular mais proxima
    se a distancia for <= _CORNER_SNAP_PX."""
    px, py = point
    best_dist = _CORNER_SNAP_PX
    best_target: tuple[float, float] | None = None
    for w in perpendiculars:
        if w.orientation == "horizontal":
            # linha y = w_y; intersection x = ponto.x
            wy = w.start[1]
            wx_min = min(w.start[0], w.end[0])
            wx_max = max(w.start[0], w.end[0])
            # ponto.x precisa estar dentro (ou quase) do range x da wall H
            if px < wx_min - _CORNER_SNAP_PX or px > wx_max + _CORNER_SNAP_PX:
                continue
            # clampa x ao range da wall H (caso esteja so um pouco fora)
            tx = max(wx_min, min(wx_max, px))
            d = abs(py - wy) + abs(px - tx) * 0.3  # leve preferencia perp
            if d < best_dist:
                best_dist = d
                best_target = (tx, wy)
        else:  # vertical
            wx = w.start[0]
            wy_min = min(w.start[1], w.end[1])
            wy_max = max(w.start[1], w.end[1])
            if py < wy_min - _CORNER_SNAP_PX or py > wy_max + _CORNER_SNAP_PX:
                continue
            ty = max(wy_min, min(wy_max, py))
            d = abs(px - wx) + abs(py - ty) * 0.3
            if d < best_dist:
                best_dist = d
                best_target = (wx, ty)
    if best_target is not None:
        return (round(best_target[0], 3), round(best_target[1], 3))
    return point


def _classify_opening(
    center: tuple[float, float], width: float, peitoris: list[dict]
) -> str:
    cx, cy = center
    on_peitoril = False
    for p in peitoris:
        bb = p.get("bbox") or []
        if len(bb) != 4:
            continue
        x1, y1, x2, y2 = bb
        x1 -= _PEITORIL_PROXIMITY_PX; x2 += _PEITORIL_PROXIMITY_PX
        y1 -= _PEITORIL_PROXIMITY_PX; y2 += _PEITORIL_PROXIMITY_PX
        if x1 <= cx <= x2 and y1 <= cy <= y2:
            on_peitoril = True
            break
    if on_peitoril:
        return "window"
    if width > _DOOR_MAX_PX:
        return "passage"
    return "door"




def _wall_id_num(wall_id: str) -> int:
    try:
        return int(wall_id.rsplit("-", 1)[-1])
    except Exception:
        return 0


def _perp_coord(w: Wall, orientation: str) -> float:
    return w.start[1] if orientation == "horizontal" else w.start[0]


def _para_range(w: Wall, orientation: str) -> tuple[float, float]:
    if orientation == "horizontal":
        return (min(w.start[0], w.end[0]), max(w.start[0], w.end[0]))
    return (min(w.start[1], w.end[1]), max(w.start[1], w.end[1]))


def _cluster_by_perp(
    walls: list[Wall], orientation: str, tolerance: float
) -> list[list[Wall]]:
    if not walls:
        return []
    ordered = sorted(walls, key=lambda w: _perp_coord(w, orientation))
    clusters: list[list[Wall]] = [[ordered[0]]]
    cur_mean = _perp_coord(ordered[0], orientation)
    for w in ordered[1:]:
        c = _perp_coord(w, orientation)
        if abs(c - cur_mean) <= tolerance:
            clusters[-1].append(w)
            cur_mean = sum(_perp_coord(x, orientation) for x in clusters[-1]) / len(
                clusters[-1]
            )
        else:
            clusters.append([w])
            cur_mean = c
    return clusters


def _make_bridge(
    a: Wall, b: Wall, a_end: float, b_start: float, orientation: str, new_id: str
) -> Wall:
    perp = (_perp_coord(a, orientation) + _perp_coord(b, orientation)) / 2.0
    if orientation == "horizontal":
        start = (round(a_end, 3), round(perp, 3))
        end = (round(b_start, 3), round(perp, 3))
    else:
        start = (round(perp, 3), round(a_end, 3))
        end = (round(perp, 3), round(b_start, 3))
    return Wall(
        wall_id=new_id,
        page_index=a.page_index,
        start=start,
        end=end,
        thickness=max(a.thickness, b.thickness),
        orientation=orientation,
        source="opening_bridge",
        confidence=0.5,
    )


# ---------- nivel 3: arc-confirm ----------

def _detect_arc_and_hinge(
    image,
    opening_center: tuple[float, float],
    opening_width: float,
    orientation: str,
) -> tuple[str, float] | None:
    """Confirma a presenca de um quarter-circle (arco da porta) no raster.

    Estrategia:
      1. Isola uma ROI quadrada centrada em `opening_center` com lado
         proporcional a `opening_width`.
      2. Binariza (black=line).
      3. Tenta cv2.HoughCircles no patch com raios proximos a
         `opening_width`. Para cada circulo candidato, mede que fracao
         da sua circunferencia cai sobre pixels pretos (arc coverage)
         e se o centro do circulo esta a <_ARC_PIVOT_TOL_RATIO*width
         de UM dos 2 cantos do gap.
      4. Se encontrar, deduz hinge_side a partir de qual canto e'
         o pivo (left/right pra horizontal, top/bottom pra vertical).

    Retorna (hinge_side, swing_deg) em caso de confirmacao; None caso
    contrario. NAO chuta: o chamador marca confidence baixa nesse caso.
    """
    if not _HAS_CV2 or image is None:
        return None

    cx, cy = opening_center
    width = float(opening_width)
    if width <= 0:
        return None

    # ROI
    pad = max(int(width * _ARC_BBOX_PAD_RATIO), 20)
    h, w = image.shape[:2]
    x0 = max(0, int(round(cx - pad)))
    x1 = min(w, int(round(cx + pad)))
    y0 = max(0, int(round(cy - pad)))
    y1 = min(h, int(round(cy + pad)))
    if x1 - x0 < 10 or y1 - y0 < 10:
        return None
    roi = image[y0:y1, x0:x1]

    # GRAY + binariza (preto = tinta da planta)
    if roi.ndim == 3:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    else:
        gray = roi
    # Threshold: linhas pretas -> 255 em mask; resto -> 0.
    _, mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

    # HoughCircles quer uint8 borrado
    blurred = cv2.GaussianBlur(gray, (5, 5), 1.0)
    r_min = max(5, int(round(width * (1.0 - _ARC_RADIUS_TOL))))
    r_max = max(r_min + 2, int(round(width * (1.0 + _ARC_RADIUS_TOL))))
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(10, int(width * 0.5)),
        param1=80,
        param2=_ARC_HOUGH_PARAM2,
        minRadius=r_min,
        maxRadius=r_max,
    )
    if circles is None:
        return None

    # cantos do gap em coords da ROI
    if orientation == "horizontal":
        corner_a_roi = (cx - width / 2.0 - x0, cy - y0)  # left corner
        corner_b_roi = (cx + width / 2.0 - x0, cy - y0)  # right corner
        side_a, side_b = "left", "right"
    else:
        corner_a_roi = (cx - x0, cy - width / 2.0 - y0)  # top corner
        corner_b_roi = (cx - x0, cy + width / 2.0 - y0)  # bottom corner
        side_a, side_b = "top", "bottom"

    best: tuple[str, float, float] | None = None  # (side, coverage, radius)
    pivot_tol = max(6.0, width * _ARC_PIVOT_TOL_RATIO)

    for (ccx, ccy, cr) in circles[0]:
        # pivo precisa coincidir com um dos cantos do gap
        da = math.hypot(ccx - corner_a_roi[0], ccy - corner_a_roi[1])
        db = math.hypot(ccx - corner_b_roi[0], ccy - corner_b_roi[1])
        if min(da, db) > pivot_tol:
            continue
        hinge = side_a if da <= db else side_b
        coverage = _arc_coverage(mask, (ccx, ccy), cr)
        if coverage < _ARC_COVERAGE_MIN:
            continue
        if best is None or coverage > best[1]:
            best = (hinge, float(coverage), float(cr))

    if best is None:
        return None

    hinge_side, coverage, radius = best
    # Swing e' o angulo varrido pelo arco. Como filtramos por proximidade
    # de 1/4 de circunferencia, assumimos 90 deg. Refinamento futuro pode
    # medir angulo exato dos endpoints da folha.
    swing_deg = round(90.0 * min(1.0, coverage / 0.25), 1)
    return hinge_side, swing_deg


def _arc_coverage(mask, center: tuple[float, float], radius: float) -> float:
    """Fracao da circunferencia do circulo coberta por pixels pretos
    no mask. Amostra 120 pontos uniformes; retorna count/120.
    """
    if radius <= 0:
        return 0.0
    h, w = mask.shape[:2]
    hits = 0
    samples = 120
    cx, cy = center
    for i in range(samples):
        theta = 2.0 * math.pi * i / samples
        px = int(round(cx + radius * math.cos(theta)))
        py = int(round(cy + radius * math.sin(theta)))
        if 0 <= px < w and 0 <= py < h:
            # tolera 1 pixel de erro (banda de 3x3)
            x0 = max(0, px - 1); x1 = min(w, px + 2)
            y0 = max(0, py - 1); y1 = min(h, py + 2)
            if mask[y0:y1, x0:x1].any():
                hits += 1
    return hits / float(samples)


# ---------- nivel 4: room mapping ----------

def _assign_rooms(
    center: tuple[float, float],
    orientation: str,
    width: float,
    rooms: list[Room],
) -> tuple[Optional[str], Optional[str]]:
    """Mapeia (room_a, room_b) tomando 2 probes perpendiculares ao opening,
    um de cada lado, a uma distancia = width/2 + margem.

    Query point-in-polygon (ray casting). Retorna (None, None) se rooms
    vazio ou se nenhum probe cai dentro de room. Retorna (id, None) se
    so um lado foi mapeado (exterior do edificio, por exemplo).
    """
    if not rooms:
        return None, None

    cx, cy = center
    offset = max(width * 0.6, 8.0)
    if orientation == "horizontal":
        # opening varre em X; os dois lados sao +/- Y
        probe_a = (cx, cy - offset)
        probe_b = (cx, cy + offset)
    else:
        probe_a = (cx - offset, cy)
        probe_b = (cx + offset, cy)

    room_a = _room_containing(probe_a, rooms)
    room_b = _room_containing(probe_b, rooms)
    # evita mapear ambos para a mesma room (opening nao separa nada)
    if room_a is not None and room_a == room_b:
        return room_a, None
    return room_a, room_b


def _room_containing(
    point: tuple[float, float], rooms: list[Room]
) -> Optional[str]:
    for room in rooms:
        if _point_in_polygon(point, room.polygon):
            return room.room_id
    return None


def _point_in_polygon(
    point: tuple[float, float], polygon: list[tuple[float, float]]
) -> bool:
    """Ray casting classico. polygon: lista de vertices sem repetir
    o ultimo (formato Room.polygon em types.py).
    """
    if len(polygon) < 3:
        return False
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        # edge cruza a linha horizontal y?
        if (y1 > y) != (y2 > y):
            x_intersect = (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1
            if x < x_intersect:
                inside = not inside
    return inside
