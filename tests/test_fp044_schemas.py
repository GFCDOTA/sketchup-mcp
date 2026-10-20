"""FP-044/F3 — os contratos JSON Schema moram em core/schemas/ e so `core.schemas` sabe esse caminho."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from jsonschema import Draft202012Validator

from core.schemas import SCHEMA_DIR, load, schema_path

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ("capability_catalog.v1", "correction_finding", "curadoria_verdict", "decision_audit_record",
             "design_spec_bundle", "judged_variant", "rag_writeback_record", "specialist_profile.v1", "visual_findings")


def _tracked() -> list[str]:
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    return [f for f in out if f]


def test_os_nove_contratos_estao_em_core_schemas_e_sao_schemas_validos():
    assert SCHEMA_DIR == ROOT / "core/schemas"
    assert sorted(p.name for p in SCHEMA_DIR.glob("*.schema.json")) == sorted(f"{c}.schema.json" for c in CONTRACTS)
    for c in CONTRACTS:
        Draft202012Validator.check_schema(load(f"{c}.schema.json"))


def test_schema_path_respeita_outra_raiz(tmp_path):
    assert schema_path("visual_findings.schema.json") == SCHEMA_DIR / "visual_findings.schema.json"
    assert schema_path("visual_findings.schema.json", tmp_path) == tmp_path / "core/schemas/visual_findings.schema.json"


def test_nenhum_codigo_monta_o_caminho_antigo_da_raiz():
    antigo = re.compile(r"""(?<![\w/])["']schemas["'/]|(?<![\w/.-])schemas/(""" + "|".join(re.escape(c) for c in CONTRACTS) + r")\.schema")
    ruins = []
    for f in _tracked():
        if not f.endswith(".py") or f.startswith("docs/archive/"):
            continue
        for n, line in enumerate((ROOT / f).read_text("utf-8", errors="replace").splitlines(), 1):
            if antigo.search(line.split("#", 1)[0]):
                ruins.append(f"{f}:{n}")
    assert ruins == [], ruins
