"""FP-056 / #442 + #488 — churrasqueira, coifa e prateleira de servico encostadas em parede REAL, medidas EM MEMORIA.

Usa o proprio planejador da A.S. (`tools.rooms.service.layout`) e os mesmos gates do p7: pre-voo (`layout_preflight` com
`planta74_twin`), gemeo em caixas (`box_geometry.validate_boxes`) x `artifacts/review/fp055/p4/defect_baseline.json`, programa
`artifacts/review/fp056/p2/program_baseline.json` e apoio por modulo (`support_check.check_modules`). Nada e gravado fora de
`--out`: gerador, consensus, fixtures e .skp intactos (SHA-256 do consensus conferido antes e depois).

Variacoes em memoria (monkeypatch; todas declaradas no JSON de saida):
  V1  larguras da churrasqueira/coifa: `widths` do item no `_programa` (layout.py:249-255) trocado por uma unica largura;
  V2  parede de apoio: `side` do item + zona de colocacao = zona do planejador MENOS a massa de parede do consensus
      (`wall_mass_pt`), para que o encosto seja a FACE da parede (a borda do cell entra 5,6 cm sob m004/m013, D-007);
  V3  posicao ao longo da parede: `_slide` (layout.py:183) chamado com `span=0` so para churrasqueira/coifa (posicao fixa,
      sem deslizar); as demais checagens do `_slide` e o `circulation_gate` do planejador continuam valendo;
  V4  prateleira de servico: caixa transladada em x ate a face real da parede oeste (pos-processamento da saida do planejador).

Uso (da raiz do repo):  PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp056/p7_as1_real_wall/probe_as1_real_wall.py
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
if os.environ.get("PT_TO_M") != "0.0259":
    sys.exit("rode com PT_TO_M=0.0259 (escala da planta_74)")

from shapely.affinity import scale as _scale  # noqa: E402
from shapely.geometry import LineString  # noqa: E402

import tools.rooms.service.layout as sl  # noqa: E402
from core.scale import PT_TO_IN, PT_TO_M  # noqa: E402
from tools.furnish_apartment import collect_boxes  # noqa: E402
from tools.rooms.shared.clearance import box_footprint_pt, wall_mass_pt  # noqa: E402
from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS  # noqa: E402
from tools.validation import (  # noqa: E402
    box_geometry,
    defect_baseline,
    known_gaps,
    layout_preflight,
)
from tools.validation.penetration import EPS_DEPTH  # noqa: E402
from tools.validation.support_check import check_modules  # noqa: E402

ROOM = "A.S. | TERRACO SOCIAL | TERRACO TECNICO"
RID = "r001"
HOSTED = ("churrasqueira", "coifa")
WIDTHS = (1.00, 0.85, 0.70)               # a lista de fallback do proprio planejador (layout.py:250)
STEP = 0.05                               # passo do `_slide` do planejador (layout.py:183)
WALL_IDS = ("m004", "m013", "m001")     # m004/m013: pedido (#488); m001: a outra `blind_wall_candidates` do spatial_model

_ORIG_PROGRAMA, _ORIG_SLIDE, _ORIG_SPLIT = sl._programa, sl._slide, sl._split_zones
STATE: dict = {}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _wall_m(con):
    return _scale(wall_mass_pt(con), PT_TO_M, PT_TO_M, origin=(0, 0))


def _split(con, room_id, cell):
    zones, err = _ORIG_SPLIT(con, room_id, cell)
    if zones is not None:   # zonas extras so para a churrasqueira/coifa (V2); as do planejador seguem identicas
        wm = STATE["wall_m"]
        for name in (sl.AS, sl.SOCIAL):
            z = zones[name].difference(wm)
            zones[f"{name}-parede"] = max(z.geoms, key=lambda g: g.area) if z.geom_type == "MultiPolygon" else z
    return zones, err


def _programa(zones):
    P = _ORIG_PROGRAMA(zones)
    v = STATE.get("variant")
    if not v:
        return P
    for spec in P:
        if spec["kind"] in HOSTED:
            if v.get("widths"):
                spec["widths"] = list(v["widths"])
            if v.get("zone"):
                spec["zone"] = v["zone"]
            if v.get("side"):
                spec["side"] = v["side"]
            if v.get("along") is not None:
                spec["prefer"] = v["along"]
    return P


def _slide(zone, side, prefer, w_m, d_m, placed, circ, step=0.05, span=4.0, hard=()):
    v = STATE.get("variant") or {}
    if v.get("pin") and v.get("along") is not None and abs(prefer - v["along"]) < 1e-9 and d_m in (0.62, 0.58):
        span = 0.0
        STATE.setdefault("diag", []).append({"kind": "churrasqueira" if d_m == 0.62 else "coifa", "w_m": w_m,
                                             "slide_rejects": _why(zone, side, prefer, w_m, d_m, placed, circ, hard)})
    return _ORIG_SLIDE(zone, side, prefer, w_m, d_m, placed, circ, step=step, span=span, hard=hard)


def _why(zone, side, along, w_m, d_m, placed, circ, hard):
    """Mesmas checagens do `_slide` (layout.py:190-203) na posicao fixa, com o valor medido de cada uma que reprova."""
    got = sl._flush_rect(zone, side, along, w_m, d_m)
    if got is None:
        return ["zona sem borda no trecho (_wall_line None)"]
    rect, out = got[0], []
    if not zone.buffer(0.02).contains(rect):
        out.append(f"fora da zona (contains com 2 cm): {rect.difference(zone).area:.4f} m2 fora")
    if circ is not None and rect.intersection(circ).area > sl._DOOR_TOL_M2:
        out.append(f"invade circulacao/giro: {rect.intersection(circ).area:.4f} m2 > _DOOR_TOL_M2 {sl._DOOR_TOL_M2}")
    hits = [rect.intersection(p.buffer(sl._CLEAR_M)).area for p in placed]
    if any(a > 0.005 for a in hits):
        out.append(f"encosta em peca ja aceita (folga _CLEAR_M {sl._CLEAR_M}): {max(hits):.4f} m2 > 0.005")
    if any(rect.intersection(h).area > sl._HARD_TOL_M2 for h in hard):
        out.append("atravessa barreira construida")
    return out


sl._programa, sl._slide, sl._split_zones = _programa, _slide, _split


def _wall_report(con, fp_pt, wm_pt):
    """Distancia da pegada a massa de parede (como `support_check`, WALL_MOUNTED) e a parede do consensus mais proxima."""
    gap = fp_pt.distance(wm_pt) * PT_TO_M
    best = None
    for w in con["walls"]:
        d = fp_pt.distance(LineString([w["start"], w["end"]]).buffer(float(w.get("thickness", 0)) / 2, cap_style=2))
        if best is None or d < best[1]:
            best = (w["id"], d)
    return {"gap_m": round(gap, 4), "in_contact": gap <= EPS_DEPTH, "nearest_wall": best[0],
            "nearest_wall_gap_m": round(best[1] * PT_TO_M, 4)}


PROGRAM_KINDS = ("bancada_gourmet", "cuba_gourmet", "banqueta", "mesa_externa", "cadeira_externa", "maq_secar",
                 "churrasqueira", "coifa", "prateleira_servico")


def _pieces(con, room, wm_pt):
    pieces = {}
    for b in room:
        if b.get("kind") in ("churrasqueira", "coifa", "prateleira_servico"):
            fp = box_footprint_pt(b, PT_TO_IN)
            pieces[b["kind"]] = {"bounds_m": [round(c * PT_TO_M, 3) for c in fp.bounds],
                                 "w_m": round(max(fp.bounds[2] - fp.bounds[0], fp.bounds[3] - fp.bounds[1]) * PT_TO_M, 3),
                                 **_wall_report(con, fp, wm_pt)}
    if "churrasqueira" in pieces and "coifa" in pieces:   # coifa fixada na churrasqueira (MODULE_SUPPORT): pegada sobre ela?
        ch = [box_footprint_pt(b, PT_TO_IN) for b in room if b.get("kind") == "churrasqueira"][0]
        co = [box_footprint_pt(b, PT_TO_IN) for b in room if b.get("kind") == "coifa"][0]
        pieces["coifa"]["over_churrasqueira_frac"] = round(co.intersection(ch).area / co.area, 3)
    return pieces


def screen(con, wm_pt):
    """Etapa 1 (so o planejador da A.S.): onde as pecas caem, distancia a parede, programa e motivo de descarte."""
    STATE["diag"] = []
    room, out = sl.build_boxes(con, RID)
    kinds = Counter(b.get("kind") for b in room)
    return {"boxes_r001": len(room), "program_present": {k: kinds.get(k, 0) for k in PROGRAM_KINDS},
            "planner_dropped": [list(d) for d in out.get("dropped", [])], "pinned_diag": list(STATE["diag"]),
            "pieces": _pieces(con, room, wm_pt)}


def circulation_if_placed(con):
    """Para a posicao que passou no `_slide` mas que o planejador descartou pelo `circulation_gate`: refaz o planejador com
    o gate do planejador permissivo (so para a peca entrar) e devolve o veredito COMPLETO do mesmo gate (portais e larguras)."""
    from tools.validation import circulation_gate as cg
    orig = cg.GateSession

    class _Permissive(orig):
        def check(self, boxes, decide_only=False):
            return {"result": "PASS", "checks": {}}
    cg.GateSession = _Permissive
    try:
        boxes, _out = sl.build_boxes(con, RID)
    finally:
        cg.GateSession = orig
    res = cg.gate(con, boxes, RID)
    cor = res["checks"].get("corredor_principal", {})
    return {"result": res["result"], "corredor_principal": cor.get("result"), "reason_code": cor.get("reason_code"),
            "portais": [{k: q.get(k) for k in ("portal_role", "conectado", "status", "w_empty_m", "w_furnished_m")}
                        for q in cor.get("portais", [])]}


def measure(con, base, program, twin, known_support, prateleira_to_wall=False):
    """Etapa 2: apartamento inteiro (`collect_boxes`) + pre-voo + gemeo x baseline + programa + apoio por modulo."""
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, summary = collect_boxes(con)
        _b, out = sl.build_boxes(con, RID)
    wm_pt = wall_mass_pt(con)
    room = [b for b in boxes if b.get("room") == ROOM]
    if prateleira_to_wall:   # V4: translada a prateleira ate a face real da parede (lado oeste)
        for b in room:
            if b.get("kind") == "prateleira_servico":
                fp = box_footprint_pt(b, PT_TO_IN)
                dx_in = -fp.distance(wm_pt) * PT_TO_IN
                b["corners"] = [[x + dx_in, y] for x, y in b["corners"]]
                for k in ("cx_in", "x_in"):
                    if k in b:
                        b[k] += dx_in
    pieces = _pieces(con, room, wm_pt)
    pre =layout_preflight.preflight(con, copy.deepcopy(boxes), summary, twin)
    rooms = {r["id"]: str(r.get("name") or r["id"]) for r in con["rooms"]}
    reports = box_geometry.validate_boxes(con, copy.deepcopy(boxes), PLANTA_74_CONSENSUS, rooms)
    reg = defect_baseline.regression(reports, base, program)
    border = set(twin.get("borderline", ()))
    sup = check_modules(boxes, con)
    sup_room = {f["module"]: f["gap_m"] for f in sup["findings"] if f["room"] == ROOM}
    sup_new = sorted(f"{f['room']}|{f['module']}" for f in sup["findings"] if (f["room"], f["module"]) not in known_support)
    sup_worse = sorted(f"{f['room']}|{f['module']}" for f in sup["findings"]
                       if (f["room"], f["module"]) in known_support
                       and f["gap_m"] > known_support[(f["room"], f["module"])] + EPS_DEPTH)
    kinds = Counter(b.get("kind") for b in room)
    return {
        "boxes_total": len(boxes), "boxes_r001": len(room),
        "r001_kinds": dict(sorted(kinds.items())),
        "program_present": {k: kinds.get(k, 0) for k in PROGRAM_KINDS},
        "planner_dropped": [list(d) for d in out.get("dropped", [])],
        "pieces": pieces,
        "preflight": pre["status"],
        "preflight_r001": {r["gate"]: r["status"] for r in pre["rooms"] if r["room_id"] == RID},
        "preflight_blocking": [{"room_id": r["room_id"], "gate": r["gate"], "reasons": r["reasons"]} for r in pre["blocking"]],
        "twin_new": [d["key"] for d in reg["new"] if d["key"] not in border],
        "twin_worse": [d["key"] for d in reg["worse"]],
        "twin_resolved": reg["resolved"], "twin_vanished_with_piece": reg["vanished_with_piece"],
        "missing_program": reg["missing_program"],
        "support_r001": sup_room, "support_new": sup_new, "support_worse": sup_worse,
    }


def variants(zones_probe, walls_m):
    """Grade: largura x parede x posicao (centro ao longo da face). Faixa = extensao da parede no consensus (start/end)
    recortada pela zona de colocacao do planejador (zona menos parede)."""
    out = [{"id": "atual", "desc": "planejador sem variacao (churrasqueira 1,00 m na constante)"},
           {"id": "p7_085", "desc": "reproducao do p7: churrasqueira/coifa [0,85, 0,70] na constante",
            "widths": [0.85, 0.70]}]
    for w in WIDTHS:
        out.append({"id": f"const_{w:.2f}", "desc": f"constante atual, largura {w:.2f} (posicao do planejador)",
                    "support": "constante", "widths": [w]})
    socz, asz = zones_probe[f"{sl.SOCIAL}-parede"], zones_probe[f"{sl.AS}-parede"]
    def _rng(w, axis, z):
        lo, hi = sorted((w["start_m"][axis], w["end_m"][axis]))
        return max(z.bounds[axis], lo), min(z.bounds[axis + 2], hi)
    faces = {   # (zona, lado, faixa da parede no eixo livre recortada pela zona)
        "m004": (f"{sl.SOCIAL}-parede", "north", *_rng(walls_m["m004"], 0, socz)),
        "m013": (f"{sl.AS}-parede", "east", *_rng(walls_m["m013"], 1, asz)),
        "m001": (f"{sl.SOCIAL}-parede", "south", *_rng(walls_m["m001"], 0, socz)),
    }
    for wall, (zone, side, lo, hi) in faces.items():
        for w in WIDTHS:
            c = lo + w / 2
            while c <= hi - w / 2 + 1e-9:
                out.append({"id": f"{wall}_{w:.2f}_{c:.2f}", "support": wall, "zone": zone, "side": side,
                            "widths": [w], "along": round(c, 4), "pin": True,
                            "desc": f"{wall} ({side}), largura {w:.2f}, centro {c:.2f} m"})
                c += STEP
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).with_name("as1_real_wall_alternatives.json")))
    args = ap.parse_args()
    t0 = time.time()
    sha_before = _sha(PLANTA_74_CONSENSUS)
    con = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
    STATE["wall_m"] = _wall_m(con)
    base = json.loads((ROOT / "artifacts/review/fp055/p4/defect_baseline.json").read_text("utf-8"))["defects"]
    program = json.loads((ROOT / "artifacts/review/fp056/p2/program_baseline.json").read_text("utf-8"))["program"]
    twin = layout_preflight.planta74_twin(PLANTA_74_CONSENSUS)
    # baseline de apoio = o que o layout atual mede (travado em tests/test_fp056_p4_support_check.py KNOWN_MODULES)
    with contextlib.redirect_stdout(io.StringIO()):
        cur, _ = collect_boxes(con)
    known_support = {(f["room"], f["module"]): f["gap_m"] for f in check_modules(cur, con)["findings"]}
    # zonas do planejador (com a variacao V2) para ler as faixas das faces
    from shapely.ops import unary_union

    from tools.rooms.shared.clearance import soft_barrier_masses_pt
    sm = sl.build_spatial_model(con, RID)
    cell = sl._cell_m(sm)
    bm = [_scale(m, PT_TO_M, PT_TO_M, origin=(0, 0)) for _i, m, _t in soft_barrier_masses_pt(con)]
    cell = cell.difference(unary_union(bm))
    cell = max(cell.geoms, key=lambda g: g.area) if cell.geom_type != "Polygon" else cell
    zones, _err = sl._split_zones(con, RID, cell)
    faces_m = {}
    for wid in WALL_IDS:
        w = next(x for x in con["walls"] if x["id"] == wid)
        faces_m[wid] = {"start_m": [round(c * PT_TO_M, 3) for c in w["start"]], "end_m": [round(c * PT_TO_M, 3) for c in w["end"]],
                        "thickness_m": round(float(w["thickness"]) * PT_TO_M, 3),
                        "openings": [{"id": o["id"], "kind_v5": o.get("kind_v5"), "width_m": round(o["opening_width_pts"] * PT_TO_M, 3),
                                      "center_m": [round(c * PT_TO_M, 3) for c in o["center"]]}
                                     for o in con["openings"] if o.get("wall_id") == wid]}
    wm_pt = wall_mass_pt(con)
    rows = []
    for v in variants(zones, faces_m):
        STATE["variant"] = v if v["id"] != "atual" else None
        s = screen(con, wm_pt)
        ch, co = s["pieces"].get("churrasqueira"), s["pieces"].get("coifa")
        hosted = bool(ch and co and ch["in_contact"] and co["in_contact"])
        row = {"variant": v, "screen": s, "hosted_on_real_wall": hosted, "gates": None}
        if any(k == "churrasqueira" and "circulation_gate" in why for k, why in s["planner_dropped"]):
            row["circulation_if_placed"] = circulation_if_placed(con)
        # etapa 2 so para as referencias e para quem o planejador colocou junto da parede pedida (sem limiar novo: a folga
        # medida sai no JSON e o "encostado" continua sendo gap <= EPS_DEPTH); o resto nem chega a ser alternativa
        if v.get("support") not in WALL_IDS or hosted or (ch and ch["nearest_wall"] == v["support"]):
            row["gates"] = measure(con, base, program, twin, known_support)
        rows.append(row)
        g = row["gates"]
        print(f"{v['id']:22} ch={'-' if not ch else (ch['gap_m'], ch['nearest_wall'])} banc={s['program_present']['bancada_gourmet']} "
              f"banq={s['program_present']['banqueta']} mesa={s['program_present']['mesa_externa']} "
              + ("" if g is None else f"boxes={g['boxes_total']} pre={g['preflight']} new={len(g['twin_new'])} "
                 f"worse={len(g['twin_worse'])} miss={g['missing_program']}"), flush=True)
    # V4: prateleira encostada na face real da parede oeste, sobre o atual e sobre a 1a variante viavel de cada parede x largura
    STATE["variant"] = None
    prat = [{"on": "atual", **measure(con, base, program, twin, known_support, prateleira_to_wall=True)}]
    seen = set()
    for r in rows:
        g, v = r["gates"], r["variant"]
        if g and r["hosted_on_real_wall"] and g["preflight"] == "PASS" and not g["twin_new"] and not g["twin_worse"]:
            k = (v["support"], v["widths"][0])
            if k not in seen:
                seen.add(k)
                STATE["variant"] = v
                prat.append({"on": v["id"], **measure(con, base, program, twin, known_support, prateleira_to_wall=True)})
    STATE["variant"] = None
    sha_after = _sha(PLANTA_74_CONSENSUS)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "tools", "core", "fixtures"], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip())
    doc = {"what": "FP-056 #442/#488: churrasqueira/coifa/prateleira encostadas em parede real (gemeo em caixas, L1)",
           "commit": commit, "code_dirty": dirty, "PT_TO_M": PT_TO_M, "EPS_DEPTH_m": EPS_DEPTH,
           "consensus": str(PLANTA_74_CONSENSUS.relative_to(ROOT)).replace("\\", "/"),
           "consensus_sha256_before": sha_before, "consensus_sha256_after": sha_after,
           "planner_constants_m": {"_AS_MAX_X_M": sl._AS_MAX_X_M, "_AS_MIN_Y_M": sl._AS_MIN_Y_M, "_TEC_MIN_X_M": sl._TEC_MIN_X_M},
           "walls": faces_m,
           "spatial_model_r001": {"blind_wall_candidates": sm.get("blind_wall_candidates"),
                                  "walls": sm.get("walls"),
                                  "circulation_zones_bounds_m": [[round(c * PT_TO_M, 3) for c in g.bounds]
                                                                 for g in sm["_geom"].get("circ") or []],
                                  "openings": [{"id": o.get("id"), "kind": o.get("kind"), "wall_id": o.get("wall_id"),
                                                "center_m": [round(c * PT_TO_M, 3) for c in o["center"]]}
                                               for o in sm.get("openings") or []]},
           "zone_faces_m": {k: [round(c, 3) for c in zones[k].bounds] for k in (f"{sl.SOCIAL}-parede", f"{sl.AS}-parede")},
           "known_support_baseline": {f"{a}|{b}": g for (a, b), g in sorted(known_support.items())},
           "known_program_gaps": sorted(known_gaps.load().get("program", {})),
           "rows": rows, "prateleira_to_wall": prat, "seconds": round(time.time() - t0)}
    Path(args.out).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"ok {len(rows)} variantes + {len(prat)} prateleira em {doc['seconds']} s; consensus intacto={sha_before == sha_after}")
    return 0 if sha_before == sha_after else 1


if __name__ == "__main__":
    sys.exit(main())
