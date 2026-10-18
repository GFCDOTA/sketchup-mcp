"""conftest.py — roda ANTES de qualquer coleta/import de teste.

`PT_TO_M` (core/scale.py) e' lido UMA vez por processo, no primeiro import de
`core.scale` — nao da pra ter dois valores validos no MESMO processo pytest.
planta_74 tem escala real verificada por cota (0.0259), diferente do default
de core.scale (ancoragem por wall-thickness, ~0.0352) que as fixtures
SINTETICAS (`fixtures/synthetic_rooms/*.json`, nomeadas por area real —
"bedroom_medium_14m2.json" etc.) foram desenhadas pra usar.

Por isso os testes marcados `@pytest.mark.planta74_scale` (ou o
`pytestmark` do modulo) tem que rodar numa invocacao de pytest SEPARADA dos
demais — dois `pytest -m ...` na CI, nao um so `pytest tests/`:

    PT_TO_M=0.0259 pytest tests/ -m planta74_scale
    pytest tests/ -m "not planta74_scale"

Este conftest so GARANTE que o valor certo (ou a ausencia de override) esta
setado ANTES de qualquer teste importar core.scale, olhando pra `-m` que foi
passado — independe de ordem de coleta dos arquivos (gotcha pago: um arquivo
alfabeticamente anterior importando core.scale sem setar nada travava o
default pra todo o processo, mesmo que um arquivo depois tentasse
os.environ.setdefault). Ver core/scale.py::assert_pt_to_m_for_source (guard
fail-fast que pega exatamente este footgun em uso fora do pytest).
"""
from __future__ import annotations

import os

PLANTA74_SCALE = "0.0259"


def pytest_configure(config) -> None:
    markexpr = (config.getoption("-m", default="") or "").strip()
    if markexpr == "planta74_scale":
        os.environ["PT_TO_M"] = PLANTA74_SCALE
    else:
        # "not planta74_scale" OU suite completa sem -m: NAO forcar 0.0259 —
        # mas tambem nao herdar um PT_TO_M de shell antigo (gotcha real:
        # sessao anterior tinha `setx PT_TO_M=0.0259` ou export vivo).
        os.environ.pop("PT_TO_M", None)


# test_bathrooms_style.py computa `ROOMS = _rooms()` no IMPORT (nao dentro de
# um teste/fixture) — coletar esse arquivo fora da invocacao planta74_scale
# faria o RuntimeError do guard estourar na COLETA e derrubar a suite
# inteira, mesmo que todos os testes dele fossem deselecionados por -m.
_EAGER_PLANTA74_FILES = {"test_bathrooms_style.py"}


def pytest_ignore_collect(collection_path, config):
    markexpr = (config.getoption("-m", default="") or "").strip()
    if markexpr != "planta74_scale" and collection_path.name in _EAGER_PLANTA74_FILES:
        return True
    return None


def pytest_collection_modifyitems(config, items) -> None:
    """Registra a marca em quem usa fixtures/planta_74/* sem precisar decorar
    cada teste manualmente (best-effort: olha o arquivo-fonte do teste)."""
    planta74_files = {
        "test_bathrooms_style.py",
        "test_bed_placement_gate.py",
        "test_circulation_gate.py",
        "test_living_room_style.py",
        "test_suites_style.py",
    }
    planta74_tests = {
        ("test_bedroom_layout.py", "test_planta_74_suites_furnish"),
        ("test_bedroom_layout.py", "test_fallback_machinery_recorded"),
        ("test_kitchen_layout_style.py", "test_filler_never_penetrates_neighbors"),
        ("test_layout_rules.py", "test_ambiguous_tv_wall_is_explained_not_crammed"),
        ("test_layout_rules.py", "test_run_emits_anti_patterns_in_json"),
        ("test_room_modes.py", "test_planta74_real_chooses_anchored_core"),
    }
    import pytest as _pytest
    for item in items:
        fname = item.path.name
        if fname in planta74_files or (fname, item.originalname) in planta74_tests:
            item.add_marker(_pytest.mark.planta74_scale)
