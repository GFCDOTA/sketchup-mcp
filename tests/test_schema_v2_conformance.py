"""Schema conformance test: observed_model.json precisa ter as chaves top-level
canonicas e tipos basicos corretos. Schema inline pra evitar dependencia em
jsonschema; checagem simples mas suficiente pra pegar regressoes estruturais.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
P12_OBSERVED = REPO_ROOT / "runs" / "proto" / "p12_v1_run" / "observed_model.json"

EXPECTED_TOP_KEYS = {
    "schema_version",
    "run_id",
    "source",
    "bounds",
    "roi",
    "walls",
    "junctions",
    "rooms",
    "scores",
    "metadata",
    "warnings",
    "openings",
    "peitoris",
}


def _require():
    if not P12_OBSERVED.exists():
        pytest.skip(f"observed_model.json ausente em {P12_OBSERVED}")


@pytest.fixture(scope="module")
def observed():
    _require()
    return json.loads(P12_OBSERVED.read_text(encoding="utf-8"))


def test_schema_has_all_top_level_keys(observed):
    got = set(observed.keys())
    missing = EXPECTED_TOP_KEYS - got
    assert not missing, f"chaves top-level ausentes: {sorted(missing)}"


def test_schema_walls_is_list(observed):
    assert isinstance(observed["walls"], list), "walls deve ser list"


def test_schema_junctions_is_list(observed):
    assert isinstance(observed["junctions"], list), "junctions deve ser list"


def test_schema_rooms_is_list(observed):
    assert isinstance(observed["rooms"], list), "rooms deve ser list"


def test_schema_openings_is_list(observed):
    assert isinstance(observed["openings"], list), "openings deve ser list"


def test_schema_peitoris_is_list(observed):
    assert isinstance(observed["peitoris"], list), "peitoris deve ser list"


def test_schema_warnings_is_list(observed):
    assert isinstance(observed["warnings"], list), "warnings deve ser list"


def test_schema_scores_has_required_keys(observed):
    scores = observed["scores"]
    assert isinstance(scores, dict), "scores deve ser dict"
    for key in ("geometry", "topology"):
        assert key in scores, f"scores.{key} ausente"
        assert isinstance(scores[key], (int, float)), f"scores.{key} nao e numero"


def test_schema_bounds_is_dict_with_pages(observed):
    bounds = observed["bounds"]
    assert isinstance(bounds, dict), "bounds deve ser dict"
    # pages e a chave canonical esperada (pode variar; validamos que e dict nao vazio)
    assert bounds, "bounds dict vazio"
    if "pages" in bounds:
        assert isinstance(bounds["pages"], (list, dict)), "bounds.pages tipo invalido"


def test_schema_source_has_filename_and_type(observed):
    source = observed["source"]
    assert isinstance(source, dict), "source deve ser dict"
    assert "filename" in source, "source.filename ausente"
    assert "source_type" in source, "source.source_type ausente"


def test_schema_metadata_is_dict(observed):
    assert isinstance(observed["metadata"], dict), "metadata deve ser dict"


def test_schema_run_id_is_string(observed):
    assert isinstance(observed["run_id"], str), "run_id deve ser string"
    assert observed["run_id"], "run_id vazio"


def test_schema_version_present(observed):
    sv = observed["schema_version"]
    # pode ser int ou str, o importante e existir e nao ser vazio
    assert sv is not None and sv != "", "schema_version vazio"


def test_schema_roi_is_list(observed):
    assert isinstance(observed["roi"], list), "roi deve ser list"
