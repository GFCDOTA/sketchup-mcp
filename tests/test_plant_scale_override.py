"""Per-plant PT_TO_M injection (verified cota-anchored scale).

planta_74's wall-thickness scale anchor (0.19 m / 5.4 pt = 0.0352) inflated
the flat ~1.36x. The verified anchor from SUITE 01's printed cota (5.45 x
4.00 m) is PT_TO_M ~= 0.0259. This guards that the builder injects that scale
for planta_74, never for quadrado/other plants, and never over an explicit
caller override. See tools/build_plan_shell_skp.PLANT_PT_TO_M.
"""
from pathlib import Path

from tools.build_plan_shell_skp import (
    PLANT_PT_TO_M,
    _plant_from_fixture_path,
    resolve_plant_pt_to_m,
)

PLANTA_74 = Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
QUADRADO = Path("fixtures/quadrado/consensus_with_window.json")


def test_registry_has_verified_planta_74_scale():
    assert PLANT_PT_TO_M["planta_74"] == 0.0259


def test_planta_74_injects_verified_scale():
    assert resolve_plant_pt_to_m(PLANTA_74, {}) == "0.0259"


def test_explicit_env_override_wins():
    # A caller-supplied PT_TO_M must never be clobbered by the registry.
    assert resolve_plant_pt_to_m(PLANTA_74, {"PT_TO_M": "0.05"}) is None


def test_quadrado_keeps_ruby_default():
    # quadrado is not in the registry -> no injection -> Ruby default (0.0352).
    assert resolve_plant_pt_to_m(QUADRADO, {}) is None


def test_non_fixture_path_never_injects():
    # _infer_plant() defaults to 'planta_74' for non-fixtures paths; the
    # injection path must NOT, or an arbitrary consensus would get the wrong
    # scale. _plant_from_fixture_path returns None off fixtures/.
    p = Path("runs/scratch/observed.json")
    assert _plant_from_fixture_path(p) is None
    assert resolve_plant_pt_to_m(p, {}) is None


def test_plant_from_fixture_path_extracts_plant():
    assert _plant_from_fixture_path(PLANTA_74) == "planta_74"
    assert _plant_from_fixture_path(QUADRADO) == "quadrado"
