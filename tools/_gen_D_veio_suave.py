"""_gen_D_veio_suave.py — gera UMA textura de PEDRA CLARA tileable (quartzo de veio suave,
marble-lite) p/ tampo+backsplash da cozinha (kinds kc_tampo/kc_backsplash).

GROUND: subtle_veined_stone.json (base [222,219,212], veio SUTIL, nunca marmore dramatico),
stone.md (anti-padroes: veio esticado/tileado obvio, contraste exagerado, branco-papel).

ABORDAGEM "D_veio_suave": quartzo de veio suave. Veios largos e MUITO leves fluindo
organicamente (marble-lite), baixo contraste, TILEABLE sem emenda.

Tileability: TODO ruido vem de somas de senos com FREQUENCIAS INTEIRAS sobre o dominio
[0,2pi) -> periodico exato em ambos os eixos (sem _value_noise/random-upsample, que costura).
Veios = domain-warp de um campo de fase periodico; sem veio reto atravessando.

Saida: assets/textures/procedural/candidates/D_veio_suave.png (1024x1024).
Roda: .venv/Scripts/python.exe tools/_gen_D_veio_suave.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/textures/procedural/candidates"
SZ = 1024
BASE = np.array([222.0, 219.0, 212.0])  # off-white quente do golden sample


def _periodic_noise(u, v, freqs, rng, decay=1.0):
    """Soma de senos com frequencias INTEIRAS -> perfeitamente tileable (periodo 2pi).
    u,v em [0,2pi). Cada banda: fase + orientacao aleatorias, amplitude ~ 1/f^decay.
    Retorna campo ~[-1,1] normalizado."""
    acc = np.zeros_like(u)
    for f in freqs:
        amp = 1.0 / (f ** decay)
        # 2 ondas por banda em direcoes aleatorias (dx,dy inteiros => tileable)
        for _ in range(2):
            ang = rng.uniform(0, 2 * np.pi)
            fx = int(round(f * np.cos(ang)))
            fy = int(round(f * np.sin(ang)))
            ph = rng.uniform(0, 2 * np.pi)
            acc += amp * np.sin(fx * u + fy * v + ph)
    return acc / (np.max(np.abs(acc)) + 1e-9)


def veined_stone(seed):
    rng = np.random.default_rng(seed)
    lin = np.linspace(0, 2 * np.pi, SZ, endpoint=False)
    u, v = np.meshgrid(lin, lin)

    # 1) domain warp suave (deforma o espaco -> veio organico, nao reto)
    warp_x = _periodic_noise(u, v, [2, 3, 5], rng, decay=1.1) * 0.9
    warp_y = _periodic_noise(u, v, [2, 3, 5], rng, decay=1.1) * 0.9

    # 2) campo de FASE de baixa freq (veios LARGOS) deformado pelo warp
    phase = (1.0 * u + 0.7 * v) + 2.2 * _periodic_noise(u + warp_x, v + warp_y, [1, 2, 3], rng, decay=1.2)
    # ridges finas e LEVES: |sin| elevado -> linhas estreitas de veio, baixo "fill"
    veins = np.abs(np.sin(phase)) ** 6.0          # 0..1, predominantemente ~0 (pedra limpa)

    # 3) mottle de fundo MUITO leve (variacao de tom da chapa, sem grao direcional)
    mottle = _periodic_noise(u, v, [3, 6, 11], rng, decay=1.0)

    # 4) micro-grao fino e periodico (quebra o "chapado", baixissima amplitude)
    grain = _periodic_noise(u, v, [37, 53, 71], rng, decay=0.6)

    # composicao em LUMINANCIA: veio levemente mais escuro; mottle/grao quase imperceptiveis.
    # amplitudes baixas = premium economico, NAO marmore dramatico.
    t = -veins * 9.0 + mottle * 2.6 + grain * 1.4   # em unidades de RGB (delta sobre BASE)
    out = BASE[None, None, :] + t[..., None]
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    img = veined_stone(2026_0619)
    path = OUT / "D_veio_suave.png"
    img.save(path)

    arr = np.asarray(img, dtype=float)
    mean_rgb = arr.reshape(-1, 3).mean(0)
    lum = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
    contrast = float(lum.std())

    # cheque rapido de tileabilidade: diff borda esq/dir e topo/base (deve ser ~0)
    seam_x = float(np.abs(arr[:, 0, :] - arr[:, -1, :]).mean())
    seam_y = float(np.abs(arr[0, :, :] - arr[-1, :, :]).mean())

    print(f"path={path}")
    print(f"size={img.size}")
    print(f"mean_rgb=[{mean_rgb[0]:.2f}, {mean_rgb[1]:.2f}, {mean_rgb[2]:.2f}]")
    print(f"contrast(std_lum)={contrast:.3f}")
    print(f"seam_x_meandiff={seam_x:.4f}  seam_y_meandiff={seam_y:.4f}  (>0 esperado mas pequeno)")


if __name__ == "__main__":
    main()
    sys.exit(0)
