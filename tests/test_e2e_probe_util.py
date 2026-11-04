"""Sonda E2E (#589): o teste abaixo documenta o comportamento esperado de `slugify` e hoje e um xfail ESTRITO (falha de proposito).
O executor local deve corrigir `tests/e2e_probe_util.py` e remover o marcador `xfail`, tornando o teste verde."""
from __future__ import annotations

import pytest

from tests.e2e_probe_util import slugify


def test_slugify_strips_outer_spaces_and_joins_words_with_a_hyphen():
    assert slugify("  Hello World ") == "Hello-World"


@pytest.mark.xfail(strict=True, reason="sonda E2E: slugify ainda nao baixa a caixa nem colapsa espacos repetidos")
def test_slugify_lowercases_and_collapses_repeated_spaces():
    assert slugify("  Hello   World  ") == "hello-world"
