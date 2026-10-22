"""Registra arquivos versionados novos (ou editados) nos manifestos FP-042: inventario, referencias P6 e blobs de assets.

Uso (cwd = raiz do repo; os arquivos ja precisam estar no indice do git, `git add`):
    python -m tools.navigation.register_evidence artifacts/review/<frente>/<fase>/README.md ...
    python -m tools.navigation.register_evidence --like docs/reports/FP-051_P0_baseline.md docs/HANDOFF.md

- Sem `--like`, so aceita `artifacts/review/**`: classificacao P6 canonica (local + blob do git), entrada no inventario
  E em `fp042_references.v1.json`; binario (PNG/JPG/SKP/PDF) tambem em `fp042_asset_blobs.v1.json`.
- Com `--like <path ja inventariado>`, copia a classificacao do modelo (doc, teste, skill, tooling) e so mexe no inventario,
  a nao ser que a classificacao copiada seja P6 canonica.
- Idempotente: path ja registrado nao duplica; o blob sha/tamanho e REFEITO a partir do indice (arquivo editado depois do
  `git add` deixa de casar — rodar de novo depois de um novo `git add`).
Os gates `pytest -k "inventory or fp042"` continuam sendo a prova; este script so evita o registro manual.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

INVENTORY = "docs/specs/fp042_inventory.v1.json"
REFERENCES = "docs/specs/fp042_references.v1.json"
ASSETS = "docs/specs/fp042_asset_blobs.v1.json"
BINARY = (".png", ".jpg", ".jpeg", ".skp", ".pdf")
P6_CANONICAL = {"domain": "reference_or_artifact", "disposition": "retain_canonical_location", "phase": "P6",
                "status": "VERIFIED_CANONICAL_LOCATION_AND_GIT_BLOB"}


class RegistrationError(ValueError):
    pass


def _load(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes().decode("utf-8")
    return json.loads(raw), ("\r\n" if "\r\n" in raw else "\n")


def _dump(path: Path, data: dict, nl: str) -> None:
    # mesmo formato do arquivo versionado (round-trip byte a byte conferido nos 3 manifestos)
    path.write_bytes((json.dumps(data, indent=2, ensure_ascii=False) + "\n").replace("\n", nl).encode("utf-8"))


def _common(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a.split("/"), b.split("/")):
        if x != y:
            break
        n += 1
    return n


def _insert(entries: list[dict], entry: dict) -> None:
    """Insere ao lado do vizinho de diretorio mais proximo (os manifestos nao sao ordenados; isto mantem os grupos juntos)."""
    if not entries:
        entries.append(entry)
        return
    best = max(range(len(entries)), key=lambda i: (_common(entries[i]["path"], entry["path"]), i))
    entries.insert(best + 1, entry)


def _blob(root: Path, path: str) -> tuple[str, int]:
    out = subprocess.check_output(["git", "-C", str(root), "ls-files", "-s", "--", path], text=True).split()
    if not out:
        raise RegistrationError(f"{path}: fora do indice do git (rodar `git add` antes de registrar)")
    sha = out[1]
    size = int(subprocess.check_output(["git", "-C", str(root), "cat-file", "-s", sha], text=True))
    return sha, size


def _upsert_blob(entries: list[dict], path: str, sha: str, size: int, group: str) -> str:
    current = next((e for e in entries if e["path"] == path), None)
    if current is None:
        _insert(entries, {"path": path, "blob_sha": sha, "blob_size": size, "owner_group": group})
        return "added"
    if current.get("blob_sha") == sha and current.get("blob_size") == size:
        return "unchanged"
    current["blob_sha"], current["blob_size"] = sha, size
    return "refreshed"


def register(root: Path, paths: list[str], like: str | None = None) -> list[dict]:
    root = Path(root)
    inv, inv_nl = _load(root / INVENTORY)
    ref, ref_nl = _load(root / REFERENCES)
    assets, assets_nl = _load(root / ASSETS)
    by_path = {e["path"]: e for e in inv["entries"]}
    if like is not None and like not in by_path:
        raise RegistrationError(f"--like {like}: path modelo nao esta no inventario")
    report = []
    for raw in paths:
        path = raw.replace("\\", "/").removeprefix("./")
        if not (root / path).is_file():
            raise RegistrationError(f"{path}: arquivo nao existe")
        if like is None and not path.startswith("artifacts/review/"):
            raise RegistrationError(f"{path}: fora de artifacts/review/ exige --like <path ja inventariado>")
        row = {"path": path}
        if path in by_path:
            row["inventory"] = "unchanged"
        else:
            model = dict(by_path[like]) if like is not None else dict(P6_CANONICAL)
            model["path"] = path
            entry = {"path": path, **{k: v for k, v in model.items() if k != "path"}}
            _insert(inv["entries"], entry)
            by_path[path] = entry
            row["inventory"] = "added"
        cls = by_path[path]
        if cls.get("phase") == "P6" and cls.get("disposition") == "retain_canonical_location":
            sha, size = _blob(root, path)
            row["references"] = _upsert_blob(ref["entries"], path, sha, size, "artifacts")
            if path.lower().endswith(BINARY):
                row["assets"] = _upsert_blob(assets["assets"], path, sha, size, "artifacts")
        report.append(row)
    _dump(root / INVENTORY, inv, inv_nl)
    _dump(root / REFERENCES, ref, ref_nl)
    _dump(root / ASSETS, assets, assets_nl)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--like", help="path ja inventariado cuja classificacao sera copiada")
    args = ap.parse_args(argv)
    try:
        for row in register(Path.cwd(), args.paths, like=args.like):
            print(json.dumps(row, ensure_ascii=False))
    except RegistrationError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
