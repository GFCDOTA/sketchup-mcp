"""DOC-EXT-01 — valida, OFFLINE, a evidencia de documentacao externa gravada pelos agentes.

    python -m tools.navigation.external_doc_evidence          # errors = [] ou a lista do que nao fecha

O agente consulta a documentacao (Context7 ou doc oficial) durante o desenvolvimento e grava
`docs/engineering/evidence/*.json` (schema `core/schemas/external_doc_evidence.v1.schema.json`). Este gate NAO chama rede: so
confere que a evidencia e coerente com o que o repositorio fixa (`uv.lock`):
  - pacote declarado pelo `uv.lock`/`pyproject.toml` tem que existir no lock e bater a versao (VERSION_MISMATCH / NOT_IN_LOCKFILE);
  - versao lida do runtime que difere do lock tem que declarar `lockfile_version` (LOCKFILE_DIVERGENCE_UNDECLARED);
  - evidencia `verified` precisa nomear as APIs conferidas (NO_APIS_VERIFIED) e ter provedor real;
  - lacuna (`documentation_provider: none`) e aceita so como NAO verificada (GAP_MARKED_VERIFIED).
Politica: `docs/engineering/external-documentation-policy.md`. Complexidade: O(E + L), E evidencias, L linhas do lock.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "docs/engineering/evidence"
SCHEMA = ROOT / "core/schemas/external_doc_evidence.v1.schema.json"
LOCK_SOURCES = ("uv.lock", "pyproject.toml")


def parse_lock(text: str) -> dict[str, str]:
    """{nome normalizado: versao} dos blocos [[package]] do uv.lock (sem dependencia de toml para manter 3.11 sem extras)."""
    out: dict[str, str] = {}
    for block in text.split("[[package]]")[1:]:
        name = re.search(r'^name = "([^"]+)"', block, re.M)
        version = re.search(r'^version = "([^"]+)"', block, re.M)
        if name and version:
            out[_norm(name.group(1))] = version.group(1)
    return out


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _schema_errors(ev: dict) -> list[str]:
    from jsonschema import Draft202012Validator
    validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    return [f"SCHEMA: {'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in validator.iter_errors(ev)]


def validate(ev: dict, lock: dict[str, str]) -> list[str]:
    errors = _schema_errors(ev)
    if errors:
        return errors
    dep, version, source = _norm(ev["dependency"]), ev["version"], ev["version_source"]
    locked = lock.get(dep)
    if source in LOCK_SOURCES:
        if locked is None:
            errors.append(f"NOT_IN_LOCKFILE: {ev['dependency']} declarado por {source} mas ausente do uv.lock")
        elif locked != version:
            errors.append(f"VERSION_MISMATCH: {ev['dependency']} evidencia {version} x uv.lock {locked}")
    elif locked is not None and locked != version and ev.get("lockfile_version") != locked:
        errors.append(f"LOCKFILE_DIVERGENCE_UNDECLARED: {ev['dependency']} runtime {version} x uv.lock {locked} "
                      "(declarar lockfile_version)")
    gap = ev["documentation_provider"] == "none" or ev["version_match"] == "unavailable"
    if gap and ev["verified"]:
        errors.append(f"GAP_MARKED_VERIFIED: {ev['dependency']} sem documentacao nao pode ser verified=true")
    if ev["verified"] and not ev["apis_verified"]:
        errors.append(f"NO_APIS_VERIFIED: {ev['dependency']} verified=true sem nomear as APIs conferidas")
    return errors


def run(root: Path = ROOT) -> dict:
    lock_path = root / "uv.lock"
    lock = parse_lock(lock_path.read_text(encoding="utf-8")) if lock_path.is_file() else {}
    errors, files = [], sorted((root / "docs/engineering/evidence").glob("*.json"))
    for f in files:
        errors += [f"{f.relative_to(root).as_posix()}: {e}" for e in validate(json.loads(f.read_text(encoding="utf-8")), lock)]
    return {"gate": "DOC-EXT-01", "files": len(files), "errors": errors,
            "proof": "EVIDENCIA_REGISTRADA_COERENTE_COM_O_LOCK_NAO_CONSULTA_REDE"}


def main() -> int:
    report = run()
    sys.stdout.write(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
