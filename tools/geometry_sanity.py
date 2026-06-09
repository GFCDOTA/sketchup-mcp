"""geometry_sanity.py — GATE determinístico BARATO de sanidade geométrica de MÓVEL (consensus-only,
sem SU/render/rede). Complementa tools/run_deterministic_gates.py (que cobre a SHELL: walls/openings).
Aqui: o MÓVEL vs o cômodo. NÃO julga beleza/premium — só impede CAOS geométrico.

Bloqueia (FAIL) / alerta (WARN):
  - bbox degenerada (<2in) ou absurda (> diagonal do cômodo)        -> FAIL
  - móvel FORA do cômodo / atravessando parede (>25% da area fora)   -> FAIL
  - móvel (não-piso) BLOQUEANDO porta (clearance ~22in)              -> FAIL
  - móvel ALTO cobrindo JANELA                                       -> WARN
  - leve transbordo na parede (<25%)                                 -> WARN

Uso: python tools/geometry_sanity.py [room_id]   (sem arg = todos os cômodos)
Saída: STATUS PASS|WARN|FAIL + itens. Exit 0 (PASS/WARN) / 1 (FAIL).
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, ".")
from shapely.geometry import Polygon  # noqa: E402
from shapely.geometry import box as shp_box  # noqa: E402

from tools.furnish_apartment import BRAINS, CONSENSUS, classify_rooms  # noqa: E402
from tools.spatial_model import build_spatial_model  # noqa: E402

from core.scale import PT_TO_IN  # noqa: E402  (fonte unica de escala; env PT_TO_M -> 0.0259)
FLOOR_KINDS = ("rug", "tapete")                      # ficam no chão: ok perto de porta/sob móvel
TALL_KINDS = ("corpo", "torre", "aereo", "dresser", "estante", "guarda_roupa", "rack_tv", "bancada")
DOOR_CLEARANCE_IN = 22.0


def _fbox(b):
    xs = [c[0] for c in b["corners"]]; ys = [c[1] for c in b["corners"]]
    return shp_box(min(xs), min(ys), max(xs), max(ys)), (min(xs), min(ys), max(xs), max(ys))


def sanity_room(con, room_id):
    r = {x["id"]: x for x in classify_rooms(con)}[room_id]
    boxes, _ = BRAINS[r["room_type"]](con, room_id)
    cell = build_spatial_model(con, room_id)["_geom"]["cell"]
    poly = Polygon([(x * PT_TO_IN, y * PT_TO_IN) for x, y in cell.exterior.coords])
    bx0, by0, bx1, by1 = [v * PT_TO_IN for v in cell.bounds]
    diag = ((bx1 - bx0) ** 2 + (by1 - by0) ** 2) ** 0.5

    doors, windows = [], []
    for o in con.get("openings", []):
        pos = o.get("position") or o.get("center")
        if not pos:
            continue
        px, py = pos[0] * PT_TO_IN, pos[1] * PT_TO_IN
        if not (bx0 - 24 <= px <= bx1 + 24 and by0 - 24 <= py <= by1 + 24):
            continue
        kind = (o.get("type") or o.get("kind") or "").lower()
        (doors if "door" in kind or "porta" in kind else windows if "window" in kind or "janela" in kind else []).append((px, py))

    fails, warns = [], []
    seen = set()
    for b in boxes:
        k = b["kind"]
        if k in seen:                                 # 1 check por tipo (boxes repetem por peça)
            continue
        seen.add(k)
        bb, (x0, y0, x1, y1) = _fbox(b)
        w, h = x1 - x0, y1 - y0
        # DEGENERADA = speck nos DOIS eixos (peca fina por design — gaveta/porta-painel/pe — NAO conta).
        if max(w, h) < 1.5:
            fails.append(f"{k}: bbox DEGENERADA ({w:.1f}x{h:.1f}in)"); continue
        if max(w, h) > diag:
            fails.append(f"{k}: bbox ABSURDA ({w:.0f}x{h:.0f}in > diag {diag:.0f})"); continue
        # FORA = CENTRO fora do comodo (8in de tolerancia: painel encostado na parede tem centro ~dentro).
        if not poly.buffer(8).contains(bb.centroid):
            fails.append(f"{k}: CENTRO fora do comodo (atravessa parede / fora do comodo)")
        elif (bb.difference(poly).area / bb.area if bb.area else 0) > 0.5:
            warns.append(f"{k}: >50% transborda a parede")
        if k not in FLOOR_KINDS:                      # bloqueio de porta — exige overlap REAL (nao toque de canto)
            for dx, dy in doors:
                ov = bb.intersection(shp_box(dx - DOOR_CLEARANCE_IN, dy - DOOR_CLEARANCE_IN,
                                             dx + DOOR_CLEARANCE_IN, dy + DOOR_CLEARANCE_IN)).area
                if ov > 25:
                    fails.append(f"{k}: BLOQUEIA porta @({dx:.0f},{dy:.0f}) (overlap {ov:.0f}in2)"); break
                elif ov > 4:
                    warns.append(f"{k}: perto da porta @({dx:.0f},{dy:.0f}) (overlap {ov:.0f}in2)")
        if k in TALL_KINDS:                           # alto sobre janela
            for wx, wy in windows:
                if bb.intersects(shp_box(wx - 6, wy - 6, wx + 6, wy + 6)):
                    warns.append(f"{k}: ALTO cobrindo janela @({wx:.0f},{wy:.0f})")
                    break

    status = "FAIL" if fails else ("WARN" if warns else "PASS")
    return {"room": room_id, "type": r["room_type"], "status": status, "fails": fails, "warns": warns,
            "n_items": len(seen)}


def main():
    con = json.loads(CONSENSUS.read_text("utf-8"))
    rid = sys.argv[1] if len(sys.argv) > 1 else None
    rooms = [rid] if rid else [r["id"] for r in classify_rooms(con) if r["room_type"] in BRAINS]
    worst = "PASS"
    for room in rooms:
        res = sanity_room(con, room)
        print(f"[{res['status']}] {res['room']} ({res['type']}) {res['n_items']} tipos"
              + ("" if res["status"] == "PASS" else ":"))
        for f in res["fails"]:
            print(f"    FAIL {f}")
        for w in res["warns"]:
            print(f"    warn {w}")
        if res["status"] == "FAIL" or (res["status"] == "WARN" and worst != "FAIL"):
            worst = res["status"]
    print(f"\ngeometry_sanity => {worst}")
    sys.exit(1 if worst == "FAIL" else 0)


if __name__ == "__main__":
    main()
