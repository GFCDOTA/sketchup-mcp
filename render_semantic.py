"""Renderiza overlay com cores semanticas: walls vermelho, bridges verde,
portas laranja, janelas ciano, passagens roxo, peitoris marrom."""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

RUN = Path(sys.argv[1])
obs = json.loads((RUN / "observed_model.json").read_text())
walls = obs["walls"]; juncs = obs["junctions"]
openings = obs.get("openings", []); peitoris = obs.get("peitoris", [])
sc = obs["scores"]

xs = [c for w in walls for c in (w["start"][0], w["end"][0])] + \
     [b for p in peitoris for b in (p["bbox"][0], p["bbox"][2])]
ys = [c for w in walls for c in (w["start"][1], w["end"][1])] + \
     [b for p in peitoris for b in (p["bbox"][1], p["bbox"][3])]
margin = 40
min_x, min_y = min(xs)-margin, min(ys)-margin
max_x, max_y = max(xs)+margin, max(ys)+margin
W, H = int(max_x-min_x), int(max_y-min_y)

base = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(base, "RGBA")
try: font = ImageFont.truetype("arial.ttf", 18)
except Exception: font = ImageFont.load_default()

# rooms shaded primeiro (atrás)
palette = [(254,226,226,120),(186,230,253,120),(187,247,208,120),(254,240,138,120),
           (216,180,254,120),(252,165,165,120),(125,211,252,120)]
for i, r in enumerate(obs["rooms"]):
    poly = r.get("polygon") or []
    if len(poly) < 3: continue
    pts = [(p[0]-min_x, p[1]-min_y) for p in poly]
    d.polygon(pts, fill=palette[i % len(palette)])

# peitoris (marrom translúcido)
for p in peitoris:
    x1,y1,x2,y2 = p["bbox"]
    d.rectangle([x1-min_x, y1-min_y, x2-min_x, y2-min_y],
                fill=(139,69,19,180), outline=(101,52,15), width=2)

# walls
for w in walls:
    x1,y1 = w["start"][0]-min_x, w["start"][1]-min_y
    x2,y2 = w["end"][0]-min_x, w["end"][1]-min_y
    if w.get("source") == "opening_bridge":
        d.line([(x1,y1),(x2,y2)], fill=(34,197,94), width=4)
    else:
        d.line([(x1,y1),(x2,y2)], fill=(220,38,38), width=4)

# junctions
for j in juncs:
    cx,cy = j["point"][0]-min_x, j["point"][1]-min_y
    col = (220,38,38) if j.get("degree",0)>=3 else (37,99,235)
    d.ellipse([cx-4,cy-4,cx+4,cy+4], fill=col)

# openings classificados
KIND_COLORS = {
    "door":    (249,115,22),   # laranja
    "window":  (6,182,212),    # ciano
    "passage": (168,85,247),   # roxo
}
for o in openings:
    cx,cy = o["center"][0]-min_x, o["center"][1]-min_y
    col = KIND_COLORS.get(o.get("kind","door"), (128,128,128))
    r = 9
    d.polygon([(cx,cy-r),(cx+r,cy),(cx,cy+r),(cx-r,cy)], fill=col, outline="black")

d.rectangle([0,0,W,32], fill=(255,255,255,230))
from collections import Counter
kinds = Counter(o.get("kind","door") for o in openings)
d.text((6,4),
       f"walls={len(walls)} juncs={len(juncs)} rooms={len(obs['rooms'])} "
       f"openings={len(openings)} ({dict(kinds)}) peitoris={len(peitoris)}  "
       f"geom={sc['geometry']} topo={sc['topology']} rooms={sc['rooms']}",
       fill="black", font=font)

out = RUN / "overlay_semantic.png"
base.save(out)
print(f"wrote {out}")
