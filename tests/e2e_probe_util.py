"""Utilitario DESCARTAVEL da sonda E2E do executor local (Issue #589). NAO e codigo de producao; nada o importa fora de tests/."""
from __future__ import annotations


def slugify(text: str) -> str:
    return text.strip().replace(" ", "-")
