"""P8 - extrai apenas pixels VERMELHOS da PNG anotada pelo usuario, gera mask + PDF."""
import cv2, numpy as np
from PIL import Image
from pathlib import Path
from skimage.morphology import skeletonize

SRC = r"C:/Users/felip_local/Documents/paredes.png"
OUT = Path("runs/proto"); OUT.mkdir(parents=True, exist_ok=True)

img = cv2.imread(SRC)  # BGR
print(f"input: {img.shape}")

# 1) filtro vermelho: R alto, G/B baixos. Usar HSV pra robusto
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
# vermelho ocupa duas faixas em HSV (wrap-around no 0/180)
m1 = cv2.inRange(hsv, (0, 100, 80), (12, 255, 255))
m2 = cv2.inRange(hsv, (170, 100, 80), (180, 255, 255))
red = cv2.bitwise_or(m1, m2)

# 2) close pra reconectar fragmentos pequenos
red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8), iterations=2)
print(f"red px: {(red>0).sum():,}")

# 3) variante crua (linhas grossas) -> PDF
cv2.imwrite(str(OUT / "p8_red_mask.png"), red)
Image.fromarray(255 - red).convert("RGB").save(OUT / "p8_red.pdf", "PDF", resolution=150.0)

# 4) variante esqueletizada (1px centerline) -> PDF
skel = skeletonize(red > 0).astype(np.uint8) * 255
skel = cv2.dilate(skel, np.ones((3,3), np.uint8), iterations=2)
cv2.imwrite(str(OUT / "p8_red_skel_mask.png"), skel)
Image.fromarray(255 - skel).convert("RGB").save(OUT / "p8_red_skel.pdf", "PDF", resolution=150.0)
print("done")
