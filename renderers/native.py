"""Renderiza debug_walls.png e debug_junctions.png nativos (replicando o SVG do repo)."""
import json, os, sys
from pathlib import Path
from PIL import Image, ImageDraw

RUN_DIR = Path(sys.argv[1])
OBS_PATH = RUN_DIR / "observed_model.json"
model = json.loads(OBS_PATH.read_text(encoding="utf-8"))
walls, juncs = model["walls"], model["junctions"]

xs, ys = [], []
for w in walls:
    xs += [w["start"][0], w["end"][0]]
    ys += [w["start"][1], w["end"][1]]
for j in juncs:
    xs.append(j["point"][0]); ys.append(j["point"][1])
margin = 20
min_x, min_y = min(xs) - margin, min(ys) - margin
max_x, max_y = max(xs) + margin, max(ys) + margin
W, H = int(max_x - min_x), int(max_y - min_y)

# debug_walls.png
a = Image.new("RGB", (W, H), "white"); da = ImageDraw.Draw(a)
for w in walls:
    da.line([(w["start"][0]-min_x, w["start"][1]-min_y),
             (w["end"][0]-min_x, w["end"][1]-min_y)],
            fill=(15,23,42), width=max(1, int(w.get("thickness",4)/2)))
a.save(RUN_DIR / "debug_walls.png")

# debug_junctions.png
b = Image.new("RGB", (W, H), "white"); db = ImageDraw.Draw(b)
for w in walls:
    db.line([(w["start"][0]-min_x, w["start"][1]-min_y),
             (w["end"][0]-min_x, w["end"][1]-min_y)],
            fill=(203,213,225), width=2)
for j in juncs:
    cx, cy = j["point"][0]-min_x, j["point"][1]-min_y
    col = (239,68,68) if j.get("degree",0) >= 3 else (37,99,235)
    r = 4
    db.ellipse([cx-r, cy-r, cx+r, cy+r], fill=col)
b.save(RUN_DIR / "debug_junctions.png")
print(f"{W}x{H} -> debug_walls.png + debug_junctions.png")

if not os.environ.get("PNG_HISTORY_DISABLE"):
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
        from png_history import register
        for kind, png in (("debug_walls", RUN_DIR / "debug_walls.png"),
                          ("debug_junctions", RUN_DIR / "debug_junctions.png")):
            register(png, kind=kind, source={"consensus": OBS_PATH},
                     generator="render_native.py",
                     params={"run_dir": str(RUN_DIR)})
    except Exception as e:
        print(f"[png_history skipped] {e}")
