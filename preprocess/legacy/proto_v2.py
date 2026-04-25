"""P2.1 e P4.1 - versoes melhoradas."""
import cv2, numpy as np, pypdfium2 as pdfium, json, sys
from PIL import Image
from pathlib import Path

OUT = Path("runs/proto"); OUT.mkdir(parents=True, exist_ok=True)
pdf = pdfium.PdfDocument("planta_74.pdf")
img = np.array(pdf[0].render(scale=3.0).to_pil())
gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
H, W = gray.shape

def save(name, mask):
    cv2.imwrite(str(OUT / f"{name}_mask.png"), mask)
    Image.fromarray(255 - mask).convert("RGB").save(OUT / f"{name}.pdf", "PDF", resolution=150.0)
    print(f"  {name}: {(mask>0).sum():,} px ({100*(mask>0).sum()/mask.size:.1f}%)")

# ---------- P2.1: distance transform em DOIS canais (preto + cinza medio) ----------
# preto solido = alvenaria estrutural
_, bw_dark = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
dist_dark = cv2.distanceTransform(bw_dark, cv2.DIST_L2, 5)
mask_dark = (dist_dark >= 3).astype(np.uint8) * 255
mask_dark = cv2.dilate(mask_dark, np.ones((5,5), np.uint8), iterations=2)
mask_dark = cv2.bitwise_and(mask_dark, bw_dark)

# cinza medio (RGB 100-180) = parede nao estrutural
mid = cv2.inRange(gray, 100, 180)
dist_mid = cv2.distanceTransform(mid, cv2.DIST_L2, 5)
mask_mid = (dist_mid >= 3).astype(np.uint8) * 255
mask_mid = cv2.dilate(mask_mid, np.ones((5,5), np.uint8), iterations=2)
mask_mid = cv2.bitwise_and(mask_mid, mid)

mask21 = cv2.bitwise_or(mask_dark, mask_mid)
# limpa minusculo
n, lbl, st, _ = cv2.connectedComponentsWithStats(mask21, 8)
clean = np.zeros_like(mask21)
for i in range(1, n):
    if st[i, cv2.CC_STAT_AREA] >= 400:
        clean[lbl == i] = 255
save("p2_1_thickness_dual", clean)

# ---------- P4.1: ROI + threshold + filtro de espessura combinado ----------
_, bw = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
roi_mask = np.zeros_like(gray)
roi_mask[:int(H*0.55), :] = 255
masked = cv2.bitwise_and(bw, roi_mask)

# distance transform pra eliminar linhas finas (cotas/texto)
dist = cv2.distanceTransform(masked, cv2.DIST_L2, 5)
thick = (dist >= 3).astype(np.uint8) * 255
thick = cv2.dilate(thick, np.ones((5,5), np.uint8), iterations=2)
thick = cv2.bitwise_and(thick, masked)

# tambem cinza-medio dentro do ROI
mid_roi = cv2.bitwise_and(cv2.inRange(gray, 100, 180), roi_mask)
dist_mid = cv2.distanceTransform(mid_roi, cv2.DIST_L2, 5)
mid_thick = (dist_mid >= 3).astype(np.uint8) * 255
mid_thick = cv2.dilate(mid_thick, np.ones((5,5), np.uint8), iterations=2)
mid_thick = cv2.bitwise_and(mid_thick, mid_roi)

mask41 = cv2.bitwise_or(thick, mid_thick)
# remove componentes pequenos
n, lbl, st, _ = cv2.connectedComponentsWithStats(mask41, 8)
clean41 = np.zeros_like(mask41)
for i in range(1, n):
    a = st[i, cv2.CC_STAT_AREA]
    if 600 <= a < 200000:
        clean41[lbl == i] = 255
save("p4_1_roi_thickness", clean41)
print("done")
