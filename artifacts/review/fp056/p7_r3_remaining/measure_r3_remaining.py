"""#502 / R3 (#495): mede EM MEMORIA (nada aplicado) as alternativas restantes: cozinha, tapete Banho 01, papeleira Banho 02.

Uso (da raiz do repo):
  PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp056/p7_r3_remaining/measure_r3_remaining.py \
      artifacts/review/fp056/p7_r3_remaining/r3_remaining_alternatives.json
Gemeo em caixas (L1) contra o baseline FP-055 P4 + pre-voo (layout_preflight): a mesma maquinaria dos gates do CI.
"""
import contextlib
import copy
import io
import json
import subprocess
import sys

from tools.furnish_apartment import collect_boxes
from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS as C
from tools.validation import box_geometry as bx
from tools.validation import defect_baseline as db
from tools.validation import known_gaps, layout_preflight

con = json.loads(C.read_text("utf-8"))
with contextlib.redirect_stdout(io.StringIO()):
    BOXES, SUMMARY = collect_boxes(con)
ROOMS = {r["id"]: str(r.get("name") or r["id"]) for r in con["rooms"]}
with open("artifacts/review/fp055/p4/defect_baseline.json", encoding="utf-8") as fh:
    BASE = json.load(fh)["defects"]
BORDER = set(known_gaps.load().get("twin_borderline", {}))
IN2CM = 2.54
KITCHEN, B1, B2 = "COZINHA", "BANHO 01", "BANHO 02"
T_COOK, T_SINK = "r004|OBJECTS|backsplash+cooktop_module", "r004|OBJECTS|backsplash+sink_module"
T_RUG, T_PAPER = "r005|OBJECTS|Enxoval+Vaso", "r006|OBJECTS|Bancada+Enxoval"


def measure(name, rid, mutate, target):
    boxes = copy.deepcopy(BOXES)
    note = mutate(boxes)
    with contextlib.redirect_stdout(io.StringIO()):
        reports = bx.validate_boxes(con, copy.deepcopy(boxes), C, ROOMS)
        reg = db.regression(reports, BASE)
        pre = layout_preflight.preflight(con, boxes, SUMMARY, layout_preflight.planta74_twin(C))
    new = [d["key"] for d in reg["new"] if d["key"] not in BORDER]
    worse = sorted(d["key"] for d in reg["worse"])
    left = [f for f in reports[rid]["findings"] if f.get("check") == "OBJECTS" and db.key(rid, f) == target]
    return {"alternative": name, "room": rid, "target": target, "applied": note,
            "target_measure_m": round(db.measure(left[0]), 5) if left else 0.0, "target_resolved": not left,
            "new_defects": new, "worse_defects": worse, "preflight_apartment": pre["status"],
            "preflight_room": sorted({r["gate"] + ":" + r["status"] for r in pre["rooms"] if r["room_id"] == rid})}


def sel(boxes, room, pred):
    return [b for b in boxes if str(b.get("room")) == room and pred(b)]


def by_module(room, module):
    return lambda bs: sel(bs, room, lambda b: b.get("module") == module)


def by_kind(room, kind):
    return lambda bs: sel(bs, room, lambda b: b.get("kind") == kind)


def shift(bs, dx=0.0, dy=0.0):
    for b in bs:
        b["x0"], b["x1"], b["y0"], b["y1"] = b["x0"] + dx, b["x1"] + dx, b["y0"] + dy, b["y1"] + dy
        if b.get("corners"):
            b["corners"] = [[c[0] + dx, c[1] + dy] for c in b["corners"]]


def set_edges(b, **edges):
    b.update(edges)
    b["corners"] = [[b["x0"], b["y0"]], [b["x1"], b["y0"]], [b["x1"], b["y1"]], [b["x0"], b["y1"]]]


def bbox(bs):
    return min(b["x0"] for b in bs), min(b["y0"] for b in bs), max(b["x1"] for b in bs), max(b["y1"] for b in bs)


def nothing(_bs):
    return "nada"


# ---- cozinha: backsplash x vidro do cooktop / cuba (4,6 cm) ------------------------------------------------------------
bsp, cook, sink = by_module(KITCHEN, "backsplash"), by_module(KITCHEN, "cooktop_module"), by_module(KITCHEN, "sink_module")


def k_shift(bs):
    d = max(b["x1"] for b in bsp(bs)) - min(b["x0"] for b in cook(bs) + sink(bs))
    shift(cook(bs) + sink(bs), dx=d)
    return f"cooktop_module e sink_module +{d * IN2CM:.1f} cm para longe da parede (frente do backsplash)"


def k_raise(bs):
    top = max(b["z0_in"] + b["h_in"] for b in cook(bs) + sink(bs) if b.get("kind") in ("kc_vidro", "kc_cuba_rim"))
    for b in bsp(bs):
        dz = top - b["z0_in"]
        b["z0_in"], b["h_in"] = top, max(b["h_in"] - dz, 0.01)
    return f"backsplash comeca no topo do vidro/borda da cuba (z0 {top * IN2CM:.1f} cm)"


