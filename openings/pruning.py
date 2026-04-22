"""Pos-deteccao: filtros que removem openings orfas/ruido.

`detect_openings` opera sobre todas as walls ingeridas (inclui carimbo,
legenda, miniplanta). Quando `select_main_component` depois filtra walls
fora da planta principal, as openings registradas entre walls dropadas
sobrevivem no output como fantasmas: seus bridges tambem foram dropados,
entao elas nao fecham polygon nenhum, mas continuam listadas em
`observed_model["openings"]`.

Este modulo poda essas orfas apos o main_component_filter. So e invocado
no pipeline SVG (raster usa `detect_architectural_roi` com papel analogo
upstream).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable

from model.types import Wall
from openings.service import Opening


# Floor multiplier usado pelo filtro B (filter_min_width_openings). Width
# abaixo de `thickness * _DEFAULT_MIN_WIDTH_MUL` e considerado ruido (gap
# residual de linha dupla, nao porta real). Um multiplicador de 3.5 da
# ~22 px com thickness=6.25 tipico do SVG; portas arquitetonicas reais
# tem ~50+ px (7-12x thickness). Variavel de ambiente OPENINGS_MIN_WIDTH_MUL
# permite rollback sem rebuild.
_DEFAULT_MIN_WIDTH_MUL = 3.5


@dataclass(frozen=True)
class PruneReport:
    input_count: int
    dropped_orphan: int
    kept: int

    def to_dict(self) -> dict:
        return {
            "input_count": self.input_count,
            "dropped_orphan": self.dropped_orphan,
            "kept": self.kept,
        }


@dataclass(frozen=True)
class MinWidthReport:
    input_count: int
    dropped_below_min: int
    kept: int
    threshold_px: float

    def to_dict(self) -> dict:
        return {
            "input_count": self.input_count,
            "dropped_below_min": self.dropped_below_min,
            "kept": self.kept,
            "threshold_px": round(self.threshold_px, 3),
        }


@dataclass(frozen=True)
class DedupReport:
    input_count: int
    merged: int
    kept: int
    gap_threshold_px: float

    def to_dict(self) -> dict:
        return {
            "input_count": self.input_count,
            "merged": self.merged,
            "kept": self.kept,
            "gap_threshold_px": round(self.gap_threshold_px, 3),
        }


def prune_orphan_openings(
    openings: Iterable[Opening],
    kept_walls: Iterable[Wall],
) -> tuple[list[Opening], PruneReport]:
    """Remove openings cujos wall_a e wall_b nao estao em kept_walls.

    kept_walls e tipicamente a saida de `select_main_component`. Um opening
    registrado entre walls que ficaram fora do componente principal e um
    fantasma: seu bridge foi dropado junto, o polygon nao fecha, e o
    registro no output apenas infla contagens.

    Politica conservadora: mantem o opening se PELO MENOS UM lado (wall_a
    ou wall_b) sobreviveu. Isso preserva portas externas onde um lado e
    fachada que ficou separada em componente distinto mas continua sendo
    um vao legitimo. Em planta_74m2 o caso `one kept` foi medido como 0;
    a regra conservadora nao muda o resultado empirico mas evita falso
    negativo em plantas com fachada separada.
    """
    openings_list = list(openings)
    kept_ids = {w.wall_id for w in kept_walls}
    out: list[Opening] = []
    dropped = 0
    for o in openings_list:
        if o.wall_a in kept_ids or o.wall_b in kept_ids:
            out.append(o)
        else:
            dropped += 1
    return out, PruneReport(
        input_count=len(openings_list),
        dropped_orphan=dropped,
        kept=len(out),
    )


def _resolve_min_width_mul(override: float | None) -> float:
    if override is not None:
        return float(override)
    env = os.environ.get("OPENINGS_MIN_WIDTH_MUL")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    return _DEFAULT_MIN_WIDTH_MUL


def filter_min_width_openings(
    openings: Iterable[Opening],
    wall_thickness: float,
    min_width_mul: float | None = None,
) -> tuple[list[Opening], MinWidthReport]:
    """Remove openings com largura abaixo de `thickness * min_width_mul`.

    Usado apenas no pipeline SVG (onde `wall_thickness` tem semantica de
    escala do documento, em user-units). Raster path nao chama este
    filtro — as constantes raster (`_MIN_OPENING_PX = 8.0` px @ 150 DPI
    em `openings/service.py`) ja sao o floor efetivo.

    Porque: em SVG, `_MIN_OPENING_MUL=3.0` em `service.py` da ~19 px
    (thickness=6.25), que deixa passar gaps residuais de linha dupla.
    Portas arquitetonicas reais tem >50 px (8+ x thickness). Subir o
    floor para 3.5x joga fora ~3 tiny gaps sem tocar em portas reais.

    O default pode ser sobrescrito via env var `OPENINGS_MIN_WIDTH_MUL`
    ou argumento explicito; backdoor de rollback se algum SVG com escala
    atipica regredir.
    """
    mul = _resolve_min_width_mul(min_width_mul)
    threshold = wall_thickness * mul
    openings_list = list(openings)
    kept = [o for o in openings_list if o.width >= threshold]
    dropped = len(openings_list) - len(kept)
    return kept, MinWidthReport(
        input_count=len(openings_list),
        dropped_below_min=dropped,
        kept=len(kept),
        threshold_px=threshold,
    )


def _parallel_range(o: Opening) -> tuple[float, float]:
    """Intervalo no eixo principal ocupado pelo opening (centro - width/2,
    centro + width/2).
    """
    cx, cy = o.center
    half = o.width / 2.0
    if o.orientation == "horizontal":
        return (cx - half, cx + half)
    return (cy - half, cy + half)


def _perp_coord(o: Opening) -> float:
    cx, cy = o.center
    return cy if o.orientation == "horizontal" else cx


def _parallel_coord(o: Opening) -> float:
    cx, cy = o.center
    return cx if o.orientation == "horizontal" else cy


def _overlap_fraction(a: Opening, b: Opening) -> float:
    """Fracao de overlap no eixo principal relativo ao menor dos dois.

    Retorna valor em [0, 1]. Zero = sem sobreposicao. 1 = um esta contido
    no outro. Usado como gate secundario: sem overlap minimo, nao sao
    duplicatas mesmo se os centros estao proximos.
    """
    a_lo, a_hi = _parallel_range(a)
    b_lo, b_hi = _parallel_range(b)
    overlap = max(0.0, min(a_hi, b_hi) - max(a_lo, b_lo))
    smaller = min(a_hi - a_lo, b_hi - b_lo)
    if smaller <= 0:
        return 0.0
    return overlap / smaller


def dedup_collinear_openings(
    openings: Iterable[Opening],
    wall_thickness: float,
    gap_mul: float = 4.0,
    overlap_min: float = 0.30,
) -> tuple[list[Opening], DedupReport]:
    """Funde openings duplicadas da mesma parede dupla.

    Quatro gates combinados (todos precisam passar para fundir):

    1. Mesma orientacao (horizontal ou vertical).
    2. Eixo perpendicular proximo: delta <= wall_thickness (tolerancia
       curta porque parede dupla tem exatamente 1 thickness de offset).
    3. Distancia entre centros no eixo principal < wall_thickness *
       gap_mul (default 4.0; consultado contra ChatGPT 2026-04-21:
       4x e conservador, 6x precisaria evidencia adicional).
    4. Overlap do intervalo paralelo >= overlap_min do menor (default
       0.30): sem overlap minimo sao portas distintas mesmo se os
       centros estao proximos, nao duplicatas.

    Quando funde, mantem a de maior width (opening_id preservado). O
    criterio de "maior width" e apropriado para parede dupla porque o
    gap real da porta e a envelope da duplicata.

    Corredor com duas portas lado-a-lado: thickness * 4 ≈ 25 px (≈ 40 cm
    em escala tipica). Portas vizinhas tem centros > 1.5 m apart (>=
    240 units, > 38 * thickness), bem acima do gate 3.
    """
    openings_list = list(openings)
    n = len(openings_list)
    if n < 2:
        return openings_list, DedupReport(
            input_count=n,
            merged=0,
            kept=n,
            gap_threshold_px=wall_thickness * gap_mul,
        )

    gap_threshold = wall_thickness * gap_mul
    perp_tol = wall_thickness

    # Union-find simples para agrupar duplicatas transitivamente.
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(n):
        oi = openings_list[i]
        for j in range(i + 1, n):
            oj = openings_list[j]
            # Gate 1: orientacao
            if oi.orientation != oj.orientation:
                continue
            # Gate 2: mesmo eixo perpendicular
            if abs(_perp_coord(oi) - _perp_coord(oj)) > perp_tol:
                continue
            # Gate 3: centros proximos no eixo principal
            if abs(_parallel_coord(oi) - _parallel_coord(oj)) >= gap_threshold:
                continue
            # Gate 4: overlap minimo
            if _overlap_fraction(oi, oj) < overlap_min:
                continue
            union(i, j)

    # Agrupar por cluster e escolher representante (maior width).
    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)

    kept: list[Opening] = []
    merged = 0
    for idxs in clusters.values():
        if len(idxs) == 1:
            kept.append(openings_list[idxs[0]])
        else:
            best = max(idxs, key=lambda i: openings_list[i].width)
            kept.append(openings_list[best])
            merged += len(idxs) - 1

    # Preserva a ordem original dos representantes.
    kept.sort(key=lambda o: openings_list.index(o))
    return kept, DedupReport(
        input_count=n,
        merged=merged,
        kept=len(kept),
        gap_threshold_px=gap_threshold,
    )
