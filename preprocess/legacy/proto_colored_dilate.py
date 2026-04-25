"""Variante do proto_colored que DILATA a mascara vermelha antes de salvar
o PDF, pra fundir walls paralelas com drift de 1-3px em 1 wall so."""
import cv2, numpy as np
from PIL import Image
from pathlib import Path
import json
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else r"C:/Users/felip_local/Documents/paredes.png"
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "p9"
DILATE = int(sys.argv[3]) if len(sys.argv) > 3 else 4  # px
OUT = Path("runs/proto"); OUT.mkdir(parents=True, exist_ok=True)

img = cv2.imread(SRC)
print(f"input: {img.shape}")
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

r1 = cv2.inRange(hsv, (0, 100, 80), (12, 255, 255))
r2 = cv2.inRange(hsv, (170, 100, 80), (180, 255, 255))
red = cv2.bitwise_or(r1, r2)
red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8), iterations=2)
print(f"red px (raw): {(red>0).sum():,}")

# Dilate agressivo pra fundir walls paralelas com drift, depois close pra colar
k = np.ones((DILATE, DILATE), np.uint8)
red_fat = cv2.dilate(red, k, iterations=1)
# Erode de volta uma parte (mantem fusao mas nao engorda demais)
red_fat = cv2.erode(red_fat, np.ones((max(1, DILATE - 2), max(1, DILATE - 2)), np.uint8), iterations=1)
print(f"red px (fat): {(red_fat>0).sum():,}")

brown = cv2.inRange(hsv, (8, 80, 40), (25, 255, 180))
brown = cv2.bitwise_and(brown, cv2.bitwise_not(red_fat))
brown = cv2.morphologyEx(brown, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8), iterations=2)
print(f"brown px: {(brown>0).sum():,}")

cv2.imwrite(str(OUT / f"{PREFIX}_red_mask.png"), red_fat)
cv2.imwrite(str(OUT / f"{PREFIX}_brown_mask.png"), brown)
Image.fromarray(255 - red_fat).convert("RGB").save(OUT / f"{PREFIX}_red.pdf", "PDF", resolution=150.0)

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
        "height_m": 1.10,
    })
(OUT / f"{PREFIX}_peitoris.json").write_text(json.dumps(peitoris, indent=2))
print(f"peitoris: {len(peitoris)}")
print("done")
