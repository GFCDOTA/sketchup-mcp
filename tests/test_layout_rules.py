"""Feedback loop / anti-patterns — prova que as regras de layout entraram.

Cobre tools/layout_rules.py (catalogo + flag_anti_patterns) e a integracao no
tools/layout_candidates.py (JSON ganha anti_patterns / anti_patterns_flagged).
Sem 3DW, sem asset, sem SKP. Felipe 2026-06-04.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.layout_rules import (MIN_SOFA_TV, RULE_BY_ID, RULES,
                                 flag_anti_patterns)

REPO = Path(__file__).resolve().parents[1]
_PLANTA = (REPO / "fixtures" / "planta_74"
           / "consensus_with_human_walls_and_soft_barriers.json")


def _bad_all_hard():
    return {"hard_gates": {"nao_invade_parede": False, "nao_bloqueia_circulacao": False,
                           "nao_bloqueia_porta_janela": False, "dentro_do_comodo": False,
                           "passagem_min_080": False},
            "metrics": {"sofa_tv_dist_m": 1.2, "sofa_door_min_m": 0.3, "tv_depth_m": 0.67,
                        "tv_wall_type": "internal", "fill_ratio": 0.16}}


def _clean():
    return {"hard_gates": {k: True for k in _bad_all_hard()["hard_gates"]},
            "metrics": {"sofa_tv_dist_m": 2.8, "sofa_door_min_m": 1.5, "tv_depth_m": 3.0,
                        "tv_wall_type": "border", "fill_ratio": 0.30}}


# ---- catalogo ----

def test_catalog_covers_felipe_rules():
    """Todas as 10 regras pedidas pelo Felipe (+ derivadas) estao no catalogo."""
    ids = {r["id"] for r in RULES}
    # processo + hard + soft, RL-01..RL-14
    assert {"RL-01", "RL-02", "RL-03", "RL-04", "RL-05", "RL-06", "RL-07",
            "RL-08", "RL-09", "RL-10", "RL-11", "RL-12", "RL-13", "RL-14"} <= ids
    for r in RULES:
        assert r["kind"] in {"process", "hard", "soft"}
        assert r["statement"] and r["anti_pattern"] and r["enforced_by"]


# ---- flag_anti_patterns: lado HARD ----

def test_hard_gates_map_to_at_least_3_anti_patterns():
    flags = flag_anti_patterns(_bad_all_hard())
    hard = {f["rule_id"] for f in flags if f["severity"] == "hard"}
    # criterio #3: >= 3 anti-patterns viram hard gate
    assert len(hard) >= 3
    # mapeamento explicito dos hard gates -> regras
    assert {"RL-07", "RL-08", "RL-09", "RL-10", "RL-14"} <= hard


def test_short_sofa_tv_distance_is_hard():
    """Sofa em cima da TV (dist < MIN_SOFA_TV) e severidade HARD, nao soft."""
    cand = _clean()
    cand["metrics"]["sofa_tv_dist_m"] = MIN_SOFA_TV - 0.5
    rl06 = [f for f in flag_anti_patterns(cand) if f["rule_id"] == "RL-06"]
    assert rl06 and rl06[0]["severity"] == "hard"


# ---- flag_anti_patterns: lado SOFT ----

def test_soft_thresholds_flag_expected_rules():
    cand = _clean()
    cand["metrics"].update({"sofa_tv_dist_m": 3.5,        # fora do ideal mas aceitavel
                            "tv_wall_type": "internal",   # nao e parede de fundo
                            "fill_ratio": 0.16})          # sub-mobiliado
    flags = {f["rule_id"]: f for f in flag_anti_patterns(cand)}
    assert flags["RL-06"]["severity"] == "soft"
    assert "RL-05" in flags and "RL-13" in flags


def test_clean_candidate_has_zero_flags():
    assert flag_anti_patterns(_clean()) == []


def test_every_flag_resolves_to_a_known_rule():
    for f in flag_anti_patterns(_bad_all_hard()):
        assert f["rule_id"] in RULE_BY_ID
        assert f["name"] == RULE_BY_ID[f["rule_id"]]["name"]


# ---- integracao com layout_candidates (planta real) ----

@pytest.mark.skipif(not _PLANTA.exists(), reason="planta_74 fixture absent")
def test_run_emits_anti_patterns_in_json():
    from tools.layout_candidates import run
    con = json.loads(_PLANTA.read_text("utf-8"))
    _, out = run(con, "r002")
    # criterio #4: JSON inclui anti_patterns por candidato + agregado
    assert "anti_patterns_flagged" in out
    assert all("anti_patterns" in c for c in out["candidates"])
    assert all("anti_patterns" in r for r in out["ranking"])
    # catalogo embarcado
    assert {r["id"] for r in out["rules"]} >= {"RL-05", "RL-06", "RL-13"}


@pytest.mark.skipif(not _PLANTA.exists(), reason="planta_74 fixture absent")
def test_ambiguous_tv_wall_is_explained_not_crammed():
    """RL-11: parede-TV AMBIGUOUS na sala r002 gera ressalva textual."""
    from tools.layout_candidates import run
    con = json.loads(_PLANTA.read_text("utf-8"))
    _, out = run(con, "r002")
    if out["tv_wall"]["confidence"] == "ambiguous":
        assert "tv_wall_uncertainty" in out
        assert "AMBIGUOUS" in out["tv_wall_uncertainty"]
        assert out["result"] in {"OK", "NO_VALID_LAYOUT"}  # gerou candidatos, nao travou
