"""Skeletoniza a mascara vermelha — cada wall vira 1px centerline.
Paralelas proximas fundem num skeleton so. Depois re-espessa pro Hough."""
import cv2, numpy as np
from PIL import Image
from pathlib import Path
from skimage.morphology import skeletonize
import json
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else r"C:/Users/felip_local/Documents/paredes.png"
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "p9"
OUT = Path("runs/proto"); OUT.mkdir(parents=True, exist_ok=True)

img = cv2.imread(SRC)
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
r1 = cv2.inRange(hsv, (0, 100, 80), (12, 255, 255))
r2 = cv2.inRange(hsv, (170, 100, 80), (180, 255, 255))
red = cv2.bitwise_or(r1, r2)
red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((5,5), np.uint8), iterations=3)

# Dilate pra fundir paralelas com gap pequeno, depois skeletonize pra reduzir
# tudo a linhas centrais de 1px.
red_fused = cv2.dilate(red, np.ones((5,5), np.uint8), iterations=2)
skel = skeletonize(red_fused > 0).astype(np.uint8) * 255
# Re-espessa um pouco pro Hough conseguir pegar (Hough gosta de 2-3px)
skel_thick = cv2.dilate(skel, np.ones((3,3), np.uint8), iterations=1)
print(f"red raw={int((red>0).sum()):,} fused={int((red_fused>0).sum()):,} skel={int((skel>0).sum()):,}")

brown = cv2.inRange(hsv, (8, 80, 40), (25, 255, 180))
brown = cv2.bitwise_and(brown, cv2.bitwise_not(cv2.dilate(skel_thick, np.ones((9,9), np.uint8))))
brown = cv2.morphologyEx(brown, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8), iterations=2)

cv2.imwrite(str(OUT / f"{PREFIX}_red_mask.png"), skel_thick)
cv2.imwrite(str(OUT / f"{PREFIX}_brown_mask.png"), brown)
Image.fromarray(255 - skel_thick).convert("RGB").save(OUT / f"{PREFIX}_red.pdf", "PDF", resolution=150.0)

n, lbl, st, _ = cv2.connectedComponentsWithStats(brown, 8)
peitoris = []
for i in range(1, n):
    x, y, w, h, area = st[i]
    if area < 200:
        continue
    peitoris.append({
        "peitoril_id": f"peitoril-{i}",
        "bbox": [int(x), int(y), int(x+w), int(y+h)],
        "area_px": int(area), "kind": "peitoril", "height_m": 1.10,
    })
(OUT / f"{PREFIX}_peitoris.json").write_text(json.dumps(peitoris, indent=2))
print(f"peitoris: {len(peitoris)} done")
