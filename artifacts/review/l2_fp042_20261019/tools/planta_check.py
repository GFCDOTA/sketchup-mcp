"""Checagens L2 por cômodo sobre o .skp mobiliado REABERTO (inspect.json) da planta_74.
Puro (shapely), sem SketchUp. Fontes de verdade:
  - plano: boxes.json (brains de produção, com room/module)
  - paredes: _shell_polygon.json do build (o polígono EXTRUDADO de verdade, em pt)
  - portas: consensus (swing_side/hinge_side conferidos contra o PDF por door_swing_audit)
Tolerâncias: reprodução plano×SKP 1 mm (aritmética idêntica; inspect arredonda 0,1 mm).
Penetração em parede/giro de porta: reportada em cm, sem limiar inventado — o
contrato do projeto é "não invadir"; o que é peça HOSPEDADA na parede (revestimento,
painel, espelho) aparece separado pelo host/interaction_policy que o próprio box declara.
uso: planta_check.py <boxes.json> <inspect.json> <shell_polygon.json> <consensus.json> <out.json>"""
import json
import math
import sys
from collections import defaultdict

from shapely.geometry import Polygon, shape
from shapely.ops import unary_union

IN, S = 0.0254, 0.0259
boxes = json.load(open(sys.argv[1], encoding="utf-8"))["boxes"]
insp = json.load(open(sys.argv[2], encoding="utf-8"))["result"]
shell_js = json.load(open(sys.argv[3], encoding="utf-8"))
con = json.load(open(sys.argv[4], encoding="utf-8"))


def shell_polys(js):
    out = []
    for p in js.get("polygons") or js.get("pieces") or []:
        if isinstance(p, dict) and "outer" in p:
            out.append(Polygon([(x * S, y * S) for x, y in p["outer"]],
                               [[(x * S, y * S) for x, y in h] for h in p.get("holes", [])]))
        elif isinstance(p, dict) and "type" in p:
            g = shape(p)
            out.append(Polygon([(x * S, y * S) for x, y in g.exterior.coords],
                               [[(x * S, y * S) for x, y in r.coords] for r in g.interiors]))
    return unary_union(out)


walls = shell_polys(shell_js)
nodes = insp["nodes"]
pieces = defaultdict(list)
for n in nodes:
    if n["path"].count("/") == 1:
        pieces[n["path"].split("/")[0]].append(n)
mods = {n["name"]: n for n in nodes if "/" not in n["path"]}

# --- plano × SKP por peça
used, rows, unmatched = set(), [], []
for i, b in enumerate(boxes):
    mod = f"{b['room']} · {b['module']}"
    label = b.get("label") or b["kind"]
    z0 = float(b.get("z0_in") or 0)
    if b.get("profile_world"):
        pts = [tuple(map(float, p)) for p in b["profile_world"]]
        ev = [float(v) for v in (b.get("extrude_vec") or [0, 0, 0])]
        pts += [(p[0] + ev[0], p[1] + ev[1], p[2] + ev[2]) for p in pts]
        lo = [min(p[k] for p in pts) * IN for k in range(3)]
        hi = [max(p[k] for p in pts) * IN for k in range(3)]
        fp = Polygon([(p[0] * IN, p[1] * IN) for p in pts]).convex_hull
    else:
        xs = [float(c[0]) for c in b["corners"]]
        ys = [float(c[1]) for c in b["corners"]]
        lo = [min(xs) * IN, min(ys) * IN, z0 * IN]
        hi = [max(xs) * IN, max(ys) * IN, (z0 + float(b["h_in"])) * IN]
        fp = Polygon([(c[0] * IN, c[1] * IN) for c in b["corners"]]).buffer(0)
    cands = [p for p in pieces.get(mod, []) if p["pid"] not in used and p["name"] == label]
    if not cands:
        unmatched.append((mod, label))
        continue

    def err(p):
        w = p["bbox_world_m"]
        return max(max(abs(w["min"][k] - lo[k]), abs(w["max"][k] - hi[k])) for k in range(3))
    best = min(cands, key=err)
    used.add(best["pid"])
    ip = b.get("interaction_policy") or {}
    rows.append({"room": b["room"], "module": b["module"], "label": label, "kind": b["kind"],
                 "err_m": round(err(best), 5), "fp": fp, "z": [round(lo[2], 4), round(hi[2], 4)],
                 "material": best["material"], "host": (b.get("host") or {}).get("relationship", "NONE"),
                 "overlap": ip.get("furniture_overlap"), "circ": ip.get("circulation"),
                 "intent": b.get("geometry_intent")})

