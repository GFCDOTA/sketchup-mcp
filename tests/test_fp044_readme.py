"""FP-044/F1 — o README descreve o que existe (sem repetir afirmacoes ja corrigidas)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_nao_afirma_o_que_ja_foi_corrigido():
    """O README descrevia taskkill por nome e `tools/*.rb` legado depois de removidos (P3b/P4c): nao pode voltar a mentir."""
    text = (ROOT / "README.md").read_text("utf-8")
    assert "ainda rodam `taskkill" not in text and "tools/*.rb" not in text
    assert "tools/sketchup/{shell,furnish,inspect,vray}" in text
    assert "docs/specs/FP-044_root_and_tools_consolidation.md" in text
