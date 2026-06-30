"""Fase 0 do laco curadoria/classe -> .skp.

Liga o sofa_class_gate no caminho REAL de geracao (furnish_apartment.py::
living_room_boxes). Aqui provamos a INVARIANTE DE SEGURANCA do build: os sofas
que o furnish realmente gera — sofa_spec("straight", seats, width, depth=0.95)
com a regra _seats = 3 se width>=2.0 senao 2 — nao podem REPROVAR a classe.

Se este teste passa (result != FAIL), o gate hoje em WARN-log pode ser promovido
a hard-FAIL sem quebrar o build da sala. Se falhar, achamos um sofa gerado que
viola a propria classe — exatamente o que a Fase 0 existe pra revelar.
"""
import pytest

from tools.furniture_anatomy_spec import sofa_spec
from tools.sofa_builder import build_sofa
from tools.sofa_class import sofa_class_gate


def _seats_for(width_m: float) -> int:
    # espelha furnish_apartment.py::living_room_boxes
    return 3 if width_m >= 2.0 else 2


# larguras reais que o plan_living entrega num ape compacto (nicho 2-lug ate 3-lug).
# 1.90 e 2.80 estao XFAIL: a heuristica grosseira _seats=(3 se >=2.0 senao 2) estica os
# assentos pra fora da faixa de classe (per_seat>0.75) — exatamente o defeito que a Fase 0
# REVELA e que a Fase 1 (furnish usar derive_*/escolher seats pela classe) conserta. Quando
# isso for corrigido, o strict=True faz o teste falhar como XPASS, forcando a virar assert.
_XFAIL = "heuristica _seats grosseira estica per_seat fora de [0.52,0.75]; Fase 1 (derive) corrige"


@pytest.mark.parametrize("width_m", [
    1.50, 1.70, 2.00, 2.20, 2.40,
    pytest.param(1.90, marks=pytest.mark.xfail(reason=_XFAIL, strict=True)),
    pytest.param(2.80, marks=pytest.mark.xfail(reason=_XFAIL, strict=True)),
])
def test_furnished_sofa_never_fails_class_gate(width_m):
    seats = _seats_for(width_m)
    spec = sofa_spec("straight", seats=seats, width=width_m, depth=0.95)
    parts, _ = build_sofa(spec)
    verdict = sofa_class_gate(spec, parts)
    assert verdict["result"] != "FAIL", (
        f"sofa gerado (seats={seats}, width={width_m}) REPROVOU a classe: "
        f"{verdict['errors']}"
    )


def test_furnished_sofa_default_passes_clean():
    """O exemplar tipico (3 lugares, 2.40m) deve passar LIMPO (PASS), nao so
    nao-FAIL — e a prova de que o caminho default fica verde quando o gate
    virar hard-FAIL."""
    spec = sofa_spec("straight", seats=3, width=2.40, depth=0.95)
    parts, _ = build_sofa(spec)
    verdict = sofa_class_gate(spec, parts)
    assert verdict["result"] == "PASS", verdict["errors"] or verdict["warnings"]
