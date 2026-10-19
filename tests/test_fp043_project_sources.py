"""FP-043/P2 — o PDF da planta tem UM resolvedor de caminho (core.project_sources).

Antes, oito módulos montavam `REPO / f"{planta}.pdf"`; a busca por `planta_74.pdf` não os via, e mover o arquivo
quebraria cada um em silêncio. Aqui: o contrato do resolvedor e a trava que impede f-strings novas.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from core.project_sources import PLANT_PDF_TEMPLATE, plant_pdf_path

ROOT = Path(__file__).resolve().parents[1]
RESOLVEDOR = "core/project_sources.py"
# `... / f"{x}.pdf"` ou `... / f"{x}" / ...pdf` montado à mão
FSTRING_PDF = re.compile(r"""f["'][^"'\n]*\{[^}]+\}[^"'\n]*\.pdf["']""")


def test_resolvedor_devolve_o_caminho_da_planta_na_raiz_informada(tmp_path):
    assert plant_pdf_path("planta_74", tmp_path) == tmp_path / PLANT_PDF_TEMPLATE.format(plant="planta_74")
    assert plant_pdf_path("planta_74").name == "planta_74.pdf"
    assert plant_pdf_path("planta_74").is_absolute()


@pytest.mark.parametrize("nome", ["", "../x", "a/b", "a\\b", ".oculto"])
def test_nome_de_planta_invalido_e_recusado(nome):
    with pytest.raises(ValueError):
        plant_pdf_path(nome)


def test_o_pdf_real_existe_no_caminho_resolvido():
    pdf = plant_pdf_path("planta_74")
    assert pdf.exists() and pdf.stat().st_size > 100_000


def test_nenhum_modulo_monta_caminho_de_pdf_por_conta_propria():
    donos = []
    for base in ("tools", "core", "interior", "scripts", "ops"):
        for f in (ROOT / base).rglob("*.py"):
            rel = f.relative_to(ROOT).as_posix()
            if rel == RESOLVEDOR:
                continue
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                code = line.split("#", 1)[0]
                if FSTRING_PDF.search(code):
                    donos.append(f"{rel}:{n}")
    assert donos == [], f"monte o caminho do PDF com core.project_sources.plant_pdf_path: {donos}"


@pytest.mark.parametrize("modulo", ["door_swing_audit", "pdf_height_labels_audit", "opening_audit", "pdf_overlay_verify"])
def test_execucao_direta_pelo_arquivo_continua_funcionando(modulo):
    """`python tools/x.py` (sem `-m`) funcionava antes do resolvedor; o fallback do import preserva."""
    r = subprocess.run([sys.executable, f"tools/{modulo}.py", "--help"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-400:]
