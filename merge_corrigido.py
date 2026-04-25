"""Alinha corrigido.png em cima de paredes.png via feature matching,
extrai os traços vermelho+marrom NOVOS do corrigido, e escreve paredes_v5.png
com o merge. Depois roda pipeline e compara.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

PAREDES = Path(r"C:/Users/felip_local/Documents/paredes.png")
CORRIGIDO = Path(r"C:/Users/felip_local/Documents/corrigido.png")
OUT = Path(r"C:/Users/felip_local/Documents/paredes_v5.png")


def filter_red_brown(img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Retorna (red_mask, brown_mask) onde 255 = pixel daquela cor."""
    if img.shape[2] == 4:
        # Usa alpha: se alpha == 0 (transparente), ignora
        alpha = img[:, :, 3]
        bgr = img[:, :, :3]
    else:
        alpha = np.full(img.shape[:2], 255, dtype=np.uint8)
        bgr = img
    b, g, r = cv2.split(bgr)
    # Vermelho puro: R alto, G e B baixos
    red = ((r > 180) & (g < 90) & (b < 90) & (alpha > 0)).astype(np.uint8) * 255
    # Marrom: R médio-alto, G médio, B baixo
    brown = ((r > 100) & (r < 200) & (g > 40) & (g < 120) & (b < 80) & (alpha > 0)).astype(np.uint8) * 255
    return red, brown


def bbox_of_mask(m: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(m > 0)
    if ys.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def align_corrigido_to_paredes(corrigido_bgr: np.ndarray, paredes_bgr: np.ndarray) -> np.ndarray:
    """Affine 4-param: mapeia bbox das walls vermelhas do corrigido no bbox das
    walls vermelhas do paredes. Ignora rotacao (input ja vem em mesma orientacao
    ortogonal)."""
    corr_red, _ = filter_red_brown(corrigido_bgr)
    par_red, _ = filter_red_brown(paredes_bgr)
    bb_c = bbox_of_mask(corr_red)
    bb_p = bbox_of_mask(par_red)
    print(f"bbox corrigido (red): {bb_c}")
    print(f"bbox paredes   (red): {bb_p}")
    if bb_c is None or bb_p is None:
        return None
    cx0, cy0, cx1, cy1 = bb_c
    px0, py0, px1, py1 = bb_p
    sx = (px1 - px0) / max(1, (cx1 - cx0))
    sy = (py1 - py0) / max(1, (cy1 - cy0))
    # Matriz 2x3 que: translada origem pra (cx0,cy0), escala, translada pra (px0,py0)
    M = np.array([
        [sx, 0.0, px0 - sx * cx0],
        [0.0, sy, py0 - sy * cy0],
    ], dtype=np.float32)
    print(f"scale sx={sx:.3f} sy={sy:.3f}")
    # Promove pra 3x3 pra usar warpPerspective homogeneo (ou usa warpAffine direto)
    return M


def main() -> int:
    paredes = cv2.imread(str(PAREDES), cv2.IMREAD_UNCHANGED)
    corrigido = cv2.imread(str(CORRIGIDO), cv2.IMREAD_UNCHANGED)
    assert paredes is not None, "paredes.png nao carregou"
    assert corrigido is not None, "corrigido.png nao carregou"
    print(f"paredes: {paredes.shape} | corrigido: {corrigido.shape}")

    par_bgr = paredes[:, :, :3] if paredes.shape[2] == 4 else paredes
    cor_bgr = corrigido[:, :, :3] if corrigido.shape[2] == 4 else corrigido

    M = align_corrigido_to_paredes(cor_bgr, par_bgr)
    if M is None:
        print("[x] Alinhamento falhou. Saindo.")
        return 1

    h_par, w_par = par_bgr.shape[:2]
    corr_warped = cv2.warpAffine(cor_bgr, M, (w_par, h_par), flags=cv2.INTER_NEAREST, borderValue=(255, 255, 255))

    # Extrai vermelho+marrom do corrigido warped
    corr_red, corr_brown = filter_red_brown(corr_warped)
    par_red, par_brown = filter_red_brown(par_bgr)

    red_new = cv2.bitwise_and(corr_red, cv2.bitwise_not(par_red))
    brown_new = cv2.bitwise_and(corr_brown, cv2.bitwise_not(par_brown))
    print(f"red_new px: {int(red_new.sum()/255)} | brown_new px: {int(brown_new.sum()/255)}")

    # Desenha em cima de paredes: vermelho puro onde tem novo vermelho, marrom onde tem novo marrom
    out = paredes.copy()
    if out.shape[2] == 4:
        out[red_new > 0] = [0, 0, 255, 255]       # BGRA vermelho puro opaco
        out[brown_new > 0] = [19, 69, 139, 255]   # BGRA marrom saddle
    else:
        out[red_new > 0] = [0, 0, 255]
        out[brown_new > 0] = [19, 69, 139]

    cv2.imwrite(str(OUT), out)
    print(f"[ok] salvou {OUT}")
    # salva tambem o warp de debug
    dbg = Path(r"E:/Claude/sketchup-mcp/runs/proto/corrigido_warped.png")
    cv2.imwrite(str(dbg), corr_warped)
    print(f"[dbg] {dbg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
