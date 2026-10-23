"""DOC-EXT-01: o gate de evidencia de documentacao externa e offline e nao aceita evidencia inconsistente com a versao local."""
from __future__ import annotations

import json

import pytest

from tools.navigation import external_doc_evidence as ede

LOCK = """
[[package]]
name = "shapely"
version = "2.1.2"

[[package]]
name = "mcp"
version = "1.28.1"
"""


def ok(**over):
    base = {"schema_version": "external_doc_evidence.v1", "dependency": "shapely", "version": "2.1.2",
            "version_source": "uv.lock", "documentation_provider": "context7", "library_id": "/shapely/shapely",
            "version_match": "unversioned", "apis_verified": ["shapely.prepare"], "checked_on": "2026-10-23",
            "verified": True, "notes": "doc da main; prepare conferido no runtime local"}
    return {**base, **over}


def check(ev):
    return ede.validate(ev, ede.parse_lock(LOCK))


def test_consistent_evidence_passes():
    assert check(ok()) == []


def test_version_that_disagrees_with_the_lockfile_fails():
    assert any("VERSION_MISMATCH" in e for e in check(ok(version="2.0.6")))


def test_runtime_version_must_declare_the_lockfile_divergence():
    errs = check(ok(dependency="mcp", version="1.28.0", version_source="runtime", library_id="/modelcontextprotocol/python-sdk/v1.28.0",
                    version_match="exact", apis_verified=["mcp.server.fastmcp.FastMCP"]))
    assert any("LOCKFILE_DIVERGENCE_UNDECLARED" in e for e in errs)
    assert check(ok(dependency="mcp", version="1.28.0", version_source="runtime", lockfile_version="1.28.1",
                    library_id="/modelcontextprotocol/python-sdk/v1.28.0", version_match="exact",
                    apis_verified=["mcp.server.fastmcp.FastMCP"])) == []


def test_python_dependency_absent_from_the_lockfile_fails():
    assert any("NOT_IN_LOCKFILE" in e for e in check(ok(dependency="leftpad")))


def test_verified_evidence_must_name_the_apis_it_checked():
    assert any("NO_APIS_VERIFIED" in e for e in check(ok(apis_verified=[])))


def test_declared_gap_is_accepted_but_never_as_verified():
    gap = ok(dependency="sketchup-ruby-api", version="26.0.429", version_source="runtime", documentation_provider="none",
             library_id=None, version_match="unavailable", apis_verified=[], verified=False,
             notes="Context7 sem a SketchUp Ruby API 26; fallback = doc oficial Trimble")
    assert check(gap) == []
    assert any("GAP_MARKED_VERIFIED" in e for e in check({**gap, "verified": True}))


def test_schema_violation_is_reported():
    assert any(e.startswith("SCHEMA") for e in check({**ok(), "extra": 1}))


def test_repository_evidence_is_valid_offline():
    report = ede.run()
    assert report["errors"] == [], report
    assert report["files"] >= 1


@pytest.mark.parametrize("bad", ["", "abc"])
def test_lock_parser_ignores_garbage(bad):
    assert ede.parse_lock(bad) == {}


def test_gate_never_imports_network_clients():
    src = ede.__file__
    text = open(src, encoding="utf-8").read()
    for forbidden in ("urllib", "requests", "httpx", "socket", "context7.com"):
        assert forbidden not in text, forbidden
    json.dumps(ok())
