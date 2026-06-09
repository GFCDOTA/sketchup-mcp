"""repo_health_gate.py — gate determinístico de higiene de estrutura do repo.

Impede regressão da organização (chore/repo-folder-hygiene 2026-06-08). Checa só o
que dá pra checar ESTATICAMENTE sobre os arquivos TRACKED + o working tree:

1. `.md` solto no root só se estiver na allowlist (CLAUDE/README/COGNITIVE).
2. nenhum `.skp` TRACKED em `runs/` (runs é scratch gitignored; evidência vai p/
   artifacts/review|canonical — regra 7).
3. nenhum worktree DENTRO do repo (arquivo `.git` em subpasta = worktree aninhado).
4. todo dir de `artifacts/review/**` que tem `.skp`/`.png` precisa de um report
   (`.json` ou `.md`) no mesmo dir (artifact reviewável sem report = cego).
5. FONTE ÚNICA DE ESCALA: só `core/scale.py` pode DEFINIR `PT_TO_M`/`PT_TO_IN` (nível
   de módulo) ou conter o literal `0.19/5.4`. Qualquer outro `.py` deve IMPORTAR de
   `core.scale`. (Mata a doença de múltiplas fontes de verdade — Felipe 2026-06-08.)

Uso:  python tools/repo_health_gate.py        (exit 1 se violar)
Tb roda como pytest (test_repo_health).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROOT_MD_ALLOWLIST = {"CLAUDE.md", "README.md", "CLAUDE_COGNITIVE_ARCHITECTURE.md"}
_SKIP_DIRS = (".venv", "node_modules", ".git", ".pytest_cache")
_SCALE_SOURCE = "core/scale.py"                      # único arquivo que pode definir escala
_SCALE_DEF = re.compile(r"^(PT_TO_M|PT_TO_IN)\s*=")   # def nível-módulo (coluna 0)
_SCALE_LITERAL = re.compile(r"0\.19\s*/\s*5\.4")      # o anchor mágico pt->m


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]


def violations() -> list[tuple[str, str]]:
    v: list[tuple[str, str]] = []
    files = _tracked()

    # 1. root .md allowlist
    for f in files:
        if "/" not in f and f.lower().endswith(".md") and f not in ROOT_MD_ALLOWLIST:
            v.append(("ROOT_MD_NOT_ALLOWLISTED", f))

    # 2. .skp tracked em runs/
    for f in files:
        if f.startswith("runs/") and f.lower().endswith(".skp"):
            v.append(("SKP_TRACKED_IN_RUNS", f))

    # 3. worktree aninhado (.git em subpasta, fora de venv/node_modules)
    for p in ROOT.rglob(".git"):
        rel = p.relative_to(ROOT)
        if any(part in _SKIP_DIRS for part in rel.parts[:-1]):
            continue
        if p.parent != ROOT:                     # root .git é o legítimo
            v.append(("NESTED_WORKTREE", str(rel)))

    # 4. cada ARTIFACT top-level em artifacts/review/<plant>/<artifact>/ que tem
    #    .skp/.png (em qualquer nivel) precisa de report (.json/.md) em qualquer nivel.
    #    Allowlist de legacy report-less (pre-hygiene; não backfillar artifact antigo).
    rev = ROOT / "artifacts" / "review"
    legacy_ok = {"_preview"}   # montages/preview sem report por design
    if rev.exists():
        for plant in rev.iterdir():
            if not plant.is_dir():
                continue
            for art in plant.iterdir():
                if not art.is_dir() or art.name in legacy_ok:
                    continue
                has_media = any(art.rglob("*.skp")) or any(art.rglob("*.png"))
                if not has_media:
                    continue
                has_report = any(art.rglob("*.json")) or any(art.rglob("*.md"))
                if not has_report:
                    v.append(("REVIEW_ARTIFACT_SEM_REPORT", str(art.relative_to(ROOT))))

    # 5. fonte ÚNICA de escala: só core/scale.py define PT_TO_M/PT_TO_IN ou o literal 0.19/5.4
    for f in files:
        if not f.endswith(".py"):
            continue
        fp = f.replace("\\", "/")
        # core/scale.py DEFINE a escala; o próprio gate DOCUMENTA a regra (menciona o literal).
        if fp in (_SCALE_SOURCE, "tools/repo_health_gate.py") or "/tests/" in fp or "test_" in Path(fp).name:
            continue
        try:
            lines = (ROOT / f).read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            code = line.split("#", 1)[0]                 # ignora comentários
            if _SCALE_DEF.match(code):
                v.append(("SCALE_DEF_FORA_DO_CORE", f"{f}:{i}"))
            elif _SCALE_LITERAL.search(code):
                v.append(("SCALE_LITERAL_FORA_DO_CORE", f"{f}:{i}"))
    return v


def main() -> int:
    v = violations()
    if not v:
        print("repo_health_gate: PASS (0 violações)")
        return 0
    print(f"repo_health_gate: FAIL ({len(v)} violações)")
    for kind, what in v:
        print(f"  [{kind}] {what}")
    return 1


def test_repo_health():
    v = violations()
    assert v == [], f"violações de higiene: {v}"


if __name__ == "__main__":
    sys.exit(main())
