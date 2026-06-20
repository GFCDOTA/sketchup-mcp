"""gen_quartzo_fio.py — gera UMA textura de PEDRA CLARA tileable p/ cozinha planejada
(kc_tampo / kc_backsplash). Abordagem "A_quartzo_fio": quartzo branco quente com FIO de veio
cinza fino, esparso e de baixissimo contraste + micrograo; o mais discreto/premium.

GROUND: subtle_veined_stone.json (base [222,219,212], veio SUTIL, NUNCA marmore dramatico),
stone.md (anti-padroes: veio esticado/tileado obvio, contraste exagerado, branco-papel).

TILEABLE: ruido de valor periodico (np.roll wrap) + warp/ridge por funcoes seno de 2*pi*x/y
(periodicas) -> sem costura. NAO ha veio reto atravessando: o fio segue um campo deslocado
por noise periodico, esparso e de baixa amplitude.

Saida: assets/textures/procedural/candidates/A_quartzo_fio.png (1024x1024).
Uso: .venv/Scripts/python.exe tools/gen_quartzo_fio.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/textures/procedural/candidates"
SZ = 1024
BASE = np.array([222.0, 219.0, 212.0])   # off-white quente do golden sample


def _periodic_noise(sz: int, scale: int, rng: np.random.Generator) -> np.ndarray:
    """Ruido de valor TILEABLE: gera grade pequena, repete-a (tile) e da upsample bilinear,
    depois desloca por np.roll. Como a grade base e periodica e o resize cobre multiplos
    inteiros do tile, as bordas casam -> sem costura."""
    g = max(2, sz // scale)
    small = rng.random((g, g))
    # wrap: duplica 1 linha/coluna do inicio no fim p/ a interpolacao fechar o loop
    wrapped = np.zeros((g + 1, g + 1))
    wrapped[:g, :g] = small
    wrapped[g, :g] = small[0, :]
    wrapped[:g, g] = small[:, 0]
    wrapped[g, g] = small[0, 0]
    up = np.asarray(Image.fromarray((wrapped * 255).astype("uint8")).resize((sz, sz), Image.BILINEAR),
                    dtype=float) / 255.0
    return up


def quartzo_fio(seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    u = np.linspace(0.0, 1.0, SZ, endpoint=False)
    X = u[None, :].repeat(SZ, 0)
    Y = u[:, None].repeat(SZ, 1)

    # --- campo de FIO: coordenada diagonal suave deslocada por noise periodico ---
    # warp periodico (wrap garantido: noise periodico + senos de 2*pi*x) -> sem veio reto
    warp = (_periodic_noise(SZ, 6, rng) - 0.5) * 1.4 + (_periodic_noise(SZ, 14, rng) - 0.5) * 0.6
    phase = (X * 1.0 + Y * 0.6) * 2.0 * np.pi   # campo diagonal de baixa frequencia
    field = np.sin(phase + warp * 2.0 * np.pi)

    # ridge fino: |field| perto de 0 vira um FIO; expoente alto -> linha esparsa e estreita
    fio = (1.0 - np.abs(field)) ** 9.0           # esparso, fino
    # modula a presenca do fio p/ ele NAO atravessar inteiro (some em trechos)
    presence = _periodic_noise(SZ, 5, rng)
    fio = fio * np.clip((presence - 0.35) / 0.5, 0.0, 1.0)

    # --- micrograo sal-e-pimenta do quartzo (tileable via roll de ruido fino periodico) ---
    micro = _periodic_noise(SZ, 256, rng) - 0.5  # quase por-pixel mas periodico
    mottle = (_periodic_noise(SZ, 40, rng) - 0.5) # variacao tonal larga, muito suave

    # composicao em LUMINANCIA: tudo BAIXO contraste (premium economico, nao marmore)
    t = (-fio * 0.10        # fio cinza levemente mais escuro que a base
         + mottle * 0.045   # nuvem tonal larguissima
         + micro * 0.055)   # grao fino
    t = t[..., None]

    out = np.clip(BASE[None, None, :] + t * 255.0, 0, 255)
    img = Image.fromarray(out.astype("uint8"))
    # leve blur p/ tirar aspecto digital do grao (mantem tile: blur e local)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    return img


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    img = quartzo_fio(seed=617)
    dst = OUT / "A_quartzo_fio.png"
    img.save(dst)

    arr = np.asarray(img, dtype=float)
    mean_rgb = arr.reshape(-1, 3).mean(0)
    lum = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
    contrast = float(lum.std())
    print(f"path={dst}")
    print(f"mean_rgb=[{mean_rgb[0]:.1f}, {mean_rgb[1]:.1f}, {mean_rgb[2]:.1f}]")
    print(f"contrast(std lum)={contrast:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
