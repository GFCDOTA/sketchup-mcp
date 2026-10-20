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
# Public compatibility paths still reach the same room implementations.
# Resolve them before checking boundaries so a facade cannot hide ownership.
LEGACY_ROOM_MODULES = {
    "tools.kitchen_layout": "tools.rooms.kitchen.layout",
    "tools.kitchen_validation": "tools.rooms.kitchen.anchor_rules",
    "tools.service_layout": "tools.rooms.service.layout",
    "interior.planners.living_room_planner": "tools.rooms.living.planner",
    **{f"tools.{name}_class": f"tools.rooms.living.{name}_class"
       for name in ("sofa", "rack", "coffee_table", "dining_table", "armchair")},
}


def collect_imports(source: str, *, module_name: str | None = None) -> set[str]:
    """Resolve static absolute AND relative imports without loading any module.

    `module_name` is the full dotted module path of the source file. The
    optional argument preserves the existing public collect_imports(source)
    contract for clients that only need absolute imports.
    """
    tree = ast.parse(source)
    imports: set[str] = set()
    package = module_name.split(".")[:-1] if module_name else []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            if not package or node.level > len(package) + 1:
                continue
            prefix = package[:len(package) - node.level + 1]
            if node.module:
                prefix += node.module.split(".")
            resolved = ".".join(prefix)
        else:
            resolved = node.module or ""
        if resolved:
            imports.add(resolved)
        # `from .. import bedroom` and `from tools import kitchen_layout`
        # import a module through an alias; a prefix-only scan misses both.
        if (node.module is None or resolved in {"tools", "tools.rooms", "interior.planners"}):
            imports.update(
                resolved + "." + alias.name if resolved else alias.name
                for alias in node.names if alias.name != "*"
            )
    return imports


def ownership_violations(files: dict[str, str]) -> list[dict]:
    """Check room implementations, including imports through legacy facades."""
    result = []
    for path, source in sorted(files.items()):
        parts = Path(path).parts
        if len(parts) < 4 or parts[:2] != ("tools", "rooms"):
            continue
        owner = parts[2]
        if owner not in ROOM_NAMES and owner != "shared":
            continue
        module_name = ".".join(Path(path).with_suffix("").parts)
        for imported in sorted(collect_imports(source, module_name=module_name)):
            canonical = imported
            for legacy, target in LEGACY_ROOM_MODULES.items():
                if imported == legacy or imported.startswith(legacy + "."):
                    canonical = target + imported[len(legacy):]
                    break
            chunks = canonical.split(".")
            if len(chunks) >= 3 and chunks[:2] == ["tools", "rooms"]:
                other = chunks[2]
                if other in ROOM_NAMES and other != owner:
                    reason = ("SHARED_IMPORTS_ROOM" if owner == "shared" and canonical != imported
                              else "CROSS_ROOM_DEPENDENCY")
                    result.append({"path": path, "owner": owner,
                                   "imported": imported, "reason": reason})
            elif (imported == "tools.furnish_apartment"
                  or imported.startswith("tools.furnish_apartment.")):
                result.append({"path": path, "owner": owner,
                               "imported": imported,
                               "reason": ("SHARED_IMPORTS_ROOM" if owner == "shared"
                                          else "ROOM_IMPORTS_ORCHESTRATOR")})
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
            "legacy_facades_checked": True,
            "legacy_migration_complete": False}


def main() -> int:
    result = scan()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
