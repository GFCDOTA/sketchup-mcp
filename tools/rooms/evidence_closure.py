"""R-18 transitivo (T0.1): fecho estatico dos simbolos provados e o digest desse fecho.

`capability_catalog.symbol_digest` cobre so o corpo da funcao listada; mudar um helper que ela chama (ex.:
`assembly.build_parts`, a geometria do gabinete) mantinha a prova L2 antiga. Aqui o fecho de um simbolo Python e o
conjunto de funcoes/classes/constantes de topo de `tools.rooms`/`core` alcancadas por NOME a partir dele (chamada local,
`from x import y`, alias de modulo `m.f`, import relativo e re-export de pacote). O digest do fecho junta o texto
normalizado de cada membro (mesma normalizacao do `symbol_digest`: sem linhas em branco nem comentario).

Fora do escopo, de proposito: `tools.sketchup.*` (executor/processo — falha alto e tem bateria L2 propria),
stdlib e terceiros, e despacho dinamico (`getattr`, metodos via `self`). Ruby segue com digest do arquivo inteiro.

Uso:
    python -m tools.rooms.evidence_closure --explain python:<mod.simbolo>
    python -m tools.rooms.evidence_closure --backfill [--write]
`--backfill` calcula o fecho de cada evidencia L2 NO COMMIT DA PROVA (git) e no HEAD; so grava quando os dois casam
(a prova de fato exercitou esse codigo). Divergencia = prova velha: revogar e refazer o L2 (skill capability-l2-proof).
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = "tools/rooms/capability_catalog.v1.json"
SCOPE = ("tools.rooms", "core")


def in_scope(module: str) -> bool:
    return any(module == p or module.startswith(p + ".") for p in SCOPE)


class WorktreeSource:
    """Codigo como esta no disco."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def read(self, rel: str) -> str | None:
        path = self.root / rel
        return path.read_text(encoding="utf-8") if path.is_file() else None


