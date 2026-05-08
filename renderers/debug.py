"""Renderiza observed_model.json em PNG. Uso: python render_debug.py <run_dir>"""
import json
import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

RUN_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("runs/test_plan")
OBS_PATH = RUN_DIR / "observed_model.json"
model = json.loads(OBS_PATH.read_text(encoding="utf-8"))

walls = model["walls"]
juncs = model["junctions"]
rooms = model["rooms"]

xs, ys = [], []
for w in walls:
    xs += [w["start"][0], w["end"][0]]
    ys += [w["start"][1], w["end"][1]]
for j in juncs:
    xs.append(j["point"][0])
    ys.append(j["point"][1])

margin = 40
min_x, min_y = min(xs) - margin, min(ys) - margin
max_x, max_y = max(xs) + margin, max(ys) + margin
w_px = int(max_x - min_x)
h_px = int(max_y - min_y)

# paleta de cores pros rooms
palette = [
    (254, 226, 226), (254, 215, 170), (254, 240, 138), (187, 247, 208),
    (186, 230, 253), (216, 180, 254), (252, 165, 165), (253, 186, 116),
    (250, 204, 21), (134, 239, 172), (125, 211, 252), (196, 181, 253),
    (248, 113, 113), (249, 115, 22),
]

img = Image.new("RGB", (w_px, h_px), "white")
d = ImageDraw.Draw(img, "RGBA")
try:
    font = ImageFont.truetype("arial.ttf", 18)
    font_small = ImageFont.truetype("arial.ttf", 12)
except Exception:
    font = ImageFont.load_default()
    font_small = ImageFont.load_default()

# fill rooms
for i, room in enumerate(rooms):
    poly = room.get("polygon") or room.get("outline") or []
    if not poly or len(poly) < 3:
        continue
    color = palette[i % len(palette)] + (140,)
    pts = [(p[0] - min_x, p[1] - min_y) for p in poly]
    d.polygon(pts, fill=color, outline=(80, 80, 80))
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    d.text((cx - 10, cy - 8), room["room_id"].replace("room-", "R"), fill="black", font=font_small)

# walls
for wall in walls:
    x1 = wall["start"][0] - min_x
    y1 = wall["start"][1] - min_y
    x2 = wall["end"][0] - min_x
    y2 = wall["end"][1] - min_y
    stroke = max(2, int(wall.get("thickness", 4) / 2))
    d.line([(x1, y1), (x2, y2)], fill=(15, 23, 42), width=stroke)

# junctions
for j in juncs:
    cx = j["point"][0] - min_x
    cy = j["point"][1] - min_y
    kind = j.get("kind", "")
    if kind == "cross":
        color = (220, 38, 38)
    elif kind == "tee":
        color = (234, 88, 12)
    elif kind == "end":
        color = (37, 99, 235)
    else:  # pass_through
        color = (100, 116, 139)
    r = 4
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

d.rectangle([0, 0, w_px, 28], fill=(255, 255, 255, 230))
sc = model["scores"]
d.text((6, 4),
       f"walls={len(walls)}  juncs={len(juncs)}  rooms={len(rooms)}  "
       f"geom={sc['geometry']}  topo={sc['topology']}  rooms_score={sc['rooms']}",
       fill="black", font=font)

out = RUN_DIR / "debug_combined.png"
img.save(out)
print(f"wrote {out.resolve()}  ({w_px}x{h_px})")

if not os.environ.get("PNG_HISTORY_DISABLE"):
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
        from png_history import register
        register(out, kind="debug_combined", source={"consensus": OBS_PATH},
                 generator="render_debug.py",
                 params={"run_dir": str(RUN_DIR), "size": [w_px, h_px]})
    except Exception as e:
        print(f"[png_history skipped] {e}")
