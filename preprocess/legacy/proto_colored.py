"""P9 - dual filter: VERMELHO -> walls full-height, MARROM -> peitoril.
Salva 2 PDFs (um por tipo) e o pipeline roda em cima do vermelho.
Peitoril fica como artifact separado pra gerar Wall(kind=peitoril) depois."""
import cv2, numpy as np
from PIL import Image
from pathlib import Path
from skimage.morphology import skeletonize
import json
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else r"C:/Users/felip_local/Documents/paredes.png"
PREFIX = sys.argv[2] if len(sys.argv) > 2 else f"{PREFIX}"
OUT = Path("runs/proto"); OUT.mkdir(parents=True, exist_ok=True)

img = cv2.imread(SRC)
print(f"input: {img.shape}")
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# vermelho (2 faixas no HSV)
r1 = cv2.inRange(hsv, (0, 100, 80), (12, 255, 255))
r2 = cv2.inRange(hsv, (170, 100, 80), (180, 255, 255))
red = cv2.bitwise_or(r1, r2)
red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8), iterations=2)
print(f"red px: {(red>0).sum():,}")

# marrom (~hue 10-25, sat alta, value medio)
brown = cv2.inRange(hsv, (8, 80, 40), (25, 255, 180))
# remove sobreposicao com vermelho (vermelho intenso pode bater faixa baixa)
brown = cv2.bitwise_and(brown, cv2.bitwise_not(red))
brown = cv2.morphologyEx(brown, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8), iterations=2)
print(f"brown px: {(brown>0).sum():,}")

# salva masks pra debug
cv2.imwrite(str(OUT / f"{PREFIX}_red_mask.png"), red)
cv2.imwrite(str(OUT / f"{PREFIX}_brown_mask.png"), brown)

# walls em pdf (so vermelho)
Image.fromarray(255 - red).convert("RGB").save(OUT / f"{PREFIX}_red.pdf", "PDF", resolution=150.0)

# peitoris: salva como JSON com bounding boxes pra adicionar no observed_model
n, lbl, st, _ = cv2.connectedComponentsWithStats(brown, 8)
peitoris = []
for i in range(1, n):
    x, y, w, h, area = st[i]
    if area < 200:
        continue
    peitoris.append({
        "peitoril_id": f"peitoril-{i}",
        "bbox": [int(x), int(y), int(x+w), int(y+h)],
        "area_px": int(area),
        "kind": "peitoril",
        "height_m": 1.10,  # padrao da legenda do PDF
    })
(OUT / f"{PREFIX}_peitoris.json").write_text(json.dumps(peitoris, indent=2))
print(f"peitoris: {len(peitoris)}")
print("done")
