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

from dataclasses import dataclass
from typing import Iterable

from model.types import Wall
from openings.service import Opening


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
