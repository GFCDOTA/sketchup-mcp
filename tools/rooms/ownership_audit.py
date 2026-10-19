"""FP-042/P1: diagnóstico estático de dependências por cômodo, sem importar app.

Um relatório mostra o código que ainda precisa ser migrado; o gate impede novas
dependências específicas entre pacotes tools.rooms. Não altera SKP ou fixtures.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROOM_NAMES = frozenset({
    "living", "bedroom", "kitchen", "bathroom", "service", "balcony",
    "closet", "home_office", "circulation",
})


def collect_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def ownership_violations(files: dict[str, str]) -> list[dict]:
    """Somente código dos novos pacotes; arquivos legados têm migração pendente."""
    result = []
    for path, source in sorted(files.items()):
        parts = Path(path).parts
        if len(parts) < 4 or parts[:2] != ("tools", "rooms"):
            continue
        owner = parts[2]
        if owner not in ROOM_NAMES and owner != "shared":
            continue
        for imported in sorted(collect_imports(source)):
            chunks = imported.split(".")
            if len(chunks) >= 3 and chunks[:2] == ["tools", "rooms"]:
                other = chunks[2]
                if other in ROOM_NAMES and other != owner:
                    result.append({"path": path, "owner": owner,
                                   "imported": imported, "reason": "CROSS_ROOM_DEPENDENCY"})
            elif owner == "shared" and imported in (
                "tools.furnish_apartment", "tools.bedroom_layout",
                "tools.kitchen_layout", "tools.bathroom_layout",
                "tools.service_layout", "tools.bedroom_designer",
            ):
                result.append({"path": path, "owner": owner,
                               "imported": imported, "reason": "SHARED_IMPORTS_ROOM"})
    return result


def scan(root: Path = ROOT) -> dict:
    files = {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
        for p in (root / "tools/rooms").rglob("*.py")
    }
    violations = ownership_violations(files)
    return {"result": "FAIL" if violations else "PASS",
            "files_scanned": len(files), "violations": violations,
            "scope": "NEW_ROOM_PACKAGES_ONLY",
            "legacy_migration_complete": False}


def main() -> int:
    result = scan()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
