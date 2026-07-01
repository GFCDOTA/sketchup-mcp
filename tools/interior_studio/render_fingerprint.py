"""render_fingerprint.py — TRADUÇÃO determinística de um render (PNG) p/ números que um
LLM de TEXTO consegue checar. A metade objetiva da ponte "agente local não vê imagem".

Não usa LLM nem rede: só PIL+numpy. Extrai exposição (cave/estouro), paleta dominante,
calor (color temperature proxy), contraste e cor por ZONA (grade 3x3 = noção espacial grosseira).
Determinístico e idempotente (mesmo PNG -> mesmo fingerprint). O `theme_intern` interpreta
estes números contra os thresholds do TEMA; a `vision_describe` cobre o que é semântico.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

# luminância perceptual (Rec.709)
_W = np.array([0.2126, 0.7152, 0.0722])


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % (int(rgb[0]), int(rgb[1]), int(rgb[2]))


def _warmth(rgb) -> float:
    """(R-B)/255 ∈ [-1,1]: >0 quente (âmbar/2700K), <0 frio (azulado)."""
    return round((float(rgb[0]) - float(rgb[2])) / 255.0, 3)


def dominant_palette(img: Image.Image, k: int = 8) -> list[dict]:
    """Top-k cores (quantização adaptativa) com %, hex, luminância e calor. Ordenado por %."""
    small = img.convert("RGB").resize((200, 200))
    q = small.quantize(colors=k, method=Image.Quantize.FASTOCTREE)
    pal = q.getpalette()
    counts = q.getcolors() or []           # [(count, palette_index), ...]
    total = sum(c for c, _ in counts) or 1
    out = []
    for count, idx in sorted(counts, reverse=True):
        rgb = pal[idx * 3: idx * 3 + 3]
        if len(rgb) < 3:
            continue
        lum = float(np.dot(rgb, _W))
        out.append({"hex": _hex(rgb), "rgb": [int(c) for c in rgb],
                    "pct": round(100 * count / total, 1),
                    "lum": round(lum, 1), "warmth": _warmth(rgb)})
    return out


def zone_colors(arr: np.ndarray) -> dict:
    """Cor média por célula de uma grade 3x3 (top-left ... bottom-right) — noção espacial
    grosseira: 'parede' tende ao topo, 'piso' embaixo, 'janela' num lado."""
    h, w, _ = arr.shape
    names = ["top_left", "top_mid", "top_right", "mid_left", "center", "mid_right",
             "bot_left", "bot_mid", "bot_right"]
    out = {}
    for i in range(3):
        for j in range(3):
            cell = arr[i * h // 3:(i + 1) * h // 3, j * w // 3:(j + 1) * w // 3]
            mean = cell.reshape(-1, 3).mean(0)
            out[names[i * 3 + j]] = {"hex": _hex(mean), "rgb": [int(c) for c in mean],
                                     "lum": round(float(np.dot(mean, _W)), 1),
                                     "warmth": _warmth(mean)}
    return out


def near_white_frac(arr: np.ndarray, thr: int = 235) -> float:
    """Fração de pixels quase-brancos (menor canal >= thr): o proxy de 'chapado de BRANCO /
    lavado'. Mais amplo que clipped_white (>=250) — pega o off-white sem cor, não só o estouro."""
    return round(float((arr.min(2) >= thr).mean()), 4)


def texture_frac(arr: np.ndarray, win: int = 8, lo: float = 1.0, hi: float = 20.0) -> float:
    """ADVISORY (não-veredito) de 'quanta variação de textura há?': fração de tiles win×win cujo
    desvio-padrão local cai na banda [lo,hi]. Textura de veio/concreto/pedra (amplitude média) cai
    na banda; a cor chapada fica abaixo. CAVEAT (revisão adversarial): NÃO é um veredito confiável de
    'tem textura?' num render de LINHA do SketchUp — (a) as texturas de TECIDO do pipeline são
    sutis (std de tile ~0.7-1.3, quase no piso de ruído) e podem ler como chapadas; (b) as arestas
    ANTIALIASED do SU caem na banda média (~5-11) e inflam o número sem material. Por isso o
    flat_white_gate reporta este número mas NÃO decide veredito com ele; a prova de textura aplicada
    é o log per-kind do place_layout_skp.rb + o olho do Felipe. Determinístico/idempotente."""
    lum = arr @ _W
    h, w = lum.shape
    hh, ww = h - h % win, w - w % win
    if hh < win or ww < win:
        return 0.0
    tstd = lum[:hh, :ww].reshape(hh // win, win, ww // win, win).std(axis=(1, 3))
    return round(float(((tstd >= lo) & (tstd <= hi)).mean()), 4)


def fingerprint(png_path: str | Path, k: int = 8) -> dict:
    """Fingerprint determinístico de um render. Devolve dict serializável."""
    p = Path(png_path)
    img = Image.open(p).convert("RGB")
    arr = np.asarray(img).astype(float)            # H,W,3
    lum = arr @ _W
    npix = lum.size
    clipped = int((arr.min(2) >= 250).sum())       # branco estourado (todos canais altos)
    dark = int((lum <= 12).sum())                   # quase-preto (perda de detalhe na sombra)
    return {
        "image": p.name,
        "size": list(img.size),
        "exposure": {
            "mean_lum": round(float(lum.mean()), 1),
            "p5": round(float(np.percentile(lum, 5)), 1),
            "p50": round(float(np.percentile(lum, 50)), 1),
            "p95": round(float(np.percentile(lum, 95)), 1),
            "contrast_std": round(float(lum.std()), 1),
        },
        "clipped_white_px": clipped,
        "clipped_pct": round(100 * clipped / npix, 3),
        "near_black_pct": round(100 * dark / npix, 1),
        "warmth": _warmth(arr.reshape(-1, 3).mean(0)),   # calor global médio
        "near_white_pct": round(100 * near_white_frac(arr), 2),   # 'chapado de branco' (flat_white_gate)
        "texture_frac": texture_frac(arr),                        # 'tem textura?' (flat_white_gate)
        "palette": dominant_palette(img, k),
        "zones": zone_colors(arr),
    }


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(fingerprint(sys.argv[1]), ensure_ascii=False, indent=2))
