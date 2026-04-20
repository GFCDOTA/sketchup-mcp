"""Renderiza o PDF inteiro em PNG pra ver a legenda."""
import pypdfium2 as pdfium
from pathlib import Path

pdf = pdfium.PdfDocument("planta_74.pdf")
page = pdf[0]
img = page.render(scale=3.0).to_pil()
out = Path("runs/planta_74/raw_page.png")
out.parent.mkdir(parents=True, exist_ok=True)
img.save(out)
print(f"{img.width}x{img.height} -> {out}")
