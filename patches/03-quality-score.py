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
- Adicionar _quality_score() real usando F1 + perimeter + connectivity + orthogonality
- Componente opcional F1 quando ground truth disponível
"""
from __future__ import annotations

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
#   model.scores.retention = _retention_score(candidates, walls)
#   model.scores.quality = _quality_score(walls, rooms, connectivity_report, orthogonality)
#   # manter geometry_score como alias deprecated por 1 release:
#   model.scores.geometry = model.scores.quality  # NÃO retention — evita quebrar consumers


# ==============================================================================
# PARTE 2 — _quality_score() real (2h)
# ==============================================================================

# Adicionar em pipeline.py após _retention_score:

def _quality_score(
    walls: list,
    rooms: list,
    connectivity_report,
    orthogonality: Optional[float] = None,
    ground_truth: Optional[dict] = None,
) -> float:
    """Score composto de QUALIDADE (não retenção).

    Componentes (todos 0.0-1.0):
    - perimeter_closure: largest_component / total_nodes do grafo de walls
    - room_density: rooms detectados / edges esperados (normalized)
    - orthogonality: 1 - (non_ortho_edges / total_edges)
    - orphan_penalty: 1 - (orphan_components / 5.0) clamped
    - f1 (opcional): F1 contra ground truth se disponível

    Se ground_truth disponível: F1 peso 0.4, resto completa 0.6
    Sem ground_truth (default): média ponderada dos componentes estruturais

    Retorna 0.0 se walls vazios; 1.0 se planta é perfeita.
    """
    if not walls:
        return 0.0

    components = {}

    # 1. Perimeter closure
    max_component_size = connectivity_report.max_component_size_within_page
    total_nodes = max(1, connectivity_report.node_count)
    components["perimeter_closure"] = min(1.0, max_component_size / total_nodes)

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

    # 5. F1 opcional
    f1 = None
    if ground_truth is not None:
        f1 = _compute_f1_against_gt(walls, ground_truth)

    # Pesos diferem se GT disponível
    if f1 is not None:
        components["f1"] = f1
        weights = {
            "f1": 0.4,
            "perimeter_closure": 0.25,
            "room_density": 0.15,
            "orthogonality": 0.10,
            "orphan_penalty": 0.10,
        }
    else:
        weights = {
            "perimeter_closure": 0.40,
            "room_density": 0.20,
            "orthogonality": 0.20,
            "orphan_penalty": 0.20,
        }

    score = sum(components[k] * weights[k] for k in weights)
    return round(min(1.0, max(0.0, score)), 4)


def _compute_orthogonality(walls: list) -> float:
    """Mede fração de edges ortogonais (Manhattan-world)."""
    if not walls:
        return 0.0

    import math

    n_ortho = 0
    for wall in walls:
        # wall tem p0, p1 (coord normalizadas ou em pixels)
        dx = wall.p1[0] - wall.p0[0]
        dy = wall.p1[1] - wall.p0[1]
        if dx == 0 and dy == 0:
            continue

        angle_deg = abs(math.degrees(math.atan2(dy, dx))) % 180
        # Tolerância: 5 graus do ângulo reto
        if angle_deg < 5 or abs(angle_deg - 90) < 5 or abs(angle_deg - 180) < 5:
            n_ortho += 1

    return n_ortho / max(1, len(walls))


def _compute_f1_against_gt(walls: list, ground_truth: dict) -> Optional[float]:
    """F1 entre walls detectados e ground truth (se disponível).

    ground_truth dict format:
    {
        "walls": [(p0, p1, thickness), ...]  # lista de walls verdadeiros
    }

    Usa matching Hungarian ou greedy baseado em distância Hausdorff.
    """
    if not walls or "walls" not in ground_truth:
        return None

    gt_walls = ground_truth["walls"]
    if not gt_walls:
        return None

    # Simplificação: matching greedy por proximidade
    # Implementação production deveria usar scipy.optimize.linear_sum_assignment
    matched_walls = set()
    matched_gt = set()

    for i, wall in enumerate(walls):
        best_match = None
        best_dist = float('inf')
        for j, gt_wall in enumerate(gt_walls):
            if j in matched_gt:
                continue
            dist = _hausdorff_wall(wall, gt_wall)
            if dist < best_dist and dist < 20.0:  # threshold em pixels
                best_dist = dist
                best_match = j

        if best_match is not None:
            matched_walls.add(i)
            matched_gt.add(best_match)

    tp = len(matched_walls)
    fp = len(walls) - tp
    fn = len(gt_walls) - len(matched_gt)

    if tp == 0:
        return 0.0

    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    f1 = 2 * (precision * recall) / (precision + recall + 1e-9)
    return f1


def _hausdorff_wall(wall, gt_wall) -> float:
    """Distância Hausdorff simplificada entre dois segmentos de parede."""
    import math
    # Distância entre endpoints
    p0_a, p1_a = wall.p0, wall.p1
    p0_b, p1_b = gt_wall[0], gt_wall[1]

    def d(p, q):
        return math.hypot(p[0] - q[0], p[1] - q[1])

    # Melhor match de endpoints
    h_ab = max(min(d(p0_a, p0_b), d(p0_a, p1_b)), min(d(p1_a, p0_b), d(p1_a, p1_b)))
    h_ba = max(min(d(p0_b, p0_a), d(p0_b, p1_a)), min(d(p1_b, p0_a), d(p1_b, p1_a)))
    return max(h_ab, h_ba)


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
#   scores = {
#       "retention": _retention_score(candidates, walls),
#       "topology": _topology_score(split_walls, connectivity_report),
#       "room": _room_score(rooms, connectivity_report),
#       "quality": _quality_score(walls, rooms, connectivity_report, orthogonality),
#       "orthogonality": round(orthogonality, 4),
#       # Alias deprecated (remover em 1 release):
#       "geometry": round(_quality_score(walls, rooms, connectivity_report, orthogonality), 4),
#   }
#
# E documentar no README + schema output.


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
