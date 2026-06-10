#!/usr/bin/env python
"""SofaFabricMaterialSpec — gerador PROCEDURAL de textura de tecido (de CLASSE,
parametrico por material_style). Track de material (GPT, geometria fechada/PASS):
nao copiar imagem de tecido; GERAR mapas tileaveis (albedo + bump/weave) que matam
o "RGB chapado" sem virar ruido, e preparam o caminho do V-Ray.

Saida: textures/fabric_<style>_albedo.png  +  fabric_<style>_bump.png  (1024, tileavel).
Aplicado no SketchUp com UV em escala real (tile_m, default 0.30 m) em build_materials.

Parametros (idioma do GPT): base_rgb, tile_m, value_variation, weave_contrast,
large_noise, bump_strength. CLASSE: mesma estrutura p/ os 3 estilos, sem exemplar.

Rodar:  <venv>/python scripts/sofa_fabric_material.py [--size 1024] [--out textures]
"""
import argparse
import os
import numpy as np
from PIL import Image

# ---- SPECS por material_style (CLASSE; valores de partida do GPT) ------------
# dark_charcoal: params exatos do GPT (tile 0.30, value_var 0.06, weave 0.08,
#   large_noise 0.025, bump 0.045). base_rgb levemente acima do #222526 do GPT
#   (40,43,45) p/ o weave continuar LEGIVEL na preview flat do SketchUp (sem
#   sheen p/ levantar) — no V-Ray pode escurecer ao 32-38 do GPT.
FABRIC_SPECS = {
    'dark_charcoal': dict(base_rgb=(40, 43, 45),  tile_m=0.30, value_variation=0.06,
                          weave_contrast=0.085, large_noise=0.025, bump_strength=0.045),
    'mid_gray':      dict(base_rgb=(118, 120, 124), tile_m=0.30, value_variation=0.05,
                          weave_contrast=0.075, large_noise=0.022, bump_strength=0.040),
    'light_linen':   dict(base_rgb=(206, 197, 182), tile_m=0.30, value_variation=0.045,
                          weave_contrast=0.10,  large_noise=0.020, bump_strength=0.050),
}

THREADS_PER_TILE = 128  # 1024/128 = 8 px/fio (~2.3mm no tile 0.30m) -> divide 1024 (tileavel)


def _organic_tileable(size, blobs, seed):
    """Ruido ORGANICO e tileavel: white noise -> low-pass gaussiano via FFT.
    A FFT de um campo de tamanho `size` e periodica por construcao -> wrap
    perfeito (tileavel), e o low-pass da manchas SUAVES (sem grid/plaid dos
    senos separaveis). `blobs` ~ numero de manchas atravessando o tile."""
    rng = np.random.default_rng(seed)
    white = rng.standard_normal((size, size))
    f = np.fft.fft2(white)
    fr = np.fft.fftfreq(size)
    r = np.sqrt(fr[None, :] ** 2 + fr[:, None] ** 2)
    cutoff = max(blobs, 1) / size                    # cycles/pixel
    f *= np.exp(-(r / cutoff) ** 2)                   # passa-baixa gaussiano
    out = np.real(np.fft.ifft2(f))
    out -= out.mean()
    m = np.max(np.abs(out))
    return out / m if m > 1e-9 else out


def _weave_height(size, threads):
    """Plain weave tileavel em [0,1]: fios verticais (warp) e horizontais (weft)
    alternando over/under em xadrez. Cristas dos fios = realce -> vira bump/relevo."""
    xs = np.arange(size) / size
    warp = np.abs(np.cos(np.pi * threads * xs))[None, :]   # ridges verticais
    weft = np.abs(np.cos(np.pi * threads * xs))[:, None]   # ridges horizontais
    ix = np.floor(threads * xs).astype(int)
    over = (ix[None, :] + ix[:, None]) % 2                 # xadrez over/under
    h = np.where(over == 0, warp, weft)                    # fio "por cima" mostra a crista
    return h  # 0..1


def generate(style, out_dir, size=1024):
    spec = FABRIC_SPECS[style]
    base = np.array(spec['base_rgb'], dtype=np.float64)
    seed = abs(hash(style)) % (2**32)

    weave = _weave_height(size, THREADS_PER_TILE)          # 0..1
    large = _organic_tileable(size, blobs=2.5, seed=seed)  # mancha grande organica BEM fraca
    fine = _organic_tileable(size, blobs=40, seed=seed + 7)  # variacao de valor fina (sub-fio)

    # brilho multiplicativo: weave (media ~0) + large_noise + value_variation.
    # Tudo de baixa amplitude -> mata chapado SEM virar ruido (regra do GPT).
    bright = (1.0
              + spec['weave_contrast'] * (weave - weave.mean())
              + spec['large_noise'] * large
              + spec['value_variation'] * fine)
    bright = np.clip(bright, 0.80, 1.20)

    albedo = np.clip(base[None, None, :] * bright[:, :, None], 0, 255).astype(np.uint8)

    # bump/weave: relevo do trancado, contraste = bump_strength em torno de 0.5.
    b = 0.5 + (weave - 0.5) * (spec['bump_strength'] / 0.045)  # normaliza p/ ~0.045 ref
    bump = np.clip(b, 0, 1)
    bump_img = np.clip(bump * 255, 0, 255).astype(np.uint8)

    os.makedirs(out_dir, exist_ok=True)
    alb_p = os.path.join(out_dir, f'fabric_{style}_albedo.png')
    bmp_p = os.path.join(out_dir, f'fabric_{style}_bump.png')
    Image.fromarray(albedo, 'RGB').save(alb_p)
    Image.fromarray(bump_img, 'L').save(bmp_p)
    return alb_p, bmp_p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--size', type=int, default=1024)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument('--out', default=os.path.join(here, 'textures'))
    ap.add_argument('--style', default=None, help='um estilo so (default: todos)')
    a = ap.parse_args()
    styles = [a.style] if a.style else list(FABRIC_SPECS)
    for s in styles:
        alb, bmp = generate(s, a.out, a.size)
        print(f'{s}: {os.path.basename(alb)} + {os.path.basename(bmp)} ({a.size}px, tile {FABRIC_SPECS[s]["tile_m"]}m)')


if __name__ == '__main__':
    main()
