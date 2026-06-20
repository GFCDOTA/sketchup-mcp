"""style_coherence_gate.py — gate DETERMINISTICO de coerencia de ESTILO + ESCALA
compacta no nivel do COMODO (camada que faltava na gramatica de interior). Espelha o
molde dos *_class_gate: checa o objetivo e devolve PASS/WARN/FAIL + metricas. NAO
auto-julga APARENCIA (isso e o GPT) — checa o deterministico:
  (1) MATERIAL_COHERENCE — todo kind load-bearing foi recolorido p/ o estilo (sem vazar default);
  (2) COMPACT_SCALE — moveis cabem no comodo compacto (footprint/area util + rack raso).

Uso: PT_TO_M=0.0259 python -m tools.style_coherence_gate r002 [--style industrial]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

M2IN = 39.3700787402
FOOTPRINT_RATIO_WARN = 0.42      # footprint movel / area util
FOOTPRINT_RATIO_FAIL = 0.58
RACK_MAX_M = 1.25
# kinds que NAO contam como footprint solido (underlay / parede / decor leve)
_SKIP_FOOTPRINT = {"tapete", "rug", "rug_field", "rug_border", "parede_concreto",
                   "frame", "canvas", "art_accent", "foliage", "trunk", "pot"}


def _edges_m(box):
    """(maior, menor) lado do retangulo orientado a partir dos corners (inches->m)."""
    c = box.get("corners")
    if not c or len(c) < 3:
        return (0.0, 0.0)
    e1 = math.dist(c[0], c[1]) / M2IN
    e2 = math.dist(c[1], c[2]) / M2IN
    return (max(e1, e2), min(e1, e2))


def style_coherence_gate(con, room_id, style="industrial"):
    os.environ["FURNISH_STYLE"] = style
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    from tools.furnish_apartment import living_room_boxes
    from tools.spatial_model import build_spatial_model
    from tools.style_spec import STYLE_TOKENS, apply_style

    st = STYLE_TOKENS.get(style)
    if not st:
        return {"result": "FAIL", "room": room_id, "style": style,
                "fails": [f"estilo desconhecido: {style}"], "warns": [], "metrics": {}}

    boxes, _out = living_room_boxes(con, room_id)
    apply_style(boxes, style)            # standalone: garante recolorido (furnish faz no collect)
    fails, warns, metrics = [], [], {}

    # (1) MATERIAL_COHERENCE — must_style kind presente tem rgb == token (nao vazou default)
    present = {b["kind"] for b in boxes}
    for k in st.must_style:
        if k in present:
            want = list(st.kind_rgb[k])
            if any(b["kind"] == k and list(b.get("rgb", [])) != want for b in boxes):
                fails.append(f"material_coherence: '{k}' nao recolorido p/ {style} (vazou default)")
    missing = [k for k in st.must_style if k not in present]
    if missing:
        warns.append(f"must_style ausentes no comodo: {missing}")

    # (2) COMPACT_SCALE — footprint movel solido / area util + rack raso
    sm = build_spatial_model(con, room_id)
    usable = sm.get("usable_area_m2") or sm.get("area_m2") or 0.0
    metrics["usable_area_m2"] = round(usable, 2)
    foot_polys = []
    for b in boxes:
        if b.get("kind") in _SKIP_FOOTPRINT or not b.get("corners"):
            continue
        try:
            foot_polys.append(Polygon([(c[0] / M2IN, c[1] / M2IN) for c in b["corners"]]))
        except Exception:  # noqa: BLE001
            pass
    foot = unary_union(foot_polys).area if foot_polys else 0.0
    metrics["furniture_footprint_m2"] = round(foot, 2)
    ratio = (foot / usable) if usable else 0.0
    metrics["footprint_ratio"] = round(ratio, 3)
    if ratio >= FOOTPRINT_RATIO_FAIL:
        fails.append(f"compact_scale: footprint {ratio:.0%} da area util (>{FOOTPRINT_RATIO_FAIL:.0%}) — apertado demais")
    elif ratio >= FOOTPRINT_RATIO_WARN:
        warns.append(f"compact_scale: footprint {ratio:.0%} da area util (limite {FOOTPRINT_RATIO_WARN:.0%})")

    rack = next((b for b in boxes if b["kind"] == "rack_tv"), None)
    if rack:
        rw = _edges_m(rack)[0]
        metrics["rack_w_m"] = round(rw, 2)
        if rw > RACK_MAX_M:
            fails.append(f"compact_scale: rack {rw:.2f}m > {RACK_MAX_M}m (apê pequeno)")

    result = "FAIL" if fails else ("WARN" if warns else "PASS")
    return {"result": result, "room": room_id, "style": style,
            "fails": fails, "warns": warns, "metrics": metrics}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("room_id", nargs="?", default="r002")
    ap.add_argument("--style", default="industrial")
    a = ap.parse_args()
    from tools.furnish_apartment import CONSENSUS
    con = json.loads(CONSENSUS.read_text("utf-8"))
    res = style_coherence_gate(con, a.room_id, a.style)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    sys.exit(1 if res["result"] == "FAIL" else 0)


if __name__ == "__main__":
    main()
