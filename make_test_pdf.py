"""Gera um PDF sintetico simples: 2 quartos com parede compartilhada."""
from PIL import Image, ImageDraw
from pathlib import Path

W, H = 800, 800
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)
# Retangulo externo 100..700 x 100..700
d.rectangle([100, 100, 700, 700], outline="black", width=6)
# Parede divisoria vertical no meio
d.line([(400, 100), (400, 700)], fill="black", width=6)
# Parede horizontal dividindo quarto esquerdo
d.line([(100, 400), (400, 400)], fill="black", width=6)

out = Path("test_plan.pdf")
img.save(out, "PDF", resolution=100.0)
print(f"wrote {out.resolve()}")
