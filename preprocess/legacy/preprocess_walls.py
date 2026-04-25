"""Aplica threshold + morfologia no PDF ORIGINAL pra isolar so paredes pretas. Salva como PDF limpo."""
import cv2
import numpy as np
import pypdfium2 as pdfium
from PIL import Image
from pathlib import Path

src_pdf = Path("planta_74.pdf")
out_pdf = Path("planta_74_clean.pdf")
out_dbg = Path("planta_74_mask.png")

pdf = pdfium.PdfDocument(str(src_pdf))
img_pil = pdf[0].render(scale=3.0).to_pil()
img = np.array(img_pil)
print(f"input: {img.shape}")

gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

# 1) so pixels muito escuros (paredes pretas solidas)
_, mask = cv2.threshold(gray, 60, 255, cv2.THRESH_BINARY_INV)

# 2) opening agressivo pra apagar cota/texto/legenda fina
# kernel 7x7 = qualquer linha < 3px desaparece. Cota tipica: 1-2px. Parede: 8-12px.
kernel = np.ones((7, 7), np.uint8)
mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

# 3) close pra reconectar paredes que o opening eventualmente quebrou
kernel_close = np.ones((3, 3), np.uint8)
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close, iterations=2)

# debug: salva mask
cv2.imwrite(str(out_dbg), mask)
print(f"mask saved: {out_dbg}  ({mask.shape})")

# 4) inverte (paredes pretas em fundo branco) e salva PDF
final = 255 - mask
Image.fromarray(final).convert("RGB").save(out_pdf, "PDF", resolution=150.0)
print(f"pdf saved: {out_pdf}")
