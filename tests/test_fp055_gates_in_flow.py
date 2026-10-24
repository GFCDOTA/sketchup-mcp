"""FP-055 #428: o gate de anatomia do guarda-roupa roda no fluxo de geracao e o veredito fica registrado (nao some)."""
from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.planta74_scale      # brain do quarto da planta_74: PT_TO_M=0.0259, processo proprio


def _con():
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    return json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))


def test_suite_01_wardrobe_passes_the_anatomy_gate_in_the_flow():
    from tools.rooms.bedroom import furnishing
    _boxes, out = furnishing.bedroom_designer_boxes(_con(), "r000")
    [rec] = out["component_anatomy"]
    assert rec["component"] == "guarda-roupa" and rec["result"] == "PASS" and rec["n_doors"] == 3


def test_suite_02_narrow_wardrobe_fails_the_door_rule_and_the_verdict_is_recorded_not_dropped():
    # Defeito de REGRA conhecido (decisao no backlog): 0,8 m com 1 porta reprova ">= 2 portas". A geracao nao para.
    from tools.rooms.bedroom import furnishing
    boxes, out = furnishing.bedroom_designer_boxes(_con(), "r003")
    [rec] = out["component_anatomy"]
    assert rec["result"] == "FAIL" and rec["width_m"] == 0.8 and "poucas portas (1)" in rec["corrections"]
    assert any(b.get("module") == "Guarda-roupa" for b in boxes)


def test_a_single_block_wardrobe_is_reported_as_fail_with_every_hard_reason(monkeypatch):
    from tools.rooms.bedroom import furnishing
    from tools.rooms.shared import wardrobe
    real = wardrobe.build_wardrobe
    monkeypatch.setattr(wardrobe, "build_wardrobe", lambda spec: (real(spec)[0][:1], real(spec)[1]))
    _boxes, out = furnishing.bedroom_designer_boxes(_con(), "r000")
    [rec] = out["component_anatomy"]
    assert rec["result"] == "FAIL" and rec["n_parts"] == 1 and not rec["checks"]["nao_bloco_unico"]
