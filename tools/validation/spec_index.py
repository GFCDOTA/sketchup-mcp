"""Redirecionamento das SPECs que saíram deste repositório.

As SPECs de produto moram em ``Plan2Space/engineering-specs`` (repositório privado), contrato de ownership v2
do ``claude-engineering-skills``. Este repo guarda só ``docs/specs/INDEX.md``: uma tabela
``| `caminho antigo` | `caminho em engineering-specs` |`` mais o SHA fixado.

Checadores de caminho usam :func:`resolves`: um caminho conta como válido se o arquivo existe **ou** se é uma
SPEC listada no índice. Caminho inventado continua falhando.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = "docs/specs/INDEX.md"
REPO = "Plan2Space/engineering-specs"

_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|")
_SHA = re.compile(r"\bSHA:\s*`([0-9a-f]{40})`")


@lru_cache(maxsize=8)
def _load(root: Path) -> tuple[dict[str, str], str | None]:
    index = root / INDEX
    if not index.exists():
        return {}, None
    moved: dict[str, str] = {}
    sha = None
    for line in index.read_text(encoding="utf-8").splitlines():
        m = _ROW.match(line)
        if m and m.group(1).endswith(".md"):
            moved[m.group(1)] = m.group(2)
        elif sha is None and (s := _SHA.search(line)):
            sha = s.group(1)
    return moved, sha


def moved_specs(root: Path = ROOT) -> dict[str, str]:
    """{caminho antigo neste repo: caminho em engineering-specs}."""
    return dict(_load(root.resolve())[0])


def pinned_sha(root: Path = ROOT) -> str | None:
    return _load(root.resolve())[1]


def is_moved(path: str, root: Path = ROOT) -> bool:
    return path.split("#", 1)[0].lstrip("./") in _load(root.resolve())[0]


def resolves(path: str, root: Path = ROOT) -> bool:
    """O caminho existe aqui ou é uma SPEC movida para engineering-specs."""
    target = path.split("#", 1)[0]
    return bool(target) and ((root / target).exists() or is_moved(target, root))


def spec_names(root: Path = ROOT) -> set[str]:
    """Nomes de arquivo das SPECs movidas (para labels ``spec:FP-NNN``)."""
    return {old.rsplit("/", 1)[-1] for old in _load(root.resolve())[0]}


def local_checkout(root: Path = ROOT) -> Path | None:
    """Clone local do engineering-specs: ``$ENGINEERING_SPECS_DIR`` ou ``<pai do repo>/engineering-specs``.

    O CI não tem acesso ao repo privado; aí retorna None e quem lê o texto da SPEC diz que pulou.
    """
    env = os.environ.get("ENGINEERING_SPECS_DIR")
    for cand in ([Path(env)] if env else []) + [root.resolve().parent / "engineering-specs"]:
        if (cand / "sketchup-mcp" / "README.md").is_file():
            return cand
    return None


def local_text(path: str, root: Path = ROOT) -> str | None:
    """Texto da SPEC movida, lido do clone local do engineering-specs (None se indisponível)."""
    new = _load(root.resolve())[0].get(path.split("#", 1)[0])
    base = local_checkout(root)
    if not new or base is None or not (base / new).is_file():
        return None
    return (base / new).read_text(encoding="utf-8")


def url(path: str, root: Path = ROOT) -> str | None:
    """Link fixado no SHA para a SPEC movida, ou None."""
    moved, sha = _load(root.resolve())
    new = moved.get(path.split("#", 1)[0])
    if not new or not sha:
        return None
    return f"https://github.com/{REPO}/blob/{sha}/{new}"
