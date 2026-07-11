"""Gate reverso PDF→consensus pra alturas de barreira (review 2026-07-11).

O PDF escreve alturas como texto ("PEITORIL H=1,10M", "MURETA H=0,70M").
tools/pdf_height_labels_audit.py extrai e verifica contra o consensus —
a direção que era 100% cega (elemento nomeado pelo PDF e ausente do .skp
não disparava nada).

Estado pinado da planta_74:
- PEITORIL 1,10m da varanda → MATCH com h_sb000 (height_m=1.1).
- MURETA 0,70m (borda oeste do terraço técnico) e PEITORIL 1,10m (borda
  leste) → UNRENDERED: elementos reais SEM barreira sourced, com
  candidatas órfãs listadas. Curadoria pendente — promover é decisão
  humana (linework órfão ambíguo; associar por palpite = fabricar).
"""
from __future__ import annotations

from tools.pdf_height_labels_audit import audit


def test_planta_74_height_labels_extracted():
    rows = audit("planta_74")
    assert len(rows) == 3, f"esperava 3 labels de altura, veio {len(rows)}"
    heights = sorted(r["height_m"] for r in rows)
    assert heights == [0.70, 1.10, 1.10]


def test_varanda_peitoril_matches_pdf():
    rows = audit("planta_74")
    match = [r for r in rows if r["verdict"] == "MATCH"]
    assert len(match) == 1
    assert match[0]["barrier_id"] == "h_sb000"
    assert match[0]["height_m"] == 1.10


def test_no_height_mismatch():
    """h_sb000 divergir do PDF = MISMATCH = quebra aqui."""
    rows = audit("planta_74")
    assert not [r for r in rows if r["verdict"] == "MISMATCH"]


def test_terraco_tecnico_elements_flagged_unrendered():
    """Os 2 elementos do terraço técnico seguem pendentes de curadoria.

    Quando a curadoria promover as polylines (mureta 0.70 + peitoril
    leste 1.10), este teste deve ser ATUALIZADO pra MATCH — ele existe
    pra impedir que os elementos sumam do radar em silêncio.
    """
    rows = audit("planta_74")
    unrendered = [r for r in rows if r["verdict"] == "UNRENDERED"]
    assert len(unrendered) == 2
    for r in unrendered:
        assert r["candidates"], f"label {r} sem candidatas de curadoria"
