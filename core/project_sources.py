"""Fonte identificada de cada projeto — onde mora o PDF da planta (FP-043 P2).

Um ÚNICO ponto resolve o caminho do PDF. Antes, oito módulos montavam `REPO / f"{planta}.pdf"` cada um por
conta própria; mover o arquivo exigiria achar cada f-string à mão (a busca por `planta_74.pdf` não as vê).

O PDF é a verdade geométrica do apartamento: este módulo só resolve o caminho, nunca lê nem copia o arquivo,
e não existe cópia de fallback (um caminho só = nenhuma cópia divergente possível).
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Local do PDF relativo à raiz do repositório. Passo 1 (este): ainda na raiz, comportamento idêntico ao anterior.
PLANT_PDF_TEMPLATE = "{plant}.pdf"


def plant_pdf_path(plant: str, repo: Path | None = None) -> Path:
    """Caminho (existente ou não) do PDF da `plant`. `repo` permite apontar para outra raiz (testes)."""
    if not plant or "/" in plant or "\\" in plant or plant.startswith("."):
        raise ValueError(f"nome de planta inválido: {plant!r}")
    return (repo if repo is not None else REPO_ROOT) / PLANT_PDF_TEMPLATE.format(plant=plant)
