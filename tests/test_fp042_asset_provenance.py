"""FP-042/P6 binary provenance gate: no silent changes to .skp, images or PDFs."""
import json
from pathlib import Path

from tools.rooms.asset_provenance import (
    MANIFEST, check_asset_provenance, git_index_assets, is_binary_asset,
)


def _manifest():
    return {"schema_version": "fp042_asset_provenance.v1",
            "assets": [{"path": "artifacts/planta_74/canonical.skp",
                        "blob_sha": "a" * 40, "owner_group": "artifacts"}]}


def test_current_git_index_assets_match_committed_provenance():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    result = check_asset_provenance(manifest, git_index_assets())
    assert result["result"] == "PASS", result
    assert result["tracked_count"] >= 33
    assert sum(Path(r["path"]).suffix.lower() == ".skp"
               for r in manifest["assets"]) >= 33


def test_blocks_modified_blob_even_if_filename_is_unchanged():
    report = check_asset_provenance(_manifest(),
                                    {"artifacts/planta_74/canonical.skp": "b" * 40})
    assert "BINARY_BLOB_CHANGED" in report["errors"]


def test_blocks_missing_and_unregistered_assets():
    p = "artifacts/planta_74/canonical.skp"
    assert "REMOVED_BINARY_ASSET" in check_asset_provenance(_manifest(), {})["errors"]
    assert "UNREGISTERED_BINARY_ASSET" in check_asset_provenance(
        _manifest(), {p: "a" * 40, "renders/new.png": "c" * 40})["errors"]


def test_rejects_duplicate_and_invalid_assets():
    payload = _manifest()
    payload["assets"].append(dict(payload["assets"][0]))
    assert "DUPLICATE_ASSET_PATH" in check_asset_provenance(
        payload, {"artifacts/planta_74/canonical.skp": "a" * 40})["errors"]
    payload["assets"][1] = {"path": "docs/fake.txt", "blob_sha": "x",
                            "owner_group": ""}
    assert "INVALID_ASSET_RECORD" in check_asset_provenance(
        payload, {"artifacts/planta_74/canonical.skp": "a" * 40})["errors"]


def test_supported_asset_kinds_include_sketchup_and_image_proofs():
    assert all(is_binary_asset("proof" + ext) for ext in
               (".skp", ".pdf", ".png", ".jpg", ".webp", ".zip"))
    assert not is_binary_asset("knowledge.json")
