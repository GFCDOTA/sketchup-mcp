"""FP-054 F1-04: propriedades e metamorficos do gate de circulacao (BLOCO 6 da spec).

Cenas sinteticas sorteadas pelo hypothesis com `derandomize=True` (deterministico: mesma semente a cada execucao):
  - transladar a cena inteira (consensus em pt + caixas em in) preserva o veredito e as larguras medidas;
  - girar a cena 90 graus (paredes h<->v) preserva o veredito e as larguras;
  - permutar a ordem das caixas preserva o resultado inteiro;
  - acrescentar um obstaculo nunca aumenta a largura mobiliada nem transforma FAIL em PASS."""
from __future__ import annotations

import copy
import json

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.scale import PT_TO_IN
from tools.navigation.baseline_probes import synthetic_room
from tools.validation import circulation_gate as cg

SETTINGS = settings(max_examples=25, deadline=None, derandomize=True, suppress_health_check=[HealthCheck.too_slow])
SIDE_M = 4.0
CON = synthetic_room(SIDE_M)
(AX, AY), (BX, BY) = CON["rooms"][0]["polygon_pts"][0], CON["rooms"][0]["polygon_pts"][2]
X0, Y0, X1, Y1 = AX * PT_TO_IN, AY * PT_TO_IN, BX * PT_TO_IN, BY * PT_TO_IN


@st.composite
def boxes(draw, max_n=6):
    n = draw(st.integers(0, max_n))
    out = []
    for i in range(n):
        w = draw(st.floats(8, 40))
        d = draw(st.floats(8, 40))
        x = draw(st.floats(X0, X1 - w))
        y = draw(st.floats(Y0, Y1 - d))
        out.append({"module": f"m{i}", "kind": "body", "z0_in": 0.0, "h_in": 30.0,
                    "corners": [[x, y], [x + w, y], [x + w, y + d], [x, y + d]]})
    return out


def _widths(res):
    return [(p.get("status"), p.get("w_empty_m"), p.get("w_furnished_m"))
            for p in res["checks"]["corredor_principal"]["portais"] if "erro" not in p]


def _transform_scene(con, bxs, fpt, fin, swap):
    """Aplica fpt nos pontos do consensus (pt) e fin nas caixas (in). `swap` troca a orientacao h<->v das paredes."""
    con = copy.deepcopy(con)
    for w in con["walls"]:
        w["start"], w["end"] = list(fpt(*w["start"])), list(fpt(*w["end"]))
        if swap:
            w["orientation"] = "v" if w["orientation"] == "h" else "h"
    for r in con["rooms"]:
        r["polygon_pts"] = [list(fpt(*p)) for p in r["polygon_pts"]]
        r["seed_pt"] = list(fpt(*r["seed_pt"]))
    for o in con["openings"]:
        o["center"] = list(fpt(*o["center"]))
    bxs = copy.deepcopy(bxs)
    for b in bxs:
        b["corners"] = [list(fin(*c)) for c in b["corners"]]
    return con, bxs


@SETTINGS
@given(boxes(), st.floats(-300, 300), st.floats(-300, 300))
def test_translation_preserves_verdict_and_widths(bxs, dx_pt, dy_pt):
    base = cg.gate(CON, bxs, "r_syn")
    con2, bxs2 = _transform_scene(CON, bxs, lambda x, y: (x + dx_pt, y + dy_pt),
                                  lambda x, y: (x + dx_pt * PT_TO_IN, y + dy_pt * PT_TO_IN), swap=False)
    moved = cg.gate(con2, bxs2, "r_syn")
    assert moved["result"] == base["result"]
    for (s0, e0, f0), (s1, e1, f1) in zip(_widths(base), _widths(moved)):
        assert s0 == s1 and abs((e0 or 0) - (e1 or 0)) <= 0.011 and abs((f0 or 0) - (f1 or 0)) <= 0.011


@SETTINGS
@given(boxes())
def test_quarter_turn_preserves_verdict_and_widths(bxs):
    base = cg.gate(CON, bxs, "r_syn")
    cx, cy = (AX + BX) / 2, (AY + BY) / 2
    con2, bxs2 = _transform_scene(CON, bxs, lambda x, y: (cx - (y - cy), cy + (x - cx)),
                                  lambda x, y: (cx * PT_TO_IN - (y - cy * PT_TO_IN), cy * PT_TO_IN + (x - cx * PT_TO_IN)),
                                  swap=True)
    turned = cg.gate(con2, bxs2, "r_syn")
    assert turned["result"] == base["result"]
    for (s0, e0, f0), (s1, e1, f1) in zip(_widths(base), _widths(turned)):
        assert s0 == s1 and abs((e0 or 0) - (e1 or 0)) <= 0.011 and abs((f0 or 0) - (f1 or 0)) <= 0.011


@SETTINGS
@given(boxes(), st.randoms(use_true_random=False))
def test_box_order_is_irrelevant(bxs, rnd):
    ref = json.dumps(cg.gate(CON, bxs, "r_syn"), sort_keys=True)
    shuffled = bxs[:]
    rnd.shuffle(shuffled)
    assert json.dumps(cg.gate(CON, shuffled, "r_syn"), sort_keys=True) == ref


@SETTINGS
@given(boxes(max_n=4), boxes(max_n=1))
def test_adding_an_obstacle_never_widens_the_corridor_nor_rescues_a_fail(bxs, extra):
    before = cg.gate(CON, bxs, "r_syn")
    extra = [{**b, "module": "extra_" + b["module"]} for b in extra]
    after = cg.gate(CON, bxs + extra, "r_syn")
    if before["result"] == "FAIL":
        assert after["result"] == "FAIL"
    for (_, _, f0), (_, _, f1) in zip(_widths(before), _widths(after)):
        if f0 is not None and f1 is not None:
            assert f1 <= f0 + 1e-9
