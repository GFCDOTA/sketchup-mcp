"""Contrato de swing/dobradiça das portas — fixture planta_74 vs PDF.

Contexto (vf_004, 2026-07-10): o painel /ask-vision + crop do PDF pegaram a
porta de ENTRADA renderizando com swing invertido (folha pra FORA da unidade;
o PDF mostra abrindo pra DENTRO da sala). Causa raiz dupla:

1. DADO: o consensus não carregava lado de swing (e 3 dobradiças estavam
   erradas) — o arco que o PDF desenha por porta nunca tinha sido medido.
2. CONSUMO: build_plan_shell_skp.rb::build_door_leaf admitia no comentário
   "We don't have side info; use cross+offset" — TODA folha no lado +cross.

A medida vem de tools/door_swing_audit.py (arcos bezier do PDF, sem
fabricação). Estes testes pinam o dado e o contrato do builder.

⚠ O .rb não executa em pytest (precisa do SketchUp) — o teste do builder é
contrato de TEXTO; a prova executável é o rebuild SU + gate visual
(artifacts/review/planta_74/). Confirmar em build SU após mudar o .rb.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "fixtures" / "planta_74" / "consensus_with_human_walls_and_soft_barriers.json"
RB = REPO / "tools" / "build_plan_shell_skp.rb"

# Verdade medida do PDF (tools.door_swing_audit, 2026-07-11) — não editar sem
# re-rodar o audit contra o PDF.
PDF_TRUTH = {
    "h_o000": {"swing_side": "neg", "hinge_side": "left"},   # ENTRADA -> sala
    "h_o001": {"swing_side": "pos", "hinge_side": "left"},   # lavabo
    "h_o002": {"swing_side": "neg", "hinge_side": "left"},   # banho 01
    "h_o003": {"swing_side": "pos", "hinge_side": "left"},   # circulação suítes
    "h_o004": {"swing_side": "neg", "hinge_side": "right"},  # suíte 02
    "h_o005": {"swing_side": "neg", "hinge_side": "right"},  # A.S.
    "h_o006": {"swing_side": "pos", "hinge_side": "right"},  # banho 02
}


def _doors():
    con = json.loads(FIXTURE.read_text("utf-8"))
    return {o["id"]: o for o in con["openings"] if o.get("kind") == "door"}


def test_every_door_carries_swing_side_from_pdf_arc():
    doors = _doors()
    assert set(doors) == set(PDF_TRUTH), "conjunto de portas mudou — re-rodar door_swing_audit"
    for oid, o in doors.items():
        assert o.get("swing_side") in ("pos", "neg"), (
            f"{oid}: sem swing_side no consensus — o builder não tem como saber "
            f"pra que lado a folha abre (vf_004)")


def test_fixture_swing_and_hinge_match_pdf_measurement():
    doors = _doors()
    for oid, truth in PDF_TRUTH.items():
        o = doors[oid]
        assert o.get("swing_side") == truth["swing_side"], (
            f"{oid}: swing_side={o.get('swing_side')!r} != PDF {truth['swing_side']!r}")
        assert o.get("hinge_side") == truth["hinge_side"], (
            f"{oid}: hinge_side={o.get('hinge_side')!r} != PDF {truth['hinge_side']!r}")


def test_door_swing_audit_is_green_against_fixture():
    """O audit determinístico (PDF -> arco -> swing/hinge) fecha com a fixture."""
    from tools.door_swing_audit import audit
    rows = audit("planta_74")
    bad = [r for r in rows if not (r.get("swing_ok") and r.get("hinge_ok"))]
    assert not bad, f"door_swing_audit divergente: {bad}"


def test_rb_builder_honors_swing_side_text_contract():
    """Contrato de texto do .rb (não executável em pytest — confirma em build SU):
    build_door_leaf precisa ler swing_side, posicionar a folha também no lado
    -cross e assinar a rotação por (hinge, swing, eixo)."""
    src = RB.read_text("utf-8")
    leaf = src[src.index("def build_door_leaf"):]
    leaf = leaf[:leaf.index("\ndef ", 1)]
    assert "swing_side" in leaf, "build_door_leaf ignora swing_side do consensus"
    assert re.search(r"swing_side\s*==\s*'neg'", leaf), (
        "build_door_leaf não tem ramo pro lado -cross (folha sempre em +cross = vf_004)")
    assert "rot_sign" in leaf, (
        "rotação sem sinal por (hinge, swing, eixo) — folha gira pro lado errado")
