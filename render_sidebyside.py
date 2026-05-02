"""Side-by-side da regiao do apto (cropado)."""
import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

A_full = Image.open(r"C:/Users/felip_local/Documents/paredes.png").convert("RGB")
# crop manual na regiao do apto na imagem original (excluir legenda/rodape)
# paredes.png: ~1200x1690. Apto fica em y~120..900, x~80..1130
A = A_full.crop((80, 120, 1140, 900))
B = Image.open("runs/proto/p9_v3_run/overlay_semantic.png").convert("RGB")

# normaliza altura
H = 700
A2 = A.resize((int(A.width * H / A.height), H))
B2 = B.resize((int(B.width * H / B.height), H))

gap = 20
W = A2.width + B2.width + gap
canvas = Image.new("RGB", (W, H + 50), "white")
canvas.paste(A2, (0, 50))
canvas.paste(B2, (A2.width + gap, 50))

d = ImageDraw.Draw(canvas)
try: font = ImageFont.truetype("arial.ttf", 22)
except Exception: font = ImageFont.load_default()
d.text((10, 12), "VOCE PINTOU", fill="black", font=font)
d.text((A2.width + gap + 10, 12), "PIPELINE EXTRAIU (rosa/azul=rooms detectados)", fill="black", font=font)

out = Path("runs/proto/p9_v3_run/sidebyside.png")
canvas.save(out)
print(f"wrote {out}  {canvas.size}")

if not os.environ.get("PNG_HISTORY_DISABLE"):
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
        from png_history import register
        register(out, kind="sidebyside",
                 source={"consensus": Path("runs/proto/p9_v3_run/observed_model.json")},
                 generator="render_sidebyside.py",
                 params={"size": list(canvas.size)})
    except Exception as e:
        print(f"[png_history skipped] {e}")
