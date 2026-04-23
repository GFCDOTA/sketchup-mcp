"""GUIDE test: planta_74.pdf rodado pelo run_pdf_pipeline. NAO e gate rigido
de numeros exatos (hardening ainda em evolucao), mas valida FAIXAS saudaveis.

Asserts de faixa:
  - 50 <= walls <= 260
  - 11 <= rooms <= 40 (F6 deve trazer pra 11-15)
  - orphan_node_count <= 5
  - largest_component_ratio >= 0.80

Se qualquer faixa estourar, significa que algum hardening regrediu.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PLANTA_PDF = REPO_ROOT / "planta_74.pdf"


def _require_inputs():
    if not PLANTA_PDF.exists():
        pytest.skip(f"planta_74.pdf ausente em {PLANTA_PDF}")


@pytest.fixture(scope="module")
def planta_observed(tmp_path_factory):
    _require_inputs()
    from model.pipeline import run_pdf_pipeline

    out = tmp_path_factory.mktemp("planta_74_snapshot")
    result = run_pdf_pipeline(
        pdf_bytes=PLANTA_PDF.read_bytes(),
        filename=PLANTA_PDF.name,
        output_dir=out,
    )
    return result.observed_model, out


def test_planta74_walls_in_healthy_range(planta_observed):
    obs, _out = planta_observed
    n = len(obs["walls"])
    assert 50 <= n <= 260, f"walls={n} fora da faixa esperada [50, 260]"


def test_planta74_rooms_in_healthy_range(planta_observed):
    obs, _out = planta_observed
    n = len(obs["rooms"])
    assert 11 <= n <= 40, f"rooms={n} fora da faixa esperada [11, 40]"


def test_planta74_orphan_nodes_bounded(planta_observed):
    obs, _out = planta_observed
    conn = obs.get("metadata", {}).get("connectivity", {})
    orphan = conn.get("orphan_node_count")
    assert orphan is not None, "connectivity.orphan_node_count ausente"
    assert orphan <= 5, f"orphan_node_count={orphan} excede 5"


def test_planta74_largest_component_ratio_healthy(planta_observed):
    obs, _out = planta_observed
    conn = obs.get("metadata", {}).get("connectivity", {})
    ratio = conn.get("largest_component_ratio")
    assert ratio is not None, "connectivity.largest_component_ratio ausente"
    assert ratio >= 0.80, f"largest_component_ratio={ratio} abaixo de 0.80"
