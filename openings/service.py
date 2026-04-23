"""Opening detector.

Para cada par de walls colineares com gap pequeno entre eles, registra um
"opening" (vao/porta) e cria uma wall fantasma preenchendo o gap. A wall
fantasma carrega `source="opening_bridge"` pra ser identificada mais tarde
e tem `confidence` reduzida.

Por que: o `polygonize` do shapely so fecha um poligono se as walls de
fato se tocam. Gaps de porta deixam o poligono aberto e nenhuma sala e
detectada. Esse modulo "fecha" os gaps semanticamente sem perder a
informacao de onde estava o vao.

F7 adiciona 4 estagios de filtro pos-deteccao bruta:
  1. Gate adaptativo `_compute_max_opening_px` substitui o limite fixo
     _MAX_OPENING_PX. Plantas com paredes pequenas (planta_74, median
     ~140 px) recebem um teto mais baixo que plantas uniformes (p12,
     median ~170 px). Evita que "paredes nao detectadas" virem portas
     espurias.
  2. Dedup por locus — openings co-localizados (mesma orientacao,
     perpendicular similar, centros a <=30 px) sao fundidos. Em planta
     real portas raramente estao tao proximas.
  3. Filtro por room membership — opening sem nenhuma room associada
     (room_a=None E room_b=None) e flutuante/espuria e removido.
  4. Modo strict opt-in — quando nenhum arco eh visivel e strict=True,
     opening eh demoted de "door" pra "passage" em vez de sair como door
     sem confirmacao. Nao muda contagem, so semantica.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from model.types import Wall


# Faixa tipica de porta arquitetonica em pixel @ 150 DPI (planta padrao):
# - porta interna 0.6-0.9 m -> ~50-100 px
# - porta dupla / porta-de-acesso  ate 1.4 m -> ~150 px
# Gaps maiores ja entram em "passagem aberta" / vao de janela e nao
# devem virar opening (provavelmente sao paredes nao detectadas, nao
# portas reais).
_MIN_OPENING_PX = 8.0
_MAX_OPENING_PX = 280.0  # fallback se _compute_max_opening_px nao resolve
_PERP_TOLERANCE = 6.0

# F7: piso e teto do gate adaptativo. O piso (180 px) garante que mesmo
# plantas com paredes curtas em massa (planta_74) ainda conseguem
# reconhecer vaos de acesso largos. O teto (320 px) protege contra
# medianas infladas.
_ADAPTIVE_GATE_MIN_PX = 180.0
_ADAPTIVE_GATE_MAX_PX = 320.0
_ADAPTIVE_GATE_FACTOR = 1.8 / 3.0  # ~0.6 * median_length

# F7: dedup por locus — openings com centro a distancia <= _LOCUS_EPS_PX
# E mesma orientacao E mesma faixa perpendicular (tolerancia _PERP_TOLERANCE)
# sao considerados o mesmo vao fisico duplicado.
_LOCUS_EPS_PX = 30.0

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
    # F7 enriched fields (level 4 — room membership). `room_a`/`room_b`
    # ficam None quando a opening esta entre interior e exterior, ou
    # quando a rooms list nao foi passada (compat com chamadas antigas).
    room_a: str | None = None
    room_b: str | None = None
    confidence: float = 1.0

    def to_dict(self) -> dict:
        d = {
            "opening_id": self.opening_id,
            "page_index": self.page_index,
            "orientation": self.orientation,
            "center": [round(self.center[0], 3), round(self.center[1], 3)],
            "width": round(self.width, 3),
            "wall_a": self.wall_a,
            "wall_b": self.wall_b,
            "kind": self.kind,
            "room_a": self.room_a,
            "room_b": self.room_b,
            "confidence": round(self.confidence, 3),
        }
        return d


def detect_openings(
    walls: list[Wall],
    peitoris: list[dict] | None = None,
    rooms: list[Any] | None = None,
    strict_openings: bool = False,
) -> tuple[list[Wall], list[Opening]]:
    """Retorna (walls_estendidas, openings_detectados).

    walls_estendidas inclui as originais + walls fantasma "opening_bridge"
    que conectam pares colineares com gap pequeno.

    `peitoris`: lista opcional de dicts com `bbox=[x1,y1,x2,y2]`. Openings
    proximos a um peitoril (centro do opening dentro do bbox expandido
    em _PEITORIL_PROXIMITY_PX) sao classificados como "window" em vez de
    "door"/"passage".

    `rooms`: opcional. Quando passado, F7-level-4 atribui `room_a`/`room_b`
    a cada opening via point-in-polygon do centroid offsetado no eixo
    perpendicular; openings com ambos os lados sem room sao dropados
    (flutuantes). Quando None, nenhum filtro por room eh aplicado.

    `strict_openings`: F7-strict mode. Quando True e o opening nao tem
    arco confirmado (hinge_side ausente — o que hoje e sempre, ja que
    level 3 nao existe nesta branch), demota "door" pra "passage".
    """
    peitoris = peitoris or []
    if not walls:
        return list(walls), []

    # antes de detectar gaps colineares, fecha cantos abertos (extensao
    # perpendicular). Isso aumenta a chance de polygonize fechar rooms.
    walls = _extend_to_perpendicular(walls)

    # F7: gate adaptativo por comprimento mediano de parede.
    max_opening_px = _compute_max_opening_px(walls)

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
                if gap < _MIN_OPENING_PX or gap > max_opening_px:
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

    # F7 estagio 2: dedup por locus.
    openings = _dedupe_openings_by_locus(openings)

    # F7 estagio 3: filtro por room membership (quando rooms disponivel).
    if rooms is not None:
        openings = _assign_and_filter_rooms(openings, rooms)

    # F7 estagio 4: strict mode demote.
    if strict_openings:
        openings = [_maybe_demote_strict(op) for op in openings]

    # Re-numera ids pra manter sequencia estavel pos-filtros (dedup +
    # room filter podem ter removido buracos). Isso mantem determinismo
    # do hash snapshot a jusante.
    renumbered: list[Opening] = []
    for i, op in enumerate(openings, start=1):
        renumbered.append(
            Opening(
                opening_id=f"opening-{i}",
                page_index=op.page_index,
                orientation=op.orientation,
                center=op.center,
                width=op.width,
                wall_a=op.wall_a,
                wall_b=op.wall_b,
                kind=op.kind,
                room_a=op.room_a,
                room_b=op.room_b,
                confidence=op.confidence,
            )
        )

    return extended, renumbered


# ---------- F7 estagio 1: gate adaptativo --------------------------------


def _compute_max_opening_px(walls: list[Wall]) -> float:
    """Computa o teto de largura de gap admissivel como opening.

    Rationale:
        - Plantas com paredes longas uniformes (p12) tendem a ter
          median alto (~170 px) -> teto ~ 180-210 (compativel com o
          comportamento atual de 280).
        - Plantas com paredes pequenas e muito fragmentadas (planta_74,
          median ~140) -> teto ~180 (piso minimo); paredes nao
          detectadas entre dois segmentos curtos NAO viram porta.

    Usa soma |dx|+|dy| que pra walls horizontais/verticais e exatamente
    o comprimento L1 (idem L2 nesse eixo unico).
    """
    if not walls:
        return _MAX_OPENING_PX
    lengths = sorted(
        abs(w.end[0] - w.start[0]) + abs(w.end[1] - w.start[1]) for w in walls
    )
    median_length = lengths[len(lengths) // 2]
    # Gaps maiores que ~0.6x o comprimento de uma parede mediana sao mais
    # provavelmente paredes nao-detectadas que portas reais.
    candidate = _ADAPTIVE_GATE_FACTOR * median_length
    return max(_ADAPTIVE_GATE_MIN_PX, min(_ADAPTIVE_GATE_MAX_PX, candidate))


# ---------- F7 estagio 2: dedup por locus --------------------------------


def _dedupe_openings_by_locus(openings: list[Opening]) -> list[Opening]:
    """Funde openings co-localizados.

    Regra: dois openings sao o mesmo vao fisico quando
        (1) mesma orientation
        (2) perp_coord proximo (dentro de _PERP_TOLERANCE)
        (3) center a distancia <= _LOCUS_EPS_PX

    Quando funde, mantem o de maior confidence (com desempate por
    width maior — portas detectadas mais completas vencem slivers).

    NAO funde openings perpendiculares mesmo se proximos — so mesmo
    eixo conta como "mesmo vao".
    """
    if len(openings) <= 1:
        return list(openings)

    kept: list[Opening] = []
    absorbed = [False] * len(openings)

    for i, op in enumerate(openings):
        if absorbed[i]:
            continue
        group = [op]
        i_perp = op.center[1] if op.orientation == "horizontal" else op.center[0]
        for j in range(i + 1, len(openings)):
            if absorbed[j]:
                continue
            other = openings[j]
            if other.orientation != op.orientation:
                continue
            j_perp = other.center[1] if other.orientation == "horizontal" else other.center[0]
            if abs(j_perp - i_perp) > _PERP_TOLERANCE:
                continue
            # distancia euclidiana entre centros (2D) — simples o bastante
            dx = op.center[0] - other.center[0]
            dy = op.center[1] - other.center[1]
            if (dx * dx + dy * dy) ** 0.5 <= _LOCUS_EPS_PX:
                group.append(other)
                absorbed[j] = True

        if len(group) == 1:
            kept.append(op)
        else:
            # Escolhe o "melhor": maior confidence, desempate por width
            # maior (porta mais completa vence sliver colado).
            best = max(group, key=lambda o: (o.confidence, o.width))
            kept.append(best)

    return kept


# ---------- F7 estagio 3: room membership filter -------------------------


def _assign_rooms(
    center: tuple[float, float],
    orientation: str,
    width: float,
    rooms: list[Any],
) -> tuple[str | None, str | None]:
    """Dada uma opening (centro + orientacao), retorna (room_a, room_b).

    Estrategia: offseta o centro um pouco pra cada lado no eixo
    perpendicular e aplica point-in-polygon. O offset eh pequeno
    (max(8 px, width * 0.15)) pra ficar dentro da room mais proxima
    sem pular pra sala vizinha.

    `rooms` e uma lista de objetos com atributo `polygon` (list[Point])
    e `room_id`. Se o objeto nao tiver esses atributos (dict bruto),
    tenta chaves equivalentes.
    """
    if not rooms:
        return (None, None)

    # offset perpendicular a orientacao da opening
    offset = max(8.0, width * 0.15)
    cx, cy = center
    if orientation == "horizontal":
        # parede horizontal -> salas ficam acima/abaixo (eixo Y)
        p_left = (cx, cy - offset)
        p_right = (cx, cy + offset)
    else:
        # parede vertical -> salas ficam esquerda/direita (eixo X)
        p_left = (cx - offset, cy)
        p_right = (cx + offset, cy)

    def _resolve(point: tuple[float, float]) -> str | None:
        for r in rooms:
            polygon = getattr(r, "polygon", None)
            if polygon is None and isinstance(r, dict):
                polygon = r.get("polygon")
            room_id = getattr(r, "room_id", None)
            if room_id is None and isinstance(r, dict):
                room_id = r.get("room_id")
            if polygon is None or room_id is None:
                continue
            poly_pts = [tuple(p) for p in polygon]
            if _point_in_polygon(point, poly_pts):
                return str(room_id)
        return None

    room_a = _resolve(p_left)
    room_b = _resolve(p_right)
    return (room_a, room_b)


def _point_in_polygon(
    point: tuple[float, float], polygon: list[tuple[float, float]]
) -> bool:
    """Ray-casting classico. Retorna True se ponto estritamente dentro
    do poligono."""
    if len(polygon) < 3:
        return False
    x, y = point
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _assign_and_filter_rooms(
    openings: list[Opening], rooms: list[Any]
) -> list[Opening]:
    """Atribui room_a/room_b a cada opening e dropa os flutuantes
    (ambos None). Mantem os que sao "exterior-interior" (um lado None
    e o outro room valido)."""
    if not rooms:
        return list(openings)

    kept: list[Opening] = []
    for op in openings:
        room_a, room_b = _assign_rooms(
            center=op.center,
            orientation=op.orientation,
            width=op.width,
            rooms=rooms,
        )
        if room_a is None and room_b is None:
            # opening flutuante sem room de nenhum lado -> drop
            continue
        kept.append(
            Opening(
                opening_id=op.opening_id,
                page_index=op.page_index,
                orientation=op.orientation,
                center=op.center,
                width=op.width,
                wall_a=op.wall_a,
                wall_b=op.wall_b,
                kind=op.kind,
                room_a=room_a,
                room_b=room_b,
                confidence=op.confidence,
            )
        )
    return kept


# ---------- F7 estagio 4: strict mode ------------------------------------


def _maybe_demote_strict(op: Opening) -> Opening:
    """Strict mode: opening sem arco confirmado vira passage (nao door).

    Nesta branch `hinge_side` nao existe no Opening — TODO arc-confirm
    (level 3) fica pra V6.2+. Enquanto isso, strict eh equivalente a
    "toda porta que nao passou por arc-confirm vira passage", que
    atualmente significa "toda porta". Por isso strict_openings default
    continua False.

    A semantica e: quando uma futura evolucao adicionar hinge_side,
    este helper ja vai funcionar corretamente — so demota quando
    hinge_side is None.
    """
    hinge_side = getattr(op, "hinge_side", None)
    if op.kind == "door" and hinge_side is None:
        return Opening(
            opening_id=op.opening_id,
            page_index=op.page_index,
            orientation=op.orientation,
            center=op.center,
            width=op.width,
            wall_a=op.wall_a,
            wall_b=op.wall_b,
            kind="passage",
            room_a=op.room_a,
            room_b=op.room_b,
            confidence=op.confidence,
        )
    return op


# ---------- helpers originais --------------------------------------------

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
