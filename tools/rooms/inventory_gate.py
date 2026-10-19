"""FP-042: gate exaustivo de arquivos versionados, sem reclassificação implícita.

Executar: python -m tools.rooms.inventory_gate
Saída: status JSON; exit 1 quando arquivo é adicionado/removido sem inventário.
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs/specs/fp042_inventory.v1.json"
CONTROL_PATHS = frozenset({
    "docs/specs/fp042_inventory.v1.json",
    "docs/specs/FP-042_exhaustive_modularization.md",
    "tools/rooms/inventory_gate.py",
    "tests/test_fp042_inventory_gate.py",
})


def check_inventory(index: dict, tracked_paths: set[str]) -> dict:
    records = index.get("entries")
    if index.get("schema_version") != "fp042_exhaustive_inventory.v1" or not isinstance(records, list):
        return {"result": "FAIL", "errors": ["INVALID_SCHEMA"]}
    paths = [rec.get("path") for rec in records if isinstance(rec, dict)]
    duplicates = sorted(path for path, n in Counter(paths).items() if n > 1)
    registered = set(paths)
    expected = tracked_paths - CONTROL_PATHS
    missing = sorted(expected - registered)
    stale = sorted(registered - expected)
    incomplete = sorted(
        r["path"] for r in records if isinstance(r, dict)
        and (not r.get("domain") or not r.get("disposition")
             or not r.get("phase") or not r.get("status"))
    )
    errors = []
    if duplicates:
        errors.append("DUPLICATE_PATHS")
    if missing:
        errors.append("UNREGISTERED_FILES")
    if stale:
        errors.append("STALE_FILES")
    if incomplete:
        errors.append("UNCLASSIFIED_FILES")
    return {
        "result": "FAIL" if errors else "PASS",
        "errors": errors,
        "registered_count": len(registered),
        "tracked_count": len(expected),
        "unregistered": missing,
        "stale": stale,
        "duplicates": duplicates,
        "incomplete": incomplete,
        "pending_count": sum(1 for r in records if r.get("status") == "PENDING_REVIEW_OR_MIGRATION"),
    }


def main() -> int:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    tracked = {item.decode("utf-8") for item in raw.split(b"\0") if item}
    index = json.loads(INVENTORY.read_text(encoding="utf-8"))
    result = check_inventory(index, tracked)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
