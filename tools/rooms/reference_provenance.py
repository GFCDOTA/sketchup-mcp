"""FP-042/P6: path + Git-blob proof for all canonical retained assets.

Unlike the binary-only gate, this checks every P6 retain_canonical_location
entry: reference JSON, markdown verdicts, SKPs, PNGs, test fixtures and archives.
This proves preservation in Git, not L2 SketchUp usability or design correctness.
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs/specs/fp042_inventory.v1.json"
MANIFEST = ROOT / "docs/specs/fp042_references.v1.json"
CANONICAL_DISPOSITION = "retain_canonical_location"


def git_index(root: Path = ROOT) -> dict[str, str]:
    raw = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=root)
    result = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        meta, filename = record.split(b"\t", 1)
        _mode, sha, stage = meta.decode("ascii").split()
        if stage == "0":
            result[filename.decode("utf-8")] = sha
    return result


def canonical_paths(inventory: dict) -> set[str]:
    return {r["path"] for r in inventory["entries"]
            if r.get("phase") == "P6" and
            r.get("disposition") == CANONICAL_DISPOSITION}


def verify(manifest: dict, inventory: dict, index: dict[str, str]) -> dict:
    rows = manifest.get("entries")
    if manifest.get("schema_version") != "fp042_canonical_references.v1" or not isinstance(rows, list):
        return {"result": "FAIL", "errors": ["INVALID_SCHEMA"]}
    names = [r.get("path") for r in rows if isinstance(r, dict)]
    duplicates = sorted(k for k, n in Counter(names).items() if n > 1)
    malformed = sorted(str(r.get("path")) for r in rows if not isinstance(r, dict) or
                       not isinstance(r.get("path"), str) or
                       not isinstance(r.get("blob_sha"), str) or len(r["blob_sha"]) != 40 or
                       not isinstance(r.get("owner_group"), str) or not r["owner_group"])
    tracked = canonical_paths(inventory)
    defined = {r["path"]: r["blob_sha"] for r in rows
               if isinstance(r, dict) and isinstance(r.get("path"), str)
               and isinstance(r.get("blob_sha"), str)}
    unregistered = sorted(tracked - defined.keys())
    foreign = sorted(defined.keys() - tracked)
    missing = sorted(tracked - index.keys())
    changed = sorted(p for p in tracked & index.keys() & defined.keys()
                     if index[p] != defined[p])
    errors = []
    if duplicates:
        errors.append("DUPLICATE_PATH")
    if malformed:
        errors.append("INVALID_RECORD")
    if unregistered:
        errors.append("UNREGISTERED_P6_REFERENCE")
    if foreign:
        errors.append("NOT_CANONICAL_P6_REFERENCE")
    if missing:
        errors.append("GIT_BLOB_MISSING")
    if changed:
        errors.append("GIT_BLOB_CHANGED")
    return {"result": "FAIL" if errors else "PASS", "errors": errors,
            "protected_count": len(tracked), "registered_count": len(rows),
            "unregistered": unregistered, "foreign": foreign, "missing": missing,
            "changed": changed, "malformed": malformed, "duplicates": duplicates,
            "proof": "GIT_BLOB_AND_PATH_NOT_SKETCHUP_L2"}


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    result = verify(manifest, inventory, git_index())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
