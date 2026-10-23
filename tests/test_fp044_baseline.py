"""FP-044/F0 — a linha de base de saida identica (caixas por comodo + canonicos) vale hoje e reprova qualquer mudanca."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

# linha de base vigente: capturada depois da decisao da Suite 01 (#381); a de artifacts/review/fp044/baseline/ fica como
# retrato historico (difere so no hash da SUITE 01)
BASELINE = Path(__file__).resolve().parents[1] / "artifacts/review/fp054/suite01_decision/fp044_baseline.json"

pytestmark = pytest.mark.planta74_scale      # collect_boxes da planta_74 exige PT_TO_M=0.0259 (processo proprio)


def test_estado_atual_e_identico_a_linha_de_base():
    from tools.validation.fp044_baseline import compare
    assert compare(json.loads(BASELINE.read_text("utf-8"))) == []


def test_mudanca_de_caixas_ou_de_canonico_e_detectada():
    from tools.validation.fp044_baseline import compare
    base = json.loads(BASELINE.read_text("utf-8"))
    bad = copy.deepcopy(base)
    bad["room_box_hashes"]["SUITE 01"] = "0" * 64
    bad["canonical_sha256"]["artifacts/planta_74/planta_74.skp"] = "0" * 64
    errors = compare(bad)
    assert "CAIXAS_MUDARAM: SUITE 01" in errors and "CANONICO_MUDOU: artifacts/planta_74/planta_74.skp" in errors
