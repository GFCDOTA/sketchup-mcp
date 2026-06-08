"""Testes do tier do oraculo (resolve_tier + parse_ask_tier). Puros, sem chamar claude.
Garante: fast=Sonnet+low; deep=comportamento ATUAL (zero regressao); fallback p/ deep;
parse robusto do body /ask."""
import json

from tools.claude_bridge.server import (
    DEFAULT_TIER, EFFORT, MODEL, TIERS, parse_ask_tier, resolve_tier,
)


def test_fast_is_sonnet_low():
    assert resolve_tier("fast") == ("sonnet", "low")


def test_deep_is_current_behavior():
    # deep tem que ser EXATAMENTE o que o gate ja usava (Opus 4.8 + xhigh)
    assert resolve_tier("deep") == (MODEL, EFFORT)


def test_default_tier_is_deep():
    assert DEFAULT_TIER == "deep"
    assert resolve_tier(DEFAULT_TIER) == (MODEL, EFFORT)


def test_unknown_and_empty_fall_back_to_default():
    base = resolve_tier(DEFAULT_TIER)
    assert resolve_tier("bogus") == base
    assert resolve_tier("") == base
    assert resolve_tier(None) == base


def test_case_and_space_insensitive():
    assert resolve_tier("FAST") == resolve_tier("fast")
    assert resolve_tier("  Deep ") == resolve_tier("deep")


def test_parse_ask_tier():
    assert parse_ask_tier(json.dumps({"tier": "fast"}).encode()) == "fast"
    assert parse_ask_tier(json.dumps({"tier": "DEEP"}).encode()) == "deep"
    assert parse_ask_tier(json.dumps({"prompt": "x"}).encode()) == ""   # sem tier
    assert parse_ask_tier(b"") == ""
    assert parse_ask_tier(b"not json") == ""
    assert parse_ask_tier(json.dumps(["a"]).encode()) == ""             # nao-dict


def test_tiers_shape():
    assert {"fast", "deep"} <= set(TIERS)
    for t in TIERS.values():
        assert "model" in t and "effort" in t
