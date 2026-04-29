"""Renderiza overlay (mask em preto + walls extraidas em vermelho + junctions em azul) pra cada prototipo."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PROTOS = ["p1_components", "p2_thickness", "p3_kmeans", "p4_roi"]
RUN_DIR = Path("runs/proto")

try:
    font = ImageFont.truetype("arial.ttf", 28)
except Exception:
    font = ImageFont.load_default()

for name in PROTOS:
    mask_png = RUN_DIR / f"{name}_mask.png"
    run_dir = RUN_DIR / f"{name}_run"
    obs = json.loads((run_dir / "observed_model.json").read_text(encoding="utf-8"))
    walls = obs["walls"]
    juncs = obs["junctions"]
    sc = obs["scores"]

    # mask como base, branca ao fundo
    mask = Image.open(mask_png).convert("L")
    base = Image.new("RGB", mask.size, "white")
    # mask preta (paredes) sobre branco
    base.paste((0, 0, 0), mask=Image.eval(mask, lambda v: 80 if v > 0 else 0))
    d = ImageDraw.Draw(base)

    # walls em vermelho
    for w in walls:
        d.line([tuple(w["start"]), tuple(w["end"])], fill=(220, 38, 38),
               width=max(2, int(w.get("thickness", 4) / 2)))
    # junctions em azul
    for j in juncs:
        cx, cy = j["point"]
        col = (220, 38, 38) if j.get("degree", 0) >= 3 else (37, 99, 235)
        r = 5
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    # legenda topo
    d.rectangle([0, 0, base.width, 50], fill=(255, 255, 255, 230))
    d.text((10, 10),
           f"{name}  walls={len(walls)} juncs={len(juncs)} rooms={len(obs['rooms'])} "
           f"geom={sc['geometry']} topo={sc['topology']}",
           fill="black", font=font)

    base.thumbnail((1200, 1200))
    out = RUN_DIR / f"{name}_overlay.png"
    base.save(out)
    print(f"wrote {out}")
