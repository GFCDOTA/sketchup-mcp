"""gen_stone_candidate_B.py — UMA textura de PEDRA CLARA tileable p/ cozinha planejada
(tampo + backsplash; kinds kc_tampo / kc_backsplash).

ABORDAGEM "B_granito_claro": granito claro pontilhado — micrograo multi-tom fino
(sal-e-pimenta SUAVE) + 1-2 veios FANTASMA. TEXTURA, nao desenho. Base quente clara
[222,219,212] (golden sample). Veio sutil, baixo contraste — premium economico, NUNCA
marmore dramatico/escuro.

TILEABLE de verdade: todo ruido usa SOMA DE SENOIDES com frequencias INTEIRAS sobre
[0,1) -> casa perfeitamente nas bordas (wrap), sem costura nem veio reto atravessando.

Saida: assets/textures/procedural/candidates/B_granito_claro.png
Uso: .venv/Scripts/python.exe tools/gen_stone_candidate_B.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/textures/procedural/candidates"
SZ = 1024
BASE = np.array([222.0, 219.0, 212.0])  # off-white quente (golden sample)


def _periodic_noise(sz: int, n_freq: int, max_k: int, rng) -> np.ndarray:
    """Ruido TILEABLE: soma de senoides 2D com frequencias INTEIRAS (periodicas
    sobre [0,1)) -> wrap perfeito nas 4 bordas. Normalizado p/ media 0, ptp 1."""
    u = (np.arange(sz) / sz)[None, :].repeat(sz, 0)  # x em [0,1)
    v = (np.arange(sz) / sz)[:, None].repeat(sz, 1)  # y em [0,1)
    acc = np.zeros((sz, sz), dtype=float)
    for _ in range(n_freq):
        kx = int(rng.integers(1, max_k + 1))
        ky = int(rng.integers(1, max_k + 1))
        phase = rng.random() * 2 * np.pi
        amp = 1.0 / np.hypot(kx, ky)  # 1/f -> espectro natural (escalas grandes dominam)
        acc += amp * np.sin(2 * np.pi * (kx * u + ky * v) + phase)
    acc -= acc.mean()
    p = np.ptp(acc)
    return acc / p if p else acc


def granito_claro(seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)

    # --- 1) sal-e-pimenta: micrograo multi-tom fino, isotropico e tileable ---
    # ruido branco wrap-by-construction (tile cheio) + leve borrao por blend de
    # vizinhos com roll (periodico) p/ "amaciar" o pixel duro sem perder o grao.
    speck = rng.normal(0.0, 1.0, (SZ, SZ))
    # suavizacao 3x3 via np.roll (wrap) -> mantem tileability, tira aliasing duro
    speck = (speck
             + np.roll(speck, 1, 0) + np.roll(speck, -1, 0)
             + np.roll(speck, 1, 1) + np.roll(speck, -1, 1)) / 5.0
    speck = (speck - speck.mean()) / (speck.std() or 1.0)

    # --- 2) mottle de fundo (variacao de tom MUITO suave, escala media) ---
    mottle = _periodic_noise(SZ, n_freq=18, max_k=6, rng=rng)

    # --- 3) 1-2 veios FANTASMA: cristas finas e fracas, onduladas (warp periodico) ---
    u = (np.arange(SZ) / SZ)[None, :].repeat(SZ, 0)
    v = (np.arange(SZ) / SZ)[:, None].repeat(SZ, 1)
    warp = _periodic_noise(SZ, n_freq=10, max_k=4, rng=rng) * 0.18
    veins = np.zeros((SZ, SZ), dtype=float)
    n_vein = int(rng.integers(1, 3))  # 1 ou 2
    for _ in range(n_vein):
        kx = int(rng.integers(2, 5))
        ky = int(rng.integers(2, 5))
        phase = rng.random() * 2 * np.pi
        field = np.sin(2 * np.pi * (kx * u + ky * v) + phase + warp * 6.0)
        ridge = np.abs(field) ** 6.0  # cresta FINA (so onde |sin|~1)
        veins += ridge
    veins = veins / max(1, n_vein)
    veins -= veins.mean()

    # --- combinar: micrograo domina (textura), mottle e veio entram FRACOS ---
    # amplitudes em niveis de cinza (sobre 255) -> baixo contraste de proposito
    t = (speck * 3.2          # sal-e-pimenta sutil (premium economico)
         + mottle * 4.0       # tom de fundo suave
         + veins * 5.0)       # veios fantasma fracos

    # leve tinte por canal no micrograo (mineral multi-tom: graos quentes/frios)
    tint = np.stack([speck * 0.6, np.zeros_like(speck), -speck * 0.7], -1)
    out = BASE[None, None, :] + t[..., None] + tint
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    img = granito_claro(seed=2106)
    path = OUT / "B_granito_claro.png"
    img.save(path)

    arr = np.asarray(img, dtype=float)
    mean_rgb = arr.reshape(-1, 3).mean(0)
    lum = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
    print(f"saved: {path}")
    print(f"size: {img.size}")
    print(f"mean_rgb: [{mean_rgb[0]:.2f}, {mean_rgb[1]:.2f}, {mean_rgb[2]:.2f}]")
    print(f"contrast (std luminance): {lum.std():.4f}")
    # checagem de costura: borda esq vs dir e topo vs base (tileability)
    seam_lr = float(np.abs(arr[:, 0, :] - arr[:, -1, :]).mean())
    seam_tb = float(np.abs(arr[0, :, :] - arr[-1, :, :]).mean())
    print(f"seam_LR_meandiff: {seam_lr:.4f}  seam_TB_meandiff: {seam_tb:.4f}")


if __name__ == "__main__":
    main()
    sys.exit(0)
