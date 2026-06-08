"""Testes do choose_gate_tier — roteamento de tier por PROPOSITO da consulta.

Puro, sem I/O. Garante o contrato da slice:
- design-intent / pre-movel -> fast;
- veredito visual FINAL -> deep (PINADO; so cede com override explicito);
- ausencia/desconhecido de proposito -> deep (compat/seguranca);
- --tier explicito vence o proposito (exceto pin sem override).
"""
from tools.consult_tier import (
    DEEP_PURPOSES, DEFAULT_TIER, FAST_PURPOSES, PINNED_DEEP_PURPOSES,
    choose_gate_tier,
)


# ---- caminho fast (pre-movel / DesignIntentSpec) ---------------------

def test_design_intent_is_fast():
    assert choose_gate_tier("design_intent") == "fast"


def test_all_fast_purposes_route_fast():
    for p in FAST_PURPOSES:
        assert choose_gate_tier(p) == "fast", p


# ---- caminho deep (o juiz) -------------------------------------------

def test_final_visual_verdict_is_deep():
    assert choose_gate_tier("final_visual_verdict") == "deep"


def test_all_deep_purposes_route_deep():
    for p in DEEP_PURPOSES:
        assert choose_gate_tier(p) == "deep", p


# ---- default seguro --------------------------------------------------

def test_absent_purpose_defaults_deep():
    assert choose_gate_tier("") == "deep"
    assert choose_gate_tier() == "deep"
    assert DEFAULT_TIER == "deep"


def test_unknown_purpose_defaults_deep():
    assert choose_gate_tier("whatever_unknown_purpose") == "deep"


def test_canonical_decision_trigger_falls_through_to_deep():
    # os 9 triggers canonicos (decisao real) nao sao fast purposes -> deep
    assert choose_gate_tier("big_pr_changes_gate_or_spec") == "deep"
    assert choose_gate_tier("a_b_c_decision_with_tradeoff") == "deep"


# ---- override explicito de tier --------------------------------------

def test_explicit_tier_overrides_purpose():
    # pedir deep num purpose fast -> deep
    assert choose_gate_tier("design_intent", explicit_tier="deep") == "deep"
    # pedir fast num purpose deep NAO-pinado -> fast
    assert choose_gate_tier("merge_decision", explicit_tier="fast") == "fast"


def test_invalid_explicit_tier_ignored():
    assert choose_gate_tier("design_intent", explicit_tier="bogus") == "fast"
    assert choose_gate_tier("merge_decision", explicit_tier="") == "deep"


# ---- HARD RULE: veredito visual final pinado em deep -----------------

def test_pinned_verdict_ignores_fast_without_override():
    # so explicit_tier nao derruba o pin do veredito final
    assert choose_gate_tier("final_visual_verdict", explicit_tier="fast") == "deep"


def test_pinned_verdict_honors_explicit_user_override():
    # ...salvo se o usuario pedir explicitamente modo rapido
    assert choose_gate_tier(
        "final_visual_verdict", explicit_tier="fast", user_override=True) == "fast"


def test_pinned_verdict_override_without_valid_tier_stays_deep():
    assert choose_gate_tier("final_visual_verdict", user_override=True) == "deep"
    assert choose_gate_tier(
        "final_visual_verdict", explicit_tier="bogus", user_override=True) == "deep"


# ---- robustez --------------------------------------------------------

def test_case_and_space_insensitive():
    assert choose_gate_tier("  Design_Intent ") == "fast"
    assert choose_gate_tier("FINAL_VISUAL_VERDICT") == "deep"
    assert choose_gate_tier("design_intent", explicit_tier="DEEP") == "deep"


def test_pinned_set_is_subset_of_deep():
    assert PINNED_DEEP_PURPOSES <= DEEP_PURPOSES


def test_fast_and_deep_purposes_disjoint():
    assert not (FAST_PURPOSES & DEEP_PURPOSES)
