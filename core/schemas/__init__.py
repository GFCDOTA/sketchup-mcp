"""Contratos JSON Schema do dominio (FP-044/F3) - o UNICO lugar que sabe onde os schemas vivem.

    from core.schemas import SCHEMA_DIR, load, schema_path

`root` existe para quem valida uma copia do repositorio (testes em diretorio temporario): o caminho relativo a raiz
continua decidido aqui, nunca por string espalhada no chamador.
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent
SCHEMA_REL = Path("core/schemas")


def schema_path(name: str, root: Path | None = None) -> Path:
    """Caminho do schema `name` (ex.: "visual_findings.schema.json"); com `root`, dentro daquela raiz."""
    return (Path(root) / SCHEMA_REL / name) if root is not None else SCHEMA_DIR / name


def load(name: str, root: Path | None = None) -> dict:
    """Le e devolve o schema `name` como dict (UTF-8)."""
    return json.loads(schema_path(name, root).read_text(encoding="utf-8"))
