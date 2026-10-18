"""Integridade geométrica do shell — review clínico 2026-07-11.

Três bugs irmãos do vf_004 (suposição silenciosa que corrompe fidelidade):

1. `_remove_small_teeth` só checava PROFUNDIDADE — comia geometria REAL do
   consensus de qualquer largura (medido na planta_74: remanescente de
   1.26pt junto ao carve da h_o005 e overhang de 2.08pt da m006, largura
   5.4 = espessura). Agora o dente precisa ser pequeno nas DUAS dimensões.
2. A extensão de junção era half-t incondicional — endpoint desenhado NA
   face externa do vizinho perpendicular ganhava stub fantasma pra fora
   (5 na planta_74), mascarado pelo bug 1 via coincidência de constante
   (2.7 < tol 3.0). Agora `_classify_endpoint_junctions` capa a extensão
   na face externa do vizinho.
3. O roteamento de opening carvava FULL-HEIGHT qualquer kind não-window
   (a whitelist FULL_HEIGHT_CARVE_KINDS existia mas não era consultada) —
   violação silenciosa da Hard Rule #2 pra kind futuro/typo.
"""
from __future__ import annotations

import json
from pathlib import Path

from tools.build_plan_shell_skp import (
    FULL_HEIGHT_CARVE_KINDS,
    _classify_endpoint_junctions,
    _remove_small_teeth,
    build_shell_polygon,
)

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "fixtures" / "planta_74" / "consensus_with_human_walls_and_soft_barriers.json"


def _fixture():
    return json.loads(FIXTURE.read_text("utf-8"))


# ---- bug 1: filtro de dentes -----------------------------------------

def test_teeth_filter_preserves_shallow_but_wide_real_feature():
    """Protrusão rasa (2.9pt) mas LARGA (80pt) é geometria real — fica."""
    ring = [(0, 0), (100, 0), (100, 50), (60, 50), (60, 52.9), (-20, 52.9),
            (-20, 50), (0, 50)]
    # feature: degrau de 2.9 de profundidade x 80 de largura no topo
    out = _remove_small_teeth([(0, 0), (100, 0), (100, 50), (90, 50),
                               (90, 52.9), (10, 52.9), (10, 50), (0, 50)])
    assert (90, 52.9) in out and (10, 52.9) in out, (
        "feature real rasa-mas-larga foi comida pelo filtro de dentes")


def test_teeth_filter_still_removes_small_corner_notch():
    """Dente pequeno nas duas dimensões (2.7x2.7) = artefato — sai."""
    out = _remove_small_teeth([(0, 0), (100, 0), (100, 50), (52.7, 50),
                               (52.7, 52.7), (50, 52.7), (50, 50), (0, 50)])
    assert (52.7, 52.7) not in out and (50, 52.7) not in out


# ---- bug 2: clamp da extensão de junção ------------------------------

def test_junction_extension_clamped_at_neighbor_outer_face():
    """Endpoint já NA face externa do vizinho: extensão = 0, não half-t."""
    walls = [
        # vizinho vertical: faces em x=97.3 .. 102.7
        {"id": "v1", "orientation": "v", "thickness": 5.4,
         "start": [100.0, 0.0], "end": [100.0, 50.0]},
        # parede h terminando exatamente na face EXTERNA (x=102.7)
        {"id": "h1", "orientation": "h", "thickness": 5.4,
         "start": [0.0, 25.0], "end": [102.7, 25.0]},
        # parede h terminando na face INTERNA (x=97.3) — corner normal,
        # deve estender half-t pra fechar o L
        {"id": "h2", "orientation": "h", "thickness": 5.4,
         "start": [0.0, 40.0], "end": [97.3, 40.0]},
    ]
    j = _classify_endpoint_junctions(walls)
    assert j["h1"][1] <= 0.01, (
        f"endpoint na face externa ganhou stub de {j['h1'][1]}pt pra fora")
    assert abs(j["h2"][1] - 2.7) < 0.01, (
        f"corner normal deixou de estender half-t (got {j['h2'][1]})")


def test_fixture_shell_preserves_real_consensus_mass():
    """planta_74: as 2 features reais ficam; os 5 stubs não nascem.

    Baseline pré-fix: 11945.24 pts². Pós-fix: +~18 pts² (features
    preservadas), mesmas 3 peças, zero erros de opening.
    """
    polys, stats = build_shell_polygon(_fixture())
    assert stats["shell_pieces_after_sliver_filter"] == 3
    assert stats["openings_skipped_by_error"] == []
    area = stats["total_shell_area_pts2"]
    assert 11960.0 < area < 11967.0, (
        f"área do shell {area} fora da banda esperada pós-fix "
        f"(features reais preservadas, stubs clampados)")


# ---- bug 3: whitelist de carve full-height (Hard Rule #2) ------------

def test_unknown_kind_never_carves_full_height():
    con = _fixture()
    con["openings"].append({
        "id": "x_test", "kind": "sliding_window", "kind_v5": "sliding_window",
        "wall_id": con["walls"][0]["id"],
        "center": list(con["walls"][0]["start"]),
        "opening_width_pts": 20.0,
        "geometry_origin": "human_annotation",
    })
    polys, stats = build_shell_polygon(con)
    carved_before = 8  # planta_74: 7 doors + 1 glazed_balcony
    assert stats["openings_carved"] == carved_before, (
        "kind desconhecido virou carve full-height — Hard Rule #2 violada")
    assert any("x_test" in e and "Hard Rule #2" in e
               for e in stats["openings_skipped_by_error"])


def test_whitelist_matches_known_kinds():
    """Todos os kinds da planta_74 continuam roteados sem erro."""
    polys, stats = build_shell_polygon(_fixture())
    assert stats["openings_carved"] == 8
    assert stats["window_apertures_3d"] == 4
    assert stats["openings_skipped_by_error"] == []
    assert "interior_door" in FULL_HEIGHT_CARVE_KINDS


# ---- contratos de texto do .rb (não executável em pytest) -----------

def test_rb_origin_default_parity_with_python():
    src = (REPO / "tools" / "build_plan_shell_skp.rb").read_text("utf-8")
    assert "origin.empty? || CARVING_ORIGINS.include?(origin)" in src, (
        ".rb diverge do Python no default de geometry_origin ausente")


def test_rb_soft_barrier_single_render_classifier():
    src = (REPO / "tools" / "build_plan_shell_skp.rb").read_text("utf-8")
    assert "render_as: render_as" in src, (
        "call site não passa render_as resolvido pro build_soft_barrier")
    assert "resolved = render_as || barrier_render_as(barrier)" in src, (
        "build_soft_barrier re-deriva render_as por conta própria")
