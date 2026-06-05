"""Regression harness dos MODOS de sala (A2 sintetico, room_modes.md).

Trava o cerebro de layout: as 4 salas sinteticas (small/medium/large/long_narrow)
+ a planta real devem TODAS escolher o core ancorado e validar. Protege contra
regressao quando mexer em detalhes finos (presets, acessorios, densidade).
Gate de sucesso do GPT: 6/6 validam, estar_ancorado vence, score breakdown
presente, top-K TV wall ativo, circulacao primaria >= 0.80 m.
"""
import json
from pathlib import Path

import pytest

from tools.layout_candidates import run

REPO = Path(__file__).resolve().parents[1]
SYNTH = REPO / "fixtures" / "synthetic_rooms"
PLANTA = (REPO / "fixtures" / "planta_74"
          / "consensus_with_human_walls_and_soft_barriers.json")
SYNTH_ROOMS = ["living_small_rect_10m2", "living_medium_rect_18m2",
               "living_large_rect_28m2", "living_long_narrow"]


def _winner(out):
    return next(c for c in out["candidates"]
                if c["template"] == out["chosen_candidate"]
                and c.get("tv_wall") == out.get("chosen_tv_wall"))


@pytest.mark.skipif(not SYNTH.exists(), reason="synthetic rooms absent")
@pytest.mark.parametrize("name", SYNTH_ROOMS)
def test_synthetic_room_chooses_anchored_core(name):
    con = json.loads((SYNTH / f"{name}.json").read_text("utf-8"))
    _, out = run(con, "living")
    assert out["result"] == "OK", f"{name}: {out.get('reason')}"
    assert out["chosen_candidate"] == "estar_ancorado", \
        f"{name} escolheu {out['chosen_candidate']}"
    win = _winner(out)
    assert win["valid"]
    assert win["hard_gates"]["passagem_min_080"]          # circulacao primaria
    assert win["hard_gates"]["rack_na_parede_tv"]         # rack na parede focal
    assert win["soft"].get("composicao", 0) > 0           # score breakdown de composicao


@pytest.mark.skipif(not PLANTA.exists(), reason="planta_74 fixture absent")
def test_planta74_real_chooses_anchored_core():
    con = json.loads(PLANTA.read_text("utf-8"))
    _, out = run(con, "r002")
    assert out["result"] == "OK"
    assert out["chosen_candidate"] == "estar_ancorado"
    assert _winner(out)["soft"].get("composicao", 0) > 0


@pytest.mark.skipif(not SYNTH.exists(), reason="synthetic rooms absent")
def test_topk_tv_walls_active():
    """top-K paredes-TV: o brain testa mais de uma parede candidata."""
    con = json.loads((SYNTH / "living_small_rect_10m2.json").read_text("utf-8"))
    _, out = run(con, "living")
    walls = {c.get("tv_wall") for c in out["candidates"] if c.get("tv_wall")}
    assert len(walls) >= 2, "esperava o ranking testar multiplas paredes-TV"
