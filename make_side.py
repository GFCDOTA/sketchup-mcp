"""Side-by-side: corrigido (seu) vs p10 (pipeline)."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

A = Path(r"C:/Users/felip_local/Documents/corrigido.png")
B = Path(r"E:/Claude/sketchup-mcp/runs/proto/p10_v1_run/overlay_semantic.png")
OUT = Path(r"E:/Claude/sketchup-mcp/runs/proto/p10_vs_corrigido.png")

a = Image.open(A).convert("RGB")
b = Image.open(B).convert("RGB")
# Normaliza altura em 700
H = 700
wa = int(a.width * H / a.height)
wb = int(b.width * H / b.height)
a = a.resize((wa, H))
b = b.resize((wb, H))
LABEL_H = 32
canvas = Image.new("RGB", (wa + wb + 20, H + LABEL_H), "white")
canvas.paste(a, (0, LABEL_H))
canvas.paste(b, (wa + 20, LABEL_H))
d = ImageDraw.Draw(canvas)
try: font = ImageFont.truetype("arial.ttf", 18)
except Exception: font = ImageFont.load_default()
d.text((6, 6), "VOCE CORRIGIU (expectativa)", fill="black", font=font)
d.text((wa + 26, 6), "PIPELINE em paredes_v5 (resultado)", fill="black", font=font)
canvas.save(OUT)
print(f"[ok] {OUT}")
