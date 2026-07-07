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
# tolerância p/ "centro fora do cômodo": painel encostado na parede tem centro ~dentro.
# Fonte ÚNICA do valor — sanity_room e o variant_sweep (_outside_room) leem daqui.
OUTSIDE_BUFFER_IN = 8.0


# ── API HERMÉTICA (boxes sintéticos em POLEGADAS) ────────────────────────────
# audit() é o gate determinístico stdlib-puro pinado por tests/test_geometry_sanity.py
# (boxes x0,y0,x1,y1 + z0_in/h_in/corners). Complementa sanity_room() (consensus-based,
# abaixo). Restaurado de 4def965 ("Frente A"); foi perdido no merge -X ours 15a15b2
# (que manteve a versão consensus-only mas dropou audit, orfanando o teste).
DEFAULTS = {
    "z_under_tol_in": -0.5,      # z0_in abaixo disso = underground (embaixo da terra)
    "min_footprint_in2": 1.0,    # footprint menor = degenerada (área ~0)
    "min_height_in": 0.2,        # altura menor = sliver 2D (WARN)
    "max_dim_m": 6.0,            # UMA dimensão de um móvel > isso = escala explodida
    "outside_margin": 1.0,       # margem p/ "fora do cômodo" (mesma unidade das caixas)
}


def _wh(b):
    return (b["x1"] - b["x0"], b["y1"] - b["y0"])


def _axis_aligned(b) -> bool:
    cs = b.get("corners")
    if not cs:
        return True  # sem corners -> assume AABB (x0..y1)
    xs = {round(c[0], 1) for c in cs}
    ys = {round(c[1], 1) for c in cs}
    return len(xs) <= 2 and len(ys) <= 2


def _pt_in_poly(x, y, poly) -> bool:
    inside, n, j = False, len(poly), len(poly) - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def audit(parts, *, rooms=None, to_m=1.0, cfg=None) -> dict:
    """parts: lista de boxes. rooms: lista de polígonos [[x,y],...] NA MESMA UNIDADE das
    caixas (opcional — só então roda fora-do-cômodo). to_m converte dimensões p/ metros
    (apt_boxes em polegadas -> to_m=0.0254). Devolve dict com overall/findings."""
    c = {**DEFAULTS, **(cfg or {})}
    findings = []

    def add(sev, check, b, detail):
        findings.append({"severity": sev, "check": check, "label": b.get("label"),
                         "kind": b.get("kind"), "detail": detail})

    for b in parts:
        w, d = _wh(b)
        z0 = b.get("z0_in")
        if z0 is not None and z0 < c["z_under_tol_in"]:
            add("FAIL", "underground", b, f"z0_in={round(z0, 2)} < {c['z_under_tol_in']}")
        if w * d < c["min_footprint_in2"]:
            add("FAIL", "degenerate_footprint", b, f"footprint={round(w * d, 3)} (w={round(w,2)} d={round(d,2)})")
        h = b.get("h_in")
        if h is not None and 0 < h < c["min_height_in"]:
            add("WARN", "degenerate_height", b, f"h_in={round(h, 3)}")
        if not b.get("decorative") and not _axis_aligned(b):
            # decorativo (tapete/manta) pode ser recortado ao comodo (poligono nao-retangular,
            # cantos arredondados) -> nao e "eixo torto" estrutural. So estrutural checa off_axis.
            add("FAIL", "off_axis", b, "corners nao axis-aligned (eixo torto)")
        for dim, nm in ((w, "w"), (d, "d")):
            if dim * to_m > c["max_dim_m"]:
                add("FAIL", "absurd_bbox", b, f"{nm}={round(dim * to_m, 2)}m > {c['max_dim_m']}m (escala explodida)")
        if rooms:
            cx, cy = (b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2
            if not any(_pt_in_poly(cx, cy, poly) for poly in rooms):
                add("FAIL", "outside_room", b, f"centro ({round(cx)},{round(cy)}) fora de todos os comodos")

    n_fail = sum(1 for f in findings if f["severity"] == "FAIL")
    n_warn = sum(1 for f in findings if f["severity"] == "WARN")
    checks = ["underground", "degenerate_footprint", "degenerate_height", "off_axis", "absurd_bbox"]
    if rooms:
        checks.append("outside_room")
    return {"overall": "FAIL" if n_fail else ("WARN" if n_warn else "PASS"),
            "n_parts": len(parts), "n_fail": n_fail, "n_warn": n_warn,
            "findings": findings, "checks_run": checks,
            "note": "PASS = sem regressao geometrica obvia; NAO julga estetica/premium (isso e o visual review)."}


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
        # FORA = CENTRO fora do comodo (OUTSIDE_BUFFER_IN de tolerancia).
        if not poly.buffer(OUTSIDE_BUFFER_IN).contains(bb.centroid):
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
