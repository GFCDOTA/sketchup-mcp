"""Testes unitários do núcleo do especialista Pinterest (reference_grammar).

Lógica pura, determinística — sem rede, sem SketchUp. Cobre o contrato, a
normalização de tokens (sinônimos/desconhecidos) e o validador (autoridade do
PDF: a referência NÃO pode mexer na posição).
"""

from __future__ import annotations

from tools.reference_grammar import (
    grammar_contract,
    normalize_grammar,
    validate_grammar_spec,
)


# --- contrato ---------------------------------------------------------------

def test_contract_lists_canonical_tokens_and_roles_for_kitchen():
    c = grammar_contract("kitchen")
    assert c["mode"] if "mode" in c else True  # contrato puro não tem mode
    assert c["room_type"] == "kitchen"
    assert any(t["token"] == "fridge_tower" for t in c["known_joinery_tokens"])
    assert "countertop" in c["palette_roles"]
    # fixed_anchors são responsabilidade do PDF, nunca da imagem
    assert "sink" in c["fixed_anchor_keys"]


def test_contract_room_type_is_case_insensitive():
    assert grammar_contract("KITCHEN")["room_type"] == "kitchen"


# --- normalização -----------------------------------------------------------

def test_normalize_collapses_synonyms_to_canonical():
    draft = {"joinery_tokens": ["integrated_fridge_tower", "open_niche"]}
    out = normalize_grammar(draft, "kitchen")
    syn = out["vocab_report"]["synonyms_applied"]
    assert syn["integrated_fridge_tower"] == "fridge_tower"
    assert syn["open_niche"] == "upper_niche"


def test_normalize_flags_unknown_token_but_keeps_it():
    draft = {"joinery_tokens": ["brand_new_token"]}
    out = normalize_grammar(draft, "kitchen")
    assert "brand_new_token" in out["vocab_report"]["unknown"]
    # vocab cresce: o token é mantido na spec, só sinalizado
    assert "brand_new_token" in out["spec"]["joinery_tokens"]


def test_normalize_injects_pdf_fixed_anchors_by_construction():
    # mesmo que o draft tente passar posição, a normalização ignora e injeta PDF
    draft = {"fixed_anchors": {"sink": "parede norte (da foto)"}}
    out = normalize_grammar(draft, "kitchen", plant="planta_74", room_id="r004")
    fa = out["spec"]["fixed_anchors"]
    assert str(fa["sink"]).startswith("pdf_")
    assert out["spec"]["plant"] == "planta_74"
    assert out["spec"]["room_id"] == "r004"


def test_normalize_flags_unknown_palette_role():
    draft = {"palette": {"countertop": "stone", "spaceship_bay": "x"}}
    out = normalize_grammar(draft, "kitchen")
    assert "spaceship_bay" in out["vocab_report"]["palette_roles_unknown"]
    assert "countertop" not in out["vocab_report"]["palette_roles_unknown"]


# --- validação (autoridade do PDF) ------------------------------------------

def _good_spec():
    return normalize_grammar(
        {"joinery_tokens": ["fridge_tower"], "palette": {"countertop": "stone"}},
        "kitchen",
        plant="planta_74",
        room_id="r004",
    )["spec"]


def test_validate_passes_canonical_spec():
    v = validate_grammar_spec(_good_spec())
    assert v["result"] in ("PASS", "WARN")
    assert v["result"] != "FAIL"


def test_validate_fails_when_reference_moves_position():
    spec = _good_spec()
    spec["fixed_anchors"] = {"_rule": "x", "sink": "mover pra parede norte"}
    v = validate_grammar_spec(spec)
    assert v["result"] == "FAIL"
    assert any("POSI" in e or "PDF" in e for e in v["errors"])


def test_validate_fails_on_missing_required_keys():
    v = validate_grammar_spec({"room": "kitchen"})
    assert v["result"] == "FAIL"
    assert any("obrigat" in e for e in v["errors"])


def test_validate_warns_on_uncanonical_token():
    spec = _good_spec()
    spec["joinery_tokens"] = ["totally_made_up"]
    v = validate_grammar_spec(spec)
    assert v["result"] == "WARN"
    assert any("canônico" in w or "canonico" in w for w in v["warnings"])
