"""Quality score — substitui `_geometry_score = len(walls)/len(candidates)`.

PATCH #03 — para aplicar em sketchup-mcp/model/pipeline.py e model/builder.py:

INVARIANTE RESOLVIDA: #6 (scores observacionais honestos)

PROBLEMA ATUAL (pipeline.py:208-211):
    def _geometry_score(candidates, walls) -> float:
        if not candidates: return 0.0
        return min(1.0, len(walls) / len(candidates))

    # Semântica invertida:
    # 1000 candidatos (ruído) + 100 walls legítimas → score 0.1 (parece ruim)
    # 10 candidatos + 10 walls → score 1.0 (parece perfeito)
    # MAIS CANDIDATOS = SCORE PIOR, mesmo que qualidade real seja igual ou melhor.

SOLUÇÃO:
- Renomear _geometry_score → _retention_score (honesto, não esconde semântica)
- Adicionar _quality_score() real usando perimeter + connectivity + rooms + orthogonality

REVIEW PENDENTE (Felipe, PR #1 comment):
- `wall.p0/p1` foi renomeado para `wall.start/end` — usar nomes reais do
  `model.types.Wall` dataclass.
- `connectivity_report.max_component_size_within_page` NÃO existe; o campo
  real `max_components_within_page` é um COUNT (número de componentes),
  não um size. A ratio que queremos (maior componente / total de nodes)
  já vive em `connectivity_report.largest_component_ratio`, então
  usamos direto.
- F1-against-GT foi removido: ground truth é contrato do consumer, não
  do pipeline (invariante §6 do CLAUDE.md). O score do extrator tem que
  ser auto-contido em artefatos observados.
"""
from __future__ import annotations

import math
from typing import Optional


# ==============================================================================
# PARTE 1 — renomear _geometry_score → _retention_score (15 min)
# ==============================================================================

# Substituir em pipeline.py:208-211:
def _retention_score(candidates: list, walls: list) -> float:
    """Taxa de retenção após filtros de classify.

    ATENÇÃO: esta métrica é RETENÇÃO, não qualidade. Um valor alto significa
    que poucos candidatos foram filtrados (pipeline permissivo). Um valor baixo
    significa que muitos foram filtrados (pipeline conservador). Nenhum dos
    dois é necessariamente melhor — depende do ruído do input.

    Para avaliar QUALIDADE da extração, use _quality_score() abaixo.
    """
    if not candidates:
        return 0.0
    return min(1.0, len(walls) / len(candidates))


# Atualizar em builder.py:47 (ou onde geometry_score é exposto no output):
#
# ANTES:
#   model.scores.geometry = _geometry_score(candidates, walls)
#
# DEPOIS:
#   orthogonality = _compute_orthogonality(walls)
#   quality = _quality_score(walls, rooms, connectivity_report, orthogonality)
#   model.scores.retention = _retention_score(candidates, walls)
#   model.scores.quality = quality
#   model.scores.orthogonality = round(orthogonality, 4)
#   # manter geometry_score como alias deprecated por 1 release:
#   model.scores.geometry = quality  # NÃO retention — evita quebrar consumers


# ==============================================================================
# PARTE 2 — _quality_score() real (2h)
# ==============================================================================

# Adicionar em pipeline.py após _retention_score:

def _quality_score(
    walls: list,
    rooms: list,
    connectivity_report,
    orthogonality: Optional[float] = None,
) -> float:
    """Score composto de QUALIDADE (não retenção).

    Componentes (todos 0.0-1.0):
    - perimeter_closure: largest component ratio of the wall graph
    - room_density: rooms detectados / edges (normalized, min floor)
    - orthogonality: fração de walls axis-aligned (Manhattan-world)
    - orphan_penalty: 1 - (orphan_components / 5.0) clamped

    Retorna 0.0 se walls vazios; 1.0 se planta é perfeita.

    Todos os componentes usam apenas artefatos OBSERVADOS pelo pipeline:
    nenhum depende de ground truth externo. GT é contrato do consumer
    (invariante §6 do CLAUDE.md).
    """
    if not walls:
        return 0.0

    components: dict[str, float] = {}

    # 1. Perimeter closure: fração dos nodes que caem no maior componente
    # do grafo de walls. `connectivity_report.largest_component_ratio` já
    # expõe exatamente isso (== max(component_sizes) / node_count).
    components["perimeter_closure"] = float(connectivity_report.largest_component_ratio)

    # 2. Room density (rooms / edge_count, com min floor 0.5 pra não zerar)
    if rooms:
        density_raw = len(rooms) / max(1, connectivity_report.edge_count)
        components["room_density"] = min(1.0, 0.5 + density_raw)
    else:
        components["room_density"] = 0.0

    # 3. Orthogonality (se disponível)
    components["orthogonality"] = orthogonality if orthogonality is not None else 0.7

    # 4. Orphan penalty (menos orfãs = melhor)
    orphan_count = connectivity_report.orphan_component_count
    components["orphan_penalty"] = max(0.0, 1.0 - (orphan_count / 5.0))

    weights = {
        "perimeter_closure": 0.40,
        "room_density": 0.20,
        "orthogonality": 0.20,
        "orphan_penalty": 0.20,
    }

    score = sum(components[k] * weights[k] for k in weights)
    return round(min(1.0, max(0.0, score)), 4)


