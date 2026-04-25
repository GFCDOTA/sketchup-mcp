"""Roda os 4 prototipos sobre planta_74.pdf, exporta mask + PDF limpo de cada."""
import cv2
import numpy as np
import pypdfium2 as pdfium
from PIL import Image
from pathlib import Path

SRC = "planta_74.pdf"
OUT = Path("runs/proto"); OUT.mkdir(parents=True, exist_ok=True)

pdf = pdfium.PdfDocument(SRC)
img = np.array(pdf[0].render(scale=3.0).to_pil())
gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
H, W = gray.shape
print(f"input {W}x{H}")

def save_mask_and_pdf(name, mask):
    cv2.imwrite(str(OUT / f"{name}_mask.png"), mask)
    inv = 255 - mask
    Image.fromarray(inv).convert("RGB").save(OUT / f"{name}.pdf", "PDF", resolution=150.0)
    n_on = int((mask > 0).sum())
    pct = 100 * n_on / mask.size
    print(f"  {name}: {n_on:,} px on ({pct:.1f}%)")

# ---------- P1: Connected Components por area/solidez ----------
# Mantem so blobs grandes e densos (paredes), descarta pequeno (texto/cota)
_, bw = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
n, labels, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
mask = np.zeros_like(bw)
for i in range(1, n):
    x, y, w, h, area = stats[i]
    if area < 800:           # cota/texto/pontos pequenos
        continue
    if max(w, h) > W * 0.6:  # bordas da pagina
        continue
    aspect = max(w, h) / max(1, min(w, h))
    if aspect > 25:          # linha super fina (cota longa)
        continue
    mask[labels == i] = 255
save_mask_and_pdf("p1_components", mask)

# ---------- P2: Distance Transform (so pixels com espessura local >= N) ----------
# Paredes tem espessura ~8-15px; cotas tem 1-2px
_, bw2 = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
dist = cv2.distanceTransform(bw2, cv2.DIST_L2, 5)
mask2 = (dist >= 3).astype(np.uint8) * 255  # raio >= 3 => espessura >= 6
mask2 = cv2.dilate(mask2, np.ones((5, 5), np.uint8), iterations=2)  # reexpande
mask2 = cv2.bitwise_and(mask2, bw2)  # so onde havia tinta original
save_mask_and_pdf("p2_thickness", mask2)

# ---------- P3: Color Quantization k-means ----------
# Reduz a 5 cores; pega so o cluster mais escuro com massa significativa
small = cv2.resize(img, (W // 4, H // 4))
data = small.reshape(-1, 3).astype(np.float32)
K = 5
criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
_, lbls, centers = cv2.kmeans(data, K, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
centers = centers.astype(np.uint8)
brightness = centers.mean(axis=1)
darkest_idx = int(np.argmin(brightness))
print(f"  P3 cluster centers (RGB): {centers.tolist()}; darkest={centers[darkest_idx].tolist()}")
target = centers[darkest_idx]
diff = np.linalg.norm(img.astype(int) - target.astype(int), axis=2)
mask3 = (diff < 30).astype(np.uint8) * 255
# limpa pequenos
mask3 = cv2.morphologyEx(mask3, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
n3, lbl3, st3, _ = cv2.connectedComponentsWithStats(mask3, 8)
clean3 = np.zeros_like(mask3)
for i in range(1, n3):
    if st3[i, cv2.CC_STAT_AREA] >= 500:
        clean3[lbl3 == i] = 255
save_mask_and_pdf("p3_kmeans", clean3)

# ---------- P4: ROI (corta legenda/notas) + threshold ----------
# Heuristica simples: pega so a parte de cima da pagina (planta), descarta tercio inferior
roi_mask = np.zeros_like(gray)
roi_h = int(H * 0.55)  # planta ocupa top ~55% nessa pagina
roi_mask[:roi_h, :] = 255
_, bw4 = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
mask4 = cv2.bitwise_and(bw4, roi_mask)
# remove componentes pequenos
n4, lbl4, st4, _ = cv2.connectedComponentsWithStats(mask4, 8)
clean4 = np.zeros_like(mask4)
for i in range(1, n4):
    a = st4[i, cv2.CC_STAT_AREA]
    if 500 <= a < 200000:
        clean4[lbl4 == i] = 255
save_mask_and_pdf("p4_roi", clean4)

print("done")
