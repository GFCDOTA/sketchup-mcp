"""FP-044 — a raiz e `tools/*.py` so ENCOLHEM: nenhuma pasta nova na raiz e nenhum arquivo solto novo em `tools/`.

A allowlist reflete o estado de `develop` @ 4840ef0 (FP-044 spec). Cada fatia (F2..F6) remove as suas linhas no mesmo PR;
adicionar uma entrada exige uma decisao deliberada (editar este arquivo e justificar no PR).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Entradas versionadas da raiz hoje. Alvo final (FP-044 §6): sem ops/ scripts/ .impeccable/ (configs/ renders/ textures/ sairam na F2; schemas/ na F3).
ROOT_ALLOWED = {
    # arquivos do projeto
    ".dockerignore", ".gitattributes", ".gitignore", "CLAUDE.md", "README.md", "docker-compose.rag.yml",
    "pyproject.toml", "uv.lock",   # docker-compose.yml (dashboard morto) arquivado em 2026-10-22 (D-002)
    # pastas com papel claro
    ".ai_bridge", ".claude", ".github", "artifacts", "assets", "core", "docs", "fixtures", "interior", "projects",
    "references", "tests", "tools",
    # pastas a aposentar nas fatias indicadas (remover a linha no PR da fatia)
    ".impeccable",   # F5 (D-008)
    "ops",           # F4 (D-009)
    # "scripts" saiu em 2026-10-22 (D-005): set_clipboard_image.ps1 foi para tools/oracle/
}
FACADES = ROOT / "docs/specs/fp044_tools_facades.v1.json"


def _tracked() -> list[str]:
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    return [f for f in out if f]


def test_raiz_nao_cresce():
    entries = {f.split("/")[0] for f in _tracked()}
    novas = sorted(entries - ROOT_ALLOWED)
    assert novas == [], f"entradas novas na raiz sem decisao (FP-044 guard): {novas}"


def test_allowlist_nao_guarda_entrada_que_ja_sumiu():
    """A allowlist encolhe junto com a raiz: entrada que nao existe mais tem de sair daqui (senao o guard 'afrouxa' sozinho)."""
    entries = {f.split("/")[0] for f in _tracked()}
    obsoletas = sorted(ROOT_ALLOWED - entries)
    assert obsoletas == [], f"remova da ROOT_ALLOWED: {obsoletas}"


def test_tools_soltos_so_encolhem():
    manifest = json.loads(FACADES.read_text("utf-8"))
    allowed = {e["path"] for e in manifest["entries"] if e["action"] != "REMOVED"}
    soltos = {f for f in _tracked() if f.startswith("tools/") and f.count("/") == 1 and f.endswith(".py")}
    novos = sorted(soltos - allowed)
    assert novos == [], f"arquivos novos soltos em tools/ (FP-044 guard): {novos}"
    fantasmas = sorted(p for p in allowed - soltos)
    assert fantasmas == [], f"marque como REMOVED no fp044_tools_facades.v1.json: {fantasmas}"
