"""Compara o PLANO (boxes.json dos brains) com o MATERIALIZADO (inspect.json do .skp
reaberto). Puro, sem SketchUp.

Tolerância de reprodução: 1 mm. O plano e o .skp vêm da MESMA aritmética (polegadas
do SketchUp); o inspect arredonda para 0,1 mm. Não é tolerância de projeto — é o
"o .rb desenhou o que o Python mandou?".

Checagens adicionais (as do contrato dos brains, refeitas sobre o .skp):
  - apoio: peça com z0=0 tem z_min ~ 0 no .skp; elevadas mantêm z0
  - contenção: toda peça dentro da face interna das paredes do cômodo
  - colisão: interseção 3D entre peças de MÓVEIS diferentes, exceto os que o
    próprio box declara furniture_overlap=ALLOW (tapete, pendente...)
  - portas: nenhuma peça não-caminhável no quadrado de giro da folha (largura x largura)
uso: compare_furnish.py <boxes.json> <inspect.json> <consensus.json> <out.json>"""
import json
import sys

IN = 0.0254
TOL = 0.001

boxes_d = json.load(open(sys.argv[1], encoding="utf-8"))
insp = json.load(open(sys.argv[2], encoding="utf-8"))["result"]
con = json.load(open(sys.argv[3], encoding="utf-8"))
s = boxes_d["pt_to_m"]
boxes = boxes_d["boxes"]


def exp_bbox(b):
    z0 = float(b.get("z0_in") or 0.0)
    if b.get("profile_world"):
        pts = [tuple(map(float, p)) for p in b["profile_world"]]
        ev = [float(v) for v in (b.get("extrude_vec") or [0, 0, 0])]
        pts = pts + [(p[0] + ev[0], p[1] + ev[1], p[2] + ev[2]) for p in pts]
        lo = [min(p[i] for p in pts) for i in range(3)]
        hi = [max(p[i] for p in pts) for i in range(3)]
    else:
        xs = [float(c[0]) for c in b["corners"]]
        ys = [float(c[1]) for c in b["corners"]]
        lo = [min(xs), min(ys), z0]
        hi = [max(xs), max(ys), z0 + float(b["h_in"])]
    return [v * IN for v in lo], [v * IN for v in hi]


nodes = insp["nodes"]
mods = {n["name"]: n for n in nodes if "/" not in n["path"]}
pieces = {}
for n in nodes:
    if n["path"].count("/") == 1:
        pieces.setdefault(n["path"].split("/")[0], []).append(n)

rows, unmatched = [], []
used = set()
for i, b in enumerate(boxes):
    mod = f"{b['room']} · {b['module']}"
    lo, hi = exp_bbox(b)
    label = b.get("label") or b["kind"]
    cands = [p for p in pieces.get(mod, []) if p["pid"] not in used and p["name"] == label]
    if not cands:
        unmatched.append({"i": i, "module": mod, "label": label})
        continue
    def err(p):
        w = p["bbox_world_m"]
        return max(max(abs(w["min"][k] - lo[k]), abs(w["max"][k] - hi[k])) for k in range(3))
    best = min(cands, key=err)
    used.add(best["pid"])
    rows.append({"i": i, "module": mod, "label": label, "kind": b["kind"], "err_m": round(err(best), 5),
                 "exp_min": [round(v, 4) for v in lo], "exp_max": [round(v, 4) for v in hi],
                 "skp_min": best["bbox_world_m"]["min"], "skp_max": best["bbox_world_m"]["max"],
                 "material": best["material"], "z0_plan_m": round(float(b.get("z0_in") or 0) * IN, 4),
                 "overlap_policy": (b.get("interaction_policy") or {}).get("furniture_overlap"),
                 "circulation": (b.get("interaction_policy") or {}).get("circulation"),
                 "pid": best["pid"]})

extra = [p["path"] for m, ps in pieces.items() for p in ps if p["pid"] not in used]
bad_fit = [r for r in rows if r["err_m"] > TOL]

