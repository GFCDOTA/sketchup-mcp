"""Fase 0+1 do laco curadoria/classe -> .skp.

Fase 0 ligou o sofa_class_gate no caminho REAL (furnish_apartment::living_room_boxes).
Fase 1 trocou a heuristica grosseira de lugares (3 se w>=2.0 senao 2) por
derive_living_sofa, que deixa a CLASSE escolher os lugares (per_seat na faixa) e nasce
do arquetipo VENEZIA curado pelo Felipe. Aqui provamos que o sofa da sala agora e'
SEMPRE in-class — logo o gate pode ser promovido a hard-FAIL sem quebrar o build.
"""
import pytest

from tools.furniture_anatomy_spec import sofa_spec
from tools.sofa_builder import build_sofa
from tools.sofa_class import derive_living_sofa, sofa_class_gate


# larguras reais de nicho num ape compacto (2-lug ate 4-lug)
@pytest.mark.parametrize("width_m", [1.50, 1.70, 1.90, 2.00, 2.20, 2.40, 2.80, 3.00])
def test_living_sofa_is_in_class(width_m):
    """Fase 1: derive_living_sofa nunca gera sofa fora da classe, e fixa a largura ao
    nicho com per_seat dentro da faixa [0.52, 0.75]."""
    spec = derive_living_sofa(width_m)
    parts, _ = build_sofa(spec)
    verdict = sofa_class_gate(spec, parts)
    assert verdict["result"] != "FAIL", verdict["errors"]
    assert abs(spec.width - round(width_m, 3)) < 1e-6
    per_seat = (spec.width - 2 * spec.arm_width) / spec.seats
    assert 0.52 <= per_seat <= 0.75, f"per_seat={per_seat:.3f} fora da classe"


def test_living_sofa_carries_venezia_premium_curation():
    """O sofa da sala nasce do arquetipo VENEZIA curado E embarca a estofaria PREMIUM
    aprovada (FP-SOFA-PREMIUM alt_001-005): braco FINO ARREDONDADO (0.14) sobre PLINTO,
    almofada UNICA coroada. O plinto SUPERSEDE os pes de ferro do venezia-slate original
    — decisao explicita do Felipe (2026-07-12): 'o sofa que ficou bom' e o premium. O
    invariante estrutural completo mora em test_living_sofa_is_approved_premium.py; aqui
    garantimos que derive_living_sofa (o caminho do furnish) carrega o premium por padrao,
    nao um box generico."""
    spec = derive_living_sofa(2.40)
    build_sofa(spec)  # nao pode levantar
    assert spec.arm_width == 0.14                  # braco fino premium (refina o thin 0.15)
    assert spec.arm_profile == "rounded"           # alt_001
    assert spec.base_style == "plinth"             # alt_002 (supersede os pes de ferro)
    assert spec.seat_style == "single_crowned"     # alt_004


def test_fase1_fixes_the_old_heuristic_defect():
    """Caracterizacao: a heuristica ANTIGA reprovava a classe em 2.8m (per_seat>0.75) —
    o defeito que a Fase 0 revelou. A Fase 1 corrige a MESMA largura de nicho."""
    old = sofa_spec("straight", seats=3, width=2.80, depth=0.95)
    old_parts, _ = build_sofa(old)
    assert sofa_class_gate(old, old_parts)["result"] == "FAIL"      # defeito documentado
    new = derive_living_sofa(2.80)
    new_parts, _ = build_sofa(new)
    assert sofa_class_gate(new, new_parts)["result"] != "FAIL"      # corrigido pela classe
