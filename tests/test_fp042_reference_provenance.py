"""Proof that every P6 canonical artifact is still in Git, unchanged."""
import json

from tools.rooms.reference_provenance import (
    INVENTORY, MANIFEST, canonical_paths, git_index, verify,
)


def _fixture():
    return ({"schema_version": "fp042_canonical_references.v1", "entries": [
        {"path": "artifacts/a.json", "blob_sha": "a" * 40,
         "owner_group": "artifacts"}]},
        {"entries": [{"path": "artifacts/a.json", "phase": "P6",
                      "disposition": "retain_canonical_location"}]})


def test_all_current_p6_canonical_entries_are_protected():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    inv = json.loads(INVENTORY.read_text(encoding="utf-8"))
    result = verify(m, inv, git_index())
    assert result["result"] == "PASS", result
    assert result["protected_count"] >= 1060
    assert len(canonical_paths(inv)) == result["registered_count"]


def test_rejects_hash_changes_and_missing_files():
    m, inv = _fixture()
    assert "GIT_BLOB_CHANGED" in verify(m, inv, {"artifacts/a.json": "b" * 40})["errors"]
    assert "GIT_BLOB_MISSING" in verify(m, inv, {})["errors"]


def test_rejects_unregistered_or_foreign_references():
    m, inv = _fixture()
    inv["entries"].append({"path": "fixtures/b.skp", "phase": "P6",
                          "disposition": "retain_canonical_location"})
    assert "UNREGISTERED_P6_REFERENCE" in verify(
        m, inv, {"artifacts/a.json": "a" * 40})["errors"]
    m, inv = _fixture()
    m["entries"].append({"path": "tools/exe.py", "blob_sha": "a" * 40,
                         "owner_group": "other"})
    assert "NOT_CANONICAL_P6_REFERENCE" in verify(
        m, inv, {"artifacts/a.json": "a" * 40})["errors"]


def test_duplicate_and_malformed_records_are_rejected():
    m, inv = _fixture()
    m["entries"].append(dict(m["entries"][0]))
    assert "DUPLICATE_PATH" in verify(
        m, inv, {"artifacts/a.json": "a" * 40})["errors"]
    m, inv = _fixture()
    m["entries"][0]["owner_group"] = ""
    assert "INVALID_RECORD" in verify(
        m, inv, {"artifacts/a.json": "a" * 40})["errors"]
