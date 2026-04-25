"""P5 = P2 esqueletizado. P6 = P4 + esqueleto. Espera-se que Hough finalmente pegue todas as paredes."""
import cv2, numpy as np, pypdfium2 as pdfium
from skimage.morphology import skeletonize
from PIL import Image
from pathlib import Path

OUT = Path("runs/proto"); OUT.mkdir(parents=True, exist_ok=True)
pdf = pdfium.PdfDocument("planta_74.pdf")
img = np.array(pdf[0].render(scale=3.0).to_pil())
gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
H, W = gray.shape

def to_pdf_via_skeleton(name, mask, dilate_after=2):
    """Esqueletiza a mask, depois dilata levemente pra Hough ter votes."""
    skel = skeletonize(mask > 0).astype(np.uint8) * 255
    if dilate_after > 0:
        skel = cv2.dilate(skel, np.ones((3,3), np.uint8), iterations=dilate_after)
    cv2.imwrite(str(OUT / f"{name}_mask.png"), skel)
    Image.fromarray(255 - skel).convert("RGB").save(OUT / f"{name}.pdf", "PDF", resolution=150.0)
    print(f"  {name}: skel {(skel>0).sum():,} px")

# P5 = base do P2 com esqueleto (1px centerline pra Hough adorar)
_, bw = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
dist = cv2.distanceTransform(bw, cv2.DIST_L2, 5)
core = (dist >= 3).astype(np.uint8) * 255
core = cv2.dilate(core, np.ones((5,5), np.uint8), iterations=2)
core = cv2.bitwise_and(core, bw)
to_pdf_via_skeleton("p5_skeleton", core, dilate_after=2)

# P6 = base do P4 (ROI top 55%) com esqueleto
roi = np.zeros_like(gray); roi[:int(H*0.55), :] = 255
masked = cv2.bitwise_and(bw, roi)
n,lbl,st,_ = cv2.connectedComponentsWithStats(masked, 8)
clean = np.zeros_like(masked)
for i in range(1, n):
    a = st[i, cv2.CC_STAT_AREA]
    if 500 <= a < 200000:
        clean[lbl == i] = 255
to_pdf_via_skeleton("p6_roi_skel", clean, dilate_after=2)

# P7 = combina P2-thickness + ROI + esqueleto (melhor de tudo)
roi_dist = cv2.bitwise_and(core, roi)
to_pdf_via_skeleton("p7_roi_thickness_skel", roi_dist, dilate_after=2)
print("done")
