"""v2: Alinhamento EXPLICITO via conhecimento da transformacao do pipeline.

O corrigido.png foi o overlay_semantic.png do pipeline aberto no Photoshop
com zoom e pintado por cima. Logo:
  corrigido -> overlay: scale down (2x aprox), subtrai 40px de header
  overlay   -> paredes: + (min_x, min_y) do bbox das walls + margin

Extrai os traços VERMELHO + MARROM que o usuario desenhou no corrigido
e desenha nas coords corretas do paredes.png.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

PAREDES = Path(r"C:/Users/felip_local/Documents/paredes.png")
CORRIGIDO = Path(r"C:/Users/felip_local/Documents/corrigido.png")
OUT = Path(r"C:/Users/felip_local/Documents/paredes_v5.png")
OBS = Path(r"E:/Claude/sketchup-mcp/runs/proto/p9_v4_run/observed_model.json")
# dimensoes conhecidas do overlay_semantic.png v4
OV_W, OV_H = 1076, 707
HEADER_Y = 40  # header com stats no topo
MARGIN = 40    # margin do render em volta do bbox das walls


def filter_red_brown(img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if img.shape[2] == 4:
        alpha = img[:, :, 3]
        bgr = img[:, :, :3]
    else:
        alpha = np.full(img.shape[:2], 255, dtype=np.uint8)
        bgr = img
    b, g, r = cv2.split(bgr)
    red = ((r > 180) & (g < 90) & (b < 90) & (alpha > 0)).astype(np.uint8) * 255
    brown = ((r > 100) & (r < 200) & (g > 40) & (g < 120) & (b < 80) & (alpha > 0)).astype(np.uint8) * 255
    return red, brown


def main() -> int:
    paredes = cv2.imread(str(PAREDES), cv2.IMREAD_UNCHANGED)
    corrigido = cv2.imread(str(CORRIGIDO), cv2.IMREAD_UNCHANGED)
    obs = json.loads(OBS.read_text())
    walls = obs["walls"]
    xs = [c for w in walls for c in (w["start"][0], w["end"][0])]
    ys = [c for w in walls for c in (w["start"][1], w["end"][1])]
    min_x = min(xs) - MARGIN  # 68.25
    min_y = min(ys) - MARGIN  # 186.375
    print(f"min_x={min_x} min_y={min_y}")

    ch, cw = corrigido.shape[:2]  # 1446, 2218
    # scale corrigido -> overlay
    sx = OV_W / cw  # 1076/2218
    sy = OV_H / ch  # 707/1446
    print(f"scale corrigido->overlay: sx={sx:.4f} sy={sy:.4f}")

    # Filtra vermelho e marrom NO CORRIGIDO
    cor_bgr = corrigido if corrigido.shape[2] < 4 else corrigido  # keep alpha for filter
    corr_red, corr_brown = filter_red_brown(corrigido)
    print(f"corrigido px: red={int(corr_red.sum()/255)} brown={int(corr_brown.sum()/255)}")

    # Resize corrigido masks para tamanho do overlay
    ov_red = cv2.resize(corr_red, (OV_W, OV_H), interpolation=cv2.INTER_NEAREST)
    ov_brown = cv2.resize(corr_brown, (OV_W, OV_H), interpolation=cv2.INTER_NEAREST)

    # Remove header (top 40px) - nao e conteudo semantico
    ov_red[:HEADER_Y, :] = 0
    ov_brown[:HEADER_Y, :] = 0

    # Embute em canvas do tamanho de paredes.png com offset (min_x, min_y)
    ph, pw = paredes.shape[:2]
    red_in_par = np.zeros((ph, pw), dtype=np.uint8)
    brown_in_par = np.zeros((ph, pw), dtype=np.uint8)
    ox, oy = int(round(min_x)), int(round(min_y - HEADER_Y))
    # y-offset compensa o header: y_paredes = (y_overlay - 40) + min_y = y_overlay + (min_y - 40)
    print(f"offset in paredes: ox={ox} oy={oy}")

    # slice safe
    y0, y1 = max(0, oy), min(ph, oy + OV_H)
    x0, x1 = max(0, ox), min(pw, ox + OV_W)
    sy0, sy1 = y0 - oy, y1 - oy
    sx0, sx1 = x0 - ox, x1 - ox
    red_in_par[y0:y1, x0:x1] = ov_red[sy0:sy1, sx0:sx1]
    brown_in_par[y0:y1, x0:x1] = ov_brown[sy0:sy1, sx0:sx1]

    # Filtra o que paredes JA tem (pra isolar SO os traços novos)
    par_bgr = paredes[:, :, :3] if paredes.shape[2] == 4 else paredes
    par_red, par_brown = filter_red_brown(par_bgr)

    # Dilata paredes existentes um pouco pra nao contar offset de 1-2px como "novo"
    kernel = np.ones((5, 5), np.uint8)
    par_red_dil = cv2.dilate(par_red, kernel)
    par_brown_dil = cv2.dilate(par_brown, kernel)

    red_new = cv2.bitwise_and(red_in_par, cv2.bitwise_not(par_red_dil))
    brown_new = cv2.bitwise_and(brown_in_par, cv2.bitwise_not(par_brown_dil))
    print(f"red_new px: {int(red_new.sum()/255)} | brown_new px: {int(brown_new.sum()/255)}")

    # Gera paredes_v5.png: paredes original + traços novos
    out = paredes.copy()
    if out.shape[2] == 4:
        out[red_new > 0] = [0, 0, 255, 255]
        out[brown_new > 0] = [19, 69, 139, 255]
    else:
        out[red_new > 0] = [0, 0, 255]
        out[brown_new > 0] = [19, 69, 139]
    cv2.imwrite(str(OUT), out)
    print(f"[ok] {OUT}")

    # Debug: mostra a mascara red+brown que foi adicionada, no espaco de paredes
    dbg = np.zeros_like(paredes)
    if dbg.shape[2] == 4:
        dbg[red_new > 0] = [0, 0, 255, 255]
        dbg[brown_new > 0] = [19, 69, 139, 255]
        dbg[par_red > 0] = [80, 80, 255, 255]   # rosa claro pra existente
        dbg[par_brown > 0] = [100, 150, 200, 255]
    dbg_out = Path(r"E:/Claude/sketchup-mcp/runs/proto/new_vs_existing.png")
    cv2.imwrite(str(dbg_out), dbg)
    print(f"[dbg] {dbg_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