def k_notch(bs):
    lim = max(b["x1"] for b in bsp(bs))
    for b in cook(bs) + sink(bs):
        if b["x0"] < lim:
            set_edges(b, x0=lim)
    return "vidro do cooktop e cuba recortados atras do backsplash (comecam na face dele)"


# ---- Banho 01: tapete x vaso (16,4 cm) ----------------------------------------------------------------------------------
vaso, rug = by_module(B1, "Vaso"), by_kind(B1, "kb_tapete")


def r_cut(bs):
    vx0, vy0, vx1, vy1 = bbox(vaso(bs))
    t = rug(bs)[0]
    w, d = t["x1"] - t["x0"], t["y1"] - t["y0"]
    opts = [(edge, v, area) for edge, v, area, ok in (
        ("x1", vx0, (vx0 - t["x0"]) * d, t["x1"] > vx0 > t["x0"]),
        ("x0", vx1, (t["x1"] - vx1) * d, t["x0"] < vx1 < t["x1"]),
        ("y1", vy0, w * (vy0 - t["y0"]), t["y1"] > vy0 > t["y0"]),
        ("y0", vy1, w * (t["y1"] - vy1), t["y0"] < vy1 < t["y1"])) if ok]
    edge, v, area = max(opts, key=lambda o: o[2])
    old = w * d
    set_edges(t, **{edge: v})
    return (f"tapete encurtado pelo lado {edge} ate a borda do vaso: {area * 6.4516e-4:.3f} m2 de {old * 6.4516e-4:.3f} m2 "
            f"(perde {(1 - area / old):.0%})")


def r_remove(bs):
    bs.remove(rug(bs)[0])
    return "tapete retirado do Banho 01"


# ---- Banho 02: papeleira x gabinete (9,4 cm) ----------------------------------------------------------------------------
paper, counter = by_kind(B2, "kb_papeleira"), by_module(B2, "Bancada")


def p_raise(bs):
    top = max(b["z0_in"] + b["h_in"] for b in counter(bs))
    for b in paper(bs):
        b["z0_in"] = top + 0.4
    return f"papeleira acima do tampo da bancada (z0 {(top + 0.4) * IN2CM:.1f} cm; atual 66 cm)"


def p_remove(bs):
    for b in paper(bs):
        bs.remove(b)
    return "papeleira retirada do Banho 02"


def p_slide(dx, dy):
    def run(bs):
        shift(paper(bs), dx / IN2CM, dy / IN2CM)
        return f"papeleira deslocada ({dx:+d}, {dy:+d}) cm ao longo da parede"
    return run


def p_best_slide():
    """Menor deslocamento AO LONGO da parede (passo 5 cm, ate 120 cm) que resolve sem defeito novo/pior.
    Perpendicular nao vale: a peca sairia da parede e ficaria flutuando (os gates nao veem isso)."""
    p = paper(BOXES)[0]
    along_y = (p["y1"] - p["y0"]) > (p["x1"] - p["x0"])        # 10 cm de profundidade x 14 cm ao longo da parede
    for d in range(5, 121, 5):
        for dx, dy in ((0, d), (0, -d)) if along_y else ((d, 0), (-d, 0)):
            r = measure(f"(b) deslocar ao longo da parede {dx:+d},{dy:+d} cm", "r006", p_slide(dx, dy), T_PAPER)
            if r["target_resolved"] and not r["new_defects"] and not r["worse_defects"]:
                return r
    return {"alternative": "(b) deslocar ao longo da parede ate 120 cm (passo 5 cm)", "room": "r006", "target": T_PAPER,
            "target_resolved": False, "applied": "nenhum deslocamento resolve sem defeito novo/pior"}


def main(path):
    out = [measure("atual", "r004", nothing, t) for t in (T_COOK, T_SINK)]
    for name, fn in (("(a) deslocar cooktop+cuba", k_shift), ("(b) backsplash acima do vidro/borda", k_raise),
                     ("(c) recortar vidro/cuba pela face do backsplash", k_notch)):
        out += [measure(name, "r004", fn, t) for t in (T_COOK, T_SINK)]
    out.append(measure("atual", "r005", nothing, T_RUG))
    out.append(measure("(a) encolher o tapete ate a borda do vaso", "r005", r_cut, T_RUG))
    out.append(measure("(b) tirar o tapete", "r005", r_remove, T_RUG))
    out.append(measure("atual", "r006", nothing, T_PAPER))
    out.append(measure("(a) papeleira acima do tampo", "r006", p_raise, T_PAPER))
    out.append(p_best_slide())
    out.append(measure("(c) tirar a papeleira", "r006", p_remove, T_PAPER))
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"generated_by": "artifacts/review/fp056/p7_r3_remaining/measure_r3_remaining.py (em memoria; nada aplicado)",
                   "commit": commit, "results": out}, fh, ensure_ascii=False, indent=1)
    for r in out:
        print(r["alternative"], "|", r["target"], "| resolvido:", r["target_resolved"], "| novos:", r.get("new_defects"),
              "| piores:", r.get("worse_defects"), "| pre:", r.get("preflight_apartment"), "|", r.get("applied"))


if __name__ == "__main__":
    main(sys.argv[1])
