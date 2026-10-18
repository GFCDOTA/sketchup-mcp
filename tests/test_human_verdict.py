"""Vocabulario canonico do veredito humano (tools/human_verdict) — a FONTE
UNICA que separa o territorio do Felipe (IMPROVED/SAME/WORSE + liked + tags) do
da maquina. Aqui pina-se o vocabulario NOVO (liked ortogonal, tags) e os
validadores puros; o rail que probe os modulos-maquina contra os literais vive
em test_variant_sweep.test_machine_never_writes_human_verdict."""
from __future__ import annotations

from tools import human_verdict as hv


def test_human_verdicts_are_the_three_regression_words():
    assert hv.HUMAN_VERDICTS == ("IMPROVED", "SAME", "WORSE")
    for v in hv.HUMAN_VERDICTS:
        assert hv.is_human_verdict(v)
    for junk in ("CANDIDATE", "PENDING_VISION", "improved", "", None, 1):
        assert not hv.is_human_verdict(junk)


def test_liked_is_bool_or_null_and_strictly_typed():
    # vocabulario valido: True / False / None (ORTOGONAL a IMPROVED/SAME/WORSE)
    assert hv.is_liked(True) and hv.is_liked(False) and hv.is_liked(None)
    # 1/0 NAO sao liked apesar de 1 == True em Python — ortogonal e tipado
    for junk in (1, 0, "true", "yes", "IMPROVED", [], {}):
        assert not hv.is_liked(junk)


def test_liked_is_orthogonal_to_the_regression_verdict():
    # um valor pode ser um veredito valido E ter liked independente — os dois
    # vocabularios nao se sobrepoem (nenhum liked e' um human_verdict e vice-versa)
    assert not any(hv.is_liked(v) for v in hv.HUMAN_VERDICTS)
    assert not any(hv.is_human_verdict(x) for x in hv.LIKED_VALUES)


def test_normalize_tags_trims_dedups_preserves_order_and_types():
    assert hv.normalize_tags(["  industrial ", "escuro demais", "industrial"]) == [
        "industrial", "escuro demais"]
    assert hv.normalize_tags(["a", "", "  ", "b", "a"]) == ["a", "b"]  # vazias/dupes fora
    assert hv.normalize_tags(("x", "y")) == ["x", "y"]                 # tupla aceita
    # entrada nao-lista ou itens nao-str -> ignorados / []
    assert hv.normalize_tags(None) == []
    assert hv.normalize_tags("industrial") == []                       # string != lista
    assert hv.normalize_tags(["ok", 1, None, {"x": 1}]) == ["ok"]


def test_human_only_fields_enumerates_the_three_human_columns():
    assert hv.HUMAN_ONLY_FIELDS == ("human_verdict", "liked", "tags")