# --- giro das portas (quarto de círculo real, do lado do swing, a partir da dobradiça)
W = {w["id"]: w for w in con["walls"]}
swings = {}
for o in con["openings"]:
    if o.get("kind") != "door" and o.get("kind_v5") != "interior_door":
        continue
    w = W[o["wall_id"]]
    horiz = abs(w["start"][1] - w["end"][1]) < 1e-6
    cx, cy = o["center"]
    hw = float(o["opening_width_pts"]) / 2
    t = float(w.get("thickness", 5.4)) / 2
    sgn = 1 if o.get("swing_side") == "pos" else -1
    along, cross = (cx, cy) if horiz else (cy, cx)
    h_al = along - hw if o.get("hinge_side") == "left" else along + hw
    u = 1 if o.get("hinge_side") == "left" else -1  # da dobradiça para o outro batente
    h_cr = cross + sgn * t
    r = 2 * hw
    pts = [(h_al, h_cr)] + [(h_al + u * r * math.cos(a), h_cr + sgn * r * math.sin(a))
                            for a in [k * math.pi / 2 / 24 for k in range(25)]]
    pts = [(a, c) if horiz else (c, a) for a, c in pts]
    swings[o["id"]] = Polygon([(x * S, y * S) for x, y in pts])

per_room = defaultdict(lambda: {"pieces": 0, "max_err_m": 0.0, "wall_penetration": [], "hosted_in_wall": [],
                                "door_swing_hits": [], "materials": defaultdict(set), "modules": set(),
                                "elevated_modules": {}})
for r in rows:
    R = per_room[r["room"]]
    R["pieces"] += 1
    R["max_err_m"] = max(R["max_err_m"], r["err_m"])
    R["modules"].add(r["module"])
    if r["material"]:
        R["materials"][r["module"]].add(r["material"])
    inter = r["fp"].intersection(walls)
    if inter.area > 1e-6:
        # profundidade ~ área / maior dimensão da interseção
        minx, miny, maxx, maxy = inter.bounds
        depth = round(inter.area / max(maxx - minx, maxy - miny, 1e-9) * 100, 1)
        item = {"module": r["module"], "label": r["label"], "area_cm2": round(inter.area * 1e4, 1),
                "depth_cm": depth, "host": r["host"], "intent": r["intent"]}
        (R["hosted_in_wall"] if r["host"] != "NONE" or r["intent"] in ("SURFACE", "SKIN") or
         r["overlap"] != "EXCLUSIVE" else R["wall_penetration"]).append(item)
    if r["circ"] != "WALKABLE" and r["z"][0] < 2.10:   # folha de porta vai até 2,10 m
        for did, sw in swings.items():
            a = r["fp"].intersection(sw).area
            if a > 1e-4:
                R["door_swing_hits"].append({"door": did, "module": r["module"], "label": r["label"],
                                             "area_cm2": round(a * 1e4, 1), "z": r["z"]})
for mname, m in mods.items():
    if " · " in mname:
        room = mname.split(" · ")[0]
        zmin = m["bbox_world_m"]["min"][2]
        if zmin > 0.02:
            per_room[room]["elevated_modules"][mname.split(" · ", 1)[1]] = zmin

out = {"n_boxes": len(boxes), "n_matched": len(rows), "unmatched": unmatched,
       "max_err_m": max((r["err_m"] for r in rows), default=None),
       "rooms": {k: {**v, "modules": sorted(v["modules"]),
                     "materials": {m: sorted(s) for m, s in v["materials"].items()}}
                 for k, v in per_room.items()},
       "loose_root": {k: insp["counts"][k] for k in ("loose_faces_at_root", "loose_edges_at_root")},
       "locked_shell": sorted(n["name"] for n in nodes if n["locked"] and "/" not in n["path"])}
json.dump(out, open(sys.argv[5], "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)
summ = {k: {"pieces": v["pieces"], "max_err_mm": round(v["max_err_m"] * 1000, 2),
            "wall_pen": [(x["module"], x["label"], x["depth_cm"]) for x in v["wall_penetration"]][:8],
            "n_hosted_in_wall": len(v["hosted_in_wall"]),
            "door_hits": [(x["door"], x["module"], x["label"], x["area_cm2"]) for x in v["door_swing_hits"]][:8]}
        for k, v in out["rooms"].items()}
sys.stdout.buffer.write(json.dumps({"n_boxes": out["n_boxes"], "n_matched": out["n_matched"],
                                    "unmatched": unmatched[:10], "max_err_m": out["max_err_m"],
                                    "loose_root": out["loose_root"], "rooms": summ},
                                   ensure_ascii=False, indent=1).encode("utf-8"))
