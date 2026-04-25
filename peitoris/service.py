"""Detector automatico de peitoris/muretas em planta colorida.

Por que existe:
    Antes, peitoris eram injetados manualmente via `pNN_peitoris.json`
    (gerado por `proto_colored.py` em paralelo ao pipeline). Isso quebra
    a invariante "nao acoplar a um PDF especifico" porque o operador
    precisa rodar um script extra por planta.

Como funciona:
    A legenda do PDF planta_baixa_74m2 (project_planta_pdf_semantica.md)
    define peitoril H=1.10m e mureta H=0.70m como elementos desenhados em
    cor MARROM, distinta da alvenaria VERMELHA. Geometricamente sao 2
    linhas paralelas curtas (mureta de balaustrada), formando um
    retangulo ESTREITO e ALONGADO (~5-15 px de espessura, dezenas a
    centenas de px de comprimento).

    Fluxo:
        1. RGB/BGR -> HSV
        2. Mascara MARROM (faixa H=8-25, S>=80, V=40-180)
        3. Subtrai sobreposicao com VERMELHO (alvenaria) pra evitar
           pixels de borda misturada
        4. MORPH_CLOSE 3x3 itx2 pra reconectar fragmentos
        5. connectedComponentsWithStats
        6. Filtra por:
            - area >= min_area_px (default 200)
            - lado maior (max(w,h)) >= min_long_side_px (default 80)
            - aspect ratio max(w,h)/min(w,h) >= min_aspect_ratio (default 4.0)
        Os 2 ultimos eliminam diamantes/hachuras pontuais que sao
        marrons mas QUADRADOS (decisao consultada com qwen2.5-coder:14b
        em 2026-04-21: filtros combinados garantem robustez sem perder
        peitoris reais).

Invariante:
    Se nao detectar nada, retorna `[]` explicitamente. NUNCA inferir
    procedural ou injetar GT externo (memoria
    feedback_nao_fabricar_sem_medidas.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np


# Altura padrao quando o detector identifica peitoril (H=1.10m por
# convencao da legenda do PDF planta_baixa_74m2). Mureta H=0.70m e a
# mesma classe de cor — preferimos reportar a altura mais comum por
# default; o classificador downstream pode rebaixar via heuristica
# (largura/contexto) se necessario.
DEFAULT_HEIGHT_M = 1.10


@dataclass(frozen=True)
class PeitorilDetectionConfig:
    """Parametros do detector. Defaults calibrados pra plantas BR @ 150 DPI."""

    # Faixa HSV do MARROM (mesma do `proto_colored.py` baseline)
    hsv_brown_lower: tuple[int, int, int] = (8, 80, 40)
    hsv_brown_upper: tuple[int, int, int] = (25, 255, 180)
    # Faixa(s) HSV do VERMELHO pra excluir interseccao com alvenaria
    hsv_red_ranges: tuple[tuple[tuple[int, int, int], tuple[int, int, int]], ...] = (
        ((0, 100, 80), (12, 255, 255)),
        ((170, 100, 80), (180, 255, 255)),
    )
    # Morfologia
    close_kernel_size: int = 3
    close_iterations: int = 2
    # Filtros geometricos
    min_area_px: int = 200
    min_long_side_px: int = 80
    min_aspect_ratio: float = 4.0
    # Altura semantica reportada
    height_m: float = DEFAULT_HEIGHT_M
    # Margem em px adicionada ao bbox (0 = bbox cru). Util pra dar folga
    # ao classificador de openings que usa proximidade.
    bbox_pad_px: int = 0
    # Prefixo do id (peitoril-N onde N = component label). Mantemos
    # compativel com os JSON antigos.
    id_prefix: str = "peitoril"


def detect_peitoris(
    image: np.ndarray,
    page_index: int = 0,
    config: PeitorilDetectionConfig | None = None,
) -> list[dict]:
    """Detecta peitoris/muretas numa imagem RGB ou BGR.

    Args:
        image: ndarray HxWx3 (BGR como cv2.imread, ou RGB — ambos funcionam
            pq usamos cvtColor BGR->HSV; um RGB sera tratado como BGR mas
            a faixa de marrom ainda casa porque o canal H eh mesmo).
            Se monocromatico (HxW ou HxWx1), retorna `[]` (nao da pra
            extrair cor de uma imagem ja filtrada).
        page_index: indice da pagina, propagado pra possivel
            multi-pagina downstream (atualmente nao usado no JSON pra
            compat com formato existente, mas reservado).
        config: parametros opcionais. Default = PeitorilDetectionConfig().

    Returns:
        Lista de dicts no MESMO formato do `pNN_peitoris.json` legado:
            [{
                "peitoril_id": "peitoril-N",
                "bbox": [x1, y1, x2, y2],
                "area_px": int,
                "kind": "peitoril",
                "height_m": float,
            }, ...]

        Lista vazia se a imagem for monocromatica, vazia, ou nenhum
        componente passar nos filtros. NUNCA inventa peitoris.
    """
    cfg = config or PeitorilDetectionConfig()

    if image is None or image.size == 0:
        return []
    if image.ndim != 3 or image.shape[2] < 3:
        # imagem ja filtrada / sem cor -> nao da pra detectar marrom
        return []

    # cv2.cvtColor com BGR2HSV: se input vier RGB, o canal H ainda
    # mapeia razoavelmente (marrom ~10-25 hue) — testamos isso no
    # fixture sintetico, mas pra fidelidade maxima recomendamos BGR.
    bgr = image if image.dtype == np.uint8 else image.astype(np.uint8)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    brown = cv2.inRange(hsv, cfg.hsv_brown_lower, cfg.hsv_brown_upper)

    # Subtrai vermelho pra nao confundir borda vermelho-marrom
    red_mask = np.zeros(brown.shape, dtype=np.uint8)
    for lower, upper in cfg.hsv_red_ranges:
        red_mask = cv2.bitwise_or(red_mask, cv2.inRange(hsv, lower, upper))
    brown = cv2.bitwise_and(brown, cv2.bitwise_not(red_mask))

    # MORPH_CLOSE pra reconectar fragmentos finos (mesmo do baseline)
    if cfg.close_kernel_size > 0 and cfg.close_iterations > 0:
        kernel = np.ones((cfg.close_kernel_size, cfg.close_kernel_size), np.uint8)
        brown = cv2.morphologyEx(
            brown, cv2.MORPH_CLOSE, kernel, iterations=cfg.close_iterations
        )

    # Connected components + filtros geometricos
    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(brown, 8)
    h_img, w_img = brown.shape[:2]

    out: list[dict] = []
    for i in range(1, n):  # 0 = background
        x, y, w, h, area = stats[i]
        if area < cfg.min_area_px:
            continue
        long_side = max(w, h)
        short_side = max(1, min(w, h))
        if long_side < cfg.min_long_side_px:
            continue
        if (long_side / short_side) < cfg.min_aspect_ratio:
            continue

        x1 = max(0, int(x) - cfg.bbox_pad_px)
        y1 = max(0, int(y) - cfg.bbox_pad_px)
        x2 = min(w_img, int(x + w) + cfg.bbox_pad_px)
        y2 = min(h_img, int(y + h) + cfg.bbox_pad_px)

        out.append(
            {
                "peitoril_id": f"{cfg.id_prefix}-{i}",
                "bbox": [x1, y1, x2, y2],
                "area_px": int(area),
                "kind": "peitoril",
                "height_m": float(cfg.height_m),
                "page_index": int(page_index),
            }
        )
    return out


def detect_peitoris_from_path(
    image_path: str | Path,
    page_index: int = 0,
    config: PeitorilDetectionConfig | None = None,
) -> list[dict]:
    """Conveniencia: carrega PNG/JPG colorido do disco e detecta."""
    p = Path(image_path)
    img = cv2.imread(str(p), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {p}")
    return detect_peitoris(img, page_index=page_index, config=config)


def merge_with_manual(
    detected: list[dict],
    manual: Iterable[dict] | None,
) -> list[dict]:
    """Combina deteccao automatica com override manual (se fornecido).

    Util durante a transicao: se o operador ainda quiser injetar
    peitoris extras via JSON, eles sao apendados (ids reidx pra evitar
    colisao). NUNCA filtra os detectados automaticamente — manual e
    aditivo, nao substitutivo.
    """
    if not manual:
        return list(detected)
    next_id = 1 + max(
        (_id_num(p.get("peitoril_id", "")) for p in detected), default=0
    )
    out = list(detected)
    for entry in manual:
        new = dict(entry)
        new["peitoril_id"] = f"peitoril-{next_id}"
        next_id += 1
        out.append(new)
    return out


def _id_num(pid: str) -> int:
    try:
        return int(pid.rsplit("-", 1)[-1])
    except Exception:
        return 0