# contenção: face interna = polígono do cômodo (eixo das paredes) recuado meia espessura
room_poly = con["rooms"][0]["polygon_pts"]
t = float(con.get("wall_thickness_pts", 5.4)) / 2.0
rx = [min(p[0] for p in room_poly) + t, max(p[0] for p in room_poly) - t]
ry = [min(p[1] for p in room_poly) + t, max(p[1] for p in room_poly) - t]
inner = {"x": [round(v * s, 4) for v in rx], "y": [round(v * s, 4) for v in ry]}
outside = [r for r in rows if r["skp_min"][0] < inner["x"][0] - TOL or r["skp_max"][0] > inner["x"][1] + TOL
           or r["skp_min"][1] < inner["y"][0] - TOL or r["skp_max"][1] > inner["y"][1] + TOL]

# colisão entre móveis diferentes (AABB das PEÇAS — exato para peças alinhadas aos eixos)
def inter(a, b):
    return all(min(a["skp_max"][k], b["skp_max"][k]) - max(a["skp_min"][k], b["skp_min"][k]) > TOL for k in range(3))
coll = []
for a_i, a in enumerate(rows):
    for b in rows[a_i + 1:]:
        if a["module"] == b["module"] or "ALLOW" in (a["overlap_policy"], b["overlap_policy"]):
            continue
        if inter(a, b):
            coll.append([a["module"] + "/" + a["label"], b["module"] + "/" + b["label"]])

# apoio por móvel
support = {}
for r in rows:
    m = support.setdefault(r["module"], {"z_min_skp": 9e9, "z0_plan_min": 9e9})
    m["z_min_skp"] = round(min(m["z_min_skp"], r["skp_min"][2]), 4)
    m["z0_plan_min"] = round(min(m["z0_plan_min"], r["z0_plan_m"]), 4)
floating = {k: v for k, v in support.items() if abs(v["z_min_skp"] - v["z0_plan_min"]) > TOL}

# portas: quadrado de giro dentro do cômodo
walls = {w["id"]: w for w in con["walls"]}
door_hits = []
for o in con["openings"]:
    if "door" not in o.get("kind", o.get("kind_v5", "")):
        continue
    w = walls[o["wall_id"]]
    half = float(o["opening_width_pts"]) / 2
    cx, cy = map(float, o["center"])
    W = float(o["opening_width_pts"])
    if w["orientation"] == "v":
        x0 = rx[0] if abs(cx - rx[0] + t) < abs(cx - rx[1] - t) else rx[1] - W
        zone = {"x": [x0 * s, (x0 + W) * s], "y": [(cy - half) * s, (cy + half) * s]}
    else:
        y0 = ry[0] if abs(cy - ry[0] + t) < abs(cy - ry[1] - t) else ry[1] - W
        zone = {"x": [(cx - half) * s, (cx + half) * s], "y": [y0 * s, (y0 + W) * s]}
    for r in rows:
        if r["circulation"] == "WALKABLE":
            continue
        if (min(r["skp_max"][0], zone["x"][1]) - max(r["skp_min"][0], zone["x"][0]) > TOL and
                min(r["skp_max"][1], zone["y"][1]) - max(r["skp_min"][1], zone["y"][0]) > TOL):
            door_hits.append({"door": o["id"], "piece": r["module"] + "/" + r["label"]})

mats = sorted({r["material"] for r in rows if r["material"]})
tex = {m["name"]: m["texture"] for m in insp["materials"] if m["texture"]}
out = {"n_boxes": len(boxes), "n_matched": len(rows), "unmatched": unmatched, "extra_skp_pieces": extra,
       "max_err_m": max((r["err_m"] for r in rows), default=None), "bad_fit": bad_fit,
       "inner_bounds_m": inner, "outside_room": [(r["module"], r["label"]) for r in outside],
       "collisions": coll, "support": support, "floating": floating, "door_zone_hits": door_hits,
       "modules": sorted(mods), "materials_used": mats, "textured_materials": tex,
       "loose_root": {k: insp["counts"][k] for k in ("loose_faces_at_root", "loose_edges_at_root")},
       "rows": rows}
json.dump(out, open(sys.argv[4], "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(json.dumps({k: out[k] for k in ("n_boxes", "n_matched", "unmatched", "extra_skp_pieces", "max_err_m",
                                      "outside_room", "collisions", "floating", "door_zone_hits", "loose_root",
                                      "textured_materials")}, ensure_ascii=False, indent=0)[:4000])
