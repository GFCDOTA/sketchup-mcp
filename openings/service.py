"""Opening detector.

Para cada par de walls colineares com gap pequeno entre eles, registra um
"opening" (vao/porta) e cria uma wall fantasma preenchendo o gap. A wall
fantasma carrega `source="opening_bridge"` pra ser identificada mais tarde
e tem `confidence` reduzida.

Por que: o `polygonize` do shapely so fecha um poligono se as walls de
fato se tocam. Gaps de porta deixam o poligono aberto e nenhuma sala e
detectada. Esse modulo "fecha" os gaps semanticamente sem perder a
informacao de onde estava o vao.
"""
from __future__ import annotations

from dataclasses import dataclass

from model.types import Wall


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
        }


def detect_openings(
    walls: list[Wall],
    peitoris: list[dict] | None = None,
) -> tuple[list[Wall], list[Opening]]:
    """Retorna (walls_estendidas, openings_detectados).

    walls_estendidas inclui as originais + walls fantasma "opening_bridge"
    que conectam pares colineares com gap pequeno.

    `peitoris`: lista opcional de dicts com `bbox=[x1,y1,x2,y2]`. Openings
    proximos a um peitoril (centro do opening dentro do bbox expandido
    em _PEITORIL_PROXIMITY_PX) sao classificados como "window" em vez de
    "door"/"passage".
    """
    peitoris = peitoris or []
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