def _compute_orthogonality(walls: list) -> float:
    """Mede fração de walls axis-aligned (Manhattan-world).

    Usa `wall.start` / `wall.end` — nomes canônicos do `model.types.Wall`.
    """
    if not walls:
        return 0.0

    n_ortho = 0
    for wall in walls:
        dx = wall.end[0] - wall.start[0]
        dy = wall.end[1] - wall.start[1]
        if dx == 0 and dy == 0:
            continue

        angle_deg = abs(math.degrees(math.atan2(dy, dx))) % 180
        # Tolerância: 5 graus do ângulo reto
        if angle_deg < 5 or abs(angle_deg - 90) < 5 or abs(angle_deg - 180) < 5:
            n_ortho += 1

    return n_ortho / max(1, len(walls))


# ==============================================================================
# INTEGRAÇÃO EM model/pipeline.py
# ==============================================================================

# Na função _compute_scores (ou onde scores são calculados), substituir:
#
# ANTES:
#   scores = {
#       "geometry": _geometry_score(candidates, walls),
#       "topology": _topology_score(split_walls, connectivity_report),
#       "room": _room_score(rooms, connectivity_report),
#   }
#
# DEPOIS:
#   orthogonality = _compute_orthogonality(walls)
#   quality = _quality_score(walls, rooms, connectivity_report, orthogonality)
#   scores = {
#       "retention": _retention_score(candidates, walls),
#       "topology": _topology_score(split_walls, connectivity_report),
#       "room": _room_score(rooms, connectivity_report),
#       "quality": quality,
#       "orthogonality": round(orthogonality, 4),
#       # Alias deprecated (remover em 1 release):
#       "geometry": quality,
#   }
#
# E documentar no README + schema output.


# ==============================================================================
# GROUND-TRUTH / F1: FORA DO ESCOPO DESTE PATCH
# ==============================================================================
#
# Versões anteriores deste patch incluíam `_compute_f1_against_gt` e
# `_hausdorff_wall`. Foram REMOVIDAS na revisão do PR #1:
#
# - Ground truth é contrato do consumer, não do extrator (CLAUDE.md §6).
# - F1 mede concordância com uma GT de referência, que não é um artefato
#   OBSERVADO pelo pipeline; introduzi-la aqui confunde avaliação
#   (consumer) com qualidade (pipeline).
# - Se alguém precisa de F1, deve implementar em `tests/` ou num harness
#   externo consumindo `observed_model.json`, não como score do extrator.


# ==============================================================================
# TESTES A ADICIONAR em tests/test_pipeline.py
# ==============================================================================

def test_quality_score_zero_when_no_walls():
    """Sem walls, quality deve ser 0."""
    # score = _quality_score([], [], connectivity_empty, None)
    # assert score == 0.0
    pass


def test_retention_score_does_not_depend_on_quality():
    """Demonstra que retention ≠ quality.

    100 walls from 1000 candidates = retention 0.1
    100 walls from 150 candidates = retention 0.67
    Mas quality pode ser IDÊNTICA se topologia é igual.
    """
    pass


def test_quality_score_penalizes_broken_perimeter():
    """Planta com perímetro aberto deve ter quality < 0.5."""
    pass


def test_quality_score_rewards_closed_perimeter_and_rooms():
    """Planta bem formada deve ter quality > 0.75."""
    pass
