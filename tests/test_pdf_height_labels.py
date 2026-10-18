"""Gate reverso PDF→consensus pra alturas de barreira (review 2026-07-11).

O PDF escreve alturas como texto ("PEITORIL H=1,10M", "MURETA H=0,70M").
tools/pdf_height_labels_audit.py extrai e verifica contra o consensus —
a direção que era 100% cega (elemento nomeado pelo PDF e ausente do .skp
não disparava nada).

Estado pinado da planta_74 (pós-curadoria 2026-07-11, chip do Felipe):
- PEITORIL 1,10m da varanda E da borda leste do terraço técnico → MATCH
  com h_sb000 (o mesmo peitoril curado cobre as duas bordas; a órfã
  sb004 duplica a borda leste — tiebreak sourced resolve).
- MURETA 0,70m (borda oeste do terraço técnico) → MATCH com h_sb001,
  promovida da banda vetorial do PDF (x223-231, y408-500) com
  proveniência pdf_vector + label; overlay visual em
  runs/vision_check/{terraco_overlay,mureta_extent_zoom}.png.
"""
from __future__ import annotations

from tools.pdf_height_labels_audit import audit


def test_planta_74_height_labels_extracted():
    rows = audit("planta_74")
    assert len(rows) == 3, f"esperava 3 labels de altura, veio {len(rows)}"
    heights = sorted(r["height_m"] for r in rows)
    assert heights == [0.70, 1.10, 1.10]


def test_all_height_labels_match_consensus():
    """PDF↔consensus fechado: toda altura nomeada tem barreira com dono."""
    rows = audit("planta_74")
    verdicts = {r["verdict"] for r in rows}
    assert verdicts == {"MATCH"}, f"labels sem MATCH: {rows}"
    by_h = {r["height_m"]: r["barrier_id"] for r in rows}
    assert by_h[0.70] == "h_sb001"
    assert by_h[1.10] == "h_sb000"


def test_no_height_mismatch():
    """height_m divergir do PDF = MISMATCH = quebra aqui."""
    rows = audit("planta_74")
    assert not [r for r in rows if r["verdict"] == "MISMATCH"]


def test_mureta_fixture_has_provenance():
    """Hard Rule #3: a promoção da h_sb001 carrega proveniência completa."""
    import json
    from pathlib import Path
    p = (Path(__file__).resolve().parent.parent / "fixtures" / "planta_74"
         / "consensus_with_human_walls_and_soft_barriers.json")
    con = json.loads(p.read_text("utf-8"))
    sb = next(s for s in con["soft_barriers"] if s["id"] == "h_sb001")
    assert sb["barrier_type"] == "mureta"
    assert sb["height_m"] == 0.70
    assert sb["render_as"] == "low_wall"
    assert sb["geometry_origin"] == "pdf_vector"
    assert "label" in sb["pdf_provenance"]