class GitSource:
    """Codigo de um commit (o da evidencia), sem checkout."""

    def __init__(self, root: Path, commit: str):
        self.root, self.commit = Path(root), commit
        self._cache: dict[str, str | None] = {}

    def read(self, rel: str) -> str | None:
        if rel not in self._cache:
            try:
                self._cache[rel] = subprocess.check_output(
                    ["git", "-C", str(self.root), "show", f"{self.commit}:{rel}"], text=True, encoding="utf-8",
                    stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                self._cache[rel] = None
        return self._cache[rel]


class _Module:
    """Membros de topo (nome -> no) e imports (nome local -> (modulo, atributo|None)) de um modulo."""

    def __init__(self, name: str, rel: str, text: str):
        self.name, self.text = name, text.replace("\r\n", "\n").replace("\r", "\n")
        tree = ast.parse(self.text)
        package = name if rel.endswith("__init__.py") else name.rpartition(".")[0]
        self.members: dict[str, ast.AST] = {}
        self.imports: dict[str, tuple[str, str | None]] = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.members[node.name] = node
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Name):
                        self.members[t.id] = node
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parts = package.split(".")
                    parent = ".".join(parts[:len(parts) - (node.level - 1)])
                    base = f"{parent}.{base}" if base else parent
                for alias in node.names:
                    self.imports[alias.asname or alias.name] = (base, alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        self.imports[alias.asname] = (alias.name, None)
                    else:
                        top = alias.name.split(".")[0]
                        self.imports[top] = (top, None)

    def member_text(self, name: str) -> str:
        node = self.members[name]
        first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        lines = self.text.split("\n")[first - 1:node.end_lineno]
        return "\n".join(ln.rstrip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#"))


class _Resolver:
    def __init__(self, source):
        self.source = source
        self._mods: dict[str, _Module | None] = {}

    def module(self, name: str) -> _Module | None:
        if name not in self._mods:
            self._mods[name] = None
            base = name.replace(".", "/")
            for rel in (base + ".py", base + "/__init__.py"):
                text = self.source.read(rel)
                if text is not None:
                    self._mods[name] = _Module(name, rel, text)
                    break
        return self._mods[name]

    def is_module(self, name: str) -> bool:
        return in_scope(name) and self.module(name) is not None

    def resolve(self, module: str, name: str, depth: int = 0) -> tuple[str, str] | None:
        """Onde `module.name` e definido de fato (segue re-export `from .x import y` ate 8 saltos)."""
        if depth > 8 or not in_scope(module):
            return None
        mod = self.module(module)
        if mod is None:
            return None
        if name in mod.members:
            return module, name
        if name in mod.imports:
            target, attr = mod.imports[name]
            if attr is not None and not self.is_module(f"{target}.{attr}"):
                return self.resolve(target, attr, depth + 1)
        return None

    def module_alias(self, mod: _Module, local: str) -> str | None:
        """Nome local que aponta para um MODULO em escopo (`import a.b as m`, `from a import b`)."""
        if local not in mod.imports:
            return None
        target, attr = mod.imports[local]
        dotted = target if attr is None else f"{target}.{attr}"
        return dotted if self.is_module(dotted) else None

    def references(self, module: str, name: str) -> set[tuple[str, str]]:
        mod = self.module(module)
        out: set[tuple[str, str]] = set()
        for node in ast.walk(mod.members[name]):
            if isinstance(node, ast.Name):
                if node.id in mod.members and node.id != name:
                    out.add((module, node.id))
                elif node.id in mod.imports and self.module_alias(mod, node.id) is None:
                    target, attr = mod.imports[node.id]
                    found = self.resolve(target, attr) if attr is not None else None
                    if found:
                        out.add(found)
            elif isinstance(node, ast.Attribute):
                chain, base = [node.attr], node.value
                while isinstance(base, ast.Attribute):
                    chain.append(base.attr)
                    base = base.value
                if not isinstance(base, ast.Name):
                    continue
                dotted = self.module_alias(mod, base.id)
                if dotted is None:
                    continue
                for attr in reversed(chain):                    # desce em submodulos: m.sub.f
                    if self.is_module(f"{dotted}.{attr}"):
                        dotted = f"{dotted}.{attr}"
                        continue
                    found = self.resolve(dotted, attr)
                    if found:
                        out.add(found)
                    break
        return out


def _split(ref: str, resolver: _Resolver) -> tuple[str, str] | None:
    parts = ref.split(".")
    for cut in range(len(parts) - 1, 0, -1):
        module = ".".join(parts[:cut])
        if resolver.module(module) is not None:
            found = resolver.resolve(module, parts[cut])
            if found is not None:
                return found
    return None


def _members(ref: str, resolver: _Resolver) -> list[tuple[str, str]]:
    """BFS sobre referencias por nome: O(membros + arestas); cada modulo e lido e parseado uma vez por resolver."""
    root = _split(ref, resolver)
    if root is None:
        return []
    seen, todo = {root}, [root]
    while todo:
        for nxt in resolver.references(*todo.pop()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return sorted(seen)


def closure(ref: str, source) -> list[str]:
    """Membros (`modulo.nome`) alcancados a partir de `ref`, ordenados. Vazio se `ref` nao existe."""
    return [f"{m}.{n}" for m, n in _members(ref, _Resolver(source))]


def closure_digest(ref: str, source) -> str | None:
    resolver = _Resolver(source)
    members = _members(ref, resolver)
    if not members:
        return None
    h = hashlib.sha256()
    for module, name in members:
        text = resolver.module(module).member_text(name)
        h.update(f"{module}.{name}".encode("utf-8") + b"\n" + text.encode("utf-8") + b"\n\x00\n")
    return h.hexdigest()


def current_closure_digest(key: str, root: Path = ROOT) -> str | None:
    """Digest do fecho de `python:<ref>` no disco (o que o gate do catalogo compara)."""
    lang, _, ref = key.partition(":")
    return closure_digest(ref, WorktreeSource(root)) if lang == "python" else None


def backfill(catalog: dict, root: Path = ROOT) -> dict:
    """Preenche `closure_digests` das evidencias L2 SO quando commit da prova e HEAD casam. Altera `catalog` in-place."""
    head = WorktreeSource(root)
    report: dict = {"written": [], "unchanged": [], "mismatch": []}
    pending: list[tuple[dict, dict]] = []
    for cap in catalog["capabilities"]:
        if cap["validation"]["state"] != "L2_PASS":
            continue
        for ev in cap["validation"]["evidence"]:
            at_commit = GitSource(root, ev["commit"])
            digests = {}
            for key in ev["symbol_digests"]:
                lang, _, ref = key.partition(":")
                if lang != "python":
                    continue
                old, now = closure_digest(ref, at_commit), closure_digest(ref, head)
                if old is None or old != now:
                    report["mismatch"].append({"capability": cap["id"], "commit": ev["commit"], "symbol": key})
                digests[key] = now
            pending.append((ev, digests))
    if report["mismatch"]:
        return report                                            # nada e gravado se uma prova estiver velha
    for ev, digests in pending:
        if ev.get("closure_digests") == digests:
            report["unchanged"].append(ev["ref"])
        else:
            ev["closure_digests"] = digests
            report["written"].append(ev["ref"])
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--explain", metavar="python:REF")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--write", action="store_true", help="com --backfill: grava no catalogo")
    args = ap.parse_args(argv)
    if args.explain:
        ref = args.explain.partition(":")[2] or args.explain
        members = closure(ref, WorktreeSource(ROOT))
        print(json.dumps({"ref": ref, "members": members, "digest": closure_digest(ref, WorktreeSource(ROOT))}, indent=1))
        return 0 if members else 1
    if args.backfill:
        path = ROOT / CATALOG
        raw = path.read_bytes().decode("utf-8")
        catalog = json.loads(raw)
        report = backfill(catalog, ROOT)
        print(json.dumps(report, indent=1, ensure_ascii=False))
        if report["mismatch"]:
            return 1
        if args.write and report["written"]:
            nl = "\r\n" if "\r\n" in raw else "\n"
            path.write_bytes((json.dumps(catalog, indent=2, ensure_ascii=False) + "\n").replace("\n", nl).encode("utf-8"))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
