"""Regressao do scale-gate da Suite 01 (chore/suite01-scale-gate).

Trava o que o workflow adversarial pediu (F3 SUSPECT = "sem testes"):
- DEFAULT (sem PT_TO_M) = 0.0352 intacto: criados full-size, colchao king-ish.
- @PT_TO_M=0.0259: geometry_sanity PASS (zero FAIL), colchao ~queen, SEM headboard duplicado.

PT_TO_M e lido no IMPORT (spatial_model/geometry_sanity), entao cada caso roda num
subprocess proprio com o env certo (nao da pra reimportar limpo no mesmo processo).
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_SNIPPET = r'''
import os, sys, json
sys.path.insert(0, r"{root}")
from tools.geometry_sanity import sanity_room
from tools.furnish_apartment import CONSENSUS, bedroom_designer_boxes
con = json.loads(CONSENSUS.read_text("utf-8"))
r = sanity_room(con, "r000")
bx, _ = bedroom_designer_boxes(con, "r000")
def span(kind, ax):
    bs = [b for b in bx if b["kind"] == kind]
    if not bs:
        return None
    b = bs[0]
    return round((b["x1"] - b["x0"]) if ax == "x" else (b["y1"] - b["y0"]), 1)
kinds = {{}}
for b in bx:
    kinds[b["kind"]] = kinds.get(b["kind"], 0) + 1
print(json.dumps({{
    "status": r["status"], "fails": r.get("fails", []),
    "colchao_x_in": span("colchao", "x"), "colchao_y_in": span("colchao", "y"),
    "tampos": kinds.get("tampo", 0), "headboard": kinds.get("headboard", 0),
    "cabeceira": kinds.get("cabeceira", 0),
}}))
'''


def _run(scale=None):
    env = dict(**__import__("os").environ)
    if scale:
        env["PT_TO_M"] = scale
    else:
        env.pop("PT_TO_M", None)
    out = subprocess.run([sys.executable, "-c", _SNIPPET.format(root=str(ROOT))],
                         capture_output=True, text=True, env=env, cwd=str(ROOT))
    assert out.returncode == 0, f"subprocess falhou: {out.stderr[-800:]}"
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_default_0352_intact():
    """Sem env: 2 criados full-size (~16in), colchao grande (king ~76in). NAO muda."""
    d = _run(None)
    assert d["tampos"] == 2, d
    # default: cama maior (footprint 0.0352) — colchao bem largo (> 60in)
    assert d["colchao_x_in"] and d["colchao_x_in"] > 60, d


def test_0259_geometry_sanity_pass():
    d = _run("0.0259")
    assert d["status"] == "PASS", d
    assert d["fails"] == [], d
    assert d["tampos"] == 2, d


def test_0259_colchao_queen():
    d = _run("0.0259")
    # queen ~1.58x2.03m -> colchao ~78in (comprimento, eixo x) x ~60in (largura, eixo y)
    lo, hi = sorted((d["colchao_x_in"], d["colchao_y_in"]))
    assert 55 <= lo <= 66, d     # largura ~60in (1.54m)
    assert 72 <= hi <= 84, d     # comprimento ~78in (1.99m)


def test_0259_no_duplicate_headboard():
    d = _run("0.0259")
    assert d["headboard"] == 0, d   # _items_to_boxes 'headboard' dropado
    assert d["cabeceira"] == 1, d   # anatomia build_bed mantida
