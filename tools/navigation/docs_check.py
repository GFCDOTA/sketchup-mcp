"""Integridade da documentação de navegação (FP-043 P1).

Três verificações, todas fail-closed e sem importar o código descrito:

1. `check_links`: todo link relativo de um .md aponta para algo que existe (âncoras `#x` não são
   conferidas; links dentro de blocos de código e URLs externas são ignorados).
2. `check_states`: linha de tabela com o caminho entre crases e a coluna `existe`/`previsto`:
   `existe` exige o caminho presente; `previsto` exige AUSENTE. Assim a documentação não declara
   capacidade que não há e não esquece de atualizar quando ela nasce.
3. `check_routes`: cada rota de navegação (`docs/architecture/navigation_routes.v1.json`) parte do
   README, chega ao índice em até 3 cliques (cada salto é um link real do .md anterior), o índice
   cita as respostas, e cada resposta existe e contém o símbolo (ou, se `absent`, NÃO existe).

Uso: python -m tools.navigation.docs_check [--root .]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from tools.navigation.consumers import REPO

ROUTES_PATH = "docs/architecture/navigation_routes.v1.json"
MAX_HOPS = 3
_FENCE = re.compile(r"```.*?```", re.S)
_INLINE = re.compile(r"`[^`\n]*`")
_LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)")
_ROW_PATH = re.compile(r"^\s*`([^`]+)`\s*$")


def _strip_code(text: str) -> str:
    return _INLINE.sub("", _FENCE.sub("", text))


def links_of(md: Path) -> list[str]:
    """Alvos relativos (sem âncora/consulta) dos links de um .md."""
    out = []
    for target in _LINK.findall(_strip_code(md.read_text(encoding="utf-8"))):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith(("#", "/")):
            continue
        out.append(re.split(r"[#?]", target, maxsplit=1)[0])
    return [t for t in out if t]


def resolve_link(md: Path, target: str) -> Path:
    return (md.parent / target).resolve()


def check_links(files: list[Path]) -> list[str]:
    broken = []
    for md in files:
        for target in links_of(md):
            if not resolve_link(md, target).exists():
                broken.append(f"{md.name}: {target}")
    return broken


def state_rows(md: Path) -> list[tuple[str, str]]:
    rows = []
    for line in md.read_text(encoding="utf-8").splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        m = _ROW_PATH.match(cells[0]) if cells else None
        state = next((c.lower() for c in cells[1:] if c.lower() in ("existe", "previsto")), None)
        if m and state:
            rows.append((m.group(1), state))
    return rows


def check_states(files: list[Path], root: Path = REPO) -> list[str]:
    wrong = []
    for md in files:
        for path, state in state_rows(md):
            present = (root / path.rstrip("/")).exists()
            if state == "existe" and not present:
                wrong.append(f"{md.name}: `{path}` declarado 'existe' mas ausente")
            if state == "previsto" and present:
                wrong.append(f"{md.name}: `{path}` declarado 'previsto' mas já existe (atualize o estado)")
    return wrong


def _has_symbol(text: str, symbol: str) -> bool:
    s = re.escape(symbol)
    return bool(re.search(rf"(^|\n)\s*(def|class|async def)\s+{s}\b|(^|\n)\s*{s}\s*[:=]|\"id\"\s*:\s*\"{s}\"|(^|\n)#+\s*{s}\b", text))


def _cited(index_md: Path, target: str, text: str, root: Path) -> bool:
    """O índice cita o caminho inteiro ou o caminho relativo à pasta dele (link relativo)."""
    full = target.rstrip("/")
    rel = Path(os.path.relpath(root / full, index_md.parent)).as_posix()
    return full in text or rel in text


def check_routes(doc: dict, root: Path = REPO) -> list[str]:
    errors = []
    if doc.get("schema_version") != "fp043_navigation_routes.v1" or not isinstance(doc.get("routes"), list):
        return ["INVALID_SCHEMA"]
    start = doc.get("start", "README.md")
    ids = [r.get("id") for r in doc["routes"]]
    errors += [f"DUPLICATE_ROUTE: {i}" for i in set(ids) if ids.count(i) > 1]
    for r in doc["routes"]:
        rid = r.get("id", "?")
        hops = r.get("hops") or []
        if not hops or hops[0] != start:
            errors.append(f"{rid}: a rota deve partir de {start}")
            continue
        if len(hops) - 1 > MAX_HOPS:
            errors.append(f"{rid}: {len(hops) - 1} cliques (máximo {MAX_HOPS})")
        for a, b in zip(hops, hops[1:]):
            md = root / a
            if not md.exists():
                errors.append(f"{rid}: salto {a} inexistente")
                break
            if (root / b).resolve() not in {resolve_link(md, t) for t in links_of(md)}:
                errors.append(f"{rid}: {a} não tem link para {b}")
        index_md = root / hops[-1]
        if not index_md.exists():
            errors.append(f"{rid}: índice {hops[-1]} inexistente")
            continue
        index_text = index_md.read_text(encoding="utf-8")
        for ans in r.get("answers", []):
            p = root / ans["path"]
            if not _cited(index_md, ans["path"], index_text, root):
                errors.append(f"{rid}: índice {hops[-1]} não cita {ans['path']}")
            if not p.exists():
                errors.append(f"{rid}: resposta {ans['path']} inexistente")
            elif ans.get("symbol") and p.is_file() and not _has_symbol(p.read_text(encoding="utf-8", errors="replace"), ans["symbol"]):
                errors.append(f"{rid}: símbolo {ans['symbol']} ausente em {ans['path']}")
        for ab in r.get("absent", []):
            if (root / ab["path"]).exists():
                errors.append(f"{rid}: {ab['path']} era declarado ausente mas existe (atualize a rota)")
            if not _cited(index_md, ab["path"], index_text, root):
                errors.append(f"{rid}: índice {hops[-1]} não explica a ausência de {ab['path']}")
    return errors


def doc_files(root: Path = REPO) -> list[Path]:
    files = [root / "README.md"]
    files += sorted((root / "docs/architecture").glob("*.md"))
    files += sorted(root.glob("tools/rooms/*/README.md"))
    return [f for f in files if f.exists()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Integridade da documentação de navegação")
    ap.add_argument("--root", default=str(REPO))
    root = Path(ap.parse_args(argv).root).resolve()
    files = doc_files(root)
    routes = root / ROUTES_PATH
    result = {
        "files": [f.relative_to(root).as_posix() for f in files],
        "broken_links": check_links(files),
        "wrong_states": check_states(files, root),
        "route_errors": check_routes(json.loads(routes.read_text(encoding="utf-8")), root) if routes.exists() else ["ROUTES_MISSING"],
    }
    result["result"] = "PASS" if not (result["broken_links"] or result["wrong_states"] or result["route_errors"]) else "FAIL"
    print(json.dumps(result, indent=1, ensure_ascii=False))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
