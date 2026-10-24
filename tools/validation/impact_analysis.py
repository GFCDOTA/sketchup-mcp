"""impact_analysis.py — o que uma mudanca afeta: SPECs, Issues abertas, testes e consumidores (FP-057 P3).

Mudanca de contrato nao reescreve todas as SPECs: lista SO as que citam o arquivo/modulo, os modulos que o importam
(consumidores) e as Issues abertas que o mencionam. Puro sobre `files` ({caminho: texto}); `from_git()` monta o mapa do checkout.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

CONTRACT_HINTS = ("core/pipeline_contracts.py", "core/constraint_result.py", "core/functional_constraints.py", "core/plan_frame.py",
                  "core/spatial_semantics.py", "docs/governance/known_gaps.json", "docs/governance/review_policy.json",
                  "tools/rooms/capability_catalog.v1.json")


@dataclass
class Impact:
    changed: list[str]
    contract_change: bool = False
    specs: list[str] = field(default_factory=list)
    consumers: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    issues: list[int] = field(default_factory=list)

    def summary(self) -> str:
        return (f"{len(self.changed)} arquivo(s); contrato={'SIM' if self.contract_change else 'nao'}; specs={self.specs}; "
                f"consumidores={len(self.consumers)}; testes={len(self.tests)}; issues={self.issues}")


def module_name(path: str) -> str | None:
    return path[:-3].replace("/", ".") if path.endswith(".py") else None


def importers(target: str, files: dict[str, str]) -> list[str]:
    """Arquivos .py que importam o modulo `target` (caminho .py), por `import a.b`, `from a.b import`, `from a import b`."""
    mod = module_name(target)
    if not mod:
        return []
    pkg, _, leaf = mod.rpartition(".")
    pats = [re.compile(rf"^\s*(?:from|import)\s+{re.escape(mod)}\b", re.M)]
    if pkg:
        pats.append(re.compile(rf"^\s*from\s+{re.escape(pkg)}\s+import\s+[^\n]*\b{re.escape(leaf)}\b", re.M))
    return sorted(p for p, text in files.items() if p != target and p.endswith(".py") and any(r.search(text) for r in pats))


def analyze(changed: list[str], files: dict[str, str], issues: list[dict] | None = None) -> Impact:
    imp = Impact(changed=sorted(changed))
    imp.contract_change = any(c in CONTRACT_HINTS or c.startswith("core/schemas/") or (c.startswith("docs/specs/") and c.endswith(".md")) for c in changed)
    cons: set[str] = set()
    for c in changed:
        cons.update(importers(c, files))
    imp.consumers = sorted(x for x in cons if not x.startswith("tests/") and x not in changed)
    imp.tests = sorted(x for x in cons if x.startswith("tests/"))
    for path, text in sorted(files.items()):
        if path.startswith("docs/specs/FP-") and path.endswith(".md") and any(f"`{c}`" in text or c in text for c in changed):
            imp.specs.append(path)
    names = {c for c in changed} | {m for c in changed if (m := module_name(c))}
    imp.issues = sorted(i["number"] for i in (issues or []) if i.get("state") == "OPEN"
                        and any(n in (i.get("body") or "") or n in (i.get("title") or "") for n in names))
    return imp


def from_git(root: Path, changed: list[str]) -> dict[str, str]:
    """Texto dos arquivos versionados relevantes (.py, SPECs e relatorios) — so leitura."""
    out = subprocess.run(["git", "ls-files", "*.py", "docs/specs/*.md"], cwd=root, capture_output=True, text=True).stdout.split()
    return {p: (root / p).read_text(encoding="utf-8", errors="replace") for p in out if (root / p).exists()}
