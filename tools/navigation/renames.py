"""Gate das renomeações autorizadas de arquivos PROTEGIDOS (FP-043 §9).

Mover um binário/referência protegida de caminho não pode ser um `regenerar o manifesto` que apaga o
diff. O registro `docs/specs/fp043_protected_renames.v1.json` lista, uma a uma, as renomeações
autorizadas com o SHA256 do CONTEÚDO ANTES (blob do git no commit-base) e este gate exige:

- `done`: origem ausente, destino rastreado e **conteúdo idêntico** (blob do git e SHA256 do blob == os registrados);
  o blob do git igual ao registrado; manifestos de assets/referências com o destino (mesmo blob) e SEM a
  origem; inventário FP-042 com o destino e sem a origem; nenhuma outra cópia rastreada com o mesmo nome
  e bytes diferentes (cópia divergente);
- `planned`: origem rastreada (ainda não movida) e destino ausente.

O gate só aceita o que está no registro: um rename não registrado continua sendo `STALE`/`UNREGISTERED`
nos gates FP-042. Prova bytes e caminho; não prova que o consumidor foi atualizado (isso é o PR de movimento).

Uso: python -m tools.navigation.renames [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from tools.navigation.consumers import REPO, tracked_files

REGISTRY = REPO / "docs/specs/fp043_protected_renames.v1.json"
SCHEMA = "fp043_protected_renames.v1"
INVENTORY = "docs/specs/fp042_inventory.v1.json"
ASSETS = "docs/specs/fp042_asset_blobs.v1.json"
REFERENCES = "docs/specs/fp042_references.v1.json"


def blob_sha256(blob: str, root: Path = REPO) -> str:
    """SHA256 do CONTEÚDO do blob do git (não do arquivo na árvore de trabalho, que no Windows pode ter CRLF)."""
    return hashlib.sha256(subprocess.check_output(["git", "cat-file", "blob", blob], cwd=root)).hexdigest()


def blob_ids(root: Path = REPO) -> dict[str, str]:
    raw = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=root)
    out = {}
    for rec in raw.split(b"\0"):
        if rec:
            meta, name = rec.split(b"\t", 1)
            mode, sha, stage = meta.decode("ascii").split()
            if stage == "0":
                out[name.decode("utf-8")] = sha
    return out


def _paths(doc: dict, key: str) -> dict[str, str]:
    return {r["path"]: r.get("blob_sha", "") for r in doc.get(key, []) if isinstance(r, dict) and "path" in r}


def check(registry: dict, tracked: list[str], root: Path = REPO, *, blobs: dict[str, str] | None = None) -> dict:
    if registry.get("schema_version") != SCHEMA or not isinstance(registry.get("renames"), list):
        return {"result": "FAIL", "errors": {"INVALID_SCHEMA": [""]}}
    tracked_set = set(tracked)
    blobs = blobs if blobs is not None else blob_ids(root)
    inventory = {e["path"] for e in json.loads((root / INVENTORY).read_text(encoding="utf-8"))["entries"]}
    assets = _paths(json.loads((root / ASSETS).read_text(encoding="utf-8")), "assets")
    refs = _paths(json.loads((root / REFERENCES).read_text(encoding="utf-8")), "entries")
    errors: dict[str, list[str]] = {}

    def flag(code: str, what: str) -> None:
        errors.setdefault(code, []).append(what)

    seen = set()
    for r in registry["renames"]:
        old, new = r.get("old_path"), r.get("new_path")
        label = f"{old} -> {new}"
        if not (isinstance(old, str) and isinstance(new, str) and old and new and old != new):
            flag("INVALID_RECORD", label)
            continue
        if old in seen:
            flag("DUPLICATE_RENAME", old)
        seen.add(old)
        for field in ("sha256", "blob_sha", "owner_group", "justification", "consumers_reviewed"):
            if not r.get(field):
                flag("MISSING_FIELD", f"{label}: {field}")
        status = r.get("status", "planned")
        if status == "planned":
            if old not in tracked_set:
                flag("PLANNED_ORIGIN_MISSING", label)
            if new in tracked_set:
                flag("PLANNED_DESTINATION_EXISTS", label)
            continue
        if status != "done":
            flag("INVALID_STATUS", label)
            continue
        if old in tracked_set:
            flag("DONE_ORIGIN_STILL_TRACKED", label)
        if new not in tracked_set:
            flag("DONE_DESTINATION_MISSING", label)
            continue
        if blobs.get(new) != r.get("blob_sha"):
            flag("BLOB_CHANGED", label)
        elif blob_sha256(r["blob_sha"], root) != r.get("sha256"):
            flag("BYTES_CHANGED", label)
        base = Path(new).name
        for other in tracked_set:
            if other != new and Path(other).name == base and base == Path(old).name and blobs.get(other) != r.get("blob_sha"):
                flag("DIVERGENT_COPY", f"{other} (mesmo nome de {new}, conteúdo diferente)")
        if old in inventory:
            flag("INVENTORY_STILL_HAS_ORIGIN", old)
        if new not in inventory:
            flag("INVENTORY_MISSING_DESTINATION", new)
        for name, manifest in (("ASSETS", assets), ("REFERENCES", refs)):
            if old in manifest:
                flag(f"{name}_STILL_HAS_ORIGIN", old)
        for name, manifest in (("ASSETS", assets), ("REFERENCES", refs)):
            expected_in = r.get(f"in_{name.lower()}", False)
            if expected_in and manifest.get(new) != r.get("blob_sha"):
                flag(f"{name}_DESTINATION_BLOB_MISMATCH", new)
            if not expected_in and new in manifest:
                flag(f"{name}_UNEXPECTED_DESTINATION", new)
    return {"result": "FAIL" if errors else "PASS", "errors": errors, "renames": len(registry["renames"]),
            "proof": "BYTES_E_CAMINHO_NAO_PROVAM_CONSUMIDORES_ATUALIZADOS"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gate das renomeações autorizadas de protegidos")
    ap.add_argument("--check", action="store_true")
    ns = ap.parse_args(argv)
    res = check(json.loads(REGISTRY.read_text(encoding="utf-8")), tracked_files())
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 1 if ns.check and res["result"] != "PASS" else 0


if __name__ == "__main__":
    sys.exit(main())
