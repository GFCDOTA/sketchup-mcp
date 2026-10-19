"""Quem consome um item do repositório.

Por que não só `grep`: dependência também mora em string (`-m tools.x`, `-RubyStartup
tools/x.rb`, `ROOT / "tools" / "x.rb"`, YAML do CI, README). Aqui juntam-se duas fontes
sobre a ÁRVORE RASTREADA (`git ls-files`):

1. imports Python por AST (`import a.b`, `from a.b import c` → também `a.b.c`);
2. referências em texto: caminho (`/` e `\\`), módulo pontuado e nome do arquivo com
   extensão quando aparece isolado (`python foo.py`, `-RubyStartup foo.rb`).

Limite assumido (e dito no relatório): caminho montado dinamicamente (por exemplo o PDF da
planta, montado com f-string antes de `core.project_sources`) não aparece. Por isso o mapa marca `dynamic_path_risk` onde isso
é conhecido e cada PR de movimento revisa o item à mão antes de mover.

Uso: python -m tools.navigation.consumers <item> [<item> ...] [--json]
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEXT_EXT = frozenset({".py", ".rb", ".md", ".json", ".yml", ".yaml", ".toml", ".ps1", ".cmd",
                      ".sh", ".txt", ".cfg", ".ini", ".html", ".js", ".css", ".jsonl", ""})
MAX_BYTES = 3_000_000
SCOPE_ROOTS = ("tools", "scripts", "ops", "interior")


def tracked_files(root: Path = REPO) -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    return [p for p in raw.decode("utf-8").split("\0") if p]


def scope_items(files: list[str]) -> list[str]:
    """Itens classificáveis: arquivo da raiz; arquivo direto de tools/scripts/ops/interior;
    e cada subdiretório dessas pastas como UMA unidade (`tools/rooms/`)."""
    items: list[str] = []
    seen: set[str] = set()
    for p in files:
        parts = p.split("/")
        if len(parts) == 1:
            item = p
        elif parts[0] in SCOPE_ROOTS:
            item = p if len(parts) == 2 else "/".join(parts[:2]) + "/"
        else:
            continue
        if item not in seen:
            seen.add(item)
            items.append(item)
    return items


def group_of(path: str) -> str:
    if path.startswith("tests/"):
        return "tests"
    if path.startswith(".github/"):
        return "ci"
    if path == "pyproject.toml" or path.startswith("docker-compose") or path.endswith("Dockerfile.dashboard"):
        return "config"
    if path.startswith("tools/mcp_server/"):
        return "mcp"
    if path.startswith(("tools/", "core/", "interior/", "scripts/", "ops/")):
        return "code"
    if path.startswith(("docs/archive/", "artifacts/_archive/")):
        return "history"
    if (path.startswith(("docs/", ".claude/", ".ai_bridge/", "README", "CLAUDE", "HANDOFF", "KICKOFF"))
            or path.endswith(".md")):
        return "docs"
    return "data"


class Corpus:
    """Árvore rastreada carregada uma vez: textos + índice de imports Python."""

    def __init__(self, root: Path = REPO, files: list[str] | None = None):
        self.root = root
        self.files = files if files is not None else tracked_files(root)
        self.texts: dict[str, str] = {}
        for p in self.files:
            f = root / p
            if f.suffix.lower() in TEXT_EXT and f.is_file() and f.stat().st_size < MAX_BYTES:
                try:
                    self.texts[p] = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
        self.imports: dict[str, set[str]] = defaultdict(set)
        for p, text in self.texts.items():
            if not p.endswith(".py"):
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.imports[alias.name].add(p)
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    self.imports[node.module].add(p)
                    for alias in node.names:
                        self.imports[f"{node.module}.{alias.name}"].add(p)

    def consumers(self, item: str) -> dict[str, list[str]]:
        own = item.rstrip("/")
        is_dir = item.endswith("/")
        tokens = {item, item.replace("/", "\\")}
        modules: set[str] = set()
        if item.endswith(".py"):
            mod = item[:-3].replace("/", ".")
            modules.add(mod[: -len(".__init__")] if mod.endswith(".__init__") else mod)
        elif is_dir:
            modules.add(own.replace("/", "."))
        # módulo de um componente só (`interior`) é genérico demais para busca em texto: só vale por import (AST)
        tokens |= {m for m in modules if "." in m}
        if is_dir and "." in own.replace("/", "."):
            tokens |= {own.replace("/", ".") + "."}
        hit: dict[str, set[str]] = defaultdict(set)

        def outside(p: str) -> bool:
            return p != own and not p.startswith(own + "/")

        for p, text in self.texts.items():
            if outside(p) and any(tok and tok in text for tok in tokens):
                hit[group_of(p)].add(p)
        for mod in modules:
            for key, importers in self.imports.items():
                if key == mod or key.startswith(mod + "."):
                    for p in importers:
                        if outside(p):
                            hit[group_of(p)].add(p)
        base = Path(own).name
        if "." in base and not is_dir:
            found = {p for s in hit.values() for p in s}
            pat = re.compile(r"(?<![\w./\\-])" + re.escape(base) + r"(?!\w)")
            for p, text in self.texts.items():
                if outside(p) and p not in found and pat.search(text):
                    hit[group_of(p)].add(p)
        return {g: sorted(v) for g, v in sorted(hit.items())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Quem consome um item do repositório")
    ap.add_argument("items", nargs="+")
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv)
    corpus = Corpus()
    result = {i: corpus.consumers(i) for i in ns.items}
    if ns.json:
        print(json.dumps(result, indent=1, ensure_ascii=False))
    else:
        for item, groups in result.items():
            print(f"{item}: " + (", ".join(f"{g}={len(v)}" for g, v in groups.items()) or "nenhum consumidor"))
            for g, v in groups.items():
                for p in v[:12]:
                    print(f"  [{g}] {p}")
                if len(v) > 12:
                    print(f"  [{g}] … +{len(v) - 12}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
