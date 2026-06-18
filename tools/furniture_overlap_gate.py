"""furniture_overlap_gate.py — gate DETERMINISTICO de COLISAO: pega "móvel em cima de
móvel" (sobreposição real), o defeito que o Felipe nomeou. O geometry_sanity só cuida
de fora-do-cômodo/bloqueia-porta; ESTE cuida de dois móveis ocupando o mesmo espaço.

Critério: dois MÓDULOS diferentes colidem se a footprint (planta) se cruza E as faixas
de ALTURA se cruzam. Considera Z -> prateleira (z alto) sobre o rack (z baixo) NÃO é
colisão; sofá e mesa no mesmo nível com footprint sobreposta É. Tapete (forro) e parede
ficam de fora (tudo pousa sobre tapete; parede é parede).

Uso: PT_TO_M=0.0259 [FURNISH_STYLE=industrial] python -m tools.furniture_overlap_gate [room_id|all]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

M2IN = 39.3700787402
Z_EPS_IN = 2.0 / 2.54 * 1.0          # ~2cm de folga vertical p/ considerar "mesmo nível"
AREA_MIN_M2 = 0.04                   # cruzamento menor que isso = roçar, ignora
FRAC_MIN = 0.12                      # E >=12% da área do menor módulo
# módulos que legitimamente se sobrepõem a tudo (não são "móvel sobre móvel")
EXCLUDE = ("tapete", "rug", "parede", "piso", "floor")


def _module_geom(boxes):
    """module -> (footprint Polygon unida, z0_in, z1_in)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polys = defaultdict(list)
    zr = defaultdict(lambda: [9e9, -9e9])
    for b in boxes:
        mod = str(b.get("module", b.get("kind", "movel")))
        if not b.get("corners"):
            continue
        try:
            polys[mod].append(Polygon([(c[0], c[1]) for c in b["corners"]]).buffer(0))
        except Exception:  # noqa: BLE001
            continue
        z0 = float(b.get("z0_in", 0.0))
        zr[mod][0] = min(zr[mod][0], z0)
        zr[mod][1] = max(zr[mod][1], z0 + float(b.get("h_in", 0.0)))
    out = {}
    for mod, ps in polys.items():
        out[mod] = (unary_union(ps), zr[mod][0], zr[mod][1])
    return out


def overlap_gate(con, room_id):
    os.environ.setdefault("PT_TO_M", "0.0259")
    from tools.furnish_apartment import BRAINS
    from tools.room_type import classify_rooms
    r = {x["id"]: x for x in classify_rooms(con)}.get(room_id)
    if not r:
        return {"result": "FAIL", "room": room_id, "fails": ["cômodo inexistente"], "warns": []}
    brain = BRAINS.get(r["room_type"])
    boxes, _ = brain(con, room_id) if brain else ([], {})
    geoms = {m: g for m, g in _module_geom(boxes or {}).items()
             if not any(e in m.lower() for e in EXCLUDE)}
    mods = sorted(geoms)
    # embutidos LEGÍTIMOS: cooktop/pia DENTRO da bancada (eletro embutido, não colisão)
    embedded = ({"cooktop", "bancada"}, {"pia", "bancada"}, {"cuba", "bancada"})
    fails, warns = [], []
    for i in range(len(mods)):
        for j in range(i + 1, len(mods)):
            if {mods[i].lower(), mods[j].lower()} in embedded:
                continue
            pa, za0, za1 = geoms[mods[i]]
            pb, zb0, zb1 = geoms[mods[j]]
            z_ov = min(za1, zb1) - max(za0, zb0)
            if z_ov <= Z_EPS_IN:                       # alturas não se cruzam -> ok (empilhado)
                continue
            inter = pa.intersection(pb).area / (M2IN * M2IN)   # m²
            if inter < AREA_MIN_M2:
                continue
            amin = min(pa.area, pb.area) / (M2IN * M2IN)
            frac = inter / amin if amin else 0.0
            if frac >= FRAC_MIN:
                msg = f"{mods[i]} × {mods[j]}: {inter*10000:.0f} cm² sobrepostos ({frac:.0%} do menor)"
                (fails if frac >= 0.30 else warns).append(msg)
    result = "FAIL" if fails else ("WARN" if warns else "PASS")
    return {"result": result, "room": room_id, "room_name": r["name"],
            "n_modules": len(mods), "fails": fails, "warns": warns}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("room", nargs="?", default="all")
    a = ap.parse_args()
    from tools.furnish_apartment import CONSENSUS
    from tools.room_type import classify_rooms
    con = json.loads(CONSENSUS.read_text("utf-8"))
    rooms = ([a.room] if a.room != "all"
             else [r["id"] for r in classify_rooms(con)])
    worst = "PASS"
    for rid in rooms:
        res = overlap_gate(con, rid)
        if res["result"] == "FAIL":
            worst = "FAIL"
        elif res["result"] == "WARN" and worst != "FAIL":
            worst = "WARN"
        tag = {"PASS": "ok", "WARN": "warn", "FAIL": "FAIL"}[res["result"]]
        print(f"[{tag:4}] {res.get('room_name', rid)} ({res['n_modules']} móveis)")
        for m in res["fails"] + res["warns"]:
            print(f"        {m}")
    print(f"\noverlap_gate => {worst}")
    sys.exit(1 if worst == "FAIL" else 0)


if __name__ == "__main__":
    main()
