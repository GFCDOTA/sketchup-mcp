"""Resolução da raiz do workspace — fonte ÚNICA de verdade.

REPO_ROOT      = o dir do repo  (E:\\Claude\\apps\\sketchup-mcp).
WORKSPACE_ROOT = a raiz do workspace (E:\\Claude). Robusto ao repo estar
                 aninhado em apps/ (consolidação 2026-06-09) OU flat na raiz (legado).
WORKTREES_ROOT = onde as git worktrees temporárias vivem (E:\\Claude\\worktrees).

Resolução, em ordem:
  1) env CLAUDE_WORKSPACE_ROOT (override explícito);
  2) sobe de REPO_ROOT até o ancestral que contém apps/ E ops/ (o marcador do workspace);
  3) fallback legado: REPO_ROOT.parent (repo era filho direto da raiz).
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve_workspace_root(repo_root: Path = REPO_ROOT) -> Path:
    env = os.environ.get("CLAUDE_WORKSPACE_ROOT")
    if env:
        return Path(env).resolve()
    for cand in (repo_root, *repo_root.parents):
        if (cand / "apps").is_dir() and (cand / "ops").is_dir():
            return cand
    return repo_root.parent  # layout flat legado (repo direto na raiz)


WORKSPACE_ROOT = resolve_workspace_root()
WORKTREES_ROOT = WORKSPACE_ROOT / "worktrees"


def iter_workspace_repos(workspace_root: Path = WORKSPACE_ROOT) -> "list[Path]":
    """Repos/worktrees git do workspace. Robusto ao layout aninhado (filhos de apps/ e
    worktrees/) E ao legado (filhos diretos da raiz). Retorna os Paths que contêm .git."""
    out: "list[Path]" = []
    seen = set()
    for base in (workspace_root / "apps", workspace_root / "worktrees", workspace_root):
        if not base.is_dir():
            continue
        try:
            children = sorted(base.iterdir())
        except OSError:
            continue
        for p in children:
            if not p.is_dir():
                continue
            try:
                key = p.resolve()
            except OSError:
                continue
            if key in seen or not (p / ".git").exists():
                continue
            seen.add(key)
            out.append(p)
    return out
