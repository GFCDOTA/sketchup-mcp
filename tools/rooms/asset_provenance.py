"""FP-042/P6: fail-closed provenance gate for tracked binary SketchUp assets.

Git's blob hash proves byte preservation in the repository index, NOT visual
fidelity inside SketchUp, nor the provenance of externally linked textures.
This deliberately does not read, mutate or regenerate any asset.
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/specs/fp042_asset_blobs.v1.json"
BINARY_EXTENSIONS = frozenset([".skp",".pdf",".png",".jpg",".jpeg",".webp",".gif",".obj",".fbx",".glb",".gltf",".zip",".mp4",".mov",".wav",".ttf",".bin",".blend",".psd",".ico",".heic",".step",".dll",".exe",".so"])


def is_binary_asset(path: str) -> bool:
    return Path(path).suffix.lower() in BINARY_EXTENSIONS


def git_index_assets(root: Path = ROOT) -> dict[str, str]:
    """Read Git stage-0 object IDs; no content streaming or external network."""
    raw = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=root)
    found = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        meta, name = entry.split(b"\t", 1)
        _mode, sha, stage = meta.decode("ascii").split()
        path = name.decode("utf-8")
        if stage == "0" and is_binary_asset(path):
            found[path] = sha
    return found


def check_asset_provenance(manifest: dict, indexed: dict[str, str]) -> dict:
    records = manifest.get("assets")
    if manifest.get("schema_version") != "fp042_asset_provenance.v1" or not isinstance(records, list):
        return {"result": "FAIL", "errors": ["INVALID_SCHEMA"]}
    paths = [r.get("path") for r in records if isinstance(r, dict)]
    duplicates = sorted(p for p, n in Counter(paths).items() if n > 1)
    invalid = sorted(str(r.get("path")) for r in records if
                     not isinstance(r, dict) or
                     not isinstance(r.get("path"), str) or
                     not is_binary_asset(r["path"]) or
                     not isinstance(r.get("blob_sha"), str) or
                     len(r["blob_sha"]) != 40 or
                     not isinstance(r.get("owner_group"), str) or
                     not r["owner_group"])
    registered = {r["path"]: r["blob_sha"] for r in records if
                  isinstance(r, dict) and isinstance(r.get("path"), str) and
                  isinstance(r.get("blob_sha"), str)}
    missing = sorted(indexed.keys() - registered.keys())
    stale = sorted(registered.keys() - indexed.keys())
    modified = sorted(p for p in indexed.keys() & registered.keys()
                      if indexed[p] != registered[p])
    errors = []
    if duplicates:
        errors.append("DUPLICATE_ASSET_PATH")
    if invalid:
        errors.append("INVALID_ASSET_RECORD")
    if missing:
        errors.append("UNREGISTERED_BINARY_ASSET")
    if stale:
        errors.append("REMOVED_BINARY_ASSET")
    if modified:
        errors.append("BINARY_BLOB_CHANGED")
    return {"result": "FAIL" if errors else "PASS", "errors": errors,
            "tracked_count": len(indexed), "registered_count": len(records),
            "duplicates": duplicates, "invalid": invalid,
            "unregistered": missing, "removed": stale, "modified": modified,
            "proof": "GIT_OBJECT_ID_ONLY_NOT_SKETCHUP_L2"}


def main() -> int:
    result = check_asset_provenance(
        json.loads(MANIFEST.read_text(encoding="utf-8")), git_index_assets())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
