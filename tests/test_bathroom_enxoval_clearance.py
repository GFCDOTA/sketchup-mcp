"""Enxoval do banho nunca interpenetra a louça do vaso (colisão FÍSICA).

kb_lixeira é DECORATIVE no contrato semântico (core/spatial_semantics.py) →
interaction_policy.furniture_overlap=IGNORE, então o furniture_overlap_gate
NÃO vê a lixeira (por design: IGNORE = o gate de overlap não julga). Mas
IGNORE no gate não autoriza o BUILDER a posicionar um objeto sólido de
20x20x30cm dentro do volume do vaso — esta é a guarda do lado do builder
(achado do PR #245, f159f58: em BANHO 01/02 a lixeira caía dentro da bacia).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.planta74_scale

CON = Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")


def _fp(b):
    from shapely.geometry import Polygon
    from shapely.geometry import box as sb
    cs = b.get("corners")
    if cs:
        return Polygon([(c[0], c[1]) for c in cs]).buffer(0)
    return sb(b["x0"], b["y0"], b["x1"], b["y1"])


def _z(b):
    z0 = float(b.get("z0_in", 0.0))
    return z0, z0 + float(b.get("h_in", 0.0))


def _bath_rooms():
    from tools.bathroom_layout import build_boxes
    con = json.loads(CON.read_text("utf-8"))
    out = {}
    for r in con.get("rooms", []):
        nm = str(r.get("name", "")).upper()
        if "BANHO" in nm or "LAVABO" in nm:
            boxes, _ = build_boxes(con, r["id"])
            if boxes:
                out[nm] = boxes
    return out


def test_enxoval_never_interpenetrates_vaso():
    from core.spatial_semantics import resolve_geometry_intent
    rooms = _bath_rooms()
    assert rooms, "nenhum banho/lavabo construido — teste sem objeto"
    hits = []
    for nm, boxes in sorted(rooms.items()):
        vaso = [b for b in boxes if str(b.get("module")) == "Vaso"]
        assert vaso, f"{nm}: sem vaso — teste sem objeto"
        for e in (b for b in boxes if str(b.get("module")) == "Enxoval"):
            if resolve_geometry_intent(e.get("kind"), e.get("module"))[0] == "SOFT":
                continue  # tapete: SOFT/overlap ALLOW no contrato (3515cfd)
            ez0, ez1 = _z(e)
            for v in vaso:
                vz0, vz1 = _z(v)
                if min(ez1, vz1) - max(ez0, vz0) <= 0:
                    continue  # alturas nao se cruzam (ex. gancho acima do vaso)
                a = _fp(e).intersection(_fp(v)).area * 0.0254 ** 2
                if a > 1e-6:
                    hits.append(f"{nm}: {e['kind']} x {v['kind']} = {a * 1e4:.0f} cm2")
    assert not hits, "acessorio de enxoval dentro do volume do vaso: " + "; ".join(hits)
